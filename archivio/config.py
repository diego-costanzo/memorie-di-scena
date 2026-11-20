# -*- coding: utf-8 -*-
"""
Configurazione centralizzata dell'applicazione.

Tutti i percorsi e le costanti vivono in un unico punto: modificare qui
influenza l'intera applicazione senza dover cercare valori sparsi nel codice.
Nessun altro modulo deve contenere percorsi assoluti o numeri "magici".

COSE DA SAPERE PRIMA DI MODIFICARE
----------------------------------
- `MEMORIE_DATA_DIR` (variabile d'ambiente) sposta database, cache e backup.
  È il meccanismo con cui i test restano isolati e con cui si può fare
  un'installazione "portatile" su chiavetta. Va letta solo qui.
- `IS_32_BIT` regola limiti di memoria e numero di thread: il programma deve
  restare usabile su computer poco potenti, quindi i valori sono volutamente bassi.
- I parametri OCR sono calibrati con prove reali: cambiarli cambia precisione
  e tempi di attesa. Le soglie principali sono commentate una per una.
- Le costanti sono lette all'import: dopo una modifica serve riavviare.
"""
import os
import shutil
import sys
import warnings
import logging

# Silenziamo solo i warning benigni e rumorosi (file temporanei non chiusi):
# evitiamo il filtro globale perché nasconderebbe anche errori reali e i
# DeprecationWarning che segnalano rischi futuri delle dipendenze.
warnings.filterwarnings("ignore", category=ResourceWarning)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# Radice del progetto: la cartella che contiene il pacchetto "archivio".
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# La cartella dati è sovrascrivibile tramite variabile d'ambiente: fondamentale per
# i test (che usano un database temporaneo isolato) e per installazioni portabili.
DATA_DIR = os.environ.get("MEMORIE_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "archivio.db")
COVERS_DIR = os.path.join(BASE_DIR, "static", "covers")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ------------------------------------------------------------------------------
# VERSIONE E AGGIORNAMENTI
# ------------------------------------------------------------------------------
# La versione vive in un file di testo alla radice: è l'unico valore che
# `aggiorna.sh` confronta con GitHub e che l'interfaccia mostra all'utente.
VERSION_FILE = os.path.join(BASE_DIR, "VERSION")


def versione_locale():
    """Restituisce la versione installata (es. «2.0.0»)."""
    try:
        with open(VERSION_FILE, encoding="utf-8") as file_versione:
            return file_versione.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


# Script unico che controlla e applica gli aggiornamenti in modo sicuro.
UPDATE_SCRIPT = os.path.join(BASE_DIR, "aggiorna.sh")
# Stato leggibile dall'interfaccia durante/dopo un aggiornamento (scritto da aggiorna.sh).
UPDATE_STATE_PATH = os.path.join(DATA_DIR, "aggiornamento_stato.json")
# Esito dell'ultimo controllo (cache: evita una chiamata a GitHub a ogni pagina).
UPDATE_CACHE_PATH = os.path.join(CACHE_DIR, "aggiornamento.json")

# ------------------------------------------------------------------------------
# RILEVAMENTO ARCHITETTURA (32-bit vs 64-bit) & AVVIO FULMINEO (LAZY LOADING)
# ------------------------------------------------------------------------------
IS_32_BIT = sys.maxsize <= 2**32
MAX_IMAGE_DIM = 1800 if IS_32_BIT else 2400

# ------------------------------------------------------------------------------
# OCR: parametri del motore di lettura da fotografia
# ------------------------------------------------------------------------------
# Lato minimo: sotto questa soglia l'immagine viene ingrandita, perché Tesseract
# lavora meglio su caratteri alti almeno 30-40 pixel.
OCR_UPSCALE_MIN = 1000
# Risoluzione dichiarata a Tesseract: evita la stima automatica (più lenta e instabile).
OCR_DPI = 300
# Confidenza minima (0-100) perché una riga venga mostrata all'utente.
OCR_MIN_LINE_CONF = 45
# Se la prima passata raggiunge questa confidenza media, le altre vengono saltate
# (risparmio di tempo sui computer più lenti).
OCR_GOOD_CONF = 82
# Tempo massimo per singola passata OCR (secondi): nessun blocco del server.
OCR_TIMEOUT = 30
# Lingue riconosciute, in ordine di preferenza. Si usano solo quelle
# effettivamente installate nel sistema: se un dizionario manca, viene ignorato
# senza errori (fallback silenzioso ma sicuro).
# italiano per i testi di casa, inglese per titoli e citazioni, francese e
# latino per i classici, tedesco e spagnolo per le edizioni straniere.
OCR_LINGUE_PREFERITE = ("ita", "eng", "fra", "lat", "deu", "spa")
# Se la lettura in italiano resta sotto questa confidenza, si tenta una sola
# seconda passata con tutte le lingue disponibili: risolve i titoli stranieri
# senza rallentare il caso normale (che è quasi sempre italiano).
OCR_RETRY_CONF = 68

# Pool di thread per chiamate API parallele (I/O bound, leggero anche su 32-bit)
MAX_WORKERS = 6 if IS_32_BIT else 12

# Timeout API: calibrato per non bloccare risorse (più breve su 32-bit)
API_TIMEOUT = 3.5 if IS_32_BIT else 5.0

# Cache su disco: 24 ore (evita traffico superfluo per ricerche identiche)
CACHE_EXPIRY_SEC = 86400

# Numero di backup del database conservati a rotazione
BACKUP_KEEP = 7

# Limite di upload (32 MB accoglie comodamente scatti ad alta risoluzione)
MAX_CONTENT_LENGTH = 32 * 1024 * 1024
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "jfif"}

# Migrazione di sicurezza: se archivio.db risiede nella root, spostalo in data/archivio.db
ROOT_OLD_DB = os.path.join(BASE_DIR, "archivio.db")


def allowed_file(filename):
    """Verifica che l'estensione sia tra quelle strettamente consentite."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def migra_db_legacy():
    """
    Migrazione di sicurezza (una tantum): se esiste un archivio.db nella radice
    del progetto e non è ancora presente in data/, lo sposta in modo atomico.
    """
    if os.path.exists(ROOT_OLD_DB) and not os.path.exists(DB_PATH):
        shutil.move(ROOT_OLD_DB, DB_PATH)
