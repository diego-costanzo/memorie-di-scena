# 📅 Storia delle versioni

Le versioni seguono la numerazione semantica: **MAJOR.MINOR.PATCH** (es. 2.0.0).
- **MAJOR**: cambiamenti importanti, che possono richiedere attenzione.
- **MINOR**: nuove funzioni, compatibili con i dati esistenti.
- **PATCH**: correzioni di errori, senza cambiare l'uso.

---

## [2.0.0] — 19 novembre 2026

Revisione completa del programma: più sicuro, più leggero, più solido. **L'uso quotidiano non cambia** e i dati esistenti vengono conservati.

### Aggiunto
- **Aggiornamenti automatici sicuri**: il programma controlla GitHub all'avvio e una volta alla settimana; se c'è una versione nuova mostra un avviso con **«⬆️ Aggiorna ora»** e **«Più tardi»**. L'aggiornamento parte solo dopo un clic esplicito e una conferma, ed esegue in ordine: backup del database (API nativa di SQLite), archivio dell'intera cartella `data/`, istantanea del programma, download in `data/updates/`, verifica del pacchetto, sostituzione **dei soli file di programma**, test automatici, riavvio con controllo di avvio; in caso di errore **ripristina tutto**. La cartella `data/` non viene mai sovrascritta e non si usa `git pull`.
- **Timer settimanale** installato da `installa.sh` (`memorie-aggiornamenti.timer` di systemd utente), con `RandomizedDelaySec` e `Persistent`.
- **37 test automatici** di verifica, con database temporaneo isolato (`MEMORIE_DATA_DIR`).
- **Guida visiva nel README**: immagini della pagina iniziale e dell'acquisizione da foto, più istruzioni di download e installazione passo per passo.
- **Prestiti in ritardo evidenziati**: i prestiti scaduti compaiono in rosso con i giorni di ritardo, così è impossibile dimenticarsene.
- **Esportazione inventario in CSV**: un pulsante scarica tutta la collezione (con i prestiti attivi) in un file apribile con LibreOffice o Excel, pronto da stampare o conservare.
- **Copia di sicurezza con un clic**: dalla pagina principale si scarica subito una copia coerente del database nella cartella Download, senza chiudere il programma.
- **OCR multilingue**: la lettura parte dall'italiano e, se il risultato è incerto, fa una seconda passata con tutti i dizionari installati (italiano, inglese, francese, latino, tedesco, spagnolo). L'installer aggiunge i dizionari `tesseract-ocr-eng`, `-fra`, `-lat`, `-deu` e `-spa`.
- **Autodiagnostica dei dizionari OCR**: se manca l'italiano, la pagina di acquisizione mostra un avviso chiaro e gentile invece di leggere le foto con il motore sbagliato in silenzio; anche `installa.sh` riporta le lingue disponibili.
- **Backup automatico a rotazione** all'avvio: ultime 7 copie in `data/backup/`.
- **Cache su disco** delle ricerche online, con durata di 24 ore.
- **Migrazione automatica** del vecchio `archivio.db` dalla cartella principale a `data/`.
- Documentazione di comunità: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, modelli di Issue e Pull Request.

### Modificato
- Il vecchio file unico è stato diviso in un **pacchetto modulare `archivio/`**:
  - `config.py`, `utils.py`, `db.py`, `security.py`, `http.py`, `ocr.py`, `covers.py`;
  - `search/` con cache, ricerca locale e 13 fonti esterne divise per famiglia;
  - `routes/` con le rotte raggruppate per area (principale, elementi, prestiti, ricerca, diario).
- `app.py` è ora un **punto di ingresso sottile**: crea l'app, prepara il database, esegue il backup, pulisce la cache e avvia il server.
- Le copertine dei dischi non usano più un servizio proprietario: ora arrivano da **MusicBrainz + Cover Art Archive** (aperti, dati CC0), con immagine di riserva in caso di assenza o assenza di rete.
- La ricerca è più potente: **insensibile ad accenti e maiuscole**, con `%` e `_` trattati come testo letterale.
- I risultati sono **deduplicati** e ordinati per rilevanza; quelli della collezione personale restano sempre in cima.
- **OCR ripensato da zero** (`archivio/ocr.py`): raddrizzamento tramite rilevatore di orientamento, ingrandimento delle foto piccole, binarizzazione adattiva ispirata a Bradley (realizzata con soli filtri Pillow, senza numpy), più varianti di lettura scelte in base alla **confidenza misurata parola per parola**, con arresto anticipato quando la qualità è già ottima. Le righe sotto soglia vengono scartate: meglio poche righe giuste che rumore da correggere.
- L'interfaccia di acquisizione mostra un avviso di qualità della lettura («nitida», «discreta», «poco nitida» con consiglio pratico).

