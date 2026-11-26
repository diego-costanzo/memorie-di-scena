# -*- coding: utf-8 -*-
"""
Rotte principali: pagina iniziale, acquisizione OCR e upload foto.

ROTTE
-----
    GET  /               pagina iniziale: scaffale, prestiti e statistiche
    GET  /acquisizione_ocr  pagina di lettura da fotografia
    POST /ocr_upload     riceve la foto, esegue l'OCR e restituisce le righe
    POST /backup         crea e scarica una copia di sicurezza del database

NOTE SULLA PAGINA INIZIALE
--------------------------
Le due query di `index()` sono volutamente aggregate (LEFT JOIN + subquery):
caricano tutto in due passaggi, senza una query per ogni volume (problema N+1).
I prestiti scaduti ricevono `giorni_ritardo` calcolato in Python, così il
template non deve fare aritmetica sulle date.

NOTE SULL'OCR
-------------
`ocr_upload` valida estensione e dimensione, corregge l'orientamento EXIF,
salva un'anteprima ridimensionata (che diventa la copertina del volume) e poi
esegue la pipeline in `archivio/ocr.py`. L'anteprima resta in
`static/covers/` anche se l'utente non salva la scheda.
"""
import os
import secrets
import time
from datetime import date, datetime

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from .. import config
from ..db import backup_database, get_db
from ..ocr import estrai_testo_da_immagine, get_ocr_tools, immagine_rgb_su_bianco, stato_lingua_ocr
from ..ocr_analisi import analizza_righe_ocr, arricchisci_da_cataloghi
from ..ocr_analisi import analizza_righe_ocr, arricchisci_da_cataloghi
from ..utils import giorni_di_ritardo


