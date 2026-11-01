#!/usr/bin/env bash
# ==============================================================================
# SCRIPT PER CREARE IL PACCHETTO DI AGGIORNAMENTO AUTOMATICO PER ALESSIO
# Genera uno ZIP con installatore intelligente che:
# 1. Trova automaticamente la cartella Documenti/Sardelli
# 2. Salva una copia di sicurezza del database esistente
# 3. Aggiorna solo i file di programma
# 4. Aggiorna l'icona sul Desktop togliendo il terminale
# 5. Avvia direttamente il programma aggiornato
# Zero spostamenti manuali, zero terminale per Alessio.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

NOME_ZIP="Aggiornamento_MemorieDiScena.zip"
TMP_DIR="/tmp/pacchetto_aggiornamento_alessio"

rm -rf "$TMP_DIR" "$DIR/$NOME_ZIP"
mkdir -p "$TMP_DIR"

echo "📦 Preparazione pacchetto sicuro per Alessio..."

# 1. Copia i file aggiornati del programma (MAI il database)
cp "$DIR/app.py" "$TMP_DIR/"
cp "$DIR/avvia.sh" "$TMP_DIR/"
cp "$DIR/ferma.sh" "$TMP_DIR/"
cp "$DIR/installa.sh" "$TMP_DIR/"
cp "$DIR/requirements.txt" "$TMP_DIR/"
cp -r "$DIR/templates" "$TMP_DIR/"
cp -r "$DIR/static" "$TMP_DIR/"

# 2. Crea lo script di aggiornamento intelligente AGGIORNA.sh
cat << 'EOF' > "$TMP_DIR/AGGIORNA.sh"
#!/usr/bin/env bash
# ==============================================================================
# AGGIORNAMENTO AUTOMATICO TRASPARENTE - MEMORIE DI SCENA
# ==============================================================================

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Funzione per mostrare messaggi a schermo (con finestra o notifica)
mostra_avviso() {
    local titolo="$1"
    local testo="$2"
    if command -v zenity &> /dev/null; then
        zenity --info --title="$titolo" --text="$testo" --width=450 --timeout=8 2>/dev/null || true
    elif command -v notify-send &> /dev/null; then
        notify-send "$titolo" "$testo" 2>/dev/null || true
    else
        echo "$titolo: $testo"
    fi
}

mostra_errore() {
    local titolo="$1"
    local testo="$2"
    if command -v zenity &> /dev/null; then
        zenity --error --title="$titolo" --text="$testo" --width=450 2>/dev/null || true
    else
        echo "ERRORE: $testo"
    fi
}

# 1. Ricerca automatica della cartella di Alessio (Sardelli in Documenti)
DEST_DIR=""
POSSIBILI_PERCORSI=(
    "$HOME/Documenti/Sardelli"
    "$HOME/Documents/Sardelli"
    "$HOME/Documenti/AI - Progetti/Sardelli"
    "$HOME/Documenti/AI - Progetti/Sardelli - ArchivioLibri"
    "$HOME/Sardelli"
    "$HOME/memorie-di-scena"
)

for p in "${POSSIBILI_PERCORSI[@]}"; do
    if [ -d "$p" ] && [ -f "$p/app.py" ]; then
        DEST_DIR="$p"
        break
    fi
done

# Se non trovata nei percorsi standard, cerca con find
if [ -z "$DEST_DIR" ]; then
    TROVATA=$(find "$HOME" -maxdepth 4 -type d -name "Sardelli" 2>/dev/null | head -n 1)
    if [ -n "$TROVATA" ] && [ -f "$TROVATA/app.py" ]; then
        DEST_DIR="$TROVATA"
    fi
fi

if [ -z "$DEST_DIR" ]; then
    mostra_errore "Memorie di Scena" "Non sono riuscito a trovare la cartella 'Sardelli' nei Documenti.\n\nContatta Diego per verificare la posizione della cartella."
    exit 1
fi

# 2. Chiudi l'applicazione se era aperta
if [ -f "$DEST_DIR/ferma.sh" ]; then
    bash "$DEST_DIR/ferma.sh" > /dev/null 2>&1 || true
    sleep 1
else
    pkill -f "$DEST_DIR/app.py" > /dev/null 2>&1 || true
fi

# 3. SALVAGUARDIA DEI DATI DI ALESSIO: Backup del database
mkdir -p "$DEST_DIR/data"
if [ -f "$DEST_DIR/data/archivio.db" ]; then
    DATA_ORA=$(date '+%Y%m%d_%H%M%S')
    BACKUP_FILE="$DEST_DIR/data/archivio_backup_pre_aggiornamento_${DATA_ORA}.db"
    cp "$DEST_DIR/data/archivio.db" "$BACKUP_FILE"
fi

