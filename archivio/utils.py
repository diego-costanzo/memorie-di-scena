# -*- coding: utf-8 -*-
"""
Funzioni di utilità pure: testo, date e pulizia. Nessuna dipendenza da Flask o DB,
quindi facili da testare in isolamento.

DOVE VIENE USATO CIASCUN GRUPPO
-------------------------------
- `normalizza_testo` / `pattern_ricerca`: ricerca locale e diario. `normalizza`
  è registrata anche come funzione SQL in `db.get_db()`, quindi la stessa
  normalizzazione vale sia in Python sia dentro le query SQLite.
- `pulisci_snippet`: elimina i tag HTML che alcune API esterne restituiscono
  nei frammenti di testo (il risultato viene poi scopato di nuovo nel browser).
- `formatta_data_italiana`: intestazione dei fogli del Diario.
- `giorni_di_ritardo`: badge rosso dei prestiti nella pagina iniziale.

Se aggiungi una funzione qui, mantienila pura (nessun accesso a file, rete o
database) e aggiungi un test in `tests/test_smoke.py`.
"""
import html
import re
import unicodedata
from datetime import date, datetime


def normalizza_testo(testo):
    """
    Rende un testo insensibile a maiuscole/minuscole e agli accenti (utile per
    la ricerca: «perche» trova «perché», «E» trova «è»). Essenziale per chi
    cerca una citazione ricordandola a memoria, senza curarsi degli accenti.
    """
    if not testo:
        return ""
    testo = str(testo).lower()
    testo = unicodedata.normalize("NFD", testo)
    return "".join(c for c in testo if unicodedata.category(c) != "Mn")


def pattern_ricerca(frase):
    """
    Costruisce un pattern LIKE insensibile ad accenti/maiuscole e sicuro,
    trattando i metacaratteri % e _ come testo letterale (non come jolly).
    """
    norm = normalizza_testo(frase)
    norm = norm.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{norm}%"


def pulisci_snippet(testo):
    """Pulisce un frammento HTML rimuovendo tag e normalizzando spazi."""
    if not testo:
        return ""
    if not isinstance(testo, str):
        testo = str(testo)
    pulito = re.sub(r"<[^>]+>", "", testo)
    pulito = html.unescape(pulito).replace("\xa0", " ")
    return " ".join(pulito.split()).strip()


def formatta_data_italiana(dt=None):
    """Formatta la data in italiano elegante per i fogli di pergamena del Diario."""
    if dt is None:
        dt = datetime.now()
    giorni_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    mesi_it = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
               "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    giorno_sett = giorni_it[dt.weekday()]
    mese_str = mesi_it[dt.month]
    return f"{giorno_sett}, {dt.day} {mese_str} {dt.year} • ore {dt.strftime('%H:%M')}"


def giorni_di_ritardo(data_prevista, oggi=None):
    """
    Quanti giorni sono passati dalla data di rientro prevista.

    Restituisce 0 se la data manca, non è leggibile o non è ancora scaduta:
    così l'interfaccia non mostra mai un allarme per un dato incerto.
    """
    if not data_prevista:
        return 0
    if oggi is None:
        oggi = date.today()
    try:
        prevista = datetime.strptime(str(data_prevista).strip(), "%d/%m/%Y").date()
    except (ValueError, TypeError):
        return 0
    differenza = (oggi - prevista).days
    return differenza if differenza > 0 else 0
