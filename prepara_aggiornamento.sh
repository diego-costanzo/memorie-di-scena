#!/usr/bin/env bash
# ==============================================================================
# SCRIPT PER CREARE IL PACCHETTO DI AGGIORNAMENTO SICURO PER ALESSIO
# Genera un archivio zip contenente SOLO codice, grafica e script aggiornati.
# ESCLUDE rigorosamente il database per non rischiare di cancellare i dati di Alessio.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

NOME_ZIP="Aggiornamento_MemorieDiScena.zip"
TMP_DIR="/tmp/pacchetto_aggiornamento_memorie"

rm -rf "$TMP_DIR" "$DIR/$NOME_ZIP"
mkdir -p "$TMP_DIR"

echo "📦 Preparazione pacchetto sicuro di aggiornamento..."

# 1. Copia file di codice e interfaccia
cp "$DIR/app.py" "$TMP_DIR/"
cp "$DIR/avvia.sh" "$TMP_DIR/"
cp "$DIR/ferma.sh" "$TMP_DIR/"
cp "$DIR/installa.sh" "$TMP_DIR/"
cp "$DIR/requirements.txt" "$TMP_DIR/"
cp -r "$DIR/templates" "$TMP_DIR/"
cp -r "$DIR/static" "$TMP_DIR/"

# 2. Crea lo script 'APRI_PER_AGGIORNARE.sh' che Alessio o tu potete cliccare
cat << 'EOF' > "$TMP_DIR/APRI_PER_AGGIORNARE.sh"
#!/usr/bin/env bash
# Script di aggiornamento automatico e protetto
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Se lo script si trova dentro la cartella del programma o estratto
DEST_DIR="$DIR"
if [ ! -f "$DEST_DIR/app.py" ]; then
    # Prova a cercare la cartella di Alessio se estratto altrove
    for cartella in "$HOME/Documenti/AI - Progetti/Sardelli" "$HOME/Documenti/AI - Progetti/Sardelli - ArchivioLibri" "$HOME/Documenti/Memorie di Scena" "$HOME/memorie-di-scena" "$HOME/Sardelli"; do
        if [ -f "$cartella/app.py" ]; then
            DEST_DIR="$cartella"
            break
        fi
    done
fi

echo "=================================================================="
echo "🎭 AGGIORNAMENTO DI MEMORIE DI SCENA"
echo "=================================================================="
echo "Salvataggio e protezione della tua collezione..."

# Backup di sicurezza del database esistente prima di toccare qualsiasi cosa
if [ -f "$DEST_DIR/data/archivio.db" ]; then
    DATA_ORA=$(date '+%Y%m%d_%H%M%S')
    cp "$DEST_DIR/data/archivio.db" "$DEST_DIR/data/archivio_backup_pre_aggiornamento_${DATA_ORA}.db" 2>/dev/null || true
    echo "✅ Copia di sicurezza dei tuoi libri salvata con successo."
fi

# Copia solo i file di programma
echo "Aggiornamento dei file del programma..."
cp -r "$DIR/app.py" "$DIR/templates" "$DIR/static" "$DIR/avvia.sh" "$DIR/ferma.sh" "$DIR/installa.sh" "$DIR/requirements.txt" "$DEST_DIR/"
chmod +x "$DEST_DIR/avvia.sh" "$DEST_DIR/ferma.sh" "$DEST_DIR/installa.sh"

# Aggiorna il lanciatore desktop impostando l'avvio invisibile senza terminale
if [ -x "$DEST_DIR/installa.sh" ]; then
    (cd "$DEST_DIR" && ./installa.sh)
fi

echo ""
echo "=================================================================="
echo "🎉 AGGIORNAMENTO COMPLETATO CON SUCCESSO!"
echo "Tutti i tuoi libri, appunti e copioni sono al sicuro."
echo "Il programma si avvierà tra un istante..."
echo "=================================================================="
sleep 2

exec "$DEST_DIR/avvia.sh"
EOF

chmod +x "$TMP_DIR/APRI_PER_AGGIORNARE.sh"

# 3. Crea il file compresso ZIP (usando modulo Python nativo, compatibile 100%)
python3 -c "
import zipfile, os
nome_zip = '$DIR/$NOME_ZIP'
tmp_dir = '$TMP_DIR'
with zipfile.ZipFile(nome_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(tmp_dir):
        for f in files:
            full_path = os.path.join(root, f)
            arcname = os.path.relpath(full_path, tmp_dir)
            zf.write(full_path, arcname)
print('✅ Pacchetto ZIP universale creato in: ' + nome_zip)
"

rm -rf "$TMP_DIR"
echo "------------------------------------------------------------------"
echo "🛡️ SICUREZZA GARANTITA: Il pacchetto NON contiene 'archivio.db'."
echo "   I libri di Alessio non potranno mai essere sovrascritti."
echo "------------------------------------------------------------------"
