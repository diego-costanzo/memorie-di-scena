# 🔐 Sicurezza

## Come funziona il programma, in breve

**Memorie di Scena** è un'applicazione locale:

- ascolta solo su `127.0.0.1` (il tuo computer), non sulla rete;
- non ha account, login remoti o servizi cloud;
- salva tutti i dati in un database SQLite locale (`data/archivio.db`);
- usa una chiave di sessione casuale per installazione (`data/.secret_key`, permessi `0600`), cookie `HttpOnly` e `SameSite=Lax`, validazione dell'header `Host` contro il DNS rebinding, header HTTP difensivi e un token CSRF su ogni operazione che modifica i dati.

Questo riduce molto la superficie di rischio, ma non elimina l'importanza di segnalare un problema in modo responsabile.

---

## 🚩 Segnalare un problema di sicurezza

**Non aprire una Issue pubblica.** Una segnalazione pubblica può mettere a rischio chi usa il programma prima che sia disponibile una correzione.

Usa invece il canale privato di GitHub:

1. Apri la scheda **Security** del repository.
2. Scegli **«Report a vulnerability»** (Security Advisories).
3. Descrivi il problema.

Se il canale privato non fosse disponibile, contatta direttamente chi mantiene il progetto, indicando nell'oggetto: *«Segnalazione di sicurezza — Memorie di Scena»*.

### Cosa è utile sapere

- Versione del programma (se la conosci).
- Sistema operativo.
- Una descrizione di cosa succede e come riprodurlo.
- L'eventuale impatto (per esempio: «un'altra pagina web può leggere i dati»).

**Non allegare mai** il tuo `data/archivio.db` o i backup: contengono dati personali.

---

## ⏱️ Cosa aspettarti

- Conferma di ricezione appena possibile.
- Una valutazione del problema e, se confermato, una correzione.
- Riconoscimento pubblico del contributo, se lo desideri, dopo la correzione.

Il progetto è mantenuto con cura ma senza fretta: la buona volontà è benvenuta, le pressioni no.

---

## ✅ Versioni supportate

| Versione | Supporto |
|---|---|
| 2.x | ✅ supportata |
| 1.x | ❌ non più supportata — aggiorna all'ultima versione |

---

## 🧭 Regole per chi contribuisce al codice

- Nessuna nuova dipendenza **proprietaria**: solo software libero.
- Ogni modifica che cambia dati deve passare dal token CSRF già presente.
- I testi inseriti dall'utente vanno sempre mostrati come testo, mai come codice.
- I file caricati vanno validati per estensione, dimensione e nome.
- Le query al database vanno sempre parametrizzate (mai concatenare testo).
- Il server resta su `127.0.0.1`; non introdurre esposizione in rete senza una discussione pubblica.
