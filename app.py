#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memorie di Scena - Archivio Teatrale e Collezione Personale
Web App locale per la gestione di Libri, Copioni teatrali, CD/Vinili, Ricordi e Prestiti.
Audited & Hardened:
- SQLite gestito con context manager (commit/rollback/close garantiti e PRAGMA foreign_keys = ON)
- Upload limitati a 32MB e formati consentiti con secure_filename contro Path Traversal
- Pillow con blocco context manager, limite 2400px RAM e rilascio risorse esplicito
- Esecuzione rigorosa su host 127.0.0.1 porta 5000 con debug=False
"""

import os
import sys
import sqlite3
import urllib.parse
from datetime import datetime, date
from contextlib import contextmanager
import shutil
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance, ImageOps
import pytesseract

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "archivio.db")
COVERS_DIR = os.path.join(BASE_DIR, "static", "covers")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

# Migrazione di sicurezza: se archivio.db risiede nella root, spostalo in data/archivio.db
ROOT_OLD_DB = os.path.join(BASE_DIR, "archivio.db")
if os.path.exists(ROOT_OLD_DB) and not os.path.exists(DB_PATH):
    shutil.move(ROOT_OLD_DB, DB_PATH)
elif os.path.exists(ROOT_OLD_DB) and os.path.exists(DB_PATH):
    try:
        os.remove(ROOT_OLD_DB)
    except Exception:
        pass

app = Flask(__name__)
app.secret_key = "memorie_di_scena_registro_teatrale_chiave_protetta"

# ------------------------------------------------------------------------------
# SICUREZZA UPLOAD & RISORSE (OTTIMIZZATO PER FOTO DA SMARTPHONE MODERNI)
# ------------------------------------------------------------------------------
# 32 MB accoglie comodamente scatti ad alta risoluzione (anche a 48MP/50MP)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "jfif"}

# Previene falsi positivi 'DecompressionBomb' di Pillow su scatti ad altissima risoluzione
Image.MAX_IMAGE_PIXELS = 150_000_000

def allowed_file(filename):
    """Verifica che l'estensione sia tra quelle strettamente consentite."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.errorhandler(413)
def file_too_large(e):
    """Gestione pulita superamento quota upload."""
    return jsonify({"success": False, "errore": "Il file caricato supera la dimensione massima consentita di 32 MB."}), 413


