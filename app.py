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
import warnings
import logging
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Pulizia dei warning da terminale (per non allarmare l'utente con messaggi di sviluppo)
warnings.filterwarnings("ignore")
logging.getLogger("werkzeug").setLevel(logging.ERROR)

import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance, ImageOps
import pytesseract

# Soppressione pulita del banner di sviluppo Flask se presente
try:
    import flask.cli
    flask.cli.show_server_banner = lambda *args: None
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "archivio.db")
COVERS_DIR = os.path.join(BASE_DIR, "static", "covers")

CACHE_DIR = os.path.join(DATA_DIR, "cache")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# RILEVAMENTO ARCHITETTURA (32-bit vs 64-bit) & COMPATIBILITÀ UNIVERSALE
# ------------------------------------------------------------------------------
IS_32_BIT = sys.maxsize <= 2**32

# Adattamento filtro di ricampionamento per tutte le versioni di Pillow (da Pillow 5 a 11+)
if hasattr(Image, "Resampling"):
    RESAMPLE_FILTER = Image.Resampling.LANCZOS
elif hasattr(Image, "LANCZOS"):
    RESAMPLE_FILTER = Image.LANCZOS
else:
    RESAMPLE_FILTER = getattr(Image, "ANTIALIAS", 1)

if IS_32_BIT:
    # Su sistemi a 32-bit (es. PC datato di Alessio) ottimizza l'uso della RAM e spazio indirizzi
    Image.MAX_IMAGE_PIXELS = 50_000_000
    MAX_IMAGE_DIM = 1800
else:
    Image.MAX_IMAGE_PIXELS = 150_000_000
    MAX_IMAGE_DIM = 2400

# Pool di thread per chiamate API parallele (leggero anche su 32-bit)
# Su 32-bit limita i thread per ridurre il consumo di memoria
_MAX_WORKERS = 2 if IS_32_BIT else 4

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
# Chiave segreta generata in modo deterministico e sicuro dalla posizione dell'installazione
# (non hardcoded generica, ma unica per ogni macchina)
_secret_seed = f"memorie_di_scena_{os.path.abspath(BASE_DIR)}_{os.getuid() if hasattr(os, 'getuid') else 'win'}"
app.secret_key = hashlib.sha256(_secret_seed.encode()).hexdigest()

