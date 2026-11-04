#!/usr/bin/env bash
# ==============================================================================
# SCRIPT PER CREARE IL PACCHETTO DI AGGIORNAMENTO AUTOMATICO
# Genera uno ZIP con installatore intelligente che:
# 1. Trova automaticamente la cartella dell'applicazione nei Documenti
# 2. Salva una copia di sicurezza del database esistente
# 3. Aggiorna solo i file di programma
# 4. Aggiorna l'icona sul Desktop togliendo il terminale
# 5. Avvia direttamente il programma aggiornato
# Zero spostamenti manuali, zero terminale.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

NOME_ZIP="Aggiornamento_MemorieDiScena.zip"
TMP_DIR="/tmp/pacchetto_aggiornamento_memorie_di_scena"

rm -rf "$TMP_DIR" "$DIR/$NOME_ZIP"
mkdir -p "$TMP_DIR"

echo "📦 Preparazione pacchetto di aggiornamento sicuro..."

# 1. Copia i file aggiornati del programma (MAI il database)
cp "$DIR/app.py" "$TMP_DIR/"
cp "$DIR/avvia.sh" "$TMP_DIR/"
cp "$DIR/ferma.sh" "$TMP_DIR/"
cp "$DIR/installa.sh" "$TMP_DIR/"
cp "$DIR/requirements.txt" "$TMP_DIR/"
cp -r "$DIR/templates" "$TMP_DIR/"
cp -r "$DIR/static" "$TMP_DIR/"
mkdir -p "$TMP_DIR/data"
cp "$DIR/data/migra_database.py" "$TMP_DIR/data/"
cp "$DIR/data/migra.sh" "$TMP_DIR/data/"

# 2. Crea lo script di aggiornamento intelligente AGGIORNA.sh
cat << 'EOF' > "$TMP_DIR/AGGIORNA.sh"
#!/usr/bin/env bash
# ==============================================================================
# AGGIORNAMENTO AUTOMATICO TRASPARENTE - MEMORIE DI SCENA
# ==============================================================================

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Funzione per mostrare messaggi a schermo (supporta KDE/Q4OS kdialog, Zenity o notifiche)
mostra_avviso() {
    local titolo="$1"
    local testo="$2"
    if command -v kdialog &> /dev/null; then
        kdialog --title "$titolo" --msgbox "$testo" 2>/dev/null || true
    elif command -v zenity &> /dev/null; then
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
    if command -v kdialog &> /dev/null; then
        kdialog --title "$titolo" --error "$testo" 2>/dev/null || true
    elif command -v zenity &> /dev/null; then
        zenity --error --title="$titolo" --text="$testo" --width=450 2>/dev/null || true
    else
        echo "ERRORE: $testo"
    fi
}