# ------------------------------------------------------------------------------
# GESTIONE DATABASE CON CONTEXT MANAGER & INTEGRITÀ REFERENZIALE
# ------------------------------------------------------------------------------
@contextmanager
def get_db():
    """
    Context manager sicuro per SQLite:
    - Attiva sempre PRAGMA foreign_keys = ON;
    - Esegue commit automatico al termine del blocco;
    - Esegue rollback automatico in caso di errore;
    - Garantisce la chiusura immediata della connessione per evitare lock e leak di memoria.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Inizializza o aggiorna lo schema del database in modo sicuro e transazionale."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Tabella elementi (verifica e migrazione sicura CHECK constraint)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='elementi'")
        row = cursor.fetchone()

        if row is None:
            cursor.execute("""
                CREATE TABLE elementi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL CHECK(tipo IN ('Libro', 'Copione', 'CD / Vinile')),
                    titolo TEXT NOT NULL,
                    autore TEXT,
                    collocazione_casa TEXT,
                    note TEXT,
                    copertina_path TEXT,
                    data_inserimento TEXT NOT NULL,
                    regista TEXT,
                    prima_esibizione_luogo TEXT,
                    data_ingaggio TEXT,
                    data_prima TEXT,
                    formato TEXT,
                    etichetta_anno TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_tipo ON elementi(tipo);")
        else:
            sql_creazione = row[0]
            if "CD / Vinile" not in sql_creazione:
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("""
                    CREATE TABLE elementi_migrazione (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL CHECK(tipo IN ('Libro', 'Copione', 'CD / Vinile')),
                        titolo TEXT NOT NULL,
                        autore TEXT,
                        collocazione_casa TEXT,
                        note TEXT,
                        copertina_path TEXT,
                        data_inserimento TEXT NOT NULL,
                        regista TEXT,
                        prima_esibizione_luogo TEXT,
                        data_ingaggio TEXT,
                        data_prima TEXT,
                        formato TEXT,
                        etichetta_anno TEXT
                    );
                """)
                cursor.execute("""
                    INSERT INTO elementi_migrazione (
                        id, tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                        regista, prima_esibizione_luogo, data_ingaggio, data_prima
                    )
                    SELECT id, tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                           regista, prima_esibizione_luogo, data_ingaggio, data_prima
                    FROM elementi;
                """)
                cursor.execute("DROP TABLE elementi;")
                cursor.execute("ALTER TABLE elementi_migrazione RENAME TO elementi;")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_tipo ON elementi(tipo);")
                cursor.execute("PRAGMA foreign_keys = ON;")

            # Verifica colonne formato ed etichetta_anno
            cursor.execute("PRAGMA table_info(elementi);")
            colonne = [c[1] for c in cursor.fetchall()]
            if "formato" not in colonne:
                cursor.execute("ALTER TABLE elementi ADD COLUMN formato TEXT;")
            if "etichetta_anno" not in colonne:
                cursor.execute("ALTER TABLE elementi ADD COLUMN etichetta_anno TEXT;")

        # 2. Tabella prestiti
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prestiti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elemento_id INTEGER NOT NULL REFERENCES elementi(id) ON DELETE CASCADE,
                nome_persona TEXT NOT NULL,
                data_prestito TEXT NOT NULL,
                data_rientro_prevista TEXT,
                data_rientro_effettiva TEXT,
                stato TEXT NOT NULL DEFAULT 'In Prestito' CHECK(stato IN ('In Prestito', 'Rientrato'))
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prestiti_stato ON prestiti(stato);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prestiti_elem ON prestiti(elemento_id);")

        # 3. Tabella appunti (Taccuino dei Ricordi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appunti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elemento_id INTEGER NOT NULL REFERENCES elementi(id) ON DELETE CASCADE,
                testo TEXT NOT NULL,
                data_creazione TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appunti_elem ON appunti(elemento_id);")

        # 4. Elementi dimostrativi se vuoto
        cursor.execute("SELECT COUNT(*) FROM elementi")
        count = cursor.fetchone()[0]
        if count == 0:
            data_oggi = date.today().strftime("%d/%m/%Y")
            
            cursor.execute("""
                INSERT INTO elementi (tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                                     regista, prima_esibizione_luogo, data_ingaggio, data_prima)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'Copione', 'La locandiera', 'Carlo Goldoni', 'Studio - Cassetto grande copioni',
                'Copione con note di regia e battute annotate a matita. Ruolo di Fabrizio.',
                '/static/covers/default_copione.svg', data_oggi,
                'Giancarlo Cobelli', 'Teatro della Pergola, Firenze', '10/01/1988', '04/03/1988'
            ))

            cursor.execute("""
                INSERT INTO elementi (tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'Libro', 'Il nome della rosa', 'Umberto Eco', 'Salotto - Scaffale centrale, 2° ripiano',
                'Prima edizione Bompiani con copertina rigida telata.',
                '/static/covers/default_libro.svg', data_oggi
            ))

            cursor.execute("""
                INSERT INTO elementi (tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'Libro', 'Le città invisibili', 'Italo Calvino', 'Studio - Ripiano narrativa italiana',
                'Edizione Einaudi tascabile.', '/static/covers/default_libro.svg', data_oggi
            ))
            libro_prestito_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO prestiti (elemento_id, nome_persona, data_prestito, data_rientro_prevista, stato)
                VALUES (?, ?, ?, ?, 'In Prestito')
            """, (libro_prestito_id, 'Franco (collega di compagnia)', data_oggi, '15 del mese prossimo'))

        # Demo musicale se non presente
        cursor.execute("SELECT COUNT(*) FROM elementi WHERE tipo = 'CD / Vinile'")
        musica_count = cursor.fetchone()[0]
        if musica_count == 0:
            data_oggi = date.today().strftime("%d/%m/%Y")
            cursor.execute("""
                INSERT INTO elementi (tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento, formato, etichetta_anno)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'CD / Vinile', 'Creuza de mä', 'Fabrizio De André', 'Salotto - Mobile giradischi',
                'Stampa originale su vinile 33 giri. Uno dei dischi più cari della collezione.',
                '/static/covers/default_musica.svg', data_oggi, 'Vinile LP', 'Ricordi, 1984'
            ))
            vinile_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO appunti (elemento_id, testo, data_creazione)
                VALUES (?, ?, ?)
            """, (
                vinile_id,
                'Un capolavoro che profuma di mare, salsedine e vicoli antichi. Da ascoltare la sera in poltrona con le luci soffuse.',
                data_oggi
            ))


