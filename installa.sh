#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DI INSTALLAZIONE E CONFIGURAZIONE INIZIALE - MEMORIE DI SCENA
# Archivio Teatrale e Collezione Personale
# Idempotente: se l'ambiente è già installato, avvia direttamente l'applicazione.
# Su nuovo sistema:
# - Verifica e installa i pacchetti di sistema apt (Debian/Ubuntu)
# - Configura l'ambiente virtuale venv e pip
# - Registra l'applicazione nel menu di sistema di Debian e sul Desktop
# - Imposta i permessi di esecuzione
# ==============================================================================

set -e

# Risoluzione robusta del percorso assoluto della cartella di progetto
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$DIR"

# Funzione per registrare/aggiornare i lanciatori desktop di Debian e Scrivania
installa_lanciatori_desktop() {
    local target_dirs=()

    # 1. Menu di sistema Debian/XDG standard
    local menu_dir="$HOME/.local/share/applications"
    mkdir -p "$menu_dir" 2>/dev/null || true
    target_dirs+=("$menu_dir")

    # 2. Scrivania / Desktop (con rilevamento lingua di sistema)
    if command -v xdg-user-dir &> /dev/null; then
        local xdg_desk
        xdg_desk="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
        if [ -n "$xdg_desk" ] && [ -d "$xdg_desk" ]; then
            target_dirs+=("$xdg_desk")
        fi
    fi

    if [ -d "$HOME/Scrivania" ]; then
        target_dirs+=("$HOME/Scrivania")
    fi

    if [ -d "$HOME/Desktop" ]; then
        target_dirs+=("$HOME/Desktop")
    fi

    local desktop_content="[Desktop Entry]
Version=1.0
Type=Application
Name=Memorie di Scena
GenericName=Archivio Teatrale e Collezione
Comment=Memorie di Scena - Archivio Teatrale, Biblioteca e Collezione Personale
Exec=/bin/bash \"$DIR/avvia.sh\"
Path=$DIR
Icon=accessories-dictionary
Terminal=false
Categories=Office;Database;
StartupNotify=true"

    # Deduplicazione sicura delle cartelle gestendo spazi nei nomi
    declare -A viste_dirs
    for d in "${target_dirs[@]}"; do
        if [ -n "$d" ] && [ -d "$d" ] && [ -z "${viste_dirs["$d"]}" ]; then
            viste_dirs["$d"]=1
            # Rimuove l'eventuale lanciatore precedente per pulizia
            rm -f "$d/archivio-sardelli.desktop" 2>/dev/null || true
            local desktop_path="$d/memorie-di-scena.desktop"
            printf "%s\n" "$desktop_content" > "$desktop_path"
            chmod +x "$desktop_path"
            if command -v gio &> /dev/null; then
                gio set "$desktop_path" metadata::trusted true 2>/dev/null || true
            fi
        fi
    done
}

