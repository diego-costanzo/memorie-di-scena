#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI AVVIO QUOTIDIANO - MEMORIE DI SCENA
# Archivio Teatrale e Collezione Personale
# Risolve percorsi assoluti, verifica l'ambiente, avvia l'app locale e
# apre automaticamente il browser predefinito a tutto schermo.
# Gestione sicura dei segnali per terminazione pulita (SIGTERM).
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

echo "=================================================================="
echo "   🎭 MEMORIE DI SCENA"
echo "   Archivio Teatrale, Biblioteca e Collezione Personale"
echo "=================================================================="
echo ""
echo "Caricamento dell'applicazione in corso..."

# ------------------------------------------------------------------------------
# 2. CONTROLLO SERVER E GESTIONE PROCESSO FLASK
# ------------------------------------------------------------------------------
SERVER_PID=""
if curl -s -m 1 "$APP_URL" > /dev/null 2>&1; then
    echo "L'archivio è già in esecuzione su $APP_URL"
else
    # Avvia l'app in background
    "$PYTHON_BIN" "$APP_PY" &
    SERVER_PID=$!

    # Gestione pulita e sicura del segnale di arresto (SIGTERM)
    cleanup() {
        # Disarma i trap per prevenire chiamate ricorsive su EXIT
        trap - SIGINT SIGTERM SIGHUP EXIT
        echo ""
        echo "Chiusura di Memorie di Scena in corso..."
        if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
            kill -TERM "$SERVER_PID" 2>/dev/null || true
            wait "$SERVER_PID" 2>/dev/null || true
        fi
        echo "Arrivederci!"
        exit 0
    }
    trap cleanup SIGINT SIGTERM SIGHUP EXIT

    # Attesa che il server Flask risponda (massimo 30 tentativi da 0.5s)
    TENTATIVI=0
    MASSIMO_TENTATIVI=30
    SERVER_PRONTO=0

    while [ "$TENTATIVI" -lt "$MASSIMO_TENTATIVI" ]; do
        if curl -s -m 1 "$APP_URL" > /dev/null 2>&1; then
            SERVER_PRONTO=1
            break
        fi
        sleep 0.5
        TENTATIVI=$((TENTATIVI + 1))
    done

    if [ "$SERVER_PRONTO" -ne 1 ]; then
        echo "Attenzione: il server sta impiegando più tempo del previsto ad avviarsi."
    fi
fi

echo ""
echo "------------------------------------------------------------------"
echo "✅ MEMORIE DI SCENA È PRONTO!"
echo "Indirizzo locale: $APP_URL"
echo "Apertura automatica della libreria a schermo intero..."
echo "------------------------------------------------------------------"
echo "💡 NOTA: Per chiudere l'archivio, premi [CTRL] + [C] in questa finestra."
echo ""

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
    # 2. Se è presente Firefox: avvia in modalità Kiosk (senza barre, URL né schede)
    elif command -v firefox &> /dev/null; then
        firefox --kiosk "$url" &> /dev/null &
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

# Se abbiamo avviato noi il server Flask, attendiamo che termini o riceva il segnale di chiusura
if [ -n "$SERVER_PID" ]; then
    wait "$SERVER_PID"
fi