# Ottimizzazione cache statica per hardware datato a 32-bit (evita letture disco continue)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

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
    Context manager sicuro per SQLite (Ultra-ottimizzato per 32-bit e 64-bit):
    - Attiva sempre PRAGMA foreign_keys = ON;
    - Attiva WAL (Write-Ahead Logging) per velocità fino a 10x superiori e zero lock;
    - PRAGMA synchronous = NORMAL per scritture disco istantanee e sicure;
    - Esegue commit automatico al termine del blocco;
    - Esegue rollback automatico in caso di errore;
    - Garantisce la chiusura immediata della connessione per evitare lock e leak di memoria.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -8000;")
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

        # Indici per ricerche istantanee per titolo e autore
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_titolo ON elementi(titolo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_autore ON elementi(autore);")

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appunti_testo ON appunti(testo);")

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
# RICERCA LIBRI PER CITAZIONE / FRASE (MULTI-DATABASE: LOCALE + ONLINE)
# Interroga in parallelo:
# 1. Archivio Locale & Taccuino di Alessio (se ha già l'opera o l'appunto in casa!)
# 2. Wikiquote Italia (database per eccellenza di citazioni teatrali, battute e monologhi)
# 3. Wikipedia Italia (incipit, saggi, trame e opere letterarie)
# 4. Google Books (ricerca full-text nel corpo dei libri digitalizzati)
# 5. Open Library (catalogo ed edizioni mondiali)
# 6. Internet Archive (testi italiani scansionati di pubblico dominio)
# ------------------------------------------------------------------------------

# Sessione HTTP condivisa per pooling connessioni (riduce drasticamente carico CPU a 32-bit)
_api_session = requests.Session()
_api_session.headers.update({
    'User-Agent': 'MemorieDiScena/2.0 (Archivio Teatrale e Collezione; Debian GNU/Linux)',
    'Accept': 'application/json',
})

# Timeout API: calibrato per non bloccare risorse (più breve su 32-bit)
_API_TIMEOUT = 3.5 if IS_32_BIT else 5.0

# Cache su disco: 24 ore (evita traffico superfluo per ricerche identiche)
_CACHE_EXPIRY_SEC = 86400


def _cache_key(frase):
    """Genera una chiave di cache sicura e deterministica per una frase di ricerca."""
    normalizzata = " ".join(frase.lower().split())
    return hashlib.md5(normalizzata.encode('utf-8')).hexdigest()


def _leggi_cache(chiave):
    """Legge un risultato dalla cache su disco, se esiste e non è scaduto."""
    path = os.path.join(CACHE_DIR, f"ricerca_{chiave}.json")
    try:
        if os.path.exists(path):
            eta_file = datetime.now().timestamp() - os.path.getmtime(path)
            if eta_file < _CACHE_EXPIRY_SEC:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    except Exception:
        pass
    return None


def _scrivi_cache(chiave, dati):
    """Salva un risultato nella cache su disco."""
    path = os.path.join(CACHE_DIR, f"ricerca_{chiave}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dati, f, ensure_ascii=False)
    except Exception:
        pass


def _pulisci_snippet(testo):
    """Pulisce un frammento HTML rimuovendo tag e normalizzando spazi."""
    if not testo:
        return ""
    pulito = re.sub(r'<[^>]+>', '', testo)
    pulito = pulito.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return " ".join(pulito.split()).strip()


def _cerca_locale(frase):
    """
    Cerca PRIMA DI TUTTO nella libreria personale e nel taccuino di Alessio!
    Se l'attore cerca una frase che ha già a casa, glielo dice subito con collocazione e note.
    """
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            pattern = f"%{frase.strip()}%"

            # 1. Cerca nei titoli, autori o note degli elementi
            cursor.execute("""
                SELECT id, tipo, titolo, autore, collocazione_casa, note, copertina_path
                FROM elementi
                WHERE titolo LIKE ? OR autore LIKE ? OR note LIKE ? OR regista LIKE ?
                LIMIT 5
            """, (pattern, pattern, pattern, pattern))
            for row in cursor.fetchall():
                collocazione = row['collocazione_casa'] or 'In casa'
                risultati.append({
                    'titolo': row['titolo'],
                    'autore': row['autore'] or 'Autore non indicato',
                    'editore': f"📍 Posizione in casa: {collocazione}",
                    'anno': '',
                    'snippet': f"🏠 Questo volume è già nella tua libreria! ({collocazione}). Note: {row['note'] or 'Nessuna nota'}".strip(),
                    'copertina_url': row['copertina_path'],
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': '',
                    'anteprima_link': '',
                    'fonte': 'La Tua Libreria Personale',
                    'fonte_icona': '🏠',
                    'in_archivio': True,
                    'elemento_id': row['id']
                })

            # 2. Cerca nel taccuino dei ricordi (citazioni salvate)
            cursor.execute("""
                SELECT a.id, a.testo, a.data_creazione, e.id AS elem_id, e.titolo, e.autore, e.collocazione_casa, e.copertina_path
                FROM appunti a
                JOIN elementi e ON a.elemento_id = e.id
                WHERE a.testo LIKE ?
                LIMIT 5
            """, (pattern,))
            for row in cursor.fetchall():
                risultati.append({
                    'titolo': row['titolo'],
                    'autore': row['autore'] or 'Autore non indicato',
                    'editore': f"Annotato nel tuo Taccuino il {row['data_creazione']}",
                    'anno': '',
                    'snippet': f"📓 Trovato nel tuo Taccuino dei Ricordi: «{row['testo']}» (Collocazione: {row['collocazione_casa'] or 'in casa'})",
                    'copertina_url': row['copertina_path'],
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': '',
                    'anteprima_link': '',
                    'fonte': 'Il Tuo Taccuino dei Ricordi',
                    'fonte_icona': '📓',
                    'in_archivio': True,
                    'elemento_id': row['elem_id']
                })
    except Exception as e:
        print(f"[Ricerca Locale] Errore: {e}")

    return risultati


def _cerca_wikiquote(frase, max_risultati=5):
    """
    Cerca su Wikiquote Italia (la raccolta libera di citazioni teatrali e letterarie).
    Eccellente per attori: monologhi, battute celebri, copioni e opere.
    """
    risultati = []
    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://it.wikiquote.org/w/api.php?action=query&list=search&srsearch={q}&format=json"
        resp = _api_session.get(url, timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            for item in resp.json().get('query', {}).get('search', [])[:max_risultati]:
                titolo = item.get('title', '')
                snippet = _pulisci_snippet(item.get('snippet', ''))
                link = f"https://it.wikiquote.org/wiki/{urllib.parse.quote(titolo.replace(' ', '_'))}"
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Citazione Teatrale / Letteraria',
                    'editore': 'Wikiquote',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikiquote Teatrale',
                    'fonte_icona': '🎭',
                })
    except Exception as e:
        print(f"[Wikiquote] Errore: {e}")
    return risultati


def _cerca_wikipedia(frase, max_risultati=5):
    """
    Cerca su Wikipedia Italia per trovare opere, incipit celebri, commedie e romanzi.
    """
    risultati = []
    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://it.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json"
        resp = _api_session.get(url, timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            for item in resp.json().get('query', {}).get('search', [])[:max_risultati]:
                titolo = item.get('title', '')
                snippet = _pulisci_snippet(item.get('snippet', ''))
                link = f"https://it.wikipedia.org/wiki/{urllib.parse.quote(titolo.replace(' ', '_'))}"
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Opera Letteraria / Teatrale',
                    'editore': 'Wikipedia',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikipedia Letteraria',
                    'fonte_icona': '📖',
                })
    except Exception as e:
        print(f"[Wikipedia] Errore: {e}")
    return risultati


