# -*- coding: utf-8 -*-
"""
Sicurezza dell'applicazione: chiave segreta, protezione cookie e CSRF.

La funzione `init_security(app)` va chiamata durante la creazione dell'app.

COME FUNZIONA IL CSRF (importante per chi aggiunge moduli o form)
-----------------------------------------------------------------
Il programma è raggiungibile solo da 127.0.0.1, ma un'altra pagina aperta nel
browser potrebbe tentare di inviare richieste al posto dell'utente. Per questo
OGNI richiesta POST/PUT/PATCH/DELETE deve portare il token della sessione:

    - form HTML:  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    - chiamate JS: header `X-CSRF-Token` oppure campo `csrf_token` nel JSON.

Il token è esposto ai template dal context processor `_inietta_csrf`, quindi
in ogni pagina basta scrivere `{{ csrf_token }}`. Se manca, la richiesta viene
rifiutata con 400 e un messaggio JSON: è la causa più frequente di un form che
"smette di funzionare" dopo una modifica al template.

NOTE
----
- La chiave segreta deriva dal percorso dell'installazione e dall'utente: non è
  una password condivisa, ma resta locale e sufficiente per firmare i cookie.
- Il confronto usa `secrets.compare_digest` per non esporre differenze di tempo.
"""
import hashlib
import os
import secrets

from flask import jsonify, request, session

from . import config


def _csrf_token():
    """Genera (o riusa) il token CSRF della sessione corrente."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def init_security(app):
    """Configura chiave segreta, cookie protetti e validazione CSRF."""
    # Chiave segreta deterministica e sicura dalla posizione dell'installazione
    # (non hardcoded generica, ma unica per ogni macchina).
    _seed = f"memorie_di_scena_{os.path.abspath(config.BASE_DIR)}_{os.getuid() if hasattr(os, 'getuid') else 'win'}"
    app.secret_key = hashlib.sha256(_seed.encode()).hexdigest()

    # Cookie di sessione protetti: SameSite Lax mitiga i CSRF via browser, HttpOnly contro XSS.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    @app.context_processor
    def _inietta_csrf():
        """Espone il token CSRF a tutti i template."""
        return {"csrf_token": _csrf_token()}

    @app.before_request
    def _proteggi_csrf():
        """Valida il token CSRF su ogni richiesta che modifica lo stato."""
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token_atteso = session.get("_csrf_token")
            if not token_atteso:
                return jsonify({"success": False, "errore": "Sessione scaduta: ricarica la pagina."}), 400

            inviato = (
                request.form.get("csrf_token")
                or (request.get_json(silent=True) or {}).get("csrf_token")
                or request.headers.get("X-CSRF-Token")
            )
            if not inviato or not secrets.compare_digest(str(inviato), str(token_atteso)):
                return jsonify({"success": False, "errore": "Token di sicurezza non valido."}), 400