### Corretto (sicurezza e affidabilità)
- **CSRF**: token di sessione obbligatorio su POST/PUT/PATCH/DELETE.
- **XSS**: rimozione degli attributi `onclick`/`onsubmit` inline, uso di `data-*`, escaping sicuro ed evidenziazione dei risultati senza iniettare HTML.
- **Link non sicuri**: blocco di `javascript:`, `data:`, `vbscript:` e dei protocolli relativi.
- **Cookie**: `HttpOnly` e `SameSite=Lax`; chiave segreta unica derivata dall'installazione.
- **Database**: `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, `mmap_size=256MB`; connessioni sempre chiuse (niente `ResourceWarning` né perdite di memoria).
- **Upload**: estensioni consentite, limite di 32 MB, nome file ripulito, protezione da path traversal.
- **Prestazioni**: corretta una query con molte chiamate ripetute (N+1) nella pagina iniziale; OCR caricato solo quando serve; dimensioni immagine adattate a 32/64 bit.
- **Salvataggio da OCR**: il modulo di acquisizione ora include il token CSRF; prima ogni salvataggio veniva rifiutato con errore 400.
- **Tipo volume validato**: un valore fuori dall'elenco ammesso viene ricondotto a «Libro», evitando errori 500.
- **CSV sicuro**: i valori che iniziano con `=`, `+`, `-`, `@` vengono prefissati da apostrofo, così non vengono interpretati come formule da LibreOffice o Excel.
- **Prestiti robusti**: un ID volume non numerico o inesistente produce un avviso comprensibile invece di un errore 500.
- **Copertine protette**: le immagini scaricate dal web vengono accettate solo se sono immagini e non superano i 2 MB.
- **Anteprime OCR**: nome file con suffisso casuale, per non sovrascrivere due acquisizioni nello stesso secondo.
- **Chiavi esterne**: la migrazione dello schema riattiva correttamente `foreign_keys` fuori dalla transazione.
- **Link nei risultati**: gli indirizzi delle schede esterne passano la stessa validazione dei link sicuri.
- **Cestino del Diario**: le azioni cestina/ripristina/svuota inviano il token CSRF e non vengono più rifiutate.
- **Modifica scheda**: il form viene azzerato a ogni apertura e il server salva i campi specifici solo per il tipo corretto, evitando che regista/formato/etichetta «migrino» su un Libro.
- **Ricerca a prova di errore**: un risultato esterno senza titolo non fa più fallire l'intera ricerca.
- **Backup senza collisioni**: due copie ravvicinate producono file distinti (timestamp con microsecondi + controllo finale).
- **Un solo prestito attivo**: indice univoco parziale a livello di database sullo stesso volume.
- **Copertine e anteprime**: download a blocchi con limite di memoria; pulizia automatica delle anteprime OCR mai salvate. I campi `pagine` e l'URL della copertina sono ora schermati nel risultato.
- **Best practice Linux**: niente soppressione globale dei warning (solo `ResourceWarning`), limiti superiori di versione in `requirements.txt` e verifica dell'identità dell'app sulla porta 5000 prima di dichiararla già attiva.

### Rimosso
- Dipendenza dalla API iTunes per le copertine musicali (servizio proprietario), sostituita da fonti aperte.

---

## [1.0.0] — versione iniziale

Prima versione pubblica del taccuino:

- catalogo di libri, copioni teatrali, CD e vinili;
- registro dei prestiti con rientro;
- Taccuino dei Ricordi per ogni opera;
- Diario dei Pensieri su fogli in stile pergamena, con cronologia e cestino a 30 giorni;
- acquisizione da fotografia con OCR in italiano;
- Bussola Culturale con ricerca locale e archivi esterni;
- installazione guidata con icona sulla Scrivania e avvio senza terminale.