def scarica_copertina_web(titolo, autore, tipo, elemento_id):
    """
    Recupera la copertina online senza bloccare il database.
    Fallback immediato su eleganti SVG classici se offline o non trovato.
    """
    if tipo == 'Copione':
        fallback_path = "/static/covers/default_copione.svg"
    elif tipo == 'CD / Vinile':
        fallback_path = "/static/covers/default_musica.svg"
    else:
        fallback_path = "/static/covers/default_libro.svg"

    if not titolo:
        return fallback_path

    headers = {'User-Agent': 'MemorieDiScena/2.0 (Debian GNU/Linux)'}

    # Ricerca musicale su iTunes Store API
    if tipo == 'CD / Vinile':
        try:
            termine = f"{titolo} {autore if autore else ''}".strip()
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote_plus(termine)}&entity=album&limit=1"
            resp = requests.get(url, timeout=3.5, headers=headers)
            if resp.status_code == 200:
                dati = resp.json()
                if dati.get('results'):
                    art_url = dati['results'][0].get('artworkUrl100', '')
                    if art_url:
                        art_url = art_url.replace('/100x100bb.jpg', '/600x600bb.jpg')
                        img_resp = requests.get(art_url, timeout=4, headers=headers)
                        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                            filename = f"copertina_{elemento_id}_{int(datetime.now().timestamp())}.jpg"
                            file_path = os.path.join(COVERS_DIR, filename)
                            with open(file_path, 'wb') as f:
                                f.write(img_resp.content)
                            return f"/static/covers/{filename}"
        except Exception as e:
            print(f"[Musica] Errore recupero copertina '{titolo}': {e}")

    # Ricerca libri/copioni su Open Library
    try:
        q_titolo = urllib.parse.quote_plus(titolo.strip())
        url = f"https://openlibrary.org/search.json?title={q_titolo}&limit=1"
        if autore and autore.strip():
            url += f"&author={urllib.parse.quote_plus(autore.strip())}"
        
        resp = requests.get(url, timeout=3.5, headers=headers)
        if resp.status_code == 200:
            dati = resp.json()
            docs = dati.get('docs', [])
            if docs and docs[0].get('cover_i'):
                cover_id = docs[0]['cover_i']
                img_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                img_resp = requests.get(img_url, timeout=4, headers=headers)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    filename = f"copertina_{elemento_id}_{int(datetime.now().timestamp())}.jpg"
                    file_path = os.path.join(COVERS_DIR, filename)
                    with open(file_path, 'wb') as f:
                        f.write(img_resp.content)
                    return f"/static/covers/{filename}"
    except Exception as e:
        print(f"[OpenLibrary] Errore recupero copertina '{titolo}': {e}")

    # Ricerca di riserva su Wikipedia
    try:
        wiki_url = f"https://it.wikipedia.org/w/api.php?action=query&format=json&prop=pageimages&pithumbsize=400&titles={urllib.parse.quote_plus(titolo.strip())}"
        wiki_resp = requests.get(wiki_url, timeout=3, headers=headers)
        if wiki_resp.status_code == 200:
            pagine = wiki_resp.json().get('query', {}).get('pages', {})
            for pid, pdata in pagine.items():
                if 'thumbnail' in pdata and 'source' in pdata['thumbnail']:
                    src = pdata['thumbnail']['source']
                    img_resp = requests.get(src, timeout=4, headers=headers)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        filename = f"copertina_{elemento_id}_{int(datetime.now().timestamp())}.jpg"
                        file_path = os.path.join(COVERS_DIR, filename)
                        with open(file_path, 'wb') as f:
                            f.write(img_resp.content)
                        return f"/static/covers/{filename}"
    except Exception as e:
        print(f"[Wikipedia] Errore recupero copertina '{titolo}': {e}")

    return fallback_path


