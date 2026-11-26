# 📅 Storia delle versioni

Le versioni seguono la numerazione semantica: **MAJOR.MINOR.PATCH** (es. 2.0.0).
- **MAJOR**: cambiamenti importanti, che possono richiedere attenzione.
- **MINOR**: nuove funzioni, compatibili con i dati esistenti.
- **PATCH**: correzioni di errori, senza cambiare l'uso.

---

## [2.1.0] — 26 novembre 2026

Potenziamento completo dell'acquisizione da fotografia (OCR più affidabile e intelligente), compatibile con i dati esistenti.

### Aggiunto
- **Analisi intelligente dei campi OCR (`archivio/ocr_analisi.py`)**: riconoscimento automatico di tipo (`Libro`, `Copione`, `CD / Vinile`), formato disco (`Vinile LP`, `Vinile 45 giri`, `CD`), codice `ISBN-10`/`ISBN-13` con verifica checksum, regista/teatro/editore e distinzione titolo/autore basata su dimensione dei caratteri e posizione nella foto.
- **Precompilazione non invasiva e badge ruolo**: la pagina di acquisizione suggerisce i campi vuoti senza sovrascrivere ciò che hai già scritto e mostra badge chiari sulle righe lette (`Titolo suggerito`, `Autore suggerito`, `Editore`, `ISBN`, `Regia`).
- **Avviso doppione in casa**: se l'opera fotografata sembra già presente nell'archivio locale, viene mostrato subito un promemoria con la collocazione.
- **Verifica opzionale dai cataloghi (`POST /api/ocr/arricchisci`)**: pulsante «🔍 Verifica e completa dai cataloghi» per correggere eventuali refusi OCR usando Open Library, Google Books o MusicBrainz (per ISBN o titolo/autore), solo su clic esplicito.
- **5 nuovi test automatici** (57 in totale) sulla fusione spaziale OCR, validazione ISBN, classificazione di libri/copioni/dischi e API di arricchimento.

### Migliorato
- **Pipeline immagini (`archivio/ocr.py`)**: nuova sequenza varianti (`nitida`, `sparsa` con `PSM 11` per copertine illustrate, `adattiva` denoise senza distorsione da `equalize`, `invertita` per testi chiari su sfondo scuro, `distesa`), upscaling adattato anche alle immagini strette/orizzontali e fusione intelligente delle righe non sovrapposte tramite bounding box (`image_to_data`).

---

## [2.0.2] — 25 novembre 2026

Audit completo di sicurezza e correzione di bug su backend, OCR, interfaccia e script.

### Sicurezza
- **Protezione anti-DNS rebinding e header difensivi**: rifiuto delle richieste con header `Host` non loopback (`403`) e aggiunta di `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` e `Content-Security-Policy` (`frame-ancestors 'none'`).
- **Chiave di sessione casuale**: `app.secret_key` viene generata casualmente con `secrets.token_hex(32)` e salvata in `data/.secret_key` con permessi `0600`, invece di derivarla dal percorso e dall'UID. Cartelle `data/`, `backup/`, `cache/` e copie di sicurezza usano permessi restrittivi (`0700`/`0600`).
- **Download copertine più severo**: disabilitati i redirect automatici (`allow_redirects=False`) verificando ogni hop prima della chiamata; accettati solo MIME raster reali (rifiutati `Content-Type` assenti e SVG) con verifica effettiva dei byte via Pillow, validazione di `mbid`/`cover_id` e chiusura garantita degli stream HTTP.
- **CSRF e parser JSON resilienti**: bloccati senza errori 500 i token CSRF non-ASCII, i payload JSON non-dizionario e i campi non stringa nelle API di ricerca e diario.
- **Path copertina e privacy Git**: verifica esplicita `isfile` su `copertina_caricata` (evita il fallback su directory con nomi come `"???"`); aggiunti `static/covers/foto_acquisita_*`, `data/.secret_key`, `data/.aggiornamento.lock` e `.vscode/` a `.gitignore`.

