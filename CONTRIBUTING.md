# 🤝 Come aiutare Memorie di Scena

Grazie per essere qui. Questo è un progetto piccolo e senza fretta: ogni aiuto gentile è benvenuto, anche solo una segnalazione scritta con parole semplici.

Non serve essere esperti di informatica per aiutare: spesso la cosa più preziosa è raccontare **cosa stavi facendo** e **cosa non ha funzionato**.

---

## 🐞 Segnalare un problema

1. Controlla se il problema è già stato segnalato nella sezione **Issues**.
2. Se non c'è, apri una **nuova Issue** scegliendo il modello *«Segnalazione di un problema»*.
3. Descrivi, con parole tue:
   - cosa volevi fare;
   - cosa è successo invece;
   - se possibile, il messaggio che è comparso;
   - il tuo sistema (per esempio *Debian 12*, *Q4OS*, *Linux Mint*).

**Non allegare mai** il file `data/archivio.db` né la cartella `data/backup/`: contengono i tuoi dati personali (libri, prestiti, diario).

---

## 💡 Proporre un'idea

Apri una Issue con il modello *«Proposta di miglioramento»*. Spiega **a chi serve** e **perché**: quando una proposta nasce da un'esigenza reale (per esempio «mio padre non riesce a leggere questo pulsante»), è molto più facile valutarla.

Le idee più preziose sono quelle che rendono il programma:

- più **semplice** da capire;
- più **leggibile** (caratteri, contrasto, messaggi chiari);
- più **sicuro** per i dati;
- più **leggero** su computer vecchi.

---

## 🛠️ Proporre una modifica al programma

### 1. Prepara l'ambiente

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python app.py
```

Il programma si apre su <http://127.0.0.1:5000>.

### 2. Fai la modifica

- Mantieni i testi visibili all'utente **in italiano semplice**.
- Non introdurre **dipendenze proprietarie**: solo software libero.
- Non salvare nel repository database, backup, cache o file personali.
- Una modifica, un obiettivo: cambiamenti piccoli sono più facili da verificare.

### 3. Verifica

```bash
venv/bin/python -m unittest discover -s tests -v
```

Tutti i test devono risultare `OK`.

### 4. Apri una Pull Request

Compila il modello proposto da GitHub. Se puoi:

- spiega **perché** hai fatto la modifica;
- allega una descrizione di come provarla a mano;
- indica se hai toccato l'aspetto grafico (e se hai verificato con caratteri grandi).

---

## 🧭 Dove mettere le mani

| Vuoi cambiare... | Guarda in... |
|---|---|
| percorsi, limiti, parametri | `archivio/config.py` |
| database, schema, backup | `archivio/db.py` |
| sicurezza, cookie, CSRF | `archivio/security.py` |
| una fonte della Bussola | `archivio/search/sources_*.py` |
| l'ordine e la rilevanza dei risultati | `archivio/search/__init__.py` |
| una pagina o una funzione | `archivio/routes/` |
| grafica e testi delle pagine | `templates/`, `static/` |

---

## ✍️ Stile dei messaggi di commit

Messaggi brevi, in italiano o in inglese, che spiegano **il perché**:

```text
Aggiunge la ricerca nei copioni teatrali
Corregge il rientro prestito con data vuota
Rende più leggibile il pulsante di conferma
```

---

## 💚 Codice di condotta

Partecipando al progetto accetti il [Codice di Condotta](CODE_OF_CONDUCT.md). In sintesi: gentilezza, ascolto e rispetto. Questo è un archivio di memorie: il tono deve essere all'altezza.

---

## 🔐 Problemi di sicurezza

Non aprire una Issue pubblica. Segui le indicazioni in [SECURITY.md](SECURITY.md).