# ------------------------------------------------------------------------------
# ROTTE APPLICATIVO
# ------------------------------------------------------------------------------

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

        # Elementi con stato prestito e conteggio appunti
        cursor.execute("""
            SELECT 
                e.*,
                p.id AS prestito_id,
                p.nome_persona AS prestito_persona,
                p.data_prestito AS prestito_data,
                p.data_rientro_prevista AS prestito_rientro_previsto,
                CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END AS in_prestito,
                (SELECT COUNT(*) FROM appunti a WHERE a.elemento_id = e.id) AS num_appunti
            FROM elementi e
            LEFT JOIN prestiti p ON e.id = p.elemento_id AND p.stato = 'In Prestito'
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
    return render_template("acquisizione_ocr.html", data_oggi=date.today().strftime("%d/%m/%Y"))


@app.route("/ocr_upload", methods=["POST"])
def ocr_upload():
    """
    Riceve un'immagine, la valida, ne limita le dimensioni in RAM a massimo 2000px,
    ed esegue l'OCR con rilascio immediato delle risorse grafiche.
    """
    if "foto" not in request.files:
        return jsonify({"success": False, "errore": "Nessuna foto ricevuta."}), 400

    file = request.files["foto"]
    if not file or file.filename == "":
        return jsonify({"success": False, "errore": "File non selezionato."}), 400

    clean_filename = secure_filename(file.filename)
    if not allowed_file(clean_filename):
        return jsonify({"success": False, "errore": "Formato file non supportato. Carica un'immagine JPG, PNG o WEBP."}), 400

    try:
        # Apertura sicura con context manager Pillow
        with Image.open(file.stream) as img:
            # Correzione orientamento EXIF se presente
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # Ottimizzazione RAM & OCR: ridimensiona se supera i 2400px sul lato lungo
            # (Risoluzione ideale per Tesseract OCR ~300 DPI, prevenendo saturazione memoria)
            max_lato = 2400
            if max(img.size) > max_lato:
                img.thumbnail((max_lato, max_lato), Image.Resampling.LANCZOS)

            # Salvataggio copia per la copertina con nome sicuro
            estensione = clean_filename.rsplit(".", 1)[1].lower()
            if estensione == "jpeg":
                estensione = "jpg"
            filename = f"foto_acquisita_{int(datetime.now().timestamp())}.{estensione}"
            save_path = os.path.join(COVERS_DIR, filename)

            rgb_img = img.convert("RGB")
            rgb_img.save(save_path, "JPEG", quality=85, optimize=True)

            # Pre-elaborazione ottimizzata OCR: scala di grigi e contrasto
            gray = rgb_img.convert("L")
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)

            # Esecuzione Tesseract
            try:
                testo_raw = pytesseract.image_to_string(enhanced, lang="ita")
            except Exception as e_lang:
                print(f"[OCR Warning] Lingua 'ita' non attiva, fallback a default: {e_lang}")
                testo_raw = pytesseract.image_to_string(enhanced)

            # Rilascio esplicito delle risorse grafiche dalla memoria
            del enhanced, enhancer, gray, rgb_img

        # Pulizia righe estratte
        linee_raw = testo_raw.splitlines()
        linee = [r.strip() for r in linee_raw if r.strip() and len(r.strip()) >= 2]

        return jsonify({
            "success": True,
            "linee": linee,
            "anteprima_url": f"/static/covers/{filename}",
            "filename": filename,
            "totale_linee": len(linee)
        })

    except Exception as e:
        print(f"[OCR Upload Error] {e}")
        return jsonify({"success": False, "errore": f"Errore durante l'elaborazione dell'immagine: {str(e)}"}), 500


@app.route("/api/elementi", methods=["POST"])
def crea_elemento():
    tipo = request.form.get("tipo", "Libro").strip()
    titolo = request.form.get("titolo", "").strip()
    autore = request.form.get("autore", "").strip()
    collocazione_casa = request.form.get("collocazione_casa", "").strip()
    note = request.form.get("note", "").strip()

    regista = request.form.get("regista", "").strip()
    prima_esibizione_luogo = request.form.get("prima_esibizione_luogo", "").strip()
    data_ingaggio = request.form.get("data_ingaggio", "").strip()
    data_prima = request.form.get("data_prima", "").strip()

    formato = request.form.get("formato", "").strip()
    etichetta_anno = request.form.get("etichetta_anno", "").strip()

    copertina_caricata = request.form.get("copertina_caricata", "").strip()

    if not titolo:
        flash("Attenzione: devi inserire almeno il titolo!", "errore")
        return redirect(url_for("index"))

    data_inserimento = date.today().strftime("%d/%m/%Y")
    
    if tipo == 'Copione':
        fallback_path = "/static/covers/default_copione.svg"
    elif tipo == 'CD / Vinile':
        fallback_path = "/static/covers/default_musica.svg"
    else:
        fallback_path = "/static/covers/default_libro.svg"

    # Validazione sicura contro Path Traversal sul percorso copertina
    percorso_copertina = fallback_path
    if copertina_caricata:
        nome_file_sicuro = secure_filename(os.path.basename(copertina_caricata))
        if os.path.exists(os.path.join(COVERS_DIR, nome_file_sicuro)):
            percorso_copertina = f"/static/covers/{nome_file_sicuro}"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO elementi (
                tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                regista, prima_esibizione_luogo, data_ingaggio, data_prima,
                formato, etichetta_anno
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tipo, titolo, autore, collocazione_casa, note, percorso_copertina, data_inserimento,
            regista if tipo == 'Copione' else None,
            prima_esibizione_luogo if tipo == 'Copione' else None,
            data_ingaggio if tipo == 'Copione' else None,
            data_prima if tipo == 'Copione' else None,
            formato if tipo == 'CD / Vinile' else None,
            etichetta_anno if tipo == 'CD / Vinile' else None
        ))
        nuovo_id = cursor.lastrowid

    # Recupero copertina online senza trattenere il lock sul database
    if percorso_copertina == fallback_path:
        copertina_recuperata = scarica_copertina_web(titolo, autore, tipo, nuovo_id)
        if copertina_recuperata != fallback_path:
            with get_db() as conn:
                conn.cursor().execute("UPDATE elementi SET copertina_path = ? WHERE id = ?", (copertina_recuperata, nuovo_id))

    flash(f"'{titolo}' è stato inserito con successo nell'Archivio!", "successo")
    return redirect(url_for("index"))


@app.route("/api/elementi/<int:elem_id>/modifica", methods=["POST"])
def modifica_elemento(elem_id):
    titolo = request.form.get("titolo", "").strip()
    autore = request.form.get("autore", "").strip()
    collocazione_casa = request.form.get("collocazione_casa", "").strip()
    note = request.form.get("note", "").strip()
    regista = request.form.get("regista", "").strip()
    prima_esibizione_luogo = request.form.get("prima_esibizione_luogo", "").strip()
    data_ingaggio = request.form.get("data_ingaggio", "").strip()
    data_prima = request.form.get("data_prima", "").strip()
    formato = request.form.get("formato", "").strip()
    etichetta_anno = request.form.get("etichetta_anno", "").strip()

    if not titolo:
        flash("Il titolo non può essere vuoto!", "errore")
        return redirect(url_for("index"))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE elementi
            SET titolo = ?, autore = ?, collocazione_casa = ?, note = ?,
                regista = ?, prima_esibizione_luogo = ?, data_ingaggio = ?, data_prima = ?,
                formato = ?, etichetta_anno = ?
            WHERE id = ?
        """, (titolo, autore, collocazione_casa, note, regista, prima_esibizione_luogo, data_ingaggio, data_prima, formato, etichetta_anno, elem_id))

    flash(f"Le modifiche a '{titolo}' sono state salvate!", "successo")
    return redirect(url_for("index"))