# 4. Copia dei file aggiornati (senza mai toccare il database esistente!)
cp "$SOURCE_DIR/app.py" "$DEST_DIR/"
cp "$SOURCE_DIR/avvia.sh" "$DEST_DIR/"
cp "$SOURCE_DIR/ferma.sh" "$DEST_DIR/"
cp "$SOURCE_DIR/installa.sh" "$DEST_DIR/"
cp "$SOURCE_DIR/requirements.txt" "$DEST_DIR/"
cp -r "$SOURCE_DIR/templates" "$DEST_DIR/"
cp -r "$SOURCE_DIR/static" "$DEST_DIR/"

chmod +x "$DEST_DIR/avvia.sh" "$DEST_DIR/ferma.sh" "$DEST_DIR/installa.sh"

# 5. Aggiorna l'icona sul desktop impostando l'avvio invisibile (senza terminale)
if [ -x "$DEST_DIR/installa.sh" ]; then
    (cd "$DEST_DIR" && bash ./installa.sh --solo-icone > /dev/null 2>&1)
fi

# 6. Avvia l'applicazione aggiornata
(cd "$DEST_DIR" && bash ./avvia.sh > /dev/null 2>&1 &)

# 7. Conferma a video per Alessio
mostra_avviso "Memorie di Scena" "🎭 Aggiornamento completato con successo!\n\nTutti i tuoi libri, copioni e ricordi sono al sicuro.\nLa nuova ricerca per citazione è attiva e da adesso l'app si avvia direttamente senza finestra del terminale."

exit 0
EOF

chmod +x "$TMP_DIR/AGGIORNA.sh"

# 3. Crea il lanciatore grafico con icona 'CLICCA_QUI_PER_AGGIORNARE.desktop'
cat << 'EOF' > "$TMP_DIR/CLICCA_QUI_PER_AGGIORNARE.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=1. CLICCA QUI PER AGGIORNARE
Comment=Aggiorna automaticamente Memorie di Scena salvando tutti i tuoi libri
Exec=/bin/bash -c "DIR=\"\$(cd \"\$(dirname \"%k\")\" && pwd)\"; bash \"\$DIR/AGGIORNA.sh\""
Icon=system-software-update
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

chmod +x "$TMP_DIR/CLICCA_QUI_PER_AGGIORNARE.desktop"

# 4. Crea un file di istruzioni chiarissimo a caratteri grandi per Alessio
cat << 'EOF' > "$TMP_DIR/ISTRUZIONI_SEMPLICI.txt"
==================================================================
        🎭 AGGIORNAMENTO DI MEMORIE DI SCENA
==================================================================

Ciao Alessio!

Per aggiornare il tuo Archivio Teatrale con la nuova ricerca per
citazione e togliere la finestra nera del terminale:

👉 METODO 1 (CON IL MOUSE - NESSUN TERMINALE):
   1. Fai clic con il TASTO DESTRO del mouse sul file "AGGIORNA.sh".
   2. Nel menu a tendina che compare, clicca su "Esegui come programma"
      (oppure su "Esegui").
   3. Fatto! Comparirà una finestrella di conferma e si aprirà l'app.

👉 SE PER SBAGLIO HAI FATTO DOPPIO CLIC SINISTRO:
   Se si è aperta una finestra di testo con delle scritte di codice,
   non ti preoccupare: chiudila con la 'X' in alto a destra,
   poi fai clic con il TASTO DESTRO su "AGGIORNA.sh" e scegli "Esegui come programma".

👉 METODO 2 (SE IL TASTO DESTRO NON MOSTRA "ESEGUI"):
   1. Fai clic con il TASTO DESTRO in un punto vuoto (bianco) della cartella.
   2. Clicca su "Apri nel terminale".
   3. Scrivi semplicemente:  ./AGGIORNA.sh   e premi INVIO.

NON DEVI SPOSTARE NESSUN FILE A MANO.
Il programma farà tutto da solo:
1. Troverà la tua cartella in Documenti/Sardelli.
2. Salverà una copia di sicurezza di tutti i tuoi libri.
3. Aggiornerà il programma.
4. Creerà l'icona sul Desktop per avviarlo d'ora in avanti senza terminale.
5. Aprirà direttamente l'archivio pronto all'uso!

Per qualsiasi cosa, Diego è sempre a disposizione.
==================================================================
EOF

# 5. Comprimi in ZIP usando modulo Python nativo
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
print('✅ Pacchetto ZIP generato con successo: ' + nome_zip)
"

rm -rf "$TMP_DIR"
echo "------------------------------------------------------------------"
echo "🛡️ Zero spostamenti manuali per Alessio."
echo "🛡️ Trova Documenti/Sardelli in automatico."
echo "🛡️ Backup del database prima di qualsiasi operazione."
echo "------------------------------------------------------------------"
