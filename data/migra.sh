#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI AVVIO MIGRAZIONE DATI - MEMORIE DI SCENA
# Permette di importare i dati da un database precedente (.db) al nuovo archivio.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$DIR/.." && pwd)"

PYTHON_BIN="python3"
if [ -f "$BASE_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$BASE_DIR/venv/bin/python"
fi

"$PYTHON_BIN" "$DIR/migra_database.py" "$@"
