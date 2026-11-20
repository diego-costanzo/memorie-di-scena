# -*- coding: utf-8 -*-
"""
Motore OCR "ingegnerizzato" per le fotografie di copertine e frontespizi.

Perché non basta una sola chiamata a Tesseract
----------------------------------------------
Una fotografia fatta col telefono ha quasi sempre tre difetti: è inclinata,
ha luce irregolare (un lato chiaro e uno in ombra) e il contrasto è basso.
Un unico passaggio di OCR su un'immagine così produce errori e righe di rumore.

Questa pipeline affronta i tre problemi in ordine, con scelte misurabili:

1.  Raddrizzamento (deskew) tramite il rilevatore di orientamento di Tesseract
    (OSD), applicato solo quando serve.
2.  Ingrandimento delle foto piccole, perché Tesseract legge bene solo se i
    caratteri sono alti almeno 30-40 pixel.
3.  Binarizzazione adattiva: la soglia non è unica per tutta l'immagine (che
    soffre la luce irregolare) ma locale, calcolata con una media mobile.
    È l'idea dell'algoritmo di Bradley, realizzata solo con filtri Pillow in C:
    nessuna dipendenza aggiuntiva, nessun ciclo Python sui pixel.
4.  Più varianti di lettura (nitida, morbida, invertita) con **misura della
    confidenza** parola per parola. Non si uniscono più i testi alla cieca:
    vince la variante con il punteggio migliore e le righe vengono accettate
    solo sopra una soglia di confidenza.
5.  Arresto anticipato: se la prima variante è già ottima, le altre non vengono
    eseguite. Sui computer lenti l'attesa resta breve.

Il modulo resta a caricamento pigro: Pillow e pytesseract vengono importati solo
quando l'utente usa davvero l'acquisizione da foto.

MAPPATURA DELLE FUNZIONI (dall'alto verso il basso)
---------------------------------------------------
    estrai_testo_da_immagine   punto di ingresso pubblico (usato dalla rotta)
    ├── _raddrizza             OSD: corregge rotazioni di 90/180/270 gradi
    ├── _ingrandisci           porta il lato minimo a OCR_UPSCALE_MIN
    ├── _combo_lingue          italiano da solo, poi tutte le lingue installate
    ├── _varianti_lettura      genera (nome, immagine, PSM) in ordine di costo
    │   ├── distesa            equalizzazione: caso normale, il più veloce
    │   ├── adattiva           binarizzazione Bradley (ombre e luci irregolari)
    │   ├── invertita          testo chiaro su fondo scuro
    │   └── nitida             autocontrast: rete di sicurezza
    ├── _leggi_righe           image_to_data → righe con confidenza pesata
    ├── _pulisci_riga          normalizza spazi e simboli di bordo
    ├── _riga_utile            filtro: scarta rumore e righe poco credibili
    ├── _punteggio             confronto oggettivo tra varianti
    └── _simili                deduplica righe lette in modo diverso

COME AGGIUNGERE UNA LINGUA
--------------------------
Aggiungere il codice (es. "por") a `OCR_LINGUE_PREFERITE` in config.py e il
pacchetto `tesseract-ocr-por` in `installa.sh`; il nome leggibile va aggiunto
in `lingue_disponibili()`. Non serve altro: la pipeline usa solo ciò che
Tesseract dichiara installato.

COME AGGIUNGERE UNA VARIANTE DI LETTURA
---------------------------------------
Aggiungere un `yield` in `_varianti_lettura` (nome, immagine, psm). Tenere le
varianti costose in fondo: l'arresto anticipato evita di eseguirle quando la
prima lettura è già buona. Ogni variante deve restare in scala di grigi.

COME CAMBIARE LA SOGLIA DI QUALITÀ
----------------------------------
Le soglie sono in `config.py` (OCR_MIN_LINE_CONF, OCR_GOOD_CONF, OCR_RETRY_CONF).
Alzarle riduce il rumore ma può scartare righe corrette: vanno provate su
fotografie reali, non solo su immagini di test.
"""
import difflib
import re

from . import config

# Cache dei nomi lingua disponibili: Tesseract viene interrogato una sola volta.
_LINGUE_INSTALLATE = None


