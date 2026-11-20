#!/usr/bin/env bash
# ==============================================================================
# AGGIORNAMENTO SICURO DA GITHUB — MEMORIE DI SCENA
# ==============================================================================
# Questo è l'UNICO punto che aggiorna il programma. Non usa `git pull` e non
# scarica mai sopra la cartella `data/`: i dati dell'utente sono sacri.
#
# USO
#   ./aggiorna.sh --check              controlla se esiste una nuova versione
#   ./aggiorna.sh --check --notifica   come sopra, ma se c'è una novità chiede
#                                      all'utente (finestra desktop) se aggiornare
#   ./aggiorna.sh --apply              scarica, salva i dati, aggiorna, verifica
#
# COSA FA `--apply`, IN ORDINE
#   1. Rifiuta di girare come amministratore (root) e prende un lucchetto:
#      due aggiornamenti non possono mai sovrapporsi.
#   2. Chiede a GitHub l'ultima versione stabile (Release/Tag). Se non è più
#      nuova di quella installata, non fa nulla.
#   3. Chiude il programma in modo pulito.
#   4. Salva: copia coerente del database (API SQLite), archivio `data/`
#      completo e istantanea dei file di programma.
#   5. Scarica il pacchetto del tag da codeload.github.com, lo estrae in una
#      cartella temporanea e controlla che contenga davvero il programma.
#   6. Copia SOLO i file del programma (mai `data/`, mai le copertine create
#      dall'utente: vengono aggiornati solo gli SVG di riserva).
#   7. Aggiorna le dipendenze, esegue i test e la migrazione del database.
#   8. Riavvia e verifica che il programma risponda. Se qualcosa non va,
#      RIPRISTINA istantanea dei file e database e riavvia la versione vecchia.
#   9. Scrive `data/aggiornamento_stato.json` (lo legge l'interfaccia) e
#      conserva le ultime 5 istantanee.
#
# VARIABILI D'AMBIENTE (per fork o prove)
#   MEMORIE_REPO         proprietario/nome del repository (default sotto)
#   MEMORIE_CANALE       "release" (default) oppure "main"
#   MEMORIE_DATA_DIR     cartella dati alternativa (installazione portatile/test)
#
# PER CHI MODIFICA
#   - Per aggiornare un nuovo file o una nuova cartella di programma, va
#     aggiunto all'elenco `FILE_PROGRAMMA` / `CARTELLE_PROGRAMMA`.
#   - `aggiorna.sh` non copia mai sé stesso mentre è in esecuzione: la nuova
#     copia viene messa da parte e sostituita con una `mv` atomica alla fine.
#   - Non introdurre `rm -rf` su percorsi che contengono la parola data.
# ==============================================================================
set -uo pipefail
# Alcune configurazioni di sistema attivano l'espansione della storia (`!`)
# anche negli script: la disattiviamo, altrimenti i messaggi con «!» falliscono.
set +H

# --- Percorsi -----------------------------------------------------------------
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

REPO="${MEMORIE_REPO:-diego-costanzo/memorie-di-scena}"
CANALE="${MEMORIE_CANALE:-release}"
DATA_DIR="${MEMORIE_DATA_DIR:-$DIR/data}"
DB_PATH="$DATA_DIR/archivio.db"
BACKUP_DIR="$DATA_DIR/backup"
CACHE_DIR="$DATA_DIR/cache"
UPDATES_DIR="$DATA_DIR/updates"
STATO_FILE="$DATA_DIR/aggiornamento_stato.json"
CACHE_FILE="$CACHE_DIR/aggiornamento.json"
INSTALLATO_FILE="$DATA_DIR/aggiornamento_installato.txt"
LOG_FILE="$DATA_DIR/aggiornamenti.log"
LOCK_FILE="$DATA_DIR/.aggiornamento.lock"

PYTHON="$DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
    echo "Python 3 non trovato: impossibile aggiornare."
    exit 1
fi

# File e cartelle che costituiscono il PROGRAMMA (mai i dati dell'utente).
FILE_PROGRAMMA=(
    app.py VERSION requirements.txt
    avvia.sh ferma.sh installa.sh aggiorna.sh
    README.md CHANGELOG.md LICENSE
)
CARTELLE_PROGRAMMA=(archivio templates tests static/css static/js)
SCRIPT_DATI=(data/migra_database.py data/migra.sh)

mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$CACHE_DIR" "$UPDATES_DIR" 2>/dev/null || true

# --- Utility ------------------------------------------------------------------
log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

say() {
    log "$*"
    echo "$*"
}

# Ruota il registro quando supera 1 MB (niente crescita infinita).
if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)" -gt 1048576 ]; then
    mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
fi

scrivi_stato() {
    # scrivi_stato <stato> <messaggio> [versione]
    "$PYTHON" - "$STATO_FILE" "$1" "$2" "${3:-}" <<'PY' 2>/dev/null || true
import datetime, json, os, sys
percorso, stato, messaggio, versione = sys.argv[1:5]
dati = {
    "stato": stato,
    "messaggio": messaggio,
    "versione": versione,
    "aggiornato_il": datetime.datetime.now().strftime("%d/%m/%Y alle %H:%M"),
    "aggiornato_il_ts": int(datetime.datetime.now().timestamp()),
}
os.makedirs(os.path.dirname(percorso), exist_ok=True)
with open(percorso + ".tmp", "w", encoding="utf-8") as f:
    json.dump(dati, f, ensure_ascii=False, indent=2)
os.replace(percorso + ".tmp", percorso)
PY
}

mostra_avviso() {
    local titolo="Memorie di Scena" testo
    # Rende reali le andate a capo scritte come \n nei messaggi.
    testo="$(printf '%b' "$1")"
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v kdialog > /dev/null; then
            kdialog --title "$titolo" --msgbox "$testo" 2>/dev/null && return 0
        elif command -v zenity > /dev/null; then
            zenity --info --title="$titolo" --text="$testo" --width=460 2>/dev/null && return 0
        elif command -v notify-send > /dev/null; then
            notify-send "$titolo" "$testo" 2>/dev/null && return 0
        fi
    fi
    echo "$titolo: $testo"
}

chiedi_conferma() {
    # Restituisce 0 solo se l'utente conferma con un clic.
    local testo
    testo="$(printf '%b' "$1")"
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v kdialog > /dev/null; then
            kdialog --title "Memorie di Scena" --yesno "$testo" 2>/dev/null
            return $?
        elif command -v zenity > /dev/null; then
            zenity --question --title="Memorie di Scena" --text="$testo" --width=460 2>/dev/null
            return $?
        fi
    fi
    return 1
}

leggi_campo() {
    # leggi_campo <json> <campo>
    "$PYTHON" -c 'import json,sys
try:
    print(json.loads(sys.argv[1]).get(sys.argv[2], ""))
except Exception:
    print("")' "$1" "$2" 2>/dev/null
}

# --- Controllo versione -------------------------------------------------------
# Restituisce un JSON con l'esito e aggiorna la cache letta dall'interfaccia.
controlla() {
    "$PYTHON" - "$REPO" "$CANALE" "$DIR" "$DATA_DIR" "$CACHE_FILE" "$INSTALLATO_FILE" <<'PY'
import datetime, json, os, re, sys, urllib.request

repo, canale, base, data_dir, cache_file, installato_file = sys.argv[1:7]

def versione_locale():
    try:
        with open(os.path.join(base, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"

def chiave_versione(valore):
    """Confronta in modo tollerante: 2.10.1 > 2.9.9, con o senza 'v'."""
    parti = re.findall(r"\d+", str(valore).lstrip("vV"))
    return tuple(int(p) for p in parti[:4]) or (0,)

def scarica(url):
    richiesta = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MemorieDiScena-Aggiornamenti",
        },
    )
    with urllib.request.urlopen(richiesta, timeout=8) as risposta:
        return json.load(risposta)

adesso = datetime.datetime.now()
locale = versione_locale()
dati = {
    "versione_locale": locale,
    "versione_remota": locale,
    "tag": "",
    "disponibile": False,
    "note": "",
    "errore": "",
    "canale": canale,
    "controllato_il": adesso.strftime("%d/%m/%Y alle %H:%M"),
    "controllato_il_ts": int(adesso.timestamp()),
}

try:
    if canale == "main":
        info = scarica("https://api.github.com/repos/%s/commits/main" % repo)
        sha = (info.get("sha") or "")[:7]
        tag = "main-" + sha if sha else ""
        installato = ""
        try:
            with open(installato_file, encoding="utf-8") as f:
                installato = f.read().strip()
        except OSError:
            pass
        dati.update({
            "tag": tag,
            "versione_remota": tag or locale,
            "disponibile": bool(sha) and installato != tag,
            "note": "Aggiornamento dal ramo principale.",
        })
    else:
        info = scarica("https://api.github.com/repos/%s/releases/latest" % repo)
        tag = info.get("tag_name") or ""
        remota = tag.lstrip("vV") or locale
        note = (info.get("body") or "").strip()
        if len(note) > 600:
            note = note[:600] + "…"
        dati.update({
            "tag": tag,
            "versione_remota": remota,
            "note": note,
            "disponibile": bool(tag) and chiave_versione(remota) > chiave_versione(locale),
        })
except Exception as errore:
    # Rete assente o repository senza Release: non è un guasto del programma.
    dati["errore"] = str(errore)[:200]
    try:
        with open(cache_file, encoding="utf-8") as f:
            precedente = json.load(f)
        if precedente.get("disponibile"):
            dati.update({
                "disponibile": True,
                "versione_remota": precedente.get("versione_remota", locale),
                "tag": precedente.get("tag", ""),
                "note": precedente.get("note", ""),
            })
    except (OSError, ValueError):
        pass

os.makedirs(os.path.dirname(cache_file), exist_ok=True)
with open(cache_file + ".tmp", "w", encoding="utf-8") as f:
    json.dump(dati, f, ensure_ascii=False, indent=2)
os.replace(cache_file + ".tmp", cache_file)
print(json.dumps(dati, ensure_ascii=False))
PY
}

