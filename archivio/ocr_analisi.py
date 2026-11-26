# -*- coding: utf-8 -*-
"""
Analisi intelligente del testo estratto dall'OCR (`archivio/ocr_analisi.py`).

Trasforma le righe grezze lette da Tesseract in suggerimenti strutturati
per la scheda (tipo opera, titolo, autore, regista, formato disco, editore,
ISBN e controllo doppioni nell'archivio locale), più un arricchimento
opzionale dai cataloghi online aperti.

PRINCIPI DI PROGETTO
--------------------
- Modulo 100% Python puro per la parte locale: nessuna dipendenza aggiuntiva,
  nessun accesso a rete durante la lettura offline della foto.
- Le euristiche usano sia il testo sia la geometria restituita dall'OCR
  (`altezza_rel` dei caratteri e posizione verticale `bbox`), perché in una
  copertina il titolo è quasi sempre più grande dell'editore o della collana.
- I suggerimenti non sovrascrivono mai ciò che l'utente ha già modificato.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
import re
import urllib.parse

from . import config
from .http import get_api_session
from .utils import normalizza_testo

# ------------------------------------------------------------------------------
# DIZIONARI DI RICONOSCIMENTO (testo italiano e internazionale di copertine)
# ------------------------------------------------------------------------------
_EDITORI_NOTI = (
    "mondadori", "einaudi", "feltrinelli", "adelphi", "rizzoli", "bompiani",
    "garzanti", "laterza", "sellerio", "guanda", "il mulino", "zanichelli",
    "marsilio", "neri pozza", "newton compton", "longanesi", "hoepli",
    "utet", "giunti", "tea", "oscar", "bur", "universale economica",
    "meridiani", "saggiatore", "il saggiatore", "minimum fax", "iperborea",
    "voland", "fazi", "piemme", "sperling", "carocci", "franco angeli",
    "edizioni", "casa editrice", "editrice", "editore", "collana",
    "ristampa", "nuova edizione", "penguin", "gallimard", "folio",
)

_PAROLE_COPIONE = (
    "copione", "commedia", "tragedia", "dramma", "atto unico",
    "in due atti", "in tre atti", "in quattro atti", "regia", "regista",
    "allestimento", "compagnia teatrale", "compagnia", "prima rappresentazione",
    "in scena", "personaggi", "interpreti", "drammaturgia", "riduzione teatrale",
    "adattamento teatrale", "palcoscenico", "proscenio", "sipario",
)

_PAROLE_MUSICA = (
    "33 giri", "45 giri", "vinile", "compact disc", "cd audio", "stereo",
    "mono", "lato a", "lato b", "side a", "side b", "siae", "casa discografica",
    "etichetta", "musiche di", "tracce", "album", "discografia",
)

_ETICHETTE_DISCO = (
    "ricordi", "rca", "rca victor", "emi", "columbia", "decca", "polygram",
    "cetra", "fonit", "fonit cetra", "cgd", "philips", "numero uno",
    "warner", "sony music", "universal", "polydor", "ariston", "durium",
    "vanilla", "curci", "deutsche grammophon", "blue note",
)

_ETICHETTE_RUOLO = {
    "titolo": "📖 Titolo?",
    "autore": "👤 Autore?",
    "regista": "🎬 Regia",
    "teatro": "🏛️ Teatro",
    "editore": "🏢 Editore / Collana",
    "etichetta": "🎵 Etichetta / Formato",
    "isbn": "🔢 ISBN",
    "prezzo": "🏷️ Prezzo / Codice",
    "nota": "📝 Nota",
}


# ------------------------------------------------------------------------------
# ISBN-10 / ISBN-13
# ------------------------------------------------------------------------------
def _isbn13_valido(codice):
    if len(codice) != 13 or not codice.isdigit() or not codice.startswith(("978", "979")):
        return False
    tot = sum((1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(codice[:12]))
    check = (10 - (tot % 10)) % 10
    return check == int(codice[12])


def _isbn10_valido(codice):
    if len(codice) != 10:
        return False
    if not codice[:9].isdigit():
        return False
    ultimo = codice[9].upper()
    if not (ultimo.isdigit() or ultimo == "X"):
        return False
    tot = sum((10 - i) * int(ch) for i, ch in enumerate(codice[:9]))
    tot += 10 if ultimo == "X" else int(ultimo)
    return tot % 11 == 0


def estrai_isbn(testo):
    """
    Cerca e valida un codice ISBN-10 o ISBN-13 nel testo letto dall'OCR.
    Restituisce la stringa canonica senza trattini, oppure "" se assente/invalido.
    """
    if not testo:
        return ""
    if isinstance(testo, (list, tuple)):
        testo = "\n".join(str(x) for x in testo if x)

    # 1. Cerca prima sequenze esplicite vicino alla parola "ISBN" (correggendo O->0, I/l->1).
    for m in re.finditer(r"(?i)isbn(?:-1[03])?\s*[:\-]?\s*([0-9oOil\-\s]{9,22}[0-9oOilxX])", testo):
        grezzo = m.group(1)
        pulito = (
            grezzo.replace("O", "0").replace("o", "0")
            .replace("I", "1").replace("l", "1")
            .replace("-", "").replace(" ", "").upper()
        )
        if _isbn13_valido(pulito) or _isbn10_valido(pulito):
            return pulito

    # 2. Cerca un ISBN-13 libero con checksum valido (978/979..., 13 cifre totali).
    for m in re.finditer(r"\b(97[89][\d\-\s]{9,18}\d)\b", testo):
        pulito = re.sub(r"[\-\s]", "", m.group(1))
        if _isbn13_valido(pulito):
            return pulito

    return ""


# ------------------------------------------------------------------------------
# EURISTICHE DI CLASSIFICAZIONE
# ------------------------------------------------------------------------------
def _contiene_parola(testo_norm, termini):
    for termine in termini:
        if re.search(r"\b" + re.escape(termine) + r"\b", testo_norm):
            return termine
    return ""


def _sembra_editore(testo_norm):
    if _contiene_parola(testo_norm, _EDITORI_NOTI):
        return True
    if re.match(r"^(ed\.|ediz\.|collana|serie|oscar|bur)\b", testo_norm):
        return True
    return False


def _sembra_prezzo_o_rumore(testo, testo_norm):
    if re.search(r"(€|\beuro\b|\blire\b|£|\$)\s*\d", testo_norm):
        return True
    if re.match(r"^[\d\s.,/:\-]+$", testo.strip()):
        return True
    if any(k in testo_norm for k in ("tutti i diritti riservati", "printed in", "stampato in", "copyright", "©")):
        return True
    return False


def _estrai_regia(riga):
    m = re.search(r"(?i)\b(?:regia\s+di|diretto\s+da|regista\s*:?)\s+([A-ZÀ-Úa-zà-ù'’.\-\s]{3,50})", riga)
    if m:
        nome = " ".join(m.group(1).split()).strip(" .,-;:")
        if len(nome) >= 3:
            return nome
    return ""


def _estrai_teatro(riga):
    m = re.search(r"(?i)\b((?:piccolo\s+)?teatro\s+[A-ZÀ-Úa-zà-ù'’.\-\s]{2,55})", riga)
    if m:
        nome = " ".join(m.group(1).split()).strip(" .,-;:")
        if len(nome) >= 7:
            return nome
    return ""


def _punteggio_autore(riga, riga_norm, altezza_rel, altezze_valide, pos_y, autori_noti):
    """Valuta quanto una riga assomigli a un nome di autore o artista."""
    if not riga or _sembra_editore(riga_norm) or _sembra_prezzo_o_rumore(riga, riga_norm):
        return -10.0

    # Prefisso esplicito ("di Italo Calvino", "by William Shakespeare")
    if re.match(r"(?i)^(di|by|autore\s*:)\s+[a-zA-ZàèéìòùÀÈÉÌÒÙ]", riga.strip()):
        return 9.0

    if any(ch.isdigit() for ch in riga):
        return -4.0
    if any(ch in riga for ch in ("?", "!", ";", ":")):
        return -3.0

    parole = [p for p in re.split(r"[\s']+", riga.strip()) if p]
    if not (1 <= len(parole) <= 5):
        return -2.0

    punti = 0.0
    if 2 <= len(parole) <= 4:
        punti += 2.5
    elif len(parole) == 1 and len(riga.strip()) >= 5:
        punti += 0.5

    # Bonus forte se l'autore esiste già nell'archivio locale dell'utente.
    if autori_noti:
        for aut_norm in autori_noti:
            if aut_norm and (riga_norm == aut_norm or aut_norm in riga_norm):
                punti += 6.0
                break

    # In copertina l'autore sta spesso in alto sopra al titolo oppure subito sotto.
    if pos_y <= 0.25:
        punti += 1.5
    if altezze_valide:
        max_h = max(altezze_valide)
        # Se è molto più piccolo del testo più grande, è più spesso autore/sottotitolo.
        if max_h > 0 and altezza_rel < max_h * 0.78:
            punti += 1.2

    # Penalizza parole comuni da titolo (articoli/preposizioni iniziali tipici di opere).
    if parole[0].lower() in ("il", "lo", "la", "i", "gli", "le", "un", "una", "l", "the", "a", "an", "sul", "sulla"):
        punti -= 2.5

    # Tutte parole con iniziale maiuscola o tutto maiuscolo tipico dei nomi propri.
    alfa = [p for p in parole if p[0].isalpha()]
    if alfa and all(p[0].isupper() for p in alfa):
        punti += 1.5

    return punti


def _punteggio_titolo(riga, riga_norm, altezza_rel, altezze_valide, pos_y, conf):
    """Valuta quanto una riga assomigli al titolo principale dell'opera."""
    if not riga or _sembra_editore(riga_norm) or _sembra_prezzo_o_rumore(riga, riga_norm):
        return -10.0

    lunghezza = len(riga.strip())
    if lunghezza < 2 or lunghezza > 110:
        return -5.0

    punti = 0.0
    if altezze_valide and max(altezze_valide) > 0:
        # Peso predominante alla dimensione del carattere sulla copertina.
        punti += (altezza_rel / max(altezze_valide)) * 6.0
    if 0.08 <= pos_y <= 0.65:
        punti += 1.5
    if 4 <= lunghezza <= 60:
        punti += 1.5
    if conf >= 70:
        punti += 1.0
    if re.match(r"(?i)^(di|by)\s+", riga.strip()):
        punti -= 5.0
    return punti


