#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI AVVIO VELOCE E SILENZIOSO - MEMORIE DI SCENA
# Archivio Teatrale e Collezione Personale
# - Esegue in background senza necessità di tenere aperto il terminale.
# - Verifica se l'app è già attiva per non duplicare processi.
# - Apre automaticamente il browser predefinito a tutto schermo.
# - Arresto pulito tramite il tasto 'Riponi il Taccuino' nell'interfaccia
#   oppure tramite lo script ./ferma.sh.
# ==============================================================================

set -e

# Risoluzione robusta del percorso assoluto della cartella dello script
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$DIR"

# ------------------------------------------------------------------------------
# 1. CONTROLLO PRELIMINARE DELL'AMBIENTE VIRTUALE
# ------------------------------------------------------------------------------
if [ ! -d "$DIR/venv" ] || [ ! -f "$DIR/venv/bin/python" ]; then
    echo "=================================================================="
    echo "❌ ERRORE: Ambiente non installato!"
    echo "------------------------------------------------------------------"
    echo "L'ambiente virtuale Python necessario non è presente in:"
    echo "  $DIR/venv"
    echo ""
    echo "👉 Per configurare automaticamente l'archivio, esegui prima:"
    echo "   ./installa.sh"
    echo "=================================================================="
    exit 1
fi

PYTHON_BIN="$DIR/venv/bin/python"
APP_PY="$DIR/app.py"
APP_URL="http://127.0.0.1:5000"
PID_FILE="$DIR/data/server.pid"
LOG_FILE="$DIR/data/server.log"

mkdir -p "$DIR/data"

# ------------------------------------------------------------------------------
# 2. CONTROLLO SERVER E AVVIO IN BACKGROUND
# ------------------------------------------------------------------------------
if curl -s -m 1 "$APP_URL" > /dev/null 2>&1; then
    echo "ℹ️  Memorie di Scena è già attivo su $APP_URL"
else
    echo "🎭 Avvio di Memorie di Scena in corso..."
    # Avvia in background disaccoppiato dal terminale (nohup + disown)
    nohup "$PYTHON_BIN" "$APP_PY" >> "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    disown "$SERVER_PID" 2>/dev/null || true
    echo "$SERVER_PID" > "$PID_FILE"

    # Attesa rapida disponibilità server (fino a 25 tentativi da 0.2s = 5s max)
    TENTATIVI=0
    SERVER_PRONTO=0
    while [ "$TENTATIVI" -lt 25 ]; do
        if curl -s -m 1 "$APP_URL" > /dev/null 2>&1; then
            SERVER_PRONTO=1
            break
        fi
        sleep 0.2
        TENTATIVI=$((TENTATIVI + 1))
    done

    if [ "$SERVER_PRONTO" -ne 1 ]; then
        echo "⚠️ Attenzione: il server sta impiegando più tempo del previsto ad avviarsi."
    fi
fi

# ------------------------------------------------------------------------------
# 3. APERTURA AUTOMATICA NEL BROWSER PREDEFINITO
# ------------------------------------------------------------------------------
apri_browser() {
    local url="$1"

    # 1. Se è presente Chromium o Google Chrome (supporta modalità app massimizzata)
    if command -v chromium &> /dev/null; then
        chromium --start-maximized --app="$url" &> /dev/null &
        return 0
    elif command -v google-chrome &> /dev/null; then
        google-chrome --start-maximized --app="$url" &> /dev/null &
        return 0
    # 2. Se è presente Firefox ESR (predefinito Debian) o Firefox standard
    elif command -v firefox-esr &> /dev/null; then
        firefox-esr "$url" &> /dev/null &
        return 0
    elif command -v firefox &> /dev/null; then
        firefox "$url" &> /dev/null &
        return 0
    # 3. Fallback universale Freedesktop (xdg-open)
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$url" &> /dev/null &
        return 0
    # 4. Fallback Python webbrowser
    else
        "$PYTHON_BIN" -m webbrowser "$url" &> /dev/null &
        return 0
    fi
}

apri_browser "$APP_URL"

echo "------------------------------------------------------------------"
echo "✅ MEMORIE DI SCENA È ATTIVO!"
echo "🌐 Indirizzo locale: $APP_URL"
echo "📕 Per chiudere: clicca 'Riponi il Taccuino' nell'app oppure esegui ./ferma.sh"
echo "------------------------------------------------------------------"
echo "💡 Il terminale può essere chiuso tranquillamente: l'app rimane attiva."
exit 0
