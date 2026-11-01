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
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null || true
        rm -f "$PID_FILE"
        echo "✅ Memorie di Scena è stato riposto con cura (arrestato)."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# Fallback: cerca processi app.py
pkill -f "$DIR/app.py" 2>/dev/null || true
echo "✅ Memorie di Scena è a riposo."
exit 0

