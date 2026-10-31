# 🎭 Memorie di Scena
### *Archivio Teatrale, Biblioteca e Collezione Personale*

Applicazione web locale, autonoma, leggera e ad alta leggibilità sviluppata per **Debian GNU/Linux** (e derivate Ubuntu/Arch), concepita come un caldo ed elegante taccuino di palcoscenico d'altri tempi.

---

## 🌟 Caratteristiche Principali

- **Design a Taccuino di Palcoscenico & Alta Leggibilità**:
  - Tavolozza calda ispirata ai teatri storici all'italiana (velluto bordeaux, carta antica a mano e finiture in oro antico).
  - Caratteri grandi (>= 19px), pulsanti ad alto contrasto e interfaccia ergonomica a prova di errore.
  - Zero framework pesanti, zero dipendenze CDN esterne: funziona al 100% offline.

- **Modello Dati Completo (SQLite Nativo)**:
  - 📖 **Libri**: Titolo, autore, collocazione in casa, editore/note, copertina.
  - 🎭 **Copioni Teatrali**: Regista, prima esibizione/teatro, data d'ingaggio, data della prima.
  - 🎵 **CD & Vinili**: Formato (Vinile LP, 45 giri, CD), artista/gruppo, etichetta/anno.
  - 🤝 **Registro Prestiti**: Tracciamento di chi ha in prestito volumi o copioni, promemoria visivo immediato e chiusura del rientro con 1 clic.
  - 📝 **Taccuino dei Ricordi**: Sezione appunti legata a ciascuna opera per conservare citazioni, memorie di prove, repliche e dediche.

- **Modulo OCR Locale con Tesseract & Pillow**:
  - Acquisizione rapida da fotografia (frontespizio o copertina).
  - Riconoscimento ottico del testo in locale (lingua italiana) senza inviare immagini a server esterni.
  - Compilazione facilitata della scheda con pulsanti rapidi `[+ Titolo]`, `[+ Autore]`, `[+ Note]`.

- **Protezione e Sicurezza**:
  - Database SQLite isolato in `data/archivio.db` con integrità referenziale (`PRAGMA foreign_keys = ON`).
  - Validazione rigorosa degli upload (`werkzeug.secure_filename`) e ottimizzazione dinamica della memoria per computer datati (downscaling immagini prima dell'OCR).

---

## 📁 Struttura del Progetto

```text
memorie-di-scena/
├── app.py                      # Backend Flask protetto (porte 127.0.0.1:5000, context manager)
├── avvia.sh                    # Script di avvio quotidiano a schermo intero (con trap di chiusura)
├── installa.sh                 # Installatore idempotente (pacchetti apt, venv, lanciatore desktop)
├── requirements.txt            # Dipendenze Python minime (flask, requests, pillow, pytesseract)
├── .gitignore                  # Esclusione cache e ambiente virtuale
├── data/
│   └── archivio.db             # Database SQLite con tutti i record, prestiti e memorie
├── static/
│   ├── css/
│   │   └── style.css           # Foglio di stile libreria classica & teatro d'altri tempi
│   ├── js/
│   │   └── app.js              # Logica frontend vanilla (filtri, modali, anteprime)
│   └── covers/                 # Copertine salvate in locale e SVG predefiniti dorati
└── templates/
    ├── index.html              # Pannello principale dell'archivio
    └── acquisizione_ocr.html   # Interfaccia a due colonne per scansione fotografica
```

---

## 🚀 Installazione e Primo Avvio

### 1. Configurazione Iniziale (Una tantum)
Apri un terminale nella cartella del progetto ed esegui:
```bash
./installa.sh
```
Lo script:
1. Verifica e installa i pacchetti di sistema necessari (`python3-venv`, `tesseract-ocr`, `tesseract-ocr-ita`).
2. Configura l'ambiente virtuale isolato `venv/`.
3. Installa le librerie Python.
4. Crea automaticamente il lanciatore desktop **«Memorie di Scena»** sia sulla **Scrivania** sia nel **Menu Applicazioni** di Debian.

### 2. Avvio Quotidiano
È possibile avviare l'applicazione semplicemente facendo doppio clic sull'icona creata sulla Scrivania, oppure da terminale con:
```bash
./avvia.sh
```
L'applicazione avvierà il servizio locale e aprirà automaticamente il browser predefinito a tutto schermo su `http://127.0.0.1:5000`.
Per chiudere in modo pulito l'archivio, premi `[CTRL] + [C]` nella finestra del terminale.