def _pulisci_anteprime_orfane(ore=24):
    """
    Rimuove le anteprime OCR (`foto_acquisita_*`) più vecchie di N ore che
    non sono state usate come copertina di nessun volume.

    `ocr_upload` salva sempre un'anteprima, ma se l'utente chiude la pagina
    senza salvare la scheda quel file resterebbe per sempre in `static/covers/`.
    Qui lo ripuliamo senza toccare le anteprime ancora collegate a una scheda.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT copertina_path FROM elementi WHERE copertina_path LIKE '/static/covers/foto\\_acquisita%' ESCAPE '\\'"
            )
            in_uso = {os.path.basename(r["copertina_path"]) for r in cursor.fetchall()}
        limite = time.time() - ore * 3600
        for nome in os.listdir(config.COVERS_DIR):
            if not nome.startswith("foto_acquisita_"):
                continue
            if nome in in_uso:
                continue
            percorso = os.path.join(config.COVERS_DIR, nome)
            try:
                if os.path.isfile(percorso) and os.path.getmtime(percorso) < limite:
                    os.remove(percorso)
            except OSError:
                pass
    except Exception as e:
        print(f"[OCR Pulizia anteprime] {e}")


def register(app):
    @app.route("/")
    def index():
        with get_db() as conn:
            cursor = conn.cursor()

            # Prestiti attivi
            cursor.execute("""
                SELECT
                    p.id AS prestito_id,
                    p.nome_persona,
                    p.data_prestito,
                    p.data_rientro_prevista,
                    e.id AS elemento_id,
                    e.tipo,
                    e.titolo,
                    e.autore,
                    e.collocazione_casa,
                    e.copertina_path
                FROM prestiti p
                JOIN elementi e ON p.elemento_id = e.id
                WHERE p.stato = 'In Prestito'
                ORDER BY p.id DESC
            """)
            prestiti_attivi = [dict(row) for row in cursor.fetchall()]

            # Segnalazione dei prestiti scaduti: un aiuto concreto, sempre visibile.
            for prestito in prestiti_attivi:
                prestito["giorni_ritardo"] = giorni_di_ritardo(prestito["data_rientro_prevista"])

            # Elementi con stato prestito e conteggio appunti (aggregato unico, senza N+1)
            cursor.execute("""
                SELECT
                    e.*,
                    p.id AS prestito_id,
                    p.nome_persona AS prestito_persona,
                    p.data_prestito AS prestito_data,
                    p.data_rientro_prevista AS prestito_rientro_previsto,
                    CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END AS in_prestito,
                    COALESCE(ac.num_appunti, 0) AS num_appunti
                FROM elementi e
                LEFT JOIN prestiti p ON e.id = p.elemento_id AND p.stato = 'In Prestito'
                LEFT JOIN (
                    SELECT elemento_id, COUNT(*) AS num_appunti
                    FROM appunti
                    GROUP BY elemento_id
                ) ac ON ac.elemento_id = e.id
                ORDER BY e.id DESC
            """)
            elementi = [dict(row) for row in cursor.fetchall()]

        conteggio_totale = len(elementi)
        conteggio_libri = sum(1 for el in elementi if el['tipo'] == 'Libro')
        conteggio_copioni = sum(1 for el in elementi if el['tipo'] == 'Copione')
        conteggio_musica = sum(1 for el in elementi if el['tipo'] == 'CD / Vinile')
        conteggio_prestiti = len(prestiti_attivi)

        return render_template(
            "index.html",
            elementi=elementi,
            prestiti_attivi=prestiti_attivi,
            totale=conteggio_totale,
            num_libri=conteggio_libri,
            num_copioni=conteggio_copioni,
            num_musica=conteggio_musica,
            num_prestiti=conteggio_prestiti,
            data_oggi=date.today().strftime("%d/%m/%Y")
        )

    @app.route("/acquisizione_ocr")
    def acquisizione_ocr():
        return render_template(
            "acquisizione_ocr.html",
            data_oggi=date.today().strftime("%d/%m/%Y"),
            stato_lingua=stato_lingua_ocr(),
        )

    @app.route("/ocr_upload", methods=["POST"])
    def ocr_upload():
        """Riceve un'immagine, la valida, ne limita le dimensioni ed esegue l'OCR."""
        # Ripulisce le anteprime di acquisizioni precedenti mai salvate.
        _pulisci_anteprime_orfane()

        if "foto" not in request.files:
            return jsonify({"success": False, "errore": "Nessuna foto ricevuta."}), 400

        file = request.files["foto"]
        if not file or file.filename == "":
            return jsonify({"success": False, "errore": "File non selezionato."}), 400

        clean_filename = secure_filename(file.filename)
        if not config.allowed_file(clean_filename):
            return jsonify({"success": False, "errore": "Formato file non supportato. Carica un'immagine JPG, PNG o WEBP."}), 400

        try:
            Image, ImageOps, resample_filter = get_ocr_tools()
            with Image.open(file.stream) as img:
                # Ridimensiona prima di trasporre/convertire per limitare la RAM
                # su foto ad altissima risoluzione (thumbnail conserva i tag EXIF).
                if max(img.size) > config.MAX_IMAGE_DIM:
                    img.thumbnail((config.MAX_IMAGE_DIM, config.MAX_IMAGE_DIM), resample_filter)
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

                # Salviamo sempre come JPEG reale: usiamo sempre l'estensione .jpg.
                filename = f"foto_acquisita_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}.jpg"
                save_path = os.path.join(config.COVERS_DIR, filename)

                # Anteprima: appoggia eventuali trasparenze su sfondo bianco.
                rgb_img = immagine_rgb_su_bianco(img, Image)
                if max(rgb_img.size) > config.MAX_IMAGE_DIM:
                    rgb_img.thumbnail((config.MAX_IMAGE_DIM, config.MAX_IMAGE_DIM), resample_filter)
                rgb_img.save(save_path, "JPEG", quality=85, optimize=True)

                risultato = estrai_testo_da_immagine(rgb_img, max_lato=config.MAX_IMAGE_DIM)

            autori_noti = []
            elementi_archivio = []
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id, tipo, titolo, autore, collocazione_casa FROM elementi")
                    for r in cur.fetchall():
                        elementi_archivio.append(dict(r))
                        if r["autore"]:
                            autori_noti.append(r["autore"])
            except Exception as db_err:
                print(f"[OCR Analisi DB] {db_err}")

            righe_dettaglio = risultato.get("righe_dettaglio") or [
                {"testo": riga, "conf": risultato.get("confidenza", 70), "bbox": (0.0, 0.0, 0.0, 0.0), "altezza_rel": 0.0}
                for riga in risultato.get("linee", [])
            ]
            analisi = analizza_righe_ocr(
                righe_dettaglio,
                autori_noti=autori_noti,
                elementi_archivio=elementi_archivio,
            )
            doppioni = analisi["doppioni_locali"]

            return jsonify({
                "success": True,
                "linee": risultato["linee"],
                "anteprima_url": f"/static/covers/{filename}",
                "filename": filename,
                "totale_linee": len(risultato["linee"]),
                "confidenza": risultato["confidenza"],
                "qualita": risultato["qualita"],
                "rotazione": risultato.get("rotazione", 0),
                "lingue": risultato.get("lingue", ""),
                "suggerimenti": analisi["suggerimenti"],
                "ruoli": [r["ruolo"] for r in analisi["ruoli_righe"]],
                "doppione_locale": doppioni[0] if doppioni else None,
                "doppioni_locali": doppioni,
            })

        except Exception as e:
            # Il dettaglio tecnico finisce solo nel log del terminale: all'utente
            # mostriamo un messaggio comprensibile, senza esporre percorsi,
            # nomi di librerie o stack trace.
            print(f"[OCR Upload Error] {e}")
            return jsonify({"success": False, "errore": "Non è stato possibile leggere la foto. Prova con un'immagine più nitida e ben illuminata."}), 500

    @app.route("/api/ocr/arricchisci", methods=["POST"])
    def api_ocr_arricchisci():
        """
        Cerca nei cataloghi aperti (per ISBN oppure titolo/autore letti dalla
        foto) e restituisce possibili schede complete per correggere eventuali
        refusi OCR con un clic.
        """
        dati = request.get_json(silent=True)
        if not isinstance(dati, dict):
            dati = {}

        def _s(k):
            v = dati.get(k)
            return v.strip() if isinstance(v, str) else ""

        isbn = _s("isbn")
        titolo = _s("titolo")
        autore = _s("autore")
        tipo = _s("tipo") or "Libro"
        if tipo not in ("Libro", "Copione", "CD / Vinile"):
            tipo = "Libro"

        if not isbn and len(titolo) < 3:
            return jsonify({
                "success": False,
                "errore": "Inserisci almeno il titolo (3+ caratteri) o un codice ISBN valido.",
            }), 400

        try:
            risultati = arricchisci_da_cataloghi(isbn=isbn, titolo=titolo, autore=autore, tipo=tipo)
            return jsonify({"success": True, "risultati": risultati})
        except Exception as e:
            print(f"[OCR Arricchisci] Errore: {e}")
            return jsonify({
                "success": False,
                "errore": "Impossibile consultare i cataloghi online in questo momento.",
            }), 500

    @app.route("/backup", methods=["POST"])
    def scarica_backup():
        """
        Copia di sicurezza con un clic: crea una copia coerente del database e
        la fa scaricare nella cartella Download del browser. In più, la copia
        resta anche in data/backup/ come le altre.
        """
        percorso = backup_database()
        if not percorso:
            flash("Non è stato possibile creare la copia di sicurezza. Riprova tra un istante.", "errore")
            return redirect(url_for("index"))

        nome = f"memorie_di_scena_{date.today().strftime('%d-%m-%Y')}.db"
        return send_file(percorso, as_attachment=True, download_name=nome)