def _pulisci_nome_autore(riga):
    return re.sub(r"(?i)^(di|by|autore\s*:)\s+", "", riga.strip()).strip()


def _rileva_tipo_e_formato(righe_norm):
    testo_unico = " \n ".join(righe_norm)
    punti_copione = sum(2 for p in _PAROLE_COPIONE if re.search(r"\b" + re.escape(p) + r"\b", testo_unico))
    punti_musica = sum(2 for p in _PAROLE_MUSICA if re.search(r"\b" + re.escape(p) + r"\b", testo_unico))
    punti_musica += sum(1 for e in _ETICHETTE_DISCO if re.search(r"\b" + re.escape(e) + r"\b", testo_unico))

    if re.search(r"\b(lp|cd)\b", testo_unico):
        punti_musica += 2

    if punti_copione >= 2 and punti_copione >= punti_musica:
        tipo = "Copione"
    elif punti_musica >= 2:
        tipo = "CD / Vinile"
    else:
        tipo = "Libro"

    formato = ""
    if tipo == "CD / Vinile":
        if re.search(r"\b45\s*giri\b", testo_unico):
            formato = "Vinile 45 giri"
        elif re.search(r"\b(cd|compact\s+disc|cd\s+audio)\b", testo_unico):
            formato = "CD"
        else:
            formato = "Vinile LP"

    return tipo, formato


