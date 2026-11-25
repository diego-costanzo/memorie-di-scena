#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI ARRESTO - MEMORIE DI SCENA
# Chiude in sicurezza il server locale dell'Archivio
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$DIR/data/server.pid"

echo "📕 Chiusura di Memorie di Scena in corso..."

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
        CMD_PID=$(ps -p "$PID" -o args= 2>/dev/null || true)
        if [[ "$CMD_PID" == *"app.py"* ]]; then
            kill -TERM "$PID" 2>/dev/null || true
            rm -f "$PID_FILE"
            echo "✅ Memorie di Scena è stato riposto con cura (arrestato)."
            exit 0
        fi
    fi
    rm -f "$PID_FILE"
fi

# Fallback sicuro: cerca solo processi Python con percorso esatto di app.py (niente regex pkill -f).
while IFS= read -r riga; do
    pid="${riga%% *}"
    cmd="${riga#* }"
    if [[ "$pid" =~ ^[0-9]+$ ]] && [[ "$cmd" == *"$DIR/app.py"* ]] && [[ "${cmd,,}" == *python* ]]; then
        kill -TERM "$pid" 2>/dev/null || true
    fi
done < <(ps -u "$(id -u)" -o pid=,args= 2>/dev/null | sed 's/^[[:space:]]*//')
echo "✅ Memorie di Scena è a riposo."
exit 0