# 1. Ricerca automatica della cartella di installazione
DEST_DIR=""
POSSIBILI_PERCORSI=(
    "$HOME/Documenti/MemorieDiScena"
    "$HOME/Documenti/memorie-di-scena"
    "$HOME/Documenti/ArchivioLibri"
    "$HOME/Documenti/Sardelli"
    "$HOME/Documents/MemorieDiScena"
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
    TROVATA=$(find "$HOME" -maxdepth 4 -type d \( -name "MemorieDiScena" -o -name "memorie-di-scena" -o -name "Sardelli" -o -name "ArchivioLibri" \) 2>/dev/null | head -n 1)
    if [ -n "$TROVATA" ] && [ -f "$TROVATA/app.py" ]; then
        DEST_DIR="$TROVATA"
    fi
fi

if [ -z "$DEST_DIR" ]; then
    mostra_errore "Memorie di Scena" "Non sono riuscito a trovare la cartella di Memorie di Scena nei Documenti.\n\nVerifica che la cartella del programma sia presente."
    exit 1
fi

# 2. Chiudi l'applicazione se era aperta
if [ -f "$DEST_DIR/ferma.sh" ]; then
    bash "$DEST_DIR/ferma.sh" > /dev/null 2>&1 || true
    sleep 1
else
    pkill -f "$DEST_DIR/app.py" > /dev/null 2>&1 || true
fi

# 3. SALVAGUARDIA DEI DATI ESISTENTI: Backup del database
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
mkdir -p "$DEST_DIR/data"
cp "$SOURCE_DIR/data/migra_database.py" "$DEST_DIR/data/"
cp "$SOURCE_DIR/data/migra.sh" "$DEST_DIR/data/"

chmod +x "$DEST_DIR/avvia.sh" "$DEST_DIR/ferma.sh" "$DEST_DIR/installa.sh" "$DEST_DIR/data/migra.sh" "$DEST_DIR/data/migra_database.py"

# 5. Aggiorna l'icona sul desktop impostando l'avvio invisibile (senza terminale)
if [ -x "$DEST_DIR/installa.sh" ]; then
    (cd "$DEST_DIR" && bash ./installa.sh --solo-icone > /dev/null 2>&1)
fi

# 6. Avvia l'applicazione aggiornata
(cd "$DEST_DIR" && bash ./avvia.sh > /dev/null 2>&1 &)

# 7. Conferma a video
mostra_avviso "Memorie di Scena" "🎭 Aggiornamento completato con successo!\n\nTutti i tuoi libri, copioni e ricordi sono al sicuro.\nLa Bussola Culturale e il nuovo Diario dei Pensieri su pergamena sono pronti all'uso!"

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
Exec=/bin/bash -c "K=\"%k\"; K=\"\${K#file://}\"; D=\"\$(dirname \"\$K\")\"; if [ -f \"\$D/AGGIORNA.sh\" ]; then bash \"\$D/AGGIORNA.sh\"; elif [ -f \"./AGGIORNA.sh\" ]; then bash \"./AGGIORNA.sh\"; else (kdialog --title \"Memorie di Scena\" --error \"Attenzione: devi prima ESTRARRE la cartella zip!\\n\\nFai clic col tasto DESTRO sul file zip e scegli 'Estrai qui'.\" 2>/dev/null || zenity --error --title \"Memorie di Scena\" --text \"Attenzione: devi prima ESTRARRE la cartella zip!\\n\\nFai clic col tasto DESTRO sul file zip e scegli 'Estrai qui'.\" 2>/dev/null || true); fi"
Icon=system-software-update
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

chmod +x "$TMP_DIR/CLICCA_QUI_PER_AGGIORNARE.desktop"

# 4. Crea un file di istruzioni chiarissimo a caratteri grandi
cat << 'EOF' > "$TMP_DIR/ISTRUZIONI_SEMPLICI.txt"
==================================================================
        🎭 AGGIORNAMENTO DI MEMORIE DI SCENA
==================================================================

Ciao!

Per aggiornare il tuo Archivio Teatrale con la nuova ricerca per
citazione e togliere la finestra nera del terminale:

PASSO 1: ESTRAI LO ZIP
Fai clic con il TASTO DESTRO sul file "Aggiornamento_MemorieDiScena.zip"
e scegli "Estrai qui" (oppure clicca sul pulsante "Estrai" in alto).

PASSO 2: AVVIA L'AGGIORNAMENTO
Entra nella cartella estratta e:
👉 Fai semplicemente doppio clic su: "1. CLICCA QUI PER AGGIORNARE"
   (Se ti compare una finestrella con scritto cosa fare, premi "Esegui").

👉 In alternativa: fai clic col TASTO DESTRO su "AGGIORNA.sh"
   e scegli "Esegui come programma" (oppure "Esegui").

👉 SE PER SBAGLIO SI APRE UNA FINESTRA DI TESTO CON CODICE:
   Non ti preoccupare: chiudila con la 'X' in alto a destra,
   poi fai clic con il TASTO DESTRO su "AGGIORNA.sh" e scegli "Esegui".

NON DEVI SPOSTARE NESSUN FILE A MANO.
Il programma farà tutto da solo in pochi secondi:
1. Troverà automaticamente la cartella dell'archivio nei Documenti.
2. Salverà una copia di sicurezza di tutti i tuoi dati e libri.
3. Aggiornerà il programma.
4. Creerà l'icona sul Desktop per avviarlo d'ora in avanti senza terminale.
5. Aprirà direttamente l'archivio pronto all'uso!

Buona consultazione del tuo archivio teatrale!
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
echo "🛡️ Zero spostamenti manuali per l'utente."
echo "🛡️ Rilevamento automatico della cartella di installazione."
echo "🛡️ Backup del database prima di qualsiasi operazione."
echo "------------------------------------------------------------------"
