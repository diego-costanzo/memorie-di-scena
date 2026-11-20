# -*- coding: utf-8 -*-
"""
ArchivioLibri — Memorie di Scena.

Pacchetto applicativo modulare. La funzione `create_app()` costruisce l'istanza
Flask applicando configurazione, sicurezza (CSRF/cookie), gestione errori e
registrazione di tutte le rotte. Il database non viene toccato qui: la sua
inizializzazione e il backup avvengono nel punto di ingresso (app.py), così i
test possono creare un'app "pulita" senza effetti collaterali sul disco.

MAPPATURA DEL PACCHETTO (per chi arriva da un fork)
---------------------------------------------------
    archivio/
    ├── __init__.py     ← questo file: factory Flask e gestione errori
    ├── config.py       ← percorsi, limiti, parametri OCR e di rete
    ├── db.py           ← UNICO punto di accesso a SQLite (schema e backup)
    ├── security.py     ← chiave segreta, cookie, token CSRF
    ├── http.py         ← sessione HTTP per thread verso le API esterne
    ├── utils.py        ← funzioni pure (testo, date), testabili da sole
    ├── ocr.py          ← pipeline di lettura delle fotografie
    ├── covers.py       ← copertine online con ripiego locale
    ├── routes/         ← rotte HTTP divise per area funzionale
    └── search/         ← Bussola Culturale: locale + 13 fonti esterne

REGOLA D'ORO: le rotte non parlano mai direttamente con `sqlite3`; usano
sempre `db.get_db()`, così PRAGMA, commit/rollback e chiusura sono garantiti.

COME AGGIUNGERE UNA ROTTA
-------------------------
1. Creare (o aprire) un modulo in `routes/` con una funzione `register(app)`.
2. Definire le rotte con `@app.route(...)`. Per le POST il token CSRF è già
   obbligatorio: il form deve contenere `<input type="hidden" name="csrf_token"
   value="{{ csrf_token }}">` oppure inviare l'header `X-CSRF-Token`.
3. Registrare il modulo in `routes/__init__.py`.
4. Aggiungere una verifica in `tests/test_smoke.py`.
"""
import os

from flask import Flask, jsonify

from . import config
from .routes import register_all
from .security import init_security


def create_app():
    """Factory dell'applicazione Flask."""
    # Template e static vivono nella radice del progetto (non dentro il pacchetto).
    app = Flask(
        "archivio",
        template_folder=os.path.join(config.BASE_DIR, "templates"),
        static_folder=os.path.join(config.BASE_DIR, "static"),
    )

    # Migrazione di sicurezza del vecchio archivio.db dalla radice (una tantum).
    config.migra_db_legacy()

    # Limite di upload e cache statica calibrati per hardware datato.
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400

    # Sicurezza: chiave segreta, cookie protetti e validazione CSRF.
    init_security(app)

    # Tutte le rotte, con nomi di endpoint invariati.
    register_all(app)

    # Gestione pulita del superamento quota upload (errore 413).
    @app.errorhandler(413)
    def file_troppo_grande(e):
        return jsonify({
            "success": False,
            "errore": "Il file caricato supera la dimensione massima consentita di 32 MB.",
        }), 413

    return app