def _cerca_doppioni_locali(titolo, autore, elementi_archivio):
    """Confronta il titolo suggerito con la collezione di casa già salvata."""
    if not titolo or not elementi_archivio:
        return []
    titolo_norm = normalizza_testo(titolo)
    if len(titolo_norm) < 4:
        return []
    autore_norm = normalizza_testo(autore) if autore else ""

    corrispondenze = []
    for el in elementi_archivio:
        el_tit_norm = normalizza_testo(el.get("titolo") or "")
        if not el_tit_norm:
            continue
        simile = (
            titolo_norm == el_tit_norm
            or (len(titolo_norm) >= 6 and (titolo_norm in el_tit_norm or el_tit_norm in titolo_norm))
            or difflib.SequenceMatcher(None, titolo_norm, el_tit_norm).ratio() >= 0.86
        )
        if not simile:
            continue
        # Se entrambi hanno autore, verifica una minima compatibilità se non è match esatto.
        el_aut_norm = normalizza_testo(el.get("autore") or "")
        if autore_norm and el_aut_norm and titolo_norm != el_tit_norm:
            if autore_norm not in el_aut_norm and el_aut_norm not in autore_norm:
                if difflib.SequenceMatcher(None, autore_norm, el_aut_norm).ratio() < 0.7:
                    continue
        corrispondenze.append({
            "id": el.get("id"),
            "titolo": el.get("titolo") or "",
            "autore": el.get("autore") or "",
            "collocazione_casa": el.get("collocazione_casa") or "",
            "tipo": el.get("tipo") or "Libro",
        })
        if len(corrispondenze) >= 3:
            break
    return corrispondenze


