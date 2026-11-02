# 🎭 Memorie di Scena
### *Un taccuino digitale artigianale per catalogare libri, copioni e ricordi — senza complicazioni e senza pretese.*

[![Piattaforma](https://img.shields.io/badge/Piattaforma-Linux%20(Debian%2C%20Q4OS%2C%20Ubuntu)-1b4332.svg)](#requisiti-e-compatibilit%C3%A0)
[![Architettura](https://img.shields.io/badge/Architettura-32--bit%20(i686)%20%7C%2064--bit%20(x86__64)-2d6a4f.svg)](#requisiti-e-compatibilit%C3%A0)
[![Database](https://img.shields.io/badge/Database-SQLite%20Locale%20(100%25%20Privato)-40916c.svg)](#la-filosofia-del-progetto)
[![Licenza](https://img.shields.io/badge/Licenza-Open%20Source%20(MIT)-52b788.svg)](#licenza)

---

## 📖 La Filosofia del Progetto

Spesso i software moderni di catalogazione sono freddi, sovradimensionati o richiedono registrazioni su cloud, abbonamenti e menu pieni di opzioni tecniche superflue. Per chi **non ha molta dimestichezza con il computer** o preferisce le cose semplici, utilizzare questi strumenti può risultare faticoso o disorientante.

**Memorie di Scena** nasce da un'esigenza umana e genuina: offrire un **archivio domestico basilare, accogliente e rilassante**, pensato come un caldo taccuino teatrale d'altri tempi. È uno strumento a misura di persona:
- **Tasti giganti e chiari:** per chi non ama dover mirare a pulsantini microscopici.
- **Caratteri grandi e ad alto contrasto:** pensati per chi non ci vede benissimo e non vuole affaticare la vista.
- **Zero terminali da usare nel quotidiano:** una volta installato, si avvia con un semplice doppio clic sull'icona della Scrivania e si apre direttamente nel browser predefinito.
- **Nessuna pretesa:** fa poche cose, ma le fa bene e con garbo, senza pretendere che l'utente sia un informatico.

---

## 🌟 Cosa puoi fare con Memorie di Scena?

### 📚 1. Catalogare la tua collezione di casa
Puoi registrare con pochi campi chiari i tuoi volumi:
- **Libri:** Titolo, autore, collocazione in casa (es. *Libreria salotto*, *Comodino camera*), note e copertina.
- **Copioni Teatrali:** Con dettagli cari a chi calca le scene o ama il teatro (regista, teatro della prima, anno d'ingaggio, note di scena).
- **Musica (CD e Vinili):** Formato (LP 33 giri, 45 giri, CD), artista, etichetta discografica e anno.

### 🤝 2. Ricordare sempre chi ha i tuoi libri in prestito
A chi non è mai capitato di prestare un libro prezioso o un copione a un amico e dimenticare a chi è stato dato?
- Un pannello ben visibile mostra subito chi ha in custodia un tuo volume e da quale data.
- Quando il libro torna a casa, basta un clic sul pulsante **«Restituito»** per rimetterlo a posto nell'archivio.

### 📝 3. Il Taccuino dei Ricordi per ogni opera
Ogni scheda ha una sezione dedicata alle memorie personali: puoi annotare una dedica trovata sul frontespizio, una citazione che ti ha colpito, ricordi delle prove teatrali, battute amate o pensieri legati a quella lettura.

### 🔎 4. Ricercare un'opera da una frase, una battuta o un titolo
Ti è mai capitato di ricordare mezza battuta, una frase memorabile o un motivo senza riuscire a ricordare il titolo esatto?
- Inserisci le parole che ricordi (es. *«nel mezzo del cammin»*, *«mirandolina cavaliere»*, *«chi è di scena»* o un artista/brano).
- L'archivio controlla prima di tutto tra i **tuoi volumi, dischi e ricordi personali** di casa.
- Se non lo trova a casa, cerca in parallelo in **8 grandi archivi digitali aperti e gratuiti**:
  - 🏛️ **OPAC SBN (Servizio Bibliotecario Nazionale):** Il catalogo ufficiale delle biblioteche pubbliche e statali italiane, con schede storiche, editori e codici BID.
  - 📜 **Wikisource:** La biblioteca libera con testi integrali di commedie, tragedie e copioni teatrali italiani (Goldoni, Pirandello, Alfieri, ecc.) con atti e scene.
  - 🎵 **MusicBrainz:** L'enciclopedia aperta mondiale per dischi in vinile (LP, 45 giri), CD, album e tracce musicali.
  - 🎭 **Wikiquote:** La raccolta libera di citazioni, battute celebri e monologhi teatrali.
  - 📖 **Wikipedia:** Voci enciclopediche, schede d'opera e trame letterarie.
  - 📚 **Google Books, Open Library e Internet Archive:** Milioni di testi mondiali e scansioni storiche di pubblico dominio.

### 📸 5. Acquisizione rapida da foto (OCR)
Per chi fatica a digitare lunghi testi sulla tastiera:
- Basta caricare o scattare una fotografia della copertina o del frontespizio.
- Il riconoscimento testo integrato (OCR in italiano) legge il testo dall'immagine e ti permette di inserire titolo, autore e note con un semplice tocco.

---

## 🛡️ Riservatezza, Semplicità e Rispetto dell'Hardware

* **100% Locale e Privato:** Tutti i tuoi dati, i libri, i ricordi e le note risiedono esclusivamente nel file `data/archivio.db` sul tuo computer. Nessun dato personale viene caricato su server esterni o nel cloud.
* **Funziona anche Offline:** L'archivio funziona regolarmente anche senza connessione Internet (la rete è richiesta solo per cercare citazioni online o scaricare copertine dal web).
* **Adatto a PC vecchi o riciclati (32-bit e 64-bit):** Testato con cura per funzionare perfettamente sia su computer moderni a 64 bit che su **vecchi computer a 32 bit** con poca memoria (ideale su distribuzioni leggere come **Q4OS**, Debian, antiX o Linux Mint).
* **Nessuna finestra nera del terminale:** All'avvio, il programma lavora silenziosamente in background e apre la schermata nel browser; per chiudere basta premere il pulsante rosso **«📕 Riponi il Taccuino (Esci)»**.

---

## 📁 Struttura del Progetto

```text
memorie-di-scena/
├── app.py                      # Il motore dell'applicazione (Flask e SQLite nativo)
├── avvia.sh                    # Script di avvio silenzioso (apre il browser senza terminale)
├── ferma.sh                    # Script per chiudere l'applicazione in modo pulito
├── installa.sh                 # Installatore semplice (prepara l'ambiente e crea l'icona sul Desktop)
├── prepara_aggiornamento.sh    # Strumento per creare pacchetti di aggiornamento sicuri
├── requirements.txt            # Dipendenze Python minime e standard
├── data/
│   └── archivio.db             # Il tuo database personale (libri, copioni, appunti e prestiti)
├── static/
│   ├── css/style.css           # Grafica accogliente a taccuino con tasti grandi
│   ├── js/app.js               # Comportamenti semplici per la pagina (senza librerie esterne)
│   └── covers/                 # Copertine salvate in locale e illustrazioni dorate
└── templates/
    ├── index.html              # Registro generale e catalogo principale
    └── acquisizione_ocr.html   # Scheda di lettura facilitata da fotografia
```

---

## 🚀 Come si installa e si avvia

### 1. Prima installazione (da fare una sola volta)
Apri un terminale nella cartella del programma ed esegui:

```bash
./installa.sh
```

Lo script si occupa di tutto da solo:
1. Verifica la presenza di Python e dei componenti di base per l'OCR.
2. Crea l'ambiente isolato per l'archivio senza toccare il resto del sistema.
3. Posiziona una comoda icona **«Memorie di Scena»** direttamente sulla tua **Scrivania** (Desktop) e nel menu delle applicazioni.

### 2. Uso quotidiano
Fai semplicemente doppio clic sull'icona **«Memorie di Scena»** sulla Scrivania (oppure avvia con `./avvia.sh`).  
L'applicazione si aprirà direttamente nel tuo browser abituale. Non serve tenere aperto nessun terminale!

### 3. Come chiudere l'archivio
Quando hai finito di consultare o aggiornare i tuoi libri, clicca sul pulsante in alto a destra:  
👉 **«📕 Riponi il Taccuino (Esci)»**  
Il programma salverà tutto e si arresterà in modo pulito.

---

## 💻 Requisiti di Sistema

* **Sistema Operativo:** Qualsiasi distribuzione Linux (Debian, Q4OS, Ubuntu, Linux Mint, Fedora, Arch, ecc.).
* **Architettura:** Compatibile sia con **32-bit (x86 / i686)** sia con **64-bit (x86_64)**.
* **Memoria RAM:** Funziona fluidamente anche con soli **512 MB – 1 GB** di RAM.
* **Spazio su Disco:** Meno di 150 MB (incluso l'ambiente Python e il motore OCR).

---

## 🤝 Contributi e Spirito del Progetto

Questo progetto non ha l'ambizione di competere con software bibliotecari complessi o gestionali professionali. È nato con amore come gesto di cura e attenzione verso chi desidera uno strumento limpido, comprensibile e privo di ostacoli tecnologici.

Se hai idee per renderlo ancora più accessibile, intuitivo o gradevole per persone anziane o poco esperte di tecnologia, sentiti libero di aprire una *Issue* o proporre una modifica (*Pull Request*).

---

## 📄 Licenza

Rilasciato sotto licenza open source [MIT](LICENSE). Sentiti libero di usarlo, condividerlo, regalarlo ad amici o parenti e migliorarlo per chiunque ne abbia bisogno.