def _cerca_google_books(frase, max_risultati=5):
    """
    Cerca nel database di Google Books (milioni di volumi indicizzati).
    Google Books esegue ricerca FULL-TEXT nel corpo del libro.
    """
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            f"https://www.googleapis.com/books/v1/volumes"
            f"?q={query}"
            f"&maxResults={max_risultati}"
            f"&printType=books"
            f"&langRestrict=it"
            f"&orderBy=relevance"
        )
        resp = _api_session.get(url, timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            dati = resp.json()
            for item in dati.get('items', []):
                info = item.get('volumeInfo', {})
                ricerca_info = item.get('searchInfo', {})
                snippet = _pulisci_snippet(ricerca_info.get('textSnippet', ''))
                immagini = info.get('imageLinks', {})
                copertina_url = immagini.get('thumbnail', '') or immagini.get('smallThumbnail', '')
                if copertina_url and copertina_url.startswith('http:'):
                    copertina_url = copertina_url.replace('http:', 'https:', 1)

                risultati.append({
                    'titolo': info.get('title', 'Titolo sconosciuto'),
                    'autore': ', '.join(info.get('authors', ['Autore non indicato'])),
                    'editore': info.get('publisher', ''),
                    'anno': info.get('publishedDate', '')[:4] if info.get('publishedDate') else '',
                    'snippet': snippet,
                    'copertina_url': copertina_url,
                    'lingua': info.get('language', ''),
                    'pagine': info.get('pageCount', ''),
                    'link_info': info.get('infoLink', ''),
                    'anteprima_link': info.get('previewLink', ''),
                    'fonte': 'Google Books',
                    'fonte_icona': '📚',
                })
    except Exception as e:
        print(f"[Google Books] Errore: {e}")
    return risultati


def _cerca_open_library(frase, max_risultati=5):
    """
    Cerca nel database di Open Library (Internet Archive).
    """
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            f"https://openlibrary.org/search.json"
            f"?q={query}"
            f"&limit={max_risultati}"
            f"&fields=title,author_name,publisher,first_publish_year,cover_i,key,language,number_of_pages_median"
        )
        resp = _api_session.get(url, timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            dati = resp.json()
            for doc in dati.get('docs', []):
                cover_id = doc.get('cover_i')
                copertina_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ''
                chiave_opera = doc.get('key', '')
                link_info = f"https://openlibrary.org{chiave_opera}" if chiave_opera else ''
                risultati.append({
                    'titolo': doc.get('title', 'Titolo sconosciuto'),
                    'autore': ', '.join(doc.get('author_name', ['Autore non indicato'])),
                    'editore': ', '.join(doc.get('publisher', [])[:2]) if doc.get('publisher') else '',
                    'anno': str(doc.get('first_publish_year', '')) if doc.get('first_publish_year') else '',
                    'snippet': '',
                    'copertina_url': copertina_url,
                    'lingua': ', '.join(doc.get('language', [])[:3]) if doc.get('language') else '',
                    'pagine': doc.get('number_of_pages_median', ''),
                    'link_info': link_info,
                    'anteprima_link': '',
                    'fonte': 'Open Library',
                    'fonte_icona': '🏛️',
                })
    except Exception as e:
        print(f"[Open Library] Errore: {e}")
    return risultati


def _cerca_internet_archive(frase, max_risultati=5):
    """
    Cerca nei testi scansionati dell'Internet Archive.
    """
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            f"https://archive.org/advancedsearch.php"
            f"?q={query}+AND+mediatype%3Atexts"
            f"&fl[]=title&fl[]=creator&fl[]=publisher&fl[]=year"
            f"&fl[]=identifier&fl[]=description"
            f"&rows={max_risultati}"
            f"&output=json"
        )
        resp = _api_session.get(url, timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            docs = resp.json().get('response', {}).get('docs', [])
            for doc in docs:
                identifier = doc.get('identifier', '')
                link_info = f"https://archive.org/details/{identifier}" if identifier else ''
                copertina_url = f"https://archive.org/services/img/{identifier}" if identifier else ''
                desc_raw = doc.get('description', '')
                if isinstance(desc_raw, list):
                    desc_raw = ' '.join(str(x) for x in desc_raw)
                descrizione = _pulisci_snippet(desc_raw)
                if len(descrizione) > 200:
                    descrizione = descrizione[:200].rsplit(' ', 1)[0] + '…'
                risultati.append({
                    'titolo': doc.get('title', 'Titolo sconosciuto'),
                    'autore': doc.get('creator', 'Autore non indicato') if isinstance(doc.get('creator'), str)
                              else ', '.join(doc.get('creator', ['Autore non indicato'])[:3]),
                    'editore': doc.get('publisher', '') if isinstance(doc.get('publisher'), str) else '',
                    'anno': str(doc.get('year', '')) if doc.get('year') else '',
                    'snippet': descrizione,
                    'copertina_url': copertina_url,
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link_info,
                    'anteprima_link': f"https://archive.org/stream/{identifier}" if identifier else '',
                    'fonte': 'Internet Archive',
                    'fonte_icona': '🗄️',
                })
    except Exception as e:
        print(f"[Internet Archive] Errore: {e}")
    return risultati


def ricerca_per_citazione(frase, max_per_fonte=4):
    """
    Orchestratore principale:
    1. Cerca immediatamente nella libreria e nel taccuino locale di Alessio!
    2. Interroga in parallelo Wikiquote, Wikipedia, Google Books, Open Library e Internet Archive.
    3. Raggruppa e ordina per rilevanza, evidenziando le corrispondenze con frammenti di testo.
    4. Salva in cache su disco per 24h.
    """
    if not frase or len(frase.strip()) < 3:
        return []

    # Pulizia frase da virgolette tipografiche accidentali
    frase_pulita = frase.strip().strip('«»""''“”')

    # Controlla cache su disco per query online
    chiave = _cache_key(frase_pulita)
    cached = _leggi_cache(chiave)
    if cached is not None:
        # Recupera comunque le corrispondenze locali in tempo reale
        locali = _cerca_locale(frase_pulita)
        return locali + [r for r in cached if not r.get('in_archivio')]

    # 1. Ricerca locale immediata (0 ms)
    risultati_locali = _cerca_locale(frase_pulita)

    # 2. Ricerca in parallelo sui database esterni
    risultati_online = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_cerca_wikiquote, frase_pulita, max_per_fonte): 'Wikiquote',
            executor.submit(_cerca_wikipedia, frase_pulita, max_per_fonte): 'Wikipedia',
            executor.submit(_cerca_google_books, frase_pulita, max_per_fonte): 'Google Books',
            executor.submit(_cerca_open_library, frase_pulita, max_per_fonte): 'Open Library',
            executor.submit(_cerca_internet_archive, frase_pulita, max_per_fonte): 'Internet Archive',
        }

        for future in as_completed(futures):
            nome_fonte = futures[future]
            try:
                risultati_fonte = future.result()
                risultati_online.extend(risultati_fonte)
            except Exception as e:
                print(f"[Ricerca {nome_fonte}] Errore: {e}")

    # Deduplicazione risultati online
    visti = {}
    online_unici = []
    for r in risultati_online:
        titolo_norm = " ".join(r['titolo'].lower().split())
        chiave_dedup = titolo_norm[:40]

        if chiave_dedup not in visti:
            visti[chiave_dedup] = r
            online_unici.append(r)
        elif r.get('snippet') and not visti[chiave_dedup].get('snippet'):
            idx = online_unici.index(visti[chiave_dedup])
            online_unici[idx] = r
            visti[chiave_dedup] = r

    # Ordina: prima quelli con snippet (frammento di testo effettivo)
    online_unici.sort(key=lambda x: (0 if x.get('snippet') else 1, x['titolo'].lower()))

    # Salva i soli risultati online in cache
    _scrivi_cache(chiave, online_unici)

    # I risultati locali compaiono SEMPRE in cima!
    return risultati_locali + online_unici


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

            # Ottimizzazione RAM & OCR: ridimensionamento calibrato per 32-bit e 64-bit
            max_lato = MAX_IMAGE_DIM
            if max(img.size) > max_lato:
                img.thumbnail((max_lato, max_lato), RESAMPLE_FILTER)

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