@app.route("/api/elementi/<int:elem_id>/elimina", methods=["POST"])
def elimina_elemento(elem_id):
    copertina = None
    titolo = ""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT titolo, copertina_path FROM elementi WHERE id = ?", (elem_id,))
        row = cursor.fetchone()
        if row:
            titolo = row['titolo']
            copertina = row['copertina_path']
            cursor.execute("DELETE FROM elementi WHERE id = ?", (elem_id,))

    # Rimuovi file locale in sicurezza se non SVG
    if copertina and not copertina.endswith(".svg"):
        safe_cover_name = secure_filename(os.path.basename(copertina))
        local_cover = os.path.join(COVERS_DIR, safe_cover_name)
        if os.path.exists(local_cover):
            try:
                os.remove(local_cover)
            except Exception:
                pass

    if titolo:
        flash(f"'{titolo}' è stato rimosso dall'archivio.", "info")
    return redirect(url_for("index"))


@app.route("/api/elementi/<int:elem_id>/aggiorna_copertina", methods=["POST"])
def aggiorna_copertina(elem_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT titolo, autore, tipo FROM elementi WHERE id = ?", (elem_id,))
        row = cursor.fetchone()

    if row:
        nuova_copertina = scarica_copertina_web(row['titolo'], row['autore'], row['tipo'], elem_id)
        with get_db() as conn:
            conn.cursor().execute("UPDATE elementi SET copertina_path = ? WHERE id = ?", (nuova_copertina, elem_id))
        flash(f"Copertina aggiornata per '{row['titolo']}'!", "successo")
    return redirect(url_for("index"))


@app.route("/api/prestiti", methods=["POST"])
def registra_prestito():
    elemento_id = request.form.get("elemento_id")
    nome_persona = request.form.get("nome_persona", "").strip()
    data_prestito = request.form.get("data_prestito", "").strip() or date.today().strftime("%d/%m/%Y")
    data_rientro_prevista = request.form.get("data_rientro_prevista", "").strip()

    if not elemento_id or not nome_persona:
        flash("Inserisci il nome della persona a cui presti il volume!", "errore")
        return redirect(url_for("index"))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM prestiti WHERE elemento_id = ? AND stato = 'In Prestito'", (elemento_id,))
        if cursor.fetchone():
            flash("Questo volume risulta già attualmente in prestito!", "errore")
            return redirect(url_for("index"))

        cursor.execute("""
            INSERT INTO prestiti (elemento_id, nome_persona, data_prestito, data_rientro_prevista, stato)
            VALUES (?, ?, ?, ?, 'In Prestito')
        """, (elemento_id, nome_persona, data_prestito, data_rientro_prevista))

        cursor.execute("SELECT titolo FROM elementi WHERE id = ?", (elemento_id,))
        elem = cursor.fetchone()
        titolo = elem['titolo'] if elem else "Volume"

    flash(f"Prestito registrato: '{titolo}' è stato prestato a {nome_persona}.", "successo")
    return redirect(url_for("index"))


@app.route("/api/prestiti/<int:prestito_id>/rientro", methods=["POST"])
def segna_rientro(prestito_id):
    data_oggi = date.today().strftime("%d/%m/%Y")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE prestiti
            SET stato = 'Rientrato', data_rientro_effettiva = ?
            WHERE id = ? AND stato = 'In Prestito'
        """, (data_oggi, prestito_id))

        cursor.execute("""
            SELECT e.titolo, p.nome_persona 
            FROM prestiti p
            JOIN elementi e ON p.elemento_id = e.id
            WHERE p.id = ?
        """, (prestito_id,))
        row = cursor.fetchone()

    if row:
        flash(f"Bentornato! '{row['titolo']}' prestato a {row['nome_persona']} è ora di nuovo a casa.", "successo")
    else:
        flash("Il prestito è stato contrassegnato come rientrato.", "successo")

    return redirect(url_for("index"))


@app.route("/api/elementi/<int:elem_id>/dettagli", methods=["GET"])
def dettagli_elemento(elem_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM elementi WHERE id = ?", (elem_id,))
        elem = cursor.fetchone()
        if not elem:
            return jsonify({"errore": "Elemento non trovato"}), 404

        cursor.execute("""
            SELECT nome_persona, data_prestito, data_rientro_prevista, data_rientro_effettiva, stato
            FROM prestiti
            WHERE elemento_id = ?
            ORDER BY id DESC
        """, (elem_id,))
        storico = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT id, testo, data_creazione
            FROM appunti
            WHERE elemento_id = ?
            ORDER BY id DESC
        """, (elem_id,))
        appunti_list = [dict(r) for r in cursor.fetchall()]

    dati = dict(elem)
    dati['storico_prestiti'] = storico
    dati['appunti'] = appunti_list
    return jsonify(dati)