def get_ocr_tools():
    """Carica Pillow (pigramente) e restituisce gli strumenti di base."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 50_000_000 if config.IS_32_BIT else 150_000_000
    resample = getattr(Image, "Resampling", None)
    filter_lanczos = resample.LANCZOS if resample else getattr(Image, "LANCZOS", 1)
    return Image, ImageOps, filter_lanczos


def _lingue_installate(pytesseract):
    """
    Elenca i dizionari effettivamente presenti, in ordine di preferenza.

    Tesseract non sbaglia se una lingua manca: semplicemente non esiste. Qui
    però lo verifichiamo, così l'interfaccia può dire la verità all'utente e
    la lettura non prova lingue che non ci sono.
    """
    global _LINGUE_INSTALLATE
    if _LINGUE_INSTALLATE is None:
        try:
            presenti = set(pytesseract.get_languages(config=""))
        except Exception:
            presenti = set()
        _LINGUE_INSTALLATE = tuple(
            lingua for lingua in config.OCR_LINGUE_PREFERITE if lingua in presenti
        )
    return _LINGUE_INSTALLATE


def _combo_lingue(pytesseract):
    """
    Restituisce (lingue_principali, lingue_estese).

    - Principali: italiano se c'è, altrimenti la prima disponibile.
    - Estese: tutte le lingue installate, unite con '+' (es. «ita+eng+fra»).
      Servono solo come seconda possibilità quando la prima delude.
    """
    installate = _lingue_installate(pytesseract)
    if not installate:
        return "", ""
    principale = "ita" if "ita" in installate else installate[0]
    estesa = "+".join(installate)
    return principale, estesa


def lingue_disponibili():
    """Nomi leggibili delle lingue di lettura disponibili, per l'interfaccia."""
    nomi = {
        "ita": "italiano",
        "eng": "inglese",
        "fra": "francese",
        "lat": "latino",
        "deu": "tedesco",
        "spa": "spagnolo",
    }
    try:
        import pytesseract

        return [nomi.get(l, l) for l in _lingue_installate(pytesseract)]
    except Exception:
        return []


def stato_lingua_ocr():
    """
    Autodiagnostica dei dizionari di lettura.

    Serve a evitare una degradazione silenziosa: se «tesseract-ocr-ita» non è
    installato, Tesseract leggerebbe l'italiano con un altro motore, con
    risultati peggiori e senza dirlo all'utente.

    Restituisce:
        {"italiano": bool, "lingue": [...], "messaggio": "..."}
    """
    try:
        import pytesseract

        installate = _lingue_installate(pytesseract)
        if "ita" in installate:
            return {"italiano": True, "lingue": lingue_disponibili(), "messaggio": ""}

        if installate:
            messaggio = (
                "Su questo computer manca il dizionario italiano per la lettura delle foto: "
                "il testo italiano può risultare meno preciso. Puoi sempre correggerlo a mano. "
                "Per installarlo, chiedi a chi ha preparato il programma di eseguire «installa.sh»."
            )
        else:
            messaggio = (
                "Il lettore di foto non è disponibile su questo computer. "
                "Puoi inserire i dati a mano."
            )
        return {"italiano": False, "lingue": lingue_disponibili(), "messaggio": messaggio}
    except Exception:
        return {
            "italiano": False,
            "lingue": [],
            "messaggio": "Il lettore di foto non è disponibile su questo computer. Puoi inserire i dati a mano.",
        }


# ------------------------------------------------------------------------------
# PREPARAZIONE DELL'IMMAGINE
# ------------------------------------------------------------------------------
def _raddrizza(img, pytesseract):
    """
    Corregge rotazioni di 90/180/270 gradi usando il rilevatore di orientamento
    di Tesseract. Se il rilevamento non è affidabile, l'immagine resta com'è.
    """
    try:
        # OSD lavora su un'immagine ridotta: è molto più veloce e altrettanto affidabile.
        piccola = img.copy()
        piccola.thumbnail((800, 800))
        osd = pytesseract.image_to_osd(piccola)
        rotazione = 0
        confidenza = 0.0
        for riga in osd.splitlines():
            if riga.startswith("Rotate:"):
                rotazione = int(riga.split(":")[1].strip())
            elif riga.startswith("Orientation confidence:"):
                confidenza = float(riga.split(":")[1].strip())

        if rotazione in (90, 180, 270) and confidenza >= 2.0:
            # Pillow ruota in senso antiorario: Tesseract indica di quanto ruotare
            # l'immagine per raddrizzarla, quindi si ruota in senso inverso.
            return img.rotate(-rotazione, expand=True, fillcolor="white"), rotazione
    except Exception:
        pass
    return img, 0