# --- Operazioni di sistema ----------------------------------------------------
ferma_app() {
    if [ -f "$DIR/ferma.sh" ]; then
        bash "$DIR/ferma.sh" > /dev/null 2>&1 || true
    fi
    pkill -f "$DIR/app.py" > /dev/null 2>&1 || true
    sleep 2
}

avvia_app() {
    # Avvio diretto (senza browser): l'utente sta già guardando la pagina.
    if command -v setsid > /dev/null; then
        PYTHONOPTIMIZE=1 PYTHONUNBUFFERED=1 setsid "$PYTHON" -O "$DIR/app.py" \
            < /dev/null >> "$DATA_DIR/server.log" 2>&1 &
    else
        PYTHONOPTIMIZE=1 PYTHONUNBUFFERED=1 nohup "$PYTHON" -O "$DIR/app.py" \
            < /dev/null >> "$DATA_DIR/server.log" 2>&1 &
    fi
    echo "$!" > "$DATA_DIR/server.pid" 2>/dev/null || true
}

attendi_avvio() {
    local tentativi=0
    while [ "$tentativi" -lt 60 ]; do
        if command -v curl > /dev/null; then
            if curl -s --max-time 1 http://127.0.0.1:5000 2>/dev/null | grep -q "Memorie di Scena"; then
                return 0
            fi
        else
            if "$PYTHON" - <<'PY' > /dev/null 2>&1
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:5000", timeout=1) as r:
        raise SystemExit(0 if b"Memorie di Scena" in r.read(4000) else 1)
except Exception:
    raise SystemExit(1)
PY
            then
                return 0
            fi
        fi
        sleep 0.5
        tentativi=$((tentativi + 1))
    done
    return 1
}

backup_database() {
    [ -f "$DB_PATH" ] || return 0
    local destinazione="$BACKUP_DIR/archivio_pre_update_$(date '+%Y%m%d_%H%M%S').db"
    "$PYTHON" - "$DB_PATH" "$destinazione" <<'PY' || return 1
import sqlite3, sys
origine = sqlite3.connect(sys.argv[1])
destinazione = sqlite3.connect(sys.argv[2])
try:
    origine.backup(destinazione)
finally:
    destinazione.close()
    origine.close()
PY
    echo "$destinazione"
}

backup_dati() {
    local file="$BACKUP_DIR/dati_pre_update_$(date '+%Y%m%d_%H%M%S').tar.gz"
    tar -czf "$file" -C "$DATA_DIR" \
        --exclude=backup --exclude=updates --exclude=.aggiornamento.lock . 2>/dev/null || true
    echo "$file"
}