def analizza_righe_ocr(righe_dettaglio, autori_noti=None, elementi_archivio=None):
    """
    Analizza le righe lette dall'OCR e produce:
        {
          "suggerimenti": {
              "tipo": "Libro|Copione|CD / Vinile",
              "titolo": "...",
              "autore": "...",
              "regista": "...",
              "prima_esibizione_luogo": "...",
              "data_prima": "...",
              "formato": "...",
              "etichetta_anno": "...",
              "note": "...",
              "isbn": "...",
          },
          "ruoli_righe": [{"ruolo": "...", "etichetta": "..."}, ...],
          "doppioni_locali": [...],
        }
    """
    voci = []
    for item in righe_dettaglio or []:
        if isinstance(item, str):
            voci.append({"testo": item, "conf": 80.0, "bbox": (0.0, 0.0, 0.0, 0.0), "altezza_rel": 0.0})
        elif isinstance(item, dict) and item.get("testo"):
            voci.append({
                "testo": str(item["testo"]).strip(),
                "conf": float(item.get("conf") or 0.0),
                "bbox": item.get("bbox") or (0.0, 0.0, 0.0, 0.0),
                "altezza_rel": float(item.get("altezza_rel") or 0.0),
            })

    if not voci:
        return {
            "suggerimenti": {
                "tipo": "Libro",
                "titolo": "",
                "autore": "",
                "regista": "",
                "prima_esibizione_luogo": "",
                "data_prima": "",
                "formato": "",
                "etichetta_anno": "",
                "note": "",
                "isbn": "",
            },
            "ruoli_righe": [],
            "doppioni_locali": [],
        }

    righe_norm = [normalizza_testo(v["testo"]) for v in voci]
    tipo, formato = _rileva_tipo_e_formato(righe_norm)
    isbn = estrai_isbn([v["testo"] for v in voci])

    altezze_valide = [v["altezza_rel"] for v in voci if v["altezza_rel"] > 0]
    autori_norm_set = {normalizza_testo(a) for a in (autori_noti or ()) if a}

    regista = ""
    teatro = ""
    data_prima = ""
    etichetta_anno = ""
    ruoli = ["nota"] * len(voci)

    # 1. Riconoscimento marcatori certi (ISBN, prezzi, regia, teatro, editori, etichette).
    for idx, v in enumerate(voci):
        testo = v["testo"]
        norm = righe_norm[idx]

        if estrai_isbn(testo):
            ruoli[idx] = "isbn"
            continue
        if _sembra_prezzo_o_rumore(testo, norm):
            ruoli[idx] = "prezzo"
            continue

        reg_trovato = _estrai_regia(testo)
        if reg_trovato and not regista:
            regista = reg_trovato
            ruoli[idx] = "regista"
            continue

        teatro_trovato = _estrai_teatro(testo)
        if teatro_trovato and not teatro and tipo == "Copione":
            teatro = teatro_trovato
            ruoli[idx] = "teatro"
            continue

        if tipo == "Copione" and not data_prima:
            m_data = re.search(r"\b(\d{2}/\d{2}/(?:19|20)\d{2})\b", testo)
            if m_data:
                data_prima = m_data.group(1)

        if tipo == "CD / Vinile" and not etichetta_anno:
            et = _contiene_parola(norm, _ETICHETTE_DISCO)
            m_anno = re.search(r"\b(19\d{2}|20\d{2})\b", testo)
            if et:
                etichetta_anno = f"{testo.strip()}"
                ruoli[idx] = "etichetta"
                continue
            if m_anno and len(testo) <= 35:
                etichetta_anno = testo.strip()
                ruoli[idx] = "etichetta"
                continue

        if _sembra_editore(norm):
            ruoli[idx] = "editore"

    # 2. Scelta migliore del Titolo (usando dimensione font e posizione).
    idx_titolo = None
    miglior_tit_score = -999.0
    for idx, v in enumerate(voci):
        if ruoli[idx] in ("isbn", "prezzo", "regista", "teatro", "editore", "etichetta"):
            continue
        pos_y = (v["bbox"][1] if v["bbox"] else 0.5)
        score = _punteggio_titolo(v["testo"], righe_norm[idx], v["altezza_rel"], altezze_valide, pos_y, v["conf"])
        if score > miglior_tit_score:
            miglior_tit_score = score
            idx_titolo = idx

    # Ripiego se tutte le righe sembravano editori/note: prendi la prima non prezzo/ISBN.
    if idx_titolo is None:
        for idx, _ in enumerate(voci):
            if ruoli[idx] not in ("isbn", "prezzo"):
                idx_titolo = idx
                break

    titolo = ""
    if idx_titolo is not None:
        titolo = voci[idx_titolo]["testo"]
        ruoli[idx_titolo] = "titolo"

    # 3. Scelta migliore dell'Autore/Artista tra le righe restanti.
    idx_autore = None
    miglior_aut_score = 1.8  # Soglia minima per non promuovere righe casuali ad autore
    for idx, v in enumerate(voci):
        if idx == idx_titolo or ruoli[idx] in ("isbn", "prezzo", "regista", "teatro", "editore", "etichetta"):
            continue
        pos_y = (v["bbox"][1] if v["bbox"] else 0.5)
        score = _punteggio_autore(v["testo"], righe_norm[idx], v["altezza_rel"], altezze_valide, pos_y, autori_norm_set)
        if score > miglior_aut_score:
            miglior_aut_score = score
            idx_autore = idx

    autore = ""
    if idx_autore is not None:
        autore = _pulisci_nome_autore(voci[idx_autore]["testo"])
        ruoli[idx_autore] = "autore"

    # 4. Note suggerite (editore, ISBN, anno/dettagli residui utili).
    parti_note = []
    for idx, v in enumerate(voci):
        if idx in (idx_titolo, idx_autore):
            continue
        if ruoli[idx] in ("editore", "etichetta"):
            parti_note.append(v["testo"])
    if isbn:
        parti_note.append(f"ISBN: {isbn}")
    note = " • ".join(dict.fromkeys(parti_note))

    ruoli_righe = [
        {"ruolo": r, "etichetta": _ETICHETTE_RUOLO.get(r, "📝 Nota")}
        for r in ruoli
    ]
    doppioni = _cerca_doppioni_locali(titolo, autore, elementi_archivio)

    return {
        "suggerimenti": {
            "tipo": tipo,
            "titolo": titolo,
            "autore": autore,
            "regista": regista,
            "prima_esibizione_luogo": teatro,
            "data_prima": data_prima,
            "formato": formato,
            "etichetta_anno": etichetta_anno,
            "note": note,
            "isbn": isbn,
        },
        "ruoli_righe": ruoli_righe,
        "doppioni_locali": doppioni,
    }