@app.route("/api/elementi/<int:elem_id>/appunti", methods=["POST"])
def aggiungi_appunto(elem_id):
    testo = request.form.get("testo", "").strip()
    if not testo:
        flash("Scrivi un pensiero o una citazione prima di salvare!", "errore")
        return redirect(url_for("index"))

    data_creazione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appunti (elemento_id, testo, data_creazione)
            VALUES (?, ?, ?)
        """, (elem_id, testo, data_creazione))

    flash("Il tuo ricordo è stato annotato con cura nel taccuino!", "successo")
    return redirect(url_for("index"))


@app.route("/api/appunti/<int:appunto_id>/elimina", methods=["POST"])
def elimina_appunto(appunto_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appunti WHERE id = ?", (appunto_id,))

    flash("Appunto rimosso dal taccuino.", "info")
    return redirect(url_for("index"))


@app.route("/api/chiudi", methods=["POST"])
def chiudi_applicazione():
    """Arresto pulito e sicuro dell'applicazione dal pulsante 'Riponi il Taccuino'."""
    def termina():
        import time, signal
        time.sleep(0.6)
        os.kill(os.getpid(), signal.SIGTERM)

    import threading
    threading.Thread(target=termina, daemon=True).start()
    return jsonify({"success": True, "messaggio": "Arrivederci!"})


if __name__ == "__main__":
    init_db()
    # Esecuzione rigorosa su interfaccia locale di loopback e senza debug mode
    app.run(host="127.0.0.1", port=5000, debug=False)