istantanea_programma() {
    local file="$BACKUP_DIR/programma_pre_update_$(date '+%Y%m%d_%H%M%S').tar.gz"
    tar -czf "$file" -C "$DIR" --ignore-failed-read \
        "${FILE_PROGRAMMA[@]}" "${CARTELLE_PROGRAMMA[@]}" "${SCRIPT_DATI[@]}" \
        static/covers/default_*.svg 2>/dev/null || return 1
    echo "$file"
}

copia_programma() {
    # copia_programma <radice-del-pacchetto>
    local radice="$1" elemento
    local -a cartelle=( "${CARTELLE_PROGRAMMA[@]}" "static/covers" "data" )

    for elemento in "${cartelle[@]}"; do
        mkdir -p "$DIR/$elemento" 2>/dev/null || true
    done

    for elemento in "${FILE_PROGRAMMA[@]}"; do
        # aggiorna.sh viene sostituito alla fine con una mv atomica.
        [ "$elemento" = "aggiorna.sh" ] && continue
        [ -f "$radice/$elemento" ] && cp -a "$radice/$elemento" "$DIR/$elemento"
    done

    for elemento in "${CARTELLE_PROGRAMMA[@]}"; do
        if [ -d "$radice/$elemento" ]; then
            cp -a "$radice/$elemento/." "$DIR/$elemento/"
        fi
    done

    for elemento in "${SCRIPT_DATI[@]}"; do
        if [ -f "$radice/$elemento" ]; then
            mkdir -p "$DIR/$(dirname "$elemento")"
            cp -a "$radice/$elemento" "$DIR/$elemento"
        fi
    done

    # Solo gli SVG di riserva: le copertine dell'utente non vengono toccate.
    for elemento in "$radice"/static/covers/default_*.svg; do
        [ -f "$elemento" ] && cp -a "$elemento" "$DIR/static/covers/"
    done

    if [ -f "$radice/aggiorna.sh" ]; then
        cp -a "$radice/aggiorna.sh" "$DIR/aggiorna.sh.nuovo"
        chmod +x "$DIR/aggiorna.sh.nuovo" 2>/dev/null || true
    fi
}

ruota_istantanee() {
    local modello
    for modello in "programma_pre_update_*.tar.gz" "dati_pre_update_*.tar.gz" "archivio_pre_update_*.db"; do
        # shellcheck disable=SC2012
        ls -1t "$BACKUP_DIR"/$modello 2>/dev/null | tail -n +6 | while read -r vecchio; do
            rm -f "$vecchio"
        done
    done
}

ripristina() {
    # ripristina <istantanea-programma> <backup-database>
    local istantanea="$1" db_backup="$2"
    say "Ripristino della versione precedente..."
    if [ -n "$istantanea" ] && [ -f "$istantanea" ]; then
        tar -xzf "$istantanea" -C "$DIR" 2>/dev/null || true
    fi
    if [ -n "$db_backup" ] && [ -f "$db_backup" ]; then
        rm -f "$DB_PATH-wal" "$DB_PATH-shm" 2>/dev/null || true
        cp -f "$db_backup" "$DB_PATH" 2>/dev/null || true
    fi
    "$PYTHON" -m pip install -r "$DIR/requirements.txt" --quiet --no-warn-script-location \
        > /dev/null 2>&1 || true
    avvia_app
    attendi_avvio || true
}

