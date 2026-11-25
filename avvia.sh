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
# 2. CONTROLLO SERVER E AVVIO IN BACKGROUND (ACCELERATO)
# ------------------------------------------------------------------------------
# Verifichiamo l'IDENTITÀ del servizio, non solo che la porta risponda: un
# altro programma sulla 5000 veniva in passato scambiato per l'archivio.
if curl -s --connect-timeout 0.15 --max-time 1 "$APP_URL" 2>/dev/null | grep -q "Memorie di Scena"; then
    echo "ℹ️  Memorie di Scena è già attivo su $APP_URL"
elif curl -s --connect-timeout 0.15 --max-time 1 "$APP_URL" > /dev/null 2>&1; then
    echo "=================================================================="
    echo "⚠️  La porta 5000 è occupata da un altro programma."
    echo "    Chiudi quel programma oppure riavvia il computer, poi riprova."
    echo "=================================================================="
    exit 1
else
    echo "🎭 Avvio rapido di Memorie di Scena in corso..."
    # Avvia in background con bytecode ottimizzato (-O / PYTHONOPTIMIZE=1) per massima reattività e leggerezza RAM
    if command -v setsid &> /dev/null; then
        PYTHONOPTIMIZE=1 PYTHONUNBUFFERED=1 setsid "$PYTHON_BIN" -O "$APP_PY" </dev/null >> "$LOG_FILE" 2>&1 &
    else
        PYTHONOPTIMIZE=1 PYTHONUNBUFFERED=1 nohup "$PYTHON_BIN" -O "$APP_PY" </dev/null >> "$LOG_FILE" 2>&1 &
    fi
    SERVER_PID=$!
    disown "$SERVER_PID" 2>/dev/null || true
    echo "$SERVER_PID" > "$PID_FILE"

    # Attesa reattiva ad alta frequenza (polling a 40ms per apertura fulminea del browser appena il server è pronto)
    TENTATIVI=0
    SERVER_PRONTO=0
    while [ "$TENTATIVI" -lt 60 ]; do
        if curl -s --connect-timeout 0.05 --max-time 1 "$APP_URL" 2>/dev/null | grep -q "Memorie di Scena"; then
            SERVER_PRONTO=1
            break
        fi
        sleep 0.04
        TENTATIVI=$((TENTATIVI + 1))
    done

    if [ "$SERVER_PRONTO" -ne 1 ]; then
        echo "⚠️ Attenzione: il server sta impiegando più tempo del previsto ad avviarsi."
    fi
fi

# ------------------------------------------------------------------------------
# 3. APERTURA AUTOMATICA NEL BROWSER PREDEFINITO (MASSIMA VELOCITÀ)
# ------------------------------------------------------------------------------
apri_browser() {
    local url="$1"

    # 1. Se è presente Chromium o Google Chrome (modalità app nativa, esclude sincronizzazioni lente di rete)
    if command -v chromium &> /dev/null; then
        nohup chromium --start-maximized --app="$url" --no-first-run --no-default-browser-check --disable-background-networking --disable-sync </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    elif command -v google-chrome &> /dev/null; then
        nohup google-chrome --start-maximized --app="$url" --no-first-run --no-default-browser-check --disable-background-networking --disable-sync </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    # 2. Se è presente Firefox ESR (predefinito Debian) o Firefox standard
    elif command -v firefox-esr &> /dev/null; then
        nohup firefox-esr "$url" </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    elif command -v firefox &> /dev/null; then
        nohup firefox "$url" </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    # 3. Fallback universale Freedesktop (xdg-open) o Konqueror (Q4OS / TDE)
    elif command -v xdg-open &> /dev/null; then
        nohup xdg-open "$url" </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    elif command -v konqueror &> /dev/null; then
        nohup konqueror "$url" </dev/null &> /dev/null &
        disown 2>/dev/null || true
        return 0
    # 4. Fallback Python webbrowser
    else
        nohup "$PYTHON_BIN" -m webbrowser "$url" </dev/null &> /dev/null &
        disown 2>/dev/null || true
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
