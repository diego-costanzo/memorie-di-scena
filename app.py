# -*- coding: utf-8 -*-
"""
Memorie di Scena — ArchivioLibri
Punto di ingresso dell'applicazione.

Mantiene il nome "app.py" per compatibilità con gli script di avvio (avvia.sh),
ma la logica è ora interamente nel pacchetto modulare `archivio/`. Qui restano
solo: creazione dell'app, inizializzazione del database, backup di sicurezza e
pulizia della cache, quindi l'avvio del server locale.

ORDINE DI AVVIO (da non cambiare senza motivo)
----------------------------------------------
1. `create_app()` costruisce Flask, applica la configurazione e registra le rotte.
2. `init_db()` crea o aggiorna lo schema (idempotente: si può eseguire a ogni avvio).
3. `backup_database()` salva una copia coerente del database prima dell'uso.
4. `pulisci_cache_scaduta()` elimina i risultati di ricerca più vecchi di 24 ore.
5. `app.run(...)` avvia il server solo su 127.0.0.1: nessun accesso dalla rete.

PER UN FORK
-----------
- Nuove funzionalità: creare un modulo in `archivio/routes/` e registrarlo in
  `archivio/routes/__init__.py` (vedi quel file).
- Nuovi parametri: aggiungerli in `archivio/config.py`, non sparpagliarli qui.
- Non abilitare `debug=True`: esporrebbe il debugger interattivo sul computer.
"""
from archivio import create_app
from archivio.db import backup_database, init_db
from archivio.search.cache import pulisci_cache_scaduta

app = create_app()


if __name__ == "__main__":
    # Preparazione una-tantum all'avvio: schema, backup coerente e cache pulita.
    init_db()
    backup_database()
    pulisci_cache_scaduta()

    # Esecuzione rigorosa su interfaccia locale di loopback, multi-thread e senza debug.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
