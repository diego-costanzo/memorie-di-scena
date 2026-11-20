# -*- coding: utf-8 -*-
"""
Rotte per gli aggiornamenti automatici da GitHub.

ROTTE
-----
    GET  /api/aggiornamenti          esito dell'ultimo controllo (con cache)
    GET  /api/aggiornamenti/stato    stato dell'aggiornamento in corso/dell'ultimo
    POST /api/aggiornamenti/applica  avvia l'aggiornamento (dopo il clic utente)

FILOSOFIA (importante per chi modifica)
---------------------------------------
- L'interfaccia NON aggiorna nulla da sola: mostra un avviso e un pulsante.
  L'aggiornamento parte solo con una POST esplicita dell'utente.
- Tutto il lavoro pericoloso (backup, sostituzione file, test, ripristino)
  vive in `aggiorna.sh`: qui si esegue solo il controllo e si lancia lo script
  in un processo separato, così la richiesta HTTP non viene interrotta quando
  il server si spegne per aggiornarsi.
- `MEMORIE_NO_UPDATE=1` disattiva l'applicazione degli aggiornamenti: usato
  dai test automatici per non lanciare mai processi reali.
- Il risultato del controllo è in cache per 12 ore: aprire la pagina molte
  volte non produce traffico verso GitHub.
"""
import json
import os
import subprocess
import time

from flask import jsonify

from .. import config

# Il controllo viene ripetuto solo dopo 12 ore (in secondi).
CACHE_FRESCA_SEC = 12 * 60 * 60
# Un aggiornamento "in corso" più vecchio di 10 minuti è considerato interrotto.
STATO_IN_CORSO_SEC = 10 * 60
# Tempo massimo concesso al controllo di rete prima di rispondere comunque.
TIMEOUT_CONTROLLO_SEC = 25


def _leggi_json(percorso, predefinito):
    """Legge un file JSON senza mai propagare errori all'interfaccia."""
    try:
        with open(percorso, encoding="utf-8") as file_json:
            return json.load(file_json)
    except (OSError, ValueError):
        return predefinito


def _aggiornamento_disattivato():
    """True quando l'applicazione degli aggiornamenti non è consentita."""
    return os.environ.get("MEMORIE_NO_UPDATE") == "1"


def _esegui_controllo():
    """
    Restituisce il risultato del controllo, usando la cache quando è fresca.

    Se lo script non è disponibile o non risponde, restituisce un esito
    neutro (nessun aggiornamento) con il motivo: la pagina deve continuare
    a funzionare anche offline.
    """
    if _aggiornamento_disattivato():
        return {
            "versione_locale": config.versione_locale(),
            "versione_remota": config.versione_locale(),
            "disponibile": False,
        }

    cache = _leggi_json(config.UPDATE_CACHE_PATH, {})
    adesso = int(time.time())
    if cache.get("controllato_il_ts") and adesso - int(cache["controllato_il_ts"]) < CACHE_FRESCA_SEC:
        return cache

    if not os.path.isfile(config.UPDATE_SCRIPT):
        return {
            "versione_locale": config.versione_locale(),
            "versione_remota": config.versione_locale(),
            "disponibile": False,
            "errore": "Sistema di aggiornamento non installato.",
        }

    try:
        subprocess.run(
            ["/bin/bash", config.UPDATE_SCRIPT, "--check"],
            cwd=config.BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_CONTROLLO_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass

    risultato = _leggi_json(config.UPDATE_CACHE_PATH, {})
    if not risultato:
        return {
            "versione_locale": config.versione_locale(),
            "versione_remota": config.versione_locale(),
            "disponibile": False,
            "errore": "Controllo non riuscito: sei collegato a Internet?",
        }
    return risultato


def _avvia_aggiornamento():
    """
    Lancia `aggiorna.sh --apply` staccato dal server web.

    `start_new_session=True` crea una nuova sessione: il processo sopravvive
    alla chiusura del server, che lo script stesso fermerà tra poco.
    """
    subprocess.Popen(
        ["/bin/bash", config.UPDATE_SCRIPT, "--apply"],
        cwd=config.BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def register(app):
    @app.route("/api/aggiornamenti", methods=["GET"])
    def stato_aggiornamenti():
        esito = _esegui_controllo()
        # La versione locale è sempre quella letta ora dal file VERSION.
        esito["versione_locale"] = config.versione_locale()
        esito["applicazione_disattivata"] = _aggiornamento_disattivato()
        return jsonify(esito)

    @app.route("/api/aggiornamenti/stato", methods=["GET"])
    def stato_aggiornamento_corrente():
        stato = _leggi_json(config.UPDATE_STATE_PATH, {"stato": "inattivo"})
        stato["versione_locale"] = config.versione_locale()
        return jsonify(stato)

    @app.route("/api/aggiornamenti/applica", methods=["POST"])
    def applica_aggiornamento():
        if _aggiornamento_disattivato():
            return jsonify({
                "success": False,
                "errore": "L'aggiornamento è disattivato in questa modalità.",
            }), 409

        if not os.path.isfile(config.UPDATE_SCRIPT):
            return jsonify({
                "success": False,
                "errore": "Sistema di aggiornamento non disponibile.",
            }), 503

        stato = _leggi_json(config.UPDATE_STATE_PATH, {})
        if stato.get("stato") == "in_corso":
            avviato_da = int(stato.get("aggiornato_il_ts") or 0)
            if time.time() - avviato_da < STATO_IN_CORSO_SEC:
                return jsonify({
                    "success": False,
                    "errore": "Un aggiornamento è già in corso. Attendi qualche istante.",
                }), 409

        try:
            _avvia_aggiornamento()
        except OSError:
            return jsonify({
                "success": False,
                "errore": "Non è stato possibile avviare l'aggiornamento.",
            }), 500

        return jsonify({
            "success": True,
            "messaggio": "Aggiornamento avviato: il programma si riavvierà da solo.",
        })
