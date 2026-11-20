# -*- coding: utf-8 -*-
"""
Registrazione delle rotte dell'applicazione.

Ogni modulo espone una funzione `register(app)` che aggiunge le proprie rotte
direttamente sull'app, mantenendo i nomi degli endpoint invariati (così i
riferimenti `url_for(...)` nei template continuano a funzionare).

PERCHÉ LE ROTTE SONO DIVISE PER AREA
------------------------------------
    main.py      pagina iniziale, OCR, copia di sicurezza
    elementi.py  scaffale: creazione, modifica, eliminazione, appunti, CSV
    prestiti.py  prestito e rientro
    ricerca.py   Bussola Culturale (API JSON)
    diario.py    Diario dei Pensieri, cestino e arresto del programma
    aggiornamenti.py  controllo e avvio degli aggiornamenti da GitHub

COME AGGIUNGERE UN NUOVO MODULO
-------------------------------
1. Creare `routes/nome_area.py` con:
       def register(app):
           @app.route("/api/...", methods=["POST"])
           def nome_funzione():
               ...
2. Importarlo qui sotto e chiamare `nome_area.register(app)` in `register_all`.
3. Mantenere i nomi degli endpoint univoci: `url_for("nome_funzione")` è usato
   nei template e nei test.
4. Le POST sono già protette da CSRF (vedi `security.py`): il form o la fetch
   devono inviare il token.
"""
from . import aggiornamenti, diario, elementi, main, prestiti, ricerca


def register_all(app):
    main.register(app)
    elementi.register(app)
    prestiti.register(app)
    ricerca.register(app)
    diario.register(app)
    aggiornamenti.register(app)
