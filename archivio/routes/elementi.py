# -*- coding: utf-8 -*-
"""
Rotte per la gestione degli elementi della collezione (libri, copioni, dischi).

ROTTE
-----
    POST /api/elementi                          crea una scheda
    POST /api/elementi/<id>/modifica            aggiorna una scheda
    POST /api/elementi/<id>/elimina             elimina scheda e copertina locale
    POST /api/elementi/<id>/aggiorna_copertina  cerca online una nuova copertina
    GET  /api/elementi/<id>/dettagli            JSON con scheda, prestiti e appunti
    POST /api/elementi/<id>/appunti             aggiunge un ricordo al taccuino
    POST /api/appunti/<id>/elimina              rimuove un ricordo
    GET  /esporta_inventario                    scarica tutto in CSV

NOTE PER CHI MODIFICA
---------------------
- I campi specifici (regista, formato, ecc.) vengono salvati solo se coerenti
  con il tipo scelto; gli altri restano NULL.
- Il percorso della copertina arriva dal client: viene sempre ridotto con
  `secure_filename` e verificato dentro `config.COVERS_DIR` per impedire il
  path traversal.
- La ricerca della copertina online avviene DOPO il commit della scheda, così
  una rete lenta non tiene aperta la transazione SQLite.
- Il CSV usa punto e virgola e BOM iniziale: senza BOM, LibreOffice mostrerebbe
  male gli accenti; senza `;`, l'italiano aprirebbe tutto in una sola colonna.
"""
import csv
import io
import os
from datetime import date, datetime

from flask import Response, flash, jsonify, redirect, request, url_for
from werkzeug.utils import secure_filename

from .. import config
from ..covers import scarica_copertina_web
from ..db import get_db


# Tipi ammessi dal CHECK della tabella `elementi` (vedi db.init_db).
# Qualunque altro valore verrebbe rifiutato da SQLite con un errore 500:
# qui si ripiega su 'Libro' per mantenere l'applicazione sempre utilizzabile.
TIPI_AMMESSI = ("Libro", "Copione", "CD / Vinile")


def _fallback_per_tipo(tipo):
    if tipo == 'Copione':
        return "/static/covers/default_copione.svg"
    if tipo == 'CD / Vinile':
        return "/static/covers/default_musica.svg"
    return "/static/covers/default_libro.svg"


def _percorso_copertina_locale(copertina_path):
    """Restituisce il path su disco se è una copertina locale non-SVG in COVERS_DIR."""
    if not copertina_path or not copertina_path.startswith("/static/covers/") or copertina_path.endswith(".svg"):
        return None
    nome_sicuro = secure_filename(os.path.basename(copertina_path))
    if not nome_sicuro:
        return None
    return os.path.join(config.COVERS_DIR, nome_sicuro)


def _rimuovi_copertina_se_orfana(cursor, copertina_path):
    """Elimina il file copertina locale solo se nessun altro elemento lo usa."""
    percorso_disco = _percorso_copertina_locale(copertina_path)
    if not percorso_disco or not os.path.isfile(percorso_disco):
        return
    cursor.execute("SELECT 1 FROM elementi WHERE copertina_path = ? LIMIT 1", (copertina_path,))
    if cursor.fetchone() is None:
        try:
            os.remove(percorso_disco)
        except OSError:
            pass


def _valore_csv(valore):
    """
    Prepara un valore per il foglio CSV neutralizzando le formule.

    LibreOffice ed Excel interpretano come formula una cella che inizia con
    `=`, `+`, `-` o `@`: un titolo come «=1+1» verrebbe calcolato invece di
    essere mostrato. Il prefisso con apostrofo è la convenzione accettata da
    entrambi i programmi per forzare il testo.
    """
    testo = "" if valore is None else str(valore)
    if testo.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + testo
    return testo


