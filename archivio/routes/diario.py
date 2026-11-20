# -*- coding: utf-8 -*-
"""
Rotte del Diario dei Pensieri & Memorie e arresto applicazione.

ROTTE
-----
    GET  /api/diario/lista                 fogli attivi, con filtro ?q=
    POST /api/diario/nuovo                 crea un foglio
    POST /api/diario/<id>/modifica         salva modifiche e versione precedente
    GET  /api/diario/<id>/cronologia       storia delle modifiche
    POST /api/diario/<id>/cestina          sposta nel cestino (30 giorni)
    POST /api/diario/<id>/ripristina       riporta fuori dal cestino
    GET  /api/diario/cestino               elenco del cestino
    POST /api/diario/svuota_cestino        svuota definitivamente il cestino
    POST /api/chiudi                       arresta il programma

NOTE
----
- Il cestino non cancella subito: imposta `eliminato = 1` e la data. La pulizia
  automatica a 30 giorni avviene in `db.init_db()`, a ogni avvio.
- La cronologia salva il testo precedente SOLO se il testo è davvero cambiato:
  non si accumulano versioni identiche per modifiche al solo titolo.
- `api_diario_modifica` restituisce 404 se l'ID non esiste, invece di aggiornare
  zero righe in silenzio.
- `/api/chiudi` è protetta da CSRF come tutte le POST; l'arresto avviene in un
  thread separato per fare in modo che la risposta arrivi al browser prima
  della chiusura del processo.
"""
import os
import threading
from datetime import datetime

from flask import jsonify, request

from .. import config
from ..db import get_db
from ..utils import formatta_data_italiana, pattern_ricerca