# Controllo settimanale degli aggiornamenti tramite timer dell'utente.
# NON installa nulla da solo: mostra un avviso e, se l'utente accetta, avvia
# l'aggiornamento protetto (backup + verifica + ripristino automatico).
installa_timer_aggiornamenti() {
    command -v systemctl &> /dev/null || return 0
    # Solo sessioni grafiche con systemd utente: altrimenti nessun timer.
    systemctl --user show-environment &> /dev/null || return 0

    local unit_dir="$HOME/.config/systemd/user"
    mkdir -p "$unit_dir" 2>/dev/null || return 0

    cat > "$unit_dir/memorie-aggiornamenti.service" <<EOF
[Unit]
Description=Memorie di Scena - controllo aggiornamenti
After=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash "$DIR/aggiorna.sh" --check --notifica
EOF

    cat > "$unit_dir/memorie-aggiornamenti.timer" <<'EOF'
[Unit]
Description=Memorie di Scena - controllo settimanale degli aggiornamenti

[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
EOF

    systemctl --user daemon-reload &> /dev/null || true
    systemctl --user enable --now memorie-aggiornamenti.timer &> /dev/null || true
}

# ------------------------------------------------------------------------------
# CONTROLLO IDEMPOTENZA: Se l'ambiente è già pronto, avvia subito l'app!
# ------------------------------------------------------------------------------
if [ -x "$DIR/venv/bin/python" ] && "$DIR/venv/bin/python" -c "import flask, requests, PIL, pytesseract" &> /dev/null; then
    # Assicura che i lanciatori siano registrati e aggiornati
    installa_lanciatori_desktop
    chmod +x "$DIR/installa.sh" "$DIR/avvia.sh"
    if [ "$1" = "--solo-icone" ]; then
        exit 0
    fi
    echo "=================================================================="
    echo "   🎭 MEMORIE DI SCENA"
    echo "=================================================================="
    echo "Archivio già configurato. Avvio in corso..."
    echo ""
    exec "$DIR/avvia.sh"
fi

# ------------------------------------------------------------------------------
# PRIMA INSTALLAZIONE (Ambiente non ancora configurato)
# ------------------------------------------------------------------------------
ARCH="$(uname -m)"
echo "=================================================================="
echo "   🏛️ INSTALLAZIONE E CONFIGURAZIONE - MEMORIE DI SCENA"
echo "   Configurazione automatica e protetta per Debian / Ubuntu"
echo "   Architettura rilevata: $ARCH"
echo "=================================================================="
if [[ "$ARCH" =~ ^i[3-6]86$ ]]; then
    echo "ℹ️  Rilevato sistema Linux a 32 bit ($ARCH)."
    echo "    Attivazione profilo di compatibilità estesa Debian i386."
fi
echo ""

# 1. Verifica pacchetti apt nativi (include moduli precompilati a 32-bit e 64-bit)
echo "🔍 1. Controllo pacchetti di sistema Debian/Ubuntu..."
PACCHETTI_NECESSARI=(
    python3
    python3-venv
    python3-pip
    python3-pil
    python3-flask
    python3-requests
    tesseract-ocr
    tesseract-ocr-ita
    tesseract-ocr-eng
    tesseract-ocr-fra
    tesseract-ocr-lat
    tesseract-ocr-deu
    tesseract-ocr-spa
)

if command -v apt-get &> /dev/null; then
    PACCHETTI_MANCANTI=()
    for pkg in "${PACCHETTI_NECESSARI[@]}"; do
        if command -v dpkg-query &> /dev/null; then
            if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
                PACCHETTI_MANCANTI+=("$pkg")
            fi
        else
            PACCHETTI_MANCANTI+=("$pkg")
        fi
    done

    if [ "${#PACCHETTI_MANCANTI[@]}" -gt 0 ]; then
        echo "➡️ Installazione pacchetti di sistema mancanti: ${PACCHETTI_MANCANTI[*]}"
        echo "   (Se richiesta, inserisci la password di amministrazione)"
        if [ "$(id -u)" -eq 0 ]; then
            apt-get update -y 2>/dev/null || true
            for pkg in "${PACCHETTI_MANCANTI[@]}"; do
                apt-get install -y "$pkg" 2>/dev/null || true
            done
        elif command -v sudo &> /dev/null; then
            sudo apt-get update -y 2>/dev/null || true
            for pkg in "${PACCHETTI_MANCANTI[@]}"; do
                sudo apt-get install -y "$pkg" 2>/dev/null || true
            done
        else
            echo "⚠️ Impossibile eseguire apt come root. Procedo con le verifiche locali."
        fi
    else
        echo "✅ Tutti i pacchetti di sistema sono già presenti."
    fi
else
    echo "ℹ️ Gestore apt non presente su questa macchina. Procedo con la configurazione Python..."
    if ! command -v python3 &> /dev/null; then
        echo "❌ ERRORE: Python 3 non trovato. Installalo prima di procedere."
        exit 1
    fi
fi

# 2. Creazione venv con system-site-packages per ereditare le librerie native Debian
echo ""
echo "📦 2. Configurazione ambiente virtuale Python (venv)..."
if [ ! -d "$DIR/venv" ] || [ ! -f "$DIR/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$DIR/venv"
    echo "✅ Ambiente virtuale creato in $DIR/venv (con supporto pacchetti di sistema)."
else
    echo "✅ Ambiente virtuale già presente."
fi

# 3. Verifica dipendenze Python
echo ""
echo "📚 3. Installazione e verifica delle librerie Python..."
# Installa o completa le dipendenze Python nell'ambiente virtuale
"$DIR/venv/bin/python" -m pip install --upgrade pip --quiet --no-warn-script-location 2>/dev/null || true

if [ -f "$DIR/requirements.txt" ]; then
    "$DIR/venv/bin/python" -m pip install -r "$DIR/requirements.txt" --no-warn-script-location --quiet 2>/dev/null || true
fi

# Fallback specifico per pytesseract (libreria Python pura senza estensioni C)
if ! "$DIR/venv/bin/python" -c "import pytesseract" &> /dev/null; then
    "$DIR/venv/bin/python" -m pip install pytesseract --no-warn-script-location --quiet 2>/dev/null || true
fi

if "$DIR/venv/bin/python" -c "import flask, requests, PIL, pytesseract" &> /dev/null; then
    echo "✅ Librerie Python verificate e pronte all'uso."
else
    echo "⚠️ Alcune librerie potrebbero richiedere l'installazione dei pacchetti apt indicati sopra."
fi

# Autodiagnostica: i dizionari servono per leggere bene le foto.
# Se manca l'italiano il programma funziona lo stesso, ma lo dice chiaramente.
LINGUE_OCR=$("$DIR/venv/bin/python" -c "import pytesseract; print(' '.join(sorted(pytesseract.get_languages(config=''))))" 2>/dev/null || echo "")
if echo "$LINGUE_OCR" | grep -qw "ita"; then
    echo "✅ Dizionario italiano per la lettura delle foto presente."
    echo "   Lingue disponibili: $LINGUE_OCR"
else
    echo "ℹ️  Il dizionario italiano per la lettura delle foto non è disponibile."
    echo "   Il programma funziona lo stesso: potrai correggere il testo a mano."
    echo "   Per installarlo, esegui: sudo apt install tesseract-ocr-ita"
fi

# 4. Registrazione lanciatori desktop
echo ""
echo "🖥️  4. Registrazione nel menu di sistema Debian e sulla Scrivania..."
installa_lanciatori_desktop
echo "   -> Registrato in: ~/.local/share/applications/memorie-di-scena.desktop"
if [ -d "$HOME/Scrivania" ]; then
    echo "   -> Registrato in: ~/Scrivania/memorie-di-scena.desktop"
elif [ -d "$HOME/Desktop" ]; then
    echo "   -> Registrato in: ~/Desktop/memorie-di-scena.desktop"
fi

# 4b. Controllo settimanale degli aggiornamenti (timer dell'utente)
installa_timer_aggiornamenti
if systemctl --user list-timers memorie-aggiornamenti.timer &> /dev/null; then
    echo "   -> Controllo aggiornamenti settimanale attivo."
fi

# 5. Permessi
echo ""
echo "🔒 5. Impostazione permessi di esecuzione..."
chmod +x "$DIR/installa.sh" "$DIR/avvia.sh" "$DIR/aggiorna.sh"
echo "✅ Script resi eseguibili."

# 6. Conclusione e primo avvio
echo ""
echo "=================================================================="
echo "🎉 CONFIGURAZIONE COMPLETATA!"
echo "Avvio automatico di Memorie di Scena..."
echo "=================================================================="
echo ""
exec "$DIR/avvia.sh"