def _ingrandisci(img, resample):
    """Ingrandisce le foto troppo piccole: i caratteri devono essere leggibili."""
    lato_max = max(img.size)
    if lato_max and lato_max < config.OCR_UPSCALE_MIN:
        fattore = config.OCR_UPSCALE_MIN / lato_max
        nuova = (max(1, int(img.width * fattore)), max(1, int(img.height * fattore)))
        return img.resize(nuova, resample)
    return img


def _binarizza_adattiva(grigio, ImageFilter, ImageChops, ImageOps):
    """
    Soglia locale secondo l'algoritmo di Bradley, realizzata senza numpy.

    Per ogni pixel si confronta la luminosità con la media del suo vicinato:
    se è sensibilmente più scura (oltre una percentuale della media) è testo.
    Un unico punto di soglia non funzionerebbe con una foto che ha un lato in
    ombra e uno in piena luce; questo sì.

    Tutti i passaggi usano filtri Pillow scritti in C: nessun ciclo sui pixel.
    """
    raggio = max(8, min(25, max(grigio.size) // 120))
    media_locale = grigio.filter(ImageFilter.BoxBlur(raggio))

    # Quanto ogni pixel è più scuro della media del vicinato (0 dove è più chiaro).
    scarto = ImageChops.subtract(media_locale, grigio)

    # Soglia proporzionale alla luminosità locale: il 12% della media.
    # Funziona sia su fondo chiaro (soglia alta) sia su fondo scuro (soglia bassa).
    soglia = media_locale.point(lambda p: int(p * 0.12))
    testo = ImageChops.subtract(scarto, soglia).point(lambda p: 255 if p > 0 else 0)

    # Testo nero su fondo bianco (ciò che Tesseract legge meglio).
    return ImageOps.invert(testo).convert("L")


def _varianti_lettura(grigio, ImageFilter, ImageChops, ImageOps):
    """
    Genera le varianti da provare, in ordine di probabilità di riuscita.
    Ogni elemento è (nome, immagine, modalità di segmentazione PSM).

    Nota ingegneristica: il motore LSTM di Tesseract 5 è addestrato su immagini
    in scala di grigi con contrasto disteso, non su immagini binarizzate. Per
    questo la prima variante è la versione "distesa" (equalizzazione
    dell'istogramma): nelle prove pratiche è quella che legge più caratteri
    corretti, e la più veloce. La binarizzazione adattiva interviene solo se la
    confidenza misurata resta bassa (foto con ombre o sfondi colorati), mentre
    l'inversione serve per le scritte chiare su fondo scuro.
    """
    disteso = ImageOps.equalize(grigio)

    # 1. Contrasto disteso: il caso più frequente e il più veloce.
    yield "distesa", disteso, 3

    # 2. Binaria adattiva: regge luci irregolari, ombre laterali e sfondi colorati.
    yield "adattiva", _binarizza_adattiva(disteso, ImageFilter, ImageChops, ImageOps), 3

    # 3. Invertita: testo chiaro su fondo scuro (locandine, dorso di vinili).
    yield "invertita", ImageOps.invert(disteso), 11

    # 4. Autocontrast: rete di sicurezza per immagini già molto contrastate,
    #    dove l'equalizzazione può esaltare il rumore di fondo.
    yield "nitida", ImageOps.autocontrast(grigio, cutoff=1), 3


# ------------------------------------------------------------------------------
# LETTURA E MISURA DELLA QUALITÀ
# ------------------------------------------------------------------------------
def _leggi_righe(immagine, psm, pytesseract, lingua=""):
    """
    Legge l'immagine e restituisce le righe in ordine di lettura, con la
    confidenza media di ciascuna (0-100). Le parole a bassa confidenza non
    entrano nel conteggio: la qualità è misurata solo su ciò che è leggibile.
    """
    opzioni = f"--oem 1 --psm {psm} --dpi {config.OCR_DPI} -c preserve_interword_spaces=1"

    dati = pytesseract.image_to_data(
        immagine,
        lang=lingua or None,
        config=opzioni,
        output_type=pytesseract.Output.DICT,
        timeout=config.OCR_TIMEOUT,
    )

    righe = {}
    ordine = []
    for i, parola in enumerate(dati.get("text", [])):
        parola = (parola or "").strip()
        if not parola:
            continue
        try:
            conf = float(dati["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < 0:
            continue

        chiave = (dati["block_num"][i], dati["par_num"][i], dati["line_num"][i])
        if chiave not in righe:
            righe[chiave] = {"parole": [], "conf": [], "pesi": []}
            ordine.append(chiave)
        righe[chiave]["parole"].append(parola)
        righe[chiave]["conf"].append(conf)
        righe[chiave]["pesi"].append(max(1, len(parola)))

    risultato = []
    for chiave in ordine:
        gruppo = righe[chiave]
        testo = " ".join(gruppo["parole"])
        peso_totale = sum(gruppo["pesi"]) or 1
        conf_media = sum(c * p for c, p in zip(gruppo["conf"], gruppo["pesi"])) / peso_totale
        risultato.append({"testo": testo, "conf": conf_media})
    return risultato


def _pulisci_riga(testo):
    """Ripulisce una riga: spazi doppi, caratteri decorativi ai bordi, punteggiatura ripetuta."""
    testo = " ".join(testo.split())
    testo = testo.strip(" \t|~_#*=\\\"'`^;:—–-•·")
    testo = re.sub(r"([.,;:!?])\1{2,}", r"\1", testo)
    return testo.strip()


def _riga_utile(testo, conf):
    """Filtro conservativo: scarta righe troppo corte, rumore o poco credibili."""
    if conf < config.OCR_MIN_LINE_CONF:
        return False
    if len(testo) < 2:
        return False
    alfanumerici = re.findall(r"[a-zA-Z0-9àèéìòùÀÈÉÌÒÙ]", testo)
    if len(alfanumerici) < 2:
        return False
    # Una riga in cui oltre metà dei caratteri sono simboli è quasi sempre rumore.
    if len(alfanumerici) / len(testo) < 0.5:
        return False
    return True


def _simili(a, b):
    """
    Riconosce la stessa riga letta da varianti diverse, anche quando una
    variante ne ha colto solo una parte (es. «Giuseppe Tomasi» contro
    «Giuseppe Tomasi di Lampedusa»).
    """
    a_norm = " ".join(re.findall(r"[a-z0-9àèéìòù]+", a.lower()))
    b_norm = " ".join(re.findall(r"[a-z0-9àèéìòù]+", b.lower()))
    if not a_norm or not b_norm:
        return False
    if a_norm in b_norm or b_norm in a_norm:
        return True
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio() >= 0.90


def _punteggio(righe):
    """
    Punteggio di una variante: confidenza media delle righe accettate, con un
    piccolo premio (fino a +10) per chi legge più testo. Così una pagina con
    poche righe ma lette bene non viene penalizzata ingiustamente.
    """
    if not righe:
        return 0.0
    conf_media = sum(r["conf"] for r in righe) / len(righe)
    caratteri = sum(len(r["testo"]) for r in righe)
    premio = min(caratteri, 150) / 150.0 * 10
    return conf_media + premio


def _conf_media(righe):
    """Confidenza media delle righe accettate (0 se non ce ne sono)."""
    if not righe:
        return 0.0
    return sum(r["conf"] for r in righe) / len(righe)


# ------------------------------------------------------------------------------
# API PRINCIPALE
# ------------------------------------------------------------------------------
def estrai_testo_da_immagine(img, max_lato=None):
    """
    Esegue la pipeline completa su un'immagine Pillow e restituisce:

        {
          "linee": ["...", "..."],       righe utili in ordine di lettura
          "confidenza": 87,              media 0-100 sulle righe mostrate
          "qualita": "alta|media|bassa", indicazione per l'interfaccia
          "rotazione": 90,               gradi corretti (0 se non serviva)
          "passate": ["distesa"],        varianti effettivamente eseguite
          "lingue": "ita",               lingue usate per la lettura
        }

    Multilingue: si parte dall'italiano (il caso normale, il più veloce e il
    più preciso per i testi di casa). Se la confidenza resta bassa, si fa una
    sola seconda passata con tutte le lingue installate, così un titolo
    straniero o una citazione in latino vengono comunque letti.
    """
    import pytesseract
    from PIL import ImageFilter, ImageChops

    _, ImageOps, resample = get_ocr_tools()

    if max_lato:
        lato = max(img.size)
        if lato > max_lato:
            img = img.copy()
            img.thumbnail((max_lato, max_lato), resample)

    img, rotazione = _raddrizza(img, pytesseract)
    grigio = _ingrandisci(img.convert("L"), resample)

    lingua_principale, lingua_estesa = _combo_lingue(pytesseract)
    migliore = {"righe": [], "punteggio": 0.0, "nome": ""}
    passate = []
    accumulo = []

    for nome, variante, psm in _varianti_lettura(grigio, ImageFilter, ImageChops, ImageOps):
        passate.append(nome)
        try:
            lette = _leggi_righe(variante, psm, pytesseract, lingua_principale)
        except Exception:
            continue

        righe_ok = []
        for riga in lette:
            testo = _pulisci_riga(riga["testo"])
            if _riga_utile(testo, riga["conf"]):
                righe_ok.append({"testo": testo, "conf": riga["conf"]})

        punteggio = _punteggio(righe_ok)
        if punteggio > migliore["punteggio"]:
            migliore = {"righe": righe_ok, "punteggio": punteggio, "nome": nome}

        # Accumulo per recuperare righe lette bene solo da una variante diversa.
        accumulo.extend(righe_ok)

        # Arresto anticipato: qualità già ottima e testo sufficiente, non serve
        # altro tempo di calcolo. Con una sola riga si richiede una confidenza
        # molto alta, per non perdere titoli o autori presenti altrove.
        righe_buone = len(migliore["righe"]) >= 2 or (
            migliore["righe"] and max(r["conf"] for r in migliore["righe"]) >= 92
        )
        if migliore["punteggio"] >= config.OCR_GOOD_CONF and righe_buone:
            break

    # Seconda possibilità multilingue: una sola passata aggiuntiva, solo se la
    # lettura italiana ha deluso e ci sono altre lingue installate.
    lingue_usate = lingua_principale
    if lingua_estesa and lingua_estesa != lingua_principale and _conf_media(migliore["righe"]) < config.OCR_RETRY_CONF:
        nome, variante, psm = next(iter(_varianti_lettura(grigio, ImageFilter, ImageChops, ImageOps)))
        try:
            lette = _leggi_righe(variante, psm, pytesseract, lingua=lingua_estesa)
            righe_ok = []
            for riga in lette:
                testo = _pulisci_riga(riga["testo"])
                if _riga_utile(testo, riga["conf"]):
                    righe_ok.append({"testo": testo, "conf": riga["conf"]})
            passate.append("multilingue")
            if _punteggio(righe_ok) > migliore["punteggio"]:
                migliore = {"righe": righe_ok, "punteggio": _punteggio(righe_ok), "nome": "multilingue"}
                lingue_usate = lingua_estesa
        except Exception:
            pass

    # Scelta finale: si usano le righe della variante migliore, non un minestrone
    # di tutte. Mescolare le letture di varianti diverse produce doppioni e righe
    # sbagliate (es. «Umberto Eco» e «Umberto Eta.»): meglio poche righe giuste,
    # che l'utente può correggere, invece di rumore da districare.
    # L'unione dei candidati si usa solo se nessuna variante ha superato il filtro.
    if migliore["righe"]:
        finali = migliore["righe"]
    else:
        finali = []
        for riga in sorted(accumulo, key=lambda r: r["conf"], reverse=True):
            if any(_simili(riga["testo"], altra["testo"]) for altra in finali):
                continue
            finali.append(riga)

    linee = [r["testo"] for r in finali]
    confidenza = int(round(sum(r["conf"] for r in finali) / len(finali))) if finali else 0

    if confidenza >= 80:
        qualita = "alta"
    elif confidenza >= 60:
        qualita = "media"
    else:
        qualita = "bassa"

    return {
        "linee": linee,
        "confidenza": confidenza,
        "qualita": qualita,
        "rotazione": rotazione,
        "passate": passate,
        "lingue": lingue_usate,
    }