def register(app):
    @app.route("/api/diario/lista", methods=["GET"])
    def api_diario_lista():
        """Elenca tutti i pensieri attivi (non eliminati), con filtro opzionale ?q=..."""
        q = request.args.get('q', '').strip()
        with get_db() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM diario_pensieri WHERE eliminato = 1")
            conteggio_cestino = cursor.fetchone()[0]

            if q:
                pattern = pattern_ricerca(q)
                cursor.execute("""
                    SELECT d.id, d.titolo, d.testo, d.fonte_riferimento, d.data_creazione, d.data_ultima_modifica,
                           (SELECT COUNT(*) FROM diario_cronologia c WHERE c.pensiero_id = d.id) AS num_revisioni
                    FROM diario_pensieri d
                    WHERE d.eliminato = 0 AND (
                        normalizza(d.testo) LIKE ? ESCAPE '\\'
                        OR normalizza(d.titolo) LIKE ? ESCAPE '\\'
                        OR normalizza(d.fonte_riferimento) LIKE ? ESCAPE '\\'
                    )
                    ORDER BY d.id DESC
                """, (pattern, pattern, pattern))
            else:
                cursor.execute("""
                    SELECT d.id, d.titolo, d.testo, d.fonte_riferimento, d.data_creazione, d.data_ultima_modifica,
                           (SELECT COUNT(*) FROM diario_cronologia c WHERE c.pensiero_id = d.id) AS num_revisioni
                    FROM diario_pensieri d
                    WHERE d.eliminato = 0
                    ORDER BY d.id DESC
                """)

            pensieri = []
            for r in cursor.fetchall():
                pensieri.append({
                    'id': r['id'],
                    'titolo': r['titolo'] or '',
                    'testo': r['testo'],
                    'fonte_riferimento': r['fonte_riferimento'] or '',
                    'data_creazione': r['data_creazione'],
                    'data_ultima_modifica': r['data_ultima_modifica'] or '',
                    'num_revisioni': r['num_revisioni']
                })

        return jsonify({
            'success': True,
            'pensieri': pensieri,
            'conteggio_cestino': conteggio_cestino,
            'totale': len(pensieri)
        })

    @app.route("/api/diario/nuovo", methods=["POST"])
    def api_diario_nuovo():
        """Salva un nuovo foglio di pergamena nel diario con data e ora indelebili."""
        dati = request.get_json(silent=True) or request.form
        testo = (dati.get('testo') or '').strip()
        if not testo:
            return jsonify({'success': False, 'messaggio': 'Scrivi il testo del pensiero o della citazione prima di salvare.'}), 400

        titolo = (dati.get('titolo') or '').strip()
        fonte = (dati.get('fonte_riferimento') or '').strip()
        data_leggibile = formatta_data_italiana()

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO diario_pensieri (titolo, testo, fonte_riferimento, data_creazione, data_ultima_modifica, eliminato)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (titolo, testo, fonte, data_leggibile, data_leggibile))
            nuovo_id = cursor.lastrowid

        return jsonify({'success': True, 'id': nuovo_id, 'data_creazione': data_leggibile})

    @app.route("/api/diario/<int:pensiero_id>/modifica", methods=["POST"])
    def api_diario_modifica(pensiero_id):
        dati = request.get_json(silent=True) or request.form
        nuovo_testo = (dati.get('testo') or '').strip()
        if not nuovo_testo:
            return jsonify({'success': False, 'messaggio': 'Il testo non può essere vuoto.'}), 400

        nuovo_titolo = (dati.get('titolo') or '').strip()
        nuova_fonte = (dati.get('fonte_riferimento') or '').strip()
        data_modifica = formatta_data_italiana()

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT testo, titolo, fonte_riferimento FROM diario_pensieri WHERE id = ?", (pensiero_id,))
            vecchio = cursor.fetchone()
            if not vecchio:
                return jsonify({'success': False, 'messaggio': 'Pensiero non trovato.'}), 404

            vecchio_testo = vecchio['testo']
            testo_modificato = (nuovo_testo != vecchio_testo.strip())

            # Salva in cronologia SOLO se c'è una modifica reale al testo
            if testo_modificato:
                cursor.execute("""
                    INSERT INTO diario_cronologia (pensiero_id, testo_precedente, data_modifica)
                    VALUES (?, ?, ?)
                """, (pensiero_id, vecchio_testo, data_modifica))

            cursor.execute("""
                UPDATE diario_pensieri
                SET titolo = ?, testo = ?, fonte_riferimento = ?, data_ultima_modifica = ?
                WHERE id = ?
            """, (nuovo_titolo, nuovo_testo, nuova_fonte, data_modifica, pensiero_id))

        return jsonify({'success': True, 'testo_modificato': testo_modificato, 'data_modifica': data_modifica})

    @app.route("/api/diario/<int:pensiero_id>/cronologia", methods=["GET"])
    def api_diario_cronologia(pensiero_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT titolo, testo, fonte_riferimento, data_creazione, data_ultima_modifica FROM diario_pensieri WHERE id = ?", (pensiero_id,))
            pensiero = cursor.fetchone()
            if not pensiero:
                return jsonify({'success': False, 'messaggio': 'Pensiero non trovato.'}), 404

            cursor.execute("""
                SELECT id, testo_precedente, data_modifica
                FROM diario_cronologia
                WHERE pensiero_id = ?
                ORDER BY id ASC
            """, (pensiero_id,))
            revisioni = [
                {
                    'id': r['id'],
                    'testo_precedente': r['testo_precedente'],
                    'data_modifica': r['data_modifica']
                }
                for r in cursor.fetchall()
            ]

        return jsonify({
            'success': True,
            'titolo': pensiero['titolo'] or '',
            'testo_attuale': pensiero['testo'],
            'fonte_riferimento': pensiero['fonte_riferimento'] or '',
            'data_creazione': pensiero['data_creazione'],
            'data_ultima_modifica': pensiero['data_ultima_modifica'],
            'revisioni': revisioni
        })

    @app.route("/api/diario/<int:pensiero_id>/cestina", methods=["POST"])
    def api_diario_cestina(pensiero_id):
        oggi_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE diario_pensieri
                SET eliminato = 1, data_eliminazione = ?
                WHERE id = ?
            """, (oggi_iso, pensiero_id))
        return jsonify({'success': True})

    @app.route("/api/diario/<int:pensiero_id>/ripristina", methods=["POST"])
    def api_diario_ripristina(pensiero_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE diario_pensieri
                SET eliminato = 0, data_eliminazione = NULL
                WHERE id = ?
            """, (pensiero_id,))
        return jsonify({'success': True})

    @app.route("/api/diario/cestino", methods=["GET"])
    def api_diario_cestino():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, titolo, testo, fonte_riferimento, data_creazione, data_eliminazione
                FROM diario_pensieri
                WHERE eliminato = 1
                ORDER BY data_eliminazione DESC
            """)
            elementi = []
            for r in cursor.fetchall():
                data_elim = r['data_eliminazione']
                giorni_rimasti = 30
                if data_elim:
                    try:
                        dt_elim = datetime.strptime(data_elim[:10], "%Y-%m-%d")
                        delta = (datetime.now() - dt_elim).days
                        giorni_rimasti = max(0, 30 - delta)
                    except Exception:
                        giorni_rimasti = 30

                elementi.append({
                    'id': r['id'],
                    'titolo': r['titolo'] or '',
                    'testo': r['testo'],
                    'fonte_riferimento': r['fonte_riferimento'] or '',
                    'data_creazione': r['data_creazione'],
                    'giorni_rimasti': giorni_rimasti
                })
        return jsonify({'success': True, 'elementi': elementi, 'totale': len(elementi)})

    @app.route("/api/diario/svuota_cestino", methods=["POST"])
    def api_diario_svuota_cestino():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM diario_pensieri WHERE eliminato = 1")
        return jsonify({'success': True})

    @app.route("/api/chiudi", methods=["POST"])
    def chiudi_applicazione():
        """Arresto pulito e sicuro dell'applicazione dal pulsante 'Riponi il Taccuino'."""
        pid_file = os.path.join(config.DATA_DIR, "server.pid")
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass

        def termina():
            import signal
            import time
            time.sleep(0.6)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=termina, daemon=True).start()
        return jsonify({"success": True, "messaggio": "Arrivederci!"})