# ------------------------------------------------------------------------------
# ARRICCHIMENTO OPZIONALE DAI CATALOGHI ONLINE (su clic esplicito dell'utente)
# ------------------------------------------------------------------------------
def _cerca_openlibrary_per_ocr(isbn, titolo, autore):
    risultati = []
    try:
        if isbn:
            url = (
                "https://openlibrary.org/search.json"
                f"?isbn={urllib.parse.quote_plus(isbn)}&limit=2"
                "&fields=title,author_name,publisher,first_publish_year,isbn"
            )
        else:
            url = (
                "https://openlibrary.org/search.json"
                f"?title={urllib.parse.quote_plus(titolo)}&limit=3"
                "&fields=title,author_name,publisher,first_publish_year,isbn"
            )
            if autore:
                url += f"&author={urllib.parse.quote_plus(autore)}"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for doc in (resp.json().get("docs") or [])[:3]:
                autori = doc.get("author_name") or []
                editori = doc.get("publisher") or []
                isbns = doc.get("isbn") or []
                risultati.append({
                    "titolo": doc.get("title") or "",
                    "autore": ", ".join(str(a) for a in autori[:2] if a),
                    "editore": str(editori[0]) if editori else "",
                    "anno": str(doc.get("first_publish_year") or ""),
                    "isbn": isbn or (str(isbns[0]) if isbns else ""),
                    "fonte": "Open Library",
                })
    except Exception as e:
        print(f"[OCR OpenLibrary] Errore: {e}")
    return [r for r in risultati if r["titolo"]]


