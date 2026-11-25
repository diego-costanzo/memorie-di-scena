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
- La chiave segreta è casuale per ogni installazione e salvata in
  `DATA_DIR/.secret_key` con permessi `0600` (solo proprietario): i cookie
  restano validi tra i riavvii senza essere prevedibili.
- Le richieste vengono validate sull'header `Host` (solo loopback locale) per
  prevenire attacchi di DNS rebinding; le risposte includono header difensivi
  (CSP, X-Frame-Options, X-Content-Type-Options).
- Il confronto CSRF usa `secrets.compare_digest` solo su stringhe ASCII valide.
"""
import os
import secrets
from urllib.parse import urlsplit

from flask import jsonify, request, session

from . import config

# Host consentiti per proteggere l'istanza locale da attacchi di DNS rebinding.
_HOST_LOOPBACK_CONSENTITI = {"127.0.0.1", "localhost", "::1"}


def _ottieni_chiave_segreta():
    """
    Restituisce una chiave segreta casuale persistita in `DATA_DIR/.secret_key`
    con permessi restrittivi (`0600`). Se la scrittura fallisce, ripiega su una
    chiave casuale in memoria.
    """
    percorso = os.path.join(config.DATA_DIR, ".secret_key")
    try:
        if os.path.isfile(percorso):
            with open(percorso, encoding="utf-8") as f:
                chiave = f.read().strip()
            if len(chiave) >= 32:
                return chiave
        chiave = secrets.token_hex(32)
        os.makedirs(config.DATA_DIR, mode=0o700, exist_ok=True)
        fd = os.open(percorso, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(chiave)
        return chiave
    except OSError:
        return secrets.token_hex(32)


def _host_valido(host_header):
    """True se l'header Host punta esclusivamente al loopback locale."""
    if not host_header:
        return False
    try:
        hostname = (urlsplit(f"//{host_header}").hostname or "").lower()
    except ValueError:
        return False
    return hostname in _HOST_LOOPBACK_CONSENTITI


def _csrf_token():
    """Genera (o riusa) il token CSRF della sessione corrente."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def init_security(app):
    """Configura chiave segreta, cookie protetti, Host check, header e CSRF."""
    app.secret_key = _ottieni_chiave_segreta()

    # Cookie di sessione protetti: SameSite Lax mitiga i CSRF via browser, HttpOnly contro XSS.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    @app.context_processor
    def _inietta_csrf():
        """Espone il token CSRF a tutti i template."""
        return {"csrf_token": _csrf_token()}

    @app.before_request
    def _proteggi_host_e_csrf():
        """Valida l'header Host (anti-DNS rebinding) e il token CSRF su scritture."""
        if not _host_valido(request.host):
            return jsonify({"success": False, "errore": "Host non consentito."}), 403

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token_atteso = session.get("_csrf_token")
            if not token_atteso:
                return jsonify({"success": False, "errore": "Sessione scaduta: ricarica la pagina."}), 400

            json_dati = request.get_json(silent=True)
            csrf_json = json_dati.get("csrf_token") if isinstance(json_dati, dict) else None
            inviato = (
                request.form.get("csrf_token")
                or csrf_json
                or request.headers.get("X-CSRF-Token")
            )
            # secrets.compare_digest su str solleva TypeError se contiene caratteri non-ASCII.
            if (
                not isinstance(inviato, str)
                or not inviato
                or not inviato.isascii()
                or not secrets.compare_digest(inviato, str(token_atteso))
            ):
                return jsonify({"success": False, "errore": "Token di sicurezza non valido."}), 400

    @app.after_request
    def _aggiungi_header_sicurezza(risposta):
        """Aggiunge header HTTP difensivi contro framing, sniffing e risorse esterne."""
        risposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        risposta.headers.setdefault("X-Frame-Options", "DENY")
        risposta.headers.setdefault("Referrer-Policy", "same-origin")
        risposta.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' https: http: data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'",
        )
        return risposta
