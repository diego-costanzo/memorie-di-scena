# -*- coding: utf-8 -*-
"""
Rotta per la ricerca per citazione (Bussola Culturale).

ROTTA
-----
    POST /api/ricerca_citazione   accetta JSON {"frase": "..."}

CONTRATTO DELLA RISPOSTA
------------------------
    success            true/false
    frase_cercata      frase ripulita usata nella ricerca
    totale_risultati   numero di risultati
    risultati          elenco di schede (vedi `search/__init__.py`)
    suggerimento       testo di aiuto quando non si trova nulla

VALIDAZIONE
-----------
- Frase vuota o più corta di 3 caratteri → 400 con messaggio in italiano.
- Oltre 500 caratteri → viene troncata, per non sovraccaricare le API esterne.
- Qualunque errore interno diventa un 500 con messaggio generico: i dettagli
  tecnici restano nel terminale, non nella pagina dell'utente.
"""
from flask import jsonify, request

from ..search import ricerca_per_citazione


def register(app):
    @app.route("/api/ricerca_citazione", methods=["POST"])
    def api_ricerca_citazione():
        dati = request.get_json(silent=True)
        if not isinstance(dati, dict):
            dati = {}
        frase_raw = dati.get("frase", "")
        frase = frase_raw.strip() if isinstance(frase_raw, str) else ""

        if not frase:
            return jsonify({"success": False, "errore": "Inserisci una frase o alcune parole chiave per cercare."}), 400

        if len(frase) < 3:
            return jsonify({"success": False, "errore": "La frase è troppo corta. Scrivi almeno 3 caratteri."}), 400

        # Limite di sicurezza sulla lunghezza dell'input
        if len(frase) > 500:
            frase = frase[:500]

        try:
            risultati = ricerca_per_citazione(frase)
            return jsonify({
                "success": True,
                "frase_cercata": frase,
                "totale_risultati": len(risultati),
                "risultati": risultati,
                "suggerimento": (
                    "💡 La ricerca per frase funziona meglio se ricordi 3-4 parole consecutive e distintive. "
                    "Google Books cerca anche dentro il testo dei libri!"
                ) if len(risultati) == 0 else ""
            })
        except Exception as e:
            print(f"[API Ricerca Citazione] Errore: {e}")
            return jsonify({
                "success": False,
                "errore": "Si è verificato un errore durante la ricerca. Riprova fra qualche istante."
            }), 500