### Corretto
- **Interfaccia**: ripristino dello scroll pagina alla chiusura del modale di uscita; evidenziazione dei risultati senza spezzare entità HTML (`&amp;`, `&quot;`) né doppio escaping nei titoli; ricerca sullo Scaffale insensibile agli accenti; placeholder esplicito `gg/mm/aaaa` per il rientro prestiti; conteggio aggiornato a 13 archivi nella Bussola; versioning statici allineato anche in `acquisizione_ocr.html`.
- **Rotte, OCR e cache**: `aggiorna_copertina` non sovrascrive più le foto locali con il segnaposto SVG se offline e rimuove i vecchi file solo quando orfani; `ocr_upload` ridimensiona prima di convertire e salva sempre file `.jpg` reali gestendo le trasparenze su sfondo bianco; passata multilingue OCR applicata alla variante migliore; `pulisci_cache_scaduta()` non cancella più `aggiornamento.json`; pulizia cestino coerente su ora locale; gestione sicura di doppi prestiti e falsi messaggi di successo.
- **Script e migrazione**: `aggiorna.sh` ora fallisce in sicurezza se `backup_database` fallisce, verifica i percorsi dentro il tarball prima dell'estrazione, ripulisce file obsoleti nelle cartelle di codice durante aggiornamento/ripristino e sostituisce `pkill -f` con controllo esatto dei processi Python dell'app (così come `ferma.sh`); `avvia.sh` aggiunge `--max-time` a `curl`; `data/migra_database.py` evita duplicazioni e inizializza direttamente lo schema di destinazione senza importare `app.py`.

### Aggiunto
- **15 nuovi test automatici** (52 in totale) su sicurezza HTTP/CSRF, redirect SSRF, upload/copertine, cache, cestino, prestiti e migrazione.

---

## [2.0.1] — 20 novembre 2026

Correzioni di sicurezza, senza cambiare nulla nell'uso quotidiano.

### Corretto
- **Copertine recuperate dal web solo da servizi fidati**: l'indirizzo dell'immagine deve essere `https` e appartenere a Wikimedia, Open Library o Cover Art Archive. Vengono rifiutati indirizzi locali o non previsti, anche dopo un rinvio (redirect). Evita che una risposta inattesa possa far scaricare contenuti dalla rete interna.
- **Copie di sicurezza verificate**: sia il pulsante «💾 Copia di sicurezza» sia il backup automatico prima di un aggiornamento controllano l'integrità della copia (`PRAGMA integrity_check`) e la scartano se non è leggibile, invece di lasciare un file che sembra valido ma non lo è.

### Aggiunto
- **2 nuovi test automatici** (37 in totale) sulle protezioni appena descritte.

---

## [2.0.0] — 19 novembre 2026

Revisione completa del programma: più sicuro, più leggero, più solido. **L'uso quotidiano non cambia** e i dati esistenti vengono conservati.

### Aggiunto
- **Aggiornamenti automatici sicuri**: il programma controlla GitHub all'avvio e una volta alla settimana; se c'è una versione nuova mostra un avviso con **«⬆️ Aggiorna ora»** e **«Più tardi»**. L'aggiornamento parte solo dopo un clic esplicito e una conferma, ed esegue in ordine: backup del database (API nativa di SQLite), archivio dell'intera cartella `data/`, istantanea del programma, download in `data/updates/`, verifica del pacchetto, sostituzione **dei soli file di programma**, test automatici, riavvio con controllo di avvio; in caso di errore **ripristina tutto**. La cartella `data/` non viene mai sovrascritta e non si usa `git pull`.
- **Timer settimanale** installato da `installa.sh` (`memorie-aggiornamenti.timer` di systemd utente), con `RandomizedDelaySec` e `Persistent`.
- **35 test automatici** di verifica, con database temporaneo isolato (`MEMORIE_DATA_DIR`).
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