def register(app):
    @app.route("/api/elementi", methods=["POST"])
    def crea_elemento():
        tipo = request.form.get("tipo", "Libro").strip()
        if tipo not in TIPI_AMMESSI:
            tipo = "Libro"
        titolo = request.form.get("titolo", "").strip()
        autore = request.form.get("autore", "").strip()
        collocazione_casa = request.form.get("collocazione_casa", "").strip()
        note = request.form.get("note", "").strip()

        regista = request.form.get("regista", "").strip()
        prima_esibizione_luogo = request.form.get("prima_esibizione_luogo", "").strip()
        data_ingaggio = request.form.get("data_ingaggio", "").strip()
        data_prima = request.form.get("data_prima", "").strip()

        formato = request.form.get("formato", "").strip()
        etichetta_anno = request.form.get("etichetta_anno", "").strip()

        copertina_caricata = request.form.get("copertina_caricata", "").strip()

        if not titolo:
            flash("Attenzione: devi inserire almeno il titolo!", "errore")
            return redirect(url_for("index"))

        data_inserimento = date.today().strftime("%d/%m/%Y")
        fallback_path = _fallback_per_tipo(tipo)

        # Validazione sicura contro Path Traversal sul percorso copertina:
        # controlla che il nome non sia vuoto (es. '.', '..', '???') e sia un file reale.
        percorso_copertina = fallback_path
        if copertina_caricata:
            nome_file_sicuro = secure_filename(os.path.basename(copertina_caricata))
            if nome_file_sicuro and os.path.isfile(os.path.join(config.COVERS_DIR, nome_file_sicuro)):
                percorso_copertina = f"/static/covers/{nome_file_sicuro}"

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO elementi (
                    tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                    regista, prima_esibizione_luogo, data_ingaggio, data_prima,
                    formato, etichetta_anno
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tipo, titolo, autore, collocazione_casa, note, percorso_copertina, data_inserimento,
                regista if tipo == 'Copione' else None,
                prima_esibizione_luogo if tipo == 'Copione' else None,
                data_ingaggio if tipo == 'Copione' else None,
                data_prima if tipo == 'Copione' else None,
                formato if tipo == 'CD / Vinile' else None,
                etichetta_anno if tipo == 'CD / Vinile' else None
            ))
            nuovo_id = cursor.lastrowid

        # Recupero copertina online senza trattenere il lock sul database
        if percorso_copertina == fallback_path:
            copertina_recuperata = scarica_copertina_web(titolo, autore, tipo, nuovo_id)
            if copertina_recuperata != fallback_path:
                with get_db() as conn:
                    conn.cursor().execute("UPDATE elementi SET copertina_path = ? WHERE id = ?", (copertina_recuperata, nuovo_id))

        flash(f"'{titolo}' è stato inserito con successo nell'Archivio!", "successo")
        return redirect(url_for("index"))

    @app.route("/api/elementi/<int:elem_id>/modifica", methods=["POST"])
    def modifica_elemento(elem_id):
        titolo = request.form.get("titolo", "").strip()
        autore = request.form.get("autore", "").strip()
        collocazione_casa = request.form.get("collocazione_casa", "").strip()
        note = request.form.get("note", "").strip()
        regista = request.form.get("regista", "").strip()
        prima_esibizione_luogo = request.form.get("prima_esibizione_luogo", "").strip()
        data_ingaggio = request.form.get("data_ingaggio", "").strip()
        data_prima = request.form.get("data_prima", "").strip()
        formato = request.form.get("formato", "").strip()
        etichetta_anno = request.form.get("etichetta_anno", "").strip()

        if not titolo:
            flash("Il titolo non può essere vuoto!", "errore")
            return redirect(url_for("index"))

        with get_db() as conn:
            cursor = conn.cursor()
            # Il tipo è immutabile: leggiamo quello salvato per decidere quali
            # campi specifici aggiornare e quali azzerare, così una scheda
            # Libro non riceve mai regista/formato/etichetta da un form diverso.
            cursor.execute("SELECT tipo FROM elementi WHERE id = ?", (elem_id,))
            row = cursor.fetchone()
            if not row:
                flash("La scheda richiesta non esiste più o è stata eliminata.", "errore")
                return redirect(url_for("index"))
            tipo = row['tipo']

            cursor.execute("""
                UPDATE elementi
                SET titolo = ?, autore = ?, collocazione_casa = ?, note = ?,
                    regista = ?, prima_esibizione_luogo = ?, data_ingaggio = ?, data_prima = ?,
                    formato = ?, etichetta_anno = ?
                WHERE id = ?
            """, (
                titolo, autore, collocazione_casa, note,
                regista if tipo == 'Copione' else None,
                prima_esibizione_luogo if tipo == 'Copione' else None,
                data_ingaggio if tipo == 'Copione' else None,
                data_prima if tipo == 'Copione' else None,
                formato if tipo == 'CD / Vinile' else None,
                etichetta_anno if tipo == 'CD / Vinile' else None,
                elem_id
            ))

        flash(f"Le modifiche a '{titolo}' sono state salvate!", "successo")
        return redirect(url_for("index"))

    @app.route("/api/elementi/<int:elem_id>/elimina", methods=["POST"])
    def elimina_elemento(elem_id):
        titolo = ""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT titolo, copertina_path FROM elementi WHERE id = ?", (elem_id,))
            row = cursor.fetchone()
            if row:
                titolo = row['titolo']
                copertina = row['copertina_path']
                cursor.execute("DELETE FROM elementi WHERE id = ?", (elem_id,))
                _rimuovi_copertina_se_orfana(cursor, copertina)

        if titolo:
            flash(f"'{titolo}' è stato rimosso dall'archivio.", "info")
        else:
            # Nessuna riga trovata: l'ID non esiste (già eliminato da un'altra
            # scheda o da un URL non valido). Evitiamo il finto successo.
            flash("La scheda da eliminare non esiste più.", "errore")
        return redirect(url_for("index"))

    @app.route("/api/elementi/<int:elem_id>/aggiorna_copertina", methods=["POST"])
    def aggiorna_copertina(elem_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT titolo, autore, tipo, copertina_path FROM elementi WHERE id = ?", (elem_id,))
            row = cursor.fetchone()

        if not row:
            flash("La scheda richiesta non esiste più o è stata eliminata.", "errore")
            return redirect(url_for("index"))

        fallback_path = _fallback_per_tipo(row['tipo'])
        vecchia_copertina = row['copertina_path']
        nuova_copertina = scarica_copertina_web(row['titolo'], row['autore'], row['tipo'], elem_id)

        # Non sovrascrivere una foto/copertina locale esistente con il segnaposto SVG
        # se la ricerca online non ha trovato nulla o il PC è offline.
        vecchia_locale = _percorso_copertina_locale(vecchia_copertina)
        if nuova_copertina == fallback_path and vecchia_locale and os.path.isfile(vecchia_locale):
            flash(
                f"Nessuna nuova copertina trovata online per '{row['titolo']}': la copertina attuale è stata mantenuta.",
                "info",
            )
            return redirect(url_for("index"))

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE elementi SET copertina_path = ? WHERE id = ?", (nuova_copertina, elem_id))
            if vecchia_copertina and vecchia_copertina != nuova_copertina:
                _rimuovi_copertina_se_orfana(cursor, vecchia_copertina)
        flash(f"Copertina aggiornata per '{row['titolo']}'!", "successo")
        return redirect(url_for("index"))

    @app.route("/api/elementi/<int:elem_id>/dettagli", methods=["GET"])
    def dettagli_elemento(elem_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM elementi WHERE id = ?", (elem_id,))
            elem = cursor.fetchone()
            if not elem:
                return jsonify({"errore": "Elemento non trovato"}), 404

            cursor.execute("""
                SELECT nome_persona, data_prestito, data_rientro_prevista, data_rientro_effettiva, stato
                FROM prestiti
                WHERE elemento_id = ?
                ORDER BY id DESC
            """, (elem_id,))
            storico = [dict(r) for r in cursor.fetchall()]

            cursor.execute("""
                SELECT id, testo, data_creazione
                FROM appunti
                WHERE elemento_id = ?
                ORDER BY id DESC
            """, (elem_id,))
            appunti_list = [dict(r) for r in cursor.fetchall()]

        dati = dict(elem)
        dati['storico_prestiti'] = storico
        dati['appunti'] = appunti_list
        return jsonify(dati)

    @app.route("/api/elementi/<int:elem_id>/appunti", methods=["POST"])
    def aggiungi_appunto(elem_id):
        testo = request.form.get("testo", "").strip()
        if not testo:
            flash("Scrivi un pensiero o una citazione prima di salvare!", "errore")
            return redirect(url_for("index"))

        data_creazione = datetime.now().strftime("%d/%m/%Y alle %H:%M")
        with get_db() as conn:
            cursor = conn.cursor()
            # Verifichiamo che la scheda esista: senza questo controllo
            # l'INSERT violerebbe la FOREIGN KEY e genererebbe un errore 500.
            cursor.execute("SELECT 1 FROM elementi WHERE id = ?", (elem_id,))
            if cursor.fetchone() is None:
                flash("Impossibile aggiungere il ricordo: la scheda non esiste più.", "errore")
                return redirect(url_for("index"))
            cursor.execute("""
                INSERT INTO appunti (elemento_id, testo, data_creazione)
                VALUES (?, ?, ?)
            """, (elem_id, testo, data_creazione))

        flash("Il tuo ricordo è stato annotato con cura nel taccuino!", "successo")
        return redirect(url_for("index"))

    @app.route("/api/appunti/<int:appunto_id>/elimina", methods=["POST"])
    def elimina_appunto(appunto_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM appunti WHERE id = ?", (appunto_id,))
            eliminato = cursor.rowcount > 0

        if eliminato:
            flash("Appunto rimosso dal taccuino.", "info")
        else:
            flash("L'appunto richiesto non esiste più.", "errore")
        return redirect(url_for("index"))

    @app.route("/esporta_inventario")
    def esporta_inventario():
        """
        Scarica l'inventario completo come foglio CSV, apribile con LibreOffice
        o stampabile. Il punto e virgola è il separatore atteso dai programmi in
        italiano; il BOM iniziale permette gli accenti corretti senza impostazioni.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    e.tipo, e.titolo, e.autore, e.collocazione_casa, e.note,
                    e.regista, e.prima_esibizione_luogo, e.data_prima, e.data_ingaggio,
                    e.formato, e.etichetta_anno,
                    p.nome_persona AS in_prestito_a,
                    p.data_prestito,
                    p.data_rientro_prevista
                FROM elementi e
                LEFT JOIN prestiti p ON e.id = p.elemento_id AND p.stato = 'In Prestito'
                ORDER BY e.tipo, e.autore, e.titolo
            """)
            righe = cursor.fetchall()

        buffer = io.StringIO()
        scrittore = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        scrittore.writerow([
            "Tipo", "Titolo", "Autore / Artista", "Dove si trova", "Note",
            "Regista", "Teatro della prima", "Data della prima", "Data ingaggio",
            "Formato", "Etichetta e anno", "In prestito a", "Prestato il", "Rientro previsto",
        ])
        for riga in righe:
            scrittore.writerow([
                _valore_csv(riga["tipo"]),
                _valore_csv(riga["titolo"]),
                _valore_csv(riga["autore"]),
                _valore_csv(riga["collocazione_casa"]),
                _valore_csv(riga["note"]),
                _valore_csv(riga["regista"]),
                _valore_csv(riga["prima_esibizione_luogo"]),
                _valore_csv(riga["data_prima"]),
                _valore_csv(riga["data_ingaggio"]),
                _valore_csv(riga["formato"]),
                _valore_csv(riga["etichetta_anno"]),
                _valore_csv(riga["in_prestito_a"]),
                _valore_csv(riga["data_prestito"]),
                _valore_csv(riga["data_rientro_prevista"]),
            ])

        contenuto = "\ufeff" + buffer.getvalue()
        nome = f"inventario_memorie_di_scena_{date.today().strftime('%d-%m-%Y')}.csv"
        risposta = Response(contenuto, mimetype="text/csv; charset=utf-8")
        risposta.headers["Content-Disposition"] = f'attachment; filename="{nome}"'
        return risposta
