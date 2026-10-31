#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI BACKUP SU GITHUB - MEMORIE DI SCENA
# Esegue il backup incrementale del database, copertine e codice su GitHub
# ==============================================================================

set -e

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$DIR"

echo "=================================================================="
echo "   💾 BACKUP MEMORIE DI SCENA SU GITHUB"
echo "=================================================================="
echo ""

# Verifica se il remote è configurato
if ! git remote get-url origin &> /dev/null; then
    echo "❌ Errore: Nessun repository remoto configurato."
    exit 1
fi

echo "🔍 Controllo modifiche all'archivio (database, note, copertine)..."
git add .

if git diff --staged --quiet; then
    echo "✅ Nessuna nuova modifica da salvare. L'archivio è già allineato con l'ultimo backup."
else
    DATA_ORA="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "📦 Salvataggio modifiche: Backup del $DATA_ORA..."
    git commit -m "backup: Aggiornamento archivio del $DATA_ORA"
    
    echo "🚀 Invio al repository privato GitHub..."
    if git push origin main; then
        echo ""
        echo "=================================================================="
        echo "🎉 BACKUP COMPLETATO CON SUCCESSO SU GITHUB!"
        echo "=================================================================="
    else
        echo "⚠️ Errore durante l'invio su GitHub. Verifica la connessione Internet."
        exit 1
    fi
fi