def _cerca_google_books_per_ocr(isbn, titolo, autore):
    risultati = []
    try:
        if isbn:
            q = f"isbn:{isbn}"
        else:
            q = f"intitle:{titolo}" + (f" inauthor:{autore}" if autore else "")
        url = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q={urllib.parse.quote_plus(q)}&maxResults=3&printType=books"
        )
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for item in (resp.json().get("items") or [])[:3]:
                info = item.get("volumeInfo") or {}
                autori = info.get("authors") or []
                ids = info.get("industryIdentifiers") or []
                cod_isbn = isbn
                if not cod_isbn:
                    for obj in ids:
                        if isinstance(obj, dict) and obj.get("identifier"):
                            cod_isbn = str(obj["identifier"])
                            break
                risultati.append({
                    "titolo": info.get("title") or "",
                    "autore": ", ".join(str(a) for a in autori[:2] if a),
                    "editore": info.get("publisher") or "",
                    "anno": (info.get("publishedDate") or "")[:4],
                    "isbn": cod_isbn,
                    "fonte": "Google Books",
                })
    except Exception as e:
        print(f"[OCR GoogleBooks] Errore: {e}")
    return [r for r in risultati if r["titolo"]]


def _cerca_musicbrainz_per_ocr(titolo, autore):
    risultati = []
    try:
        q = f"{titolo} {autore}".strip()
        url = f"https://musicbrainz.org/ws/2/release/?query={urllib.parse.quote_plus(q)}&fmt=json&limit=3"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for rel in (resp.json().get("releases") or [])[:3]:
                artisti = [a.get("name", "") for a in (rel.get("artist-credit") or []) if isinstance(a, dict) and a.get("name")]
                label_info = rel.get("label-info-list") or []
                etichetta = ""
                if label_info and isinstance(label_info, list):
                    lbl = (label_info[0] or {}).get("label")
                    if isinstance(lbl, dict):
                        etichetta = lbl.get("name") or ""
                anno = (rel.get("date") or "")[:4]
                risultati.append({
                    "titolo": rel.get("title") or "",
                    "autore": ", ".join(artisti),
                    "editore": etichetta,
                    "anno": anno,
                    "isbn": "",
                    "fonte": "MusicBrainz",
                })
    except Exception as e:
        print(f"[OCR MusicBrainz] Errore: {e}")
    return [r for r in risultati if r["titolo"]]


def arricchisci_da_cataloghi(isbn="", titolo="", autore="", tipo="Libro"):
    """
    Interroga in parallelo i cataloghi aperti pertinenti (per ISBN esatto o per
    titolo/autore) e restituisce fino a 4 schede candidate ripulite.
    """
    isbn_pulito = estrai_isbn(isbn) if isbn else ""
    titolo = (titolo or "").strip()
    autore = (autore or "").strip()

    if not isbn_pulito and len(titolo) < 2:
        return []

    compiti = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        if tipo == "CD / Vinile" and not isbn_pulito:
            compiti.append(pool.submit(_cerca_musicbrainz_per_ocr, titolo, autore))
        else:
            compiti.append(pool.submit(_cerca_openlibrary_per_ocr, isbn_pulito, titolo, autore))
            compiti.append(pool.submit(_cerca_google_books_per_ocr, isbn_pulito, titolo, autore))

        candidati = []
        for f in as_completed(compiti):
            try:
                candidati.extend(f.result())
            except Exception:
                pass

    # Deduplica per titolo + autore normalizzati.
    visti = set()
    unici = []
    for c in candidati:
        chiave = (normalizza_testo(c["titolo"]), normalizza_testo(c["autore"]))
        if chiave in visti:
            continue
        visti.add(chiave)
        unici.append(c)
        if len(unici) >= 4:
            break
    return unici
