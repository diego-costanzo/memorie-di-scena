# 🎭 Memorie di Scena
### *Archivio Teatrale, Biblioteca e Collezione Personale*

Applicazione web locale, autonoma, leggera e ad alta leggibilità sviluppata per **Debian GNU/Linux** (e derivate Ubuntu/Arch), concepita come un caldo ed elegante taccuino di palcoscenico d'altri tempi.
Perfettamente compatibile e ottimizzata sia per architetture **32-bit (i686/i386)** che **64-bit (x86_64)**.

---

## 🌟 Caratteristiche Principali

- **Design a Taccuino di Palcoscenico & Alta Leggibilità**:
  - Tavolozza calda ispirata ai teatri storici all'italiana (velluto bordeaux, carta antica a mano e finiture in oro antico).
  - Caratteri grandi (>= 19px), pulsanti ad alto contrasto e interfaccia ergonomica a prova di errore.
  - Zero framework pesanti, zero dipendenze CDN esterne: funziona al 100% offline.

- **Modello Dati Completo (SQLite Nativo & WAL Mode Ultra-Veloce)**:
  - 📖 **Libri**: Titolo, autore, collocazione in casa, editore/note, copertina.
  - 🎭 **Copioni Teatrali**: Regista, prima esibizione/teatro, data d'ingaggio, data della prima.
  - 🎵 **CD & Vinili**: Formato (Vinile LP, 45 giri, CD), artista/gruppo, etichetta/anno.
  - 🤝 **Registro Prestiti**: Tracciamento di chi ha in prestito volumi o copioni, promemoria visivo immediato e chiusura del rientro con 1 clic.
  - 📝 **Taccuino dei Ricordi**: Sezione appunti legata a ciascuna opera per conservare citazioni, memorie di prove, repliche e dediche.

- **🔎 Ricerca Libri per Frase o Citazione (Multi-Database)**:
  - **Libreria Personale & Taccuino Locale**: verifica istantaneamente se Alessio ha già il volume a casa o se ha annotato la frase nei suoi appunti!
  - **Wikiquote Italia**: banca dati per eccellenza di citazioni teatrali, battute di commedie, monologhi d'autore e drammaturgie.
  - **Wikipedia Italia**: ricerca di incipit celebri, romanzi, trame ed estratti letterari.
  - **Google Books**: ricerca full-text nel corpo dei milioni di libri scansionati.
  - **Open Library & Internet Archive**: catalogo mondiale di edizioni e testi scansionati di pubblico dominio.
  - **Cache su Disco (24h) & Session Pooling**: risparmia memoria e banda su connessioni lente e computer datati.

- **Modulo OCR Locale con Tesseract & Pillow**:
  - Acquisizione rapida da fotografia (frontespizio o copertina).
  - Riconoscimento ottico del testo in locale (lingua italiana) senza inviare immagini a server esterni.
  - Compilazione facilitata della scheda con pulsanti rapidi `[+ Titolo]`, `[+ Autore]`, `[+ Note]`.

- **Avvio Semplice in Background (Nessun Terminale Aperto)**:
  - Lanciatore Desktop standard (`Terminal=false`): un clic sull'icona della Scrivania avvia il server in silenzio e apre direttamente il browser.
  - Nessuna finestra nera del terminale da tenere aperta!
  - Chiusura comoda dal pulsante **«📕 Riponi il Taccuino (Esci)»** nell'interfaccia o tramite `./ferma.sh`.

- **Protezione, Sicurezza e Compatibilità 32-bit**:
  - Database SQLite con WAL Mode, synchronous NORMAL e indici per velocità 5-10x superiore anche su vecchi dischi meccanici.
  - Allocazione memoria calibrata: Pillow limita la dimensione RAM delle immagini prima dell'elaborazione per non saturare i sistemi a 32-bit.
  - Chiamate esterne con timeout rigidi e gestione automatica di rate-limit (nessun blocco dell'interfaccia).

---

## 📁 Struttura del Progetto

```text
memorie-di-scena/
├── app.py                      # Backend Flask protetto (motore multi-database, context manager)
├── avvia.sh                    # Script di avvio rapido in background (apre il browser, senza terminale)
├── ferma.sh                    # Script di arresto sicuro del server locale
├── installa.sh                 # Installatore idempotente (pacchetti apt, venv, lanciatore desktop)
├── requirements.txt            # Dipendenze Python minime (flask, requests, pillow, pytesseract)
├── .gitignore                  # Esclusione cache e ambiente virtuale
├── data/
│   ├── archivio.db             # Database SQLite con tutti i record, prestiti e memorie
│   ├── server.pid              # PID del server locale in esecuzione
│   └── cache/                  # Cache ricerche citazioni (24h)
├── static/
│   ├── css/
│   │   └── style.css           # Foglio di stile libreria classica & teatro d'altri tempi
│   ├── js/
│   │   └── app.js              # Logica frontend vanilla (filtri, citazioni, modali)
│   └── covers/                 # Copertine salvate in locale e SVG predefiniti dorati
└── templates/
    ├── index.html              # Pannello principale dell'archivio (con ricerca per citazione)
    └── acquisizione_ocr.html   # Interfaccia a due colonne per scansione fotografica
```

---

## 🚀 Installazione e Avvio

### 1. Configurazione Iniziale (Una tantum)
Apri un terminale nella cartella del progetto ed esegui:
```bash
./installa.sh
```
Lo script:
1. Verifica e installa i pacchetti di sistema necessari (`python3-venv`, `tesseract-ocr`, `tesseract-ocr-ita`).
2. Configura l'ambiente virtuale isolato `venv/`.
3. Crea automaticamente il lanciatore desktop **«Memorie di Scena»** sulla **Scrivania** e nel **Menu Applicazioni** di Debian (senza terminale nero visibile).

### 2. Avvio Quotidiano
Fai doppio clic sull'icona **«Memorie di Scena»** sulla Scrivania (oppure da terminale `./avvia.sh`).
L'applicazione si avvia in background e apre automaticamente il browser su `http://127.0.0.1:5000`.

### 3. Come Chiudere l'Archivio
Clicca semplicemente sul pulsante **«📕 Riponi il Taccuino (Esci)»** in alto a destra nell'applicazione web, oppure da terminale esegui:
```bash
./ferma.sh
```