# --- Applicazione dell'aggiornamento -----------------------------------------
applica() {
    if [ "$(id -u)" -eq 0 ]; then
        say "Rifiuto di aggiornare come amministratore (root): usa l'utente normale."
        exit 1
    fi

    if command -v flock > /dev/null; then
        exec 9> "$LOCK_FILE"
        if ! flock -n 9; then
            say "Un aggiornamento è già in corso."
            exit 0
        fi
    fi

    say "Controllo della versione disponibile..."
    local esito remota tag disponibile
    esito="$(controlla)"
    disponibile="$(leggi_campo "$esito" disponibile)"
    remota="$(leggi_campo "$esito" versione_remota)"
    tag="$(leggi_campo "$esito" tag)"

    if [ "$disponibile" != "True" ] || [ -z "$tag" ]; then
        say "Nessun aggiornamento disponibile."
        scrivi_stato "inattivo" "Nessun aggiornamento disponibile." "$(cat "$DIR/VERSION" 2>/dev/null || echo '')"
        return 0
    fi

    # Il tag finisce dentro un URL e un nome file: solo caratteri sicuri.
    case "$tag" in
        *[!A-Za-z0-9._-]*)
            say "Tag non valido: $tag"
            exit 1
            ;;
    esac

    # Spazio libero minimo (200 MB) per archivio, estrazione e istantanee.
    local liberi
    liberi="$(df -Pk "$DATA_DIR" 2>/dev/null | awk 'NR==2 {print $4}')"
    if [ -n "$liberi" ] && [ "$liberi" -lt 204800 ]; then
        scrivi_stato "errore" "Spazio su disco insufficiente per aggiornare in sicurezza."
        mostra_avviso "Non c'è abbastanza spazio libero per aggiornare in sicurezza. Libera un po' di spazio e riprova."
        return 1
    fi

    say "Aggiornamento da $remota in corso..."
    scrivi_stato "in_corso" "Aggiornamento a $remota in corso. Non chiudere il computer." "$remota"

    local istantanea db_backup archivio_pacchetto staging radice
    local ts
    ts="$(date '+%Y%m%d_%H%M%S')"

    ferma_app
    istantanea="$(istantanea_programma)"
    db_backup="$(backup_database)"
    backup_dati > /dev/null
    if [ -z "$istantanea" ] || [ ! -f "$istantanea" ]; then
        scrivi_stato "errore" "Impossibile creare l'istantanea di sicurezza: aggiornamento annullato."
        avvia_app
        attendi_avvio || true
        return 1
    fi

    archivio_pacchetto="$UPDATES_DIR/pacchetto_${ts}.tar.gz"
    if [ "$CANALE" = "main" ]; then
        url_pacchetto="https://codeload.github.com/$REPO/tar.gz/refs/heads/main"
    else
        url_pacchetto="https://codeload.github.com/$REPO/tar.gz/refs/tags/$tag"
    fi

    say "Scaricamento del pacchetto..."
    if command -v curl > /dev/null; then
        curl -fL --retry 2 --connect-timeout 10 --max-time 300 \
            -o "$archivio_pacchetto" "$url_pacchetto" 2>/dev/null
    else
        "$PYTHON" - "$url_pacchetto" "$archivio_pacchetto" <<'PY'
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=300) as r, open(sys.argv[2], "wb") as f:
    while True:
        blocco = r.read(262144)
        if not blocco:
            break
        f.write(blocco)