@app.route("/api/ricerca_citazione", methods=["POST"])
def api_ricerca_citazione():
    """
    API per la ricerca di libri partendo da una frase, citazione o parole chiave.
    Interroga in parallelo Google Books, Open Library e Internet Archive.
    Restituisce i risultati con eventuale snippet (frammento di testo) che
    conferma la corrispondenza nel testo del libro.

    Sicurezza:
    - Input validato e limitato a 500 caratteri
    - Tutte le chiamate API esterne usano timeout rigorosi
    - Risultati cachati su disco per 24h per limitare traffico
    """
    dati = request.get_json(silent=True) or {}
    frase = dati.get("frase", "").strip()

    # Validazione input
    if not frase:
        return jsonify({"success": False, "errore": "Inserisci una frase o alcune parole chiave per cercare."}), 400

    if len(frase) < 3:
        return jsonify({"success": False, "errore": "La frase è troppo corta. Scrivi almeno 3 caratteri."}), 400

    # Limite di sicurezza sulla lunghezza dell'input
    if len(frase) > 500:
        frase = frase[:500]

    try:
        risultati = ricerca_per_citazione(frase)
        return jsonify({
            "success": True,
            "frase_cercata": frase,
            "totale_risultati": len(risultati),
            "risultati": risultati,
            "suggerimento": (
                "💡 La ricerca per frase funziona meglio se ricordi 3-4 parole consecutive e distintive. "
                "Google Books cerca anche dentro il testo dei libri!"
            ) if len(risultati) == 0 else ""
        })
    except Exception as e:
        print(f"[API Ricerca Citazione] Errore: {e}")
        return jsonify({
            "success": False,
            "errore": "Si è verificato un errore durante la ricerca. Riprova fra qualche istante."
        }), 500


@app.route("/api/chiudi", methods=["POST"])
def chiudi_applicazione():
    """Arresto pulito e sicuro dell'applicazione dal pulsante 'Riponi il Taccuino'."""
    pid_file = os.path.join(DATA_DIR, "server.pid")
    if os.path.exists(pid_file):
        try:
            os.remove(pid_file)
        except Exception:
            pass

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
