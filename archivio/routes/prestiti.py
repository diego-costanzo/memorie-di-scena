# -*- coding: utf-8 -*-
"""
Rotte per la gestione dei prestiti.

ROTTE
-----
    POST /api/prestiti                 registra un prestito
    POST /api/prestiti/<id>/rientro    segna il rientro come avvenuto

REGOLE
------
- Un volume può avere un solo prestito con stato 'In Prestito': la seconda
  richiesta viene rifiutata con un messaggio comprensibile.
- Il rientro non cancella la riga: cambia stato e registra la data effettiva,
  così lo storico resta consultabile nella scheda del volume.
- Le date sono stringhe gg/mm/aaaa, coerenti con il resto dell'archivio.
"""
from datetime import date

from flask import flash, redirect, request, url_for

from ..db import get_db


def register(app):
    @app.route("/api/prestiti", methods=["POST"])
    def registra_prestito():
        # L'ID arriva da un modulo HTML: è testo finché non lo convertiamo.
        # Se non è un intero valido evitiamo di interrogare il database con un
        # valore sbagliato e ripieghiamo su un messaggio comprensibile.
        elemento_id_raw = request.form.get("elemento_id", "").strip()
        try:
            elemento_id = int(elemento_id_raw)
        except (TypeError, ValueError):
            flash("Scegli un volume valido prima di registrare il prestito.", "errore")
            return redirect(url_for("index"))

        nome_persona = request.form.get("nome_persona", "").strip()
        data_prestito = request.form.get("data_prestito", "").strip() or date.today().strftime("%d/%m/%Y")
        data_rientro_prevista = request.form.get("data_rientro_prevista", "").strip()

        if not nome_persona:
            flash("Inserisci il nome della persona a cui presti il volume!", "errore")
            return redirect(url_for("index"))

        with get_db() as conn:
            cursor = conn.cursor()

            # Confermiamo che il volume esista davvero: senza questo controllo
            # l'INSERT violerebbe la chiave esterna e l'utente vedrebbe un
            # errore 500 invece di un avviso chiaro.
            cursor.execute("SELECT titolo FROM elementi WHERE id = ?", (elemento_id,))
            elem = cursor.fetchone()
            if not elem:
                flash("Il volume selezionato non è più presente in archivio.", "errore")
                return redirect(url_for("index"))

            cursor.execute("SELECT id FROM prestiti WHERE elemento_id = ? AND stato = 'In Prestito'", (elemento_id,))
            if cursor.fetchone():
                flash("Questo volume risulta già attualmente in prestito!", "errore")
                return redirect(url_for("index"))

            cursor.execute("""
                INSERT INTO prestiti (elemento_id, nome_persona, data_prestito, data_rientro_prevista, stato)
                VALUES (?, ?, ?, ?, 'In Prestito')
            """, (elemento_id, nome_persona, data_prestito, data_rientro_prevista))

            titolo = elem['titolo']

        flash(f"Prestito registrato: '{titolo}' è stato prestato a {nome_persona}.", "successo")
        return redirect(url_for("index"))

    @app.route("/api/prestiti/<int:prestito_id>/rientro", methods=["POST"])
    def segna_rientro(prestito_id):
        data_oggi = date.today().strftime("%d/%m/%Y")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE prestiti
                SET stato = 'Rientrato', data_rientro_effettiva = ?
                WHERE id = ? AND stato = 'In Prestito'
            """, (data_oggi, prestito_id))

            cursor.execute("""
                SELECT e.titolo, p.nome_persona
                FROM prestiti p
                JOIN elementi e ON p.elemento_id = e.id
                WHERE p.id = ?
            """, (prestito_id,))
            row = cursor.fetchone()

        if row:
            flash(f"Bentornato! '{row['titolo']}' prestato a {row['nome_persona']} è ora di nuovo a casa.", "successo")
        else:
            flash("Il prestito è stato contrassegnato come rientrato.", "successo")

        return redirect(url_for("index"))