PY
    fi

    if [ ! -s "$archivio_pacchetto" ]; then
        say "Scaricamento non riuscito."
        scrivi_stato "errore" "Scaricamento non riuscito. I tuoi dati non sono stati toccati."
        avvia_app
        attendi_avvio || true
        rm -f "$archivio_pacchetto"
        return 1
    fi

    staging="$UPDATES_DIR/staging_${ts}"
    mkdir -p "$staging"
    if ! tar -xzf "$archivio_pacchetto" -C "$staging" --no-same-owner 2>/dev/null; then
        say "Pacchetto non valido."
        scrivi_stato "errore" "Il pacchetto scaricato non è valido. I tuoi dati non sono stati toccati."
        rm -rf "$staging" "$archivio_pacchetto"
        avvia_app
        attendi_avvio || true
        return 1
    fi

    radice="$(find "$staging" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$radice" ] || [ ! -f "$radice/app.py" ] || [ ! -d "$radice/archivio" ]; then
        say "Contenuto del pacchetto inatteso."
        scrivi_stato "errore" "Il pacchetto scaricato non contiene il programma. Nessun dato modificato."
        rm -rf "$staging" "$archivio_pacchetto"
        avvia_app
        attendi_avvio || true
        return 1
    fi

    say "Installazione dei nuovi file di programma..."
    copia_programma "$radice"
    chmod +x "$DIR/avvia.sh" "$DIR/ferma.sh" "$DIR/installa.sh" 2>/dev/null || true

    say "Aggiornamento delle dipendenze..."
    "$PYTHON" -m pip install -r "$DIR/requirements.txt" --quiet --no-warn-script-location \
        --timeout 60 > /dev/null 2>&1 || say "Avviso: alcune dipendenze non sono state aggiornate."

    say "Verifica automatica (test) della nuova versione..."
    local test_log="$DATA_DIR/verifica_aggiornamento.log"
    if ! (cd "$DIR" && "$PYTHON" -m unittest discover -s tests > "$test_log" 2>&1); then
        say "I test della nuova versione non sono passati: annullo l'aggiornamento."
        ripristina "$istantanea" "$db_backup"
        scrivi_stato "errore" "La nuova versione non ha superato i controlli: è stata ripristinata quella precedente. I tuoi dati sono intatti."
        mostra_avviso "L'aggiornamento non ha superato i controlli di sicurezza.\n\nÈ stata ripristinata la versione precedente. I tuoi dati sono intatti."
        rm -rf "$staging" "$archivio_pacchetto"
        return 1
    fi

    say "Aggiornamento dello schema del database..."
    if ! (cd "$DIR" && MEMORIE_DATA_DIR="$DATA_DIR" "$PYTHON" -c \
            "from archivio.db import init_db; init_db()" >> "$LOG_FILE" 2>&1); then
        say "La migrazione del database non è riuscita: ripristino."
        ripristina "$istantanea" "$db_backup"
        scrivi_stato "errore" "Aggiornamento annullato durante la preparazione del database: i dati sono stati ripristinati."
        mostra_avviso "Non è stato possibile preparare il database per la nuova versione.\n\nI tuoi dati sono stati ripristinati e il programma è tornato come prima."
        rm -rf "$staging" "$archivio_pacchetto"
        return 1
    fi

    # Sostituzione atomica dello script di aggiornamento (la copia in esecuzione
    # continua a lavorare sul vecchio file: nessun rischio di corruzione).
    if [ -f "$DIR/aggiorna.sh.nuovo" ]; then
        mv -f "$DIR/aggiorna.sh.nuovo" "$DIR/aggiorna.sh"
        chmod +x "$DIR/aggiorna.sh" 2>/dev/null || true
    fi

    printf '%s\n' "$tag" > "$INSTALLATO_FILE" 2>/dev/null || true

    say "Riavvio del programma..."
    avvia_app
    if ! attendi_avvio; then
        say "Il programma non risponde dopo l'aggiornamento: ripristino."
        ripristina "$istantanea" "$db_backup"
        scrivi_stato "errore" "Il programma non si è riavviato correttamente: è stata ripristinata la versione precedente."
        mostra_avviso "Il programma non si è riavviato dopo l'aggiornamento.\n\nÈ stata automaticamente ripristinata la versione precedente. I tuoi dati sono intatti."
        rm -rf "$staging" "$archivio_pacchetto"
        return 1
    fi

    ruota_istantanee
    rm -rf "$staging" "$archivio_pacchetto"
    scrivi_stato "ok" "Aggiornamento a $remota completato. I tuoi dati sono al sicuro." "$remota"
    say "Aggiornamento completato: ora sei alla versione $remota."
    mostra_avviso "Aggiornamento completato.\n\nOra usi la versione $remota.\nTutti i tuoi libri, copioni e ricordi sono al sicuro."
    return 0
}

# --- Ingresso -----------------------------------------------------------------
MODALITA=""
NOTIFICA=0
for argomento in "$@"; do
    case "$argomento" in
        --check) MODALITA="check" ;;
        --apply) MODALITA="apply" ;;
        --notifica) NOTIFICA=1 ;;
        *)
            echo "Uso: $0 --check [--notifica] | --apply"
            exit 2
            ;;
    esac
done

if [ -z "$MODALITA" ]; then
    echo "Uso: $0 --check [--notifica] | --apply"
    exit 2
fi

if [ "$MODALITA" = "apply" ]; then
    applica
    exit $?
fi

# Modalità controllo
esito="$(controlla)"
disponibile="$(leggi_campo "$esito" disponibile)"
remota="$(leggi_campo "$esito" versione_remota)"
errore="$(leggi_campo "$esito" errore)"

if [ "$disponibile" = "True" ]; then
    log "Nuova versione disponibile: $remota"
    echo "Nuova versione disponibile: $remota"
    if [ "$NOTIFICA" -eq 1 ]; then
        if chiedi_conferma "È disponibile la nuova versione $remota di Memorie di Scena.\n\nPrima di aggiornare viene salvata automaticamente una copia di tutti i tuoi dati.\n\nVuoi aggiornare ora?"; then
            applica
            exit $?
        fi
        mostra_avviso "La nuova versione $remota è pronta.\n\nApri Memorie di Scena e usa il pulsante «Aggiorna ora» quando preferisci."
    fi
else
    log "Nessun aggiornamento disponibile (${errore:-versione $remota})."
    echo "Nessun aggiornamento disponibile."
fi
exit 0
