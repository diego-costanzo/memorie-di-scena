# -*- coding: utf-8 -*-
"""
Fonti di ricerca della famiglia Wikimedia (tutte aperte, nessuna API key):
Wikiquote, Wikipedia, Wikisource e Wikidata.

Wikiquote   citazioni e battute: la fonte più utile per il teatro
Wikipedia   voci su opere e autori, con incipit celebri
Wikisource  testi integrali e copioni
Wikidata    schede di dati aperti (CC0), utili per disambiguare un titolo

Nessuna richiede registrazione. Tutte restituiscono `[]` in caso di errore e
non sollevano eccezioni: una fonte lenta non deve rallentare le altre.
"""
import urllib.parse

from .. import config
from ..http import get_api_session
from ..utils import pulisci_snippet


def cerca_wikiquote(frase, max_risultati=5):
    """Cerca su Wikiquote Italia (citazioni teatrali, battute, monologhi)."""
    risultati = []
    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://it.wikiquote.org/w/api.php?action=query&list=search&srsearch={q}&format=json"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for item in resp.json().get('query', {}).get('search', [])[:max_risultati]:
                titolo = item.get('title', '')
                snippet = pulisci_snippet(item.get('snippet', ''))
                link = f"https://it.wikiquote.org/wiki/{urllib.parse.quote(titolo.replace(' ', '_'))}"
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Citazione Teatrale / Letteraria',
                    'editore': 'Wikiquote',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikiquote Teatrale',
                    'fonte_icona': '🎭',
                })
    except Exception as e:
        print(f"[Wikiquote] Errore: {e}")
    return risultati


def cerca_wikipedia(frase, max_risultati=5):
    """Cerca su Wikipedia Italia (opere, incipit celebri, commedie e romanzi)."""
    risultati = []
    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://it.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for item in resp.json().get('query', {}).get('search', [])[:max_risultati]:
                titolo = item.get('title', '')
                snippet = pulisci_snippet(item.get('snippet', ''))
                link = f"https://it.wikipedia.org/wiki/{urllib.parse.quote(titolo.replace(' ', '_'))}"
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Opera Letteraria / Teatrale',
                    'editore': 'Wikipedia',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikipedia Letteraria',
                    'fonte_icona': '📖',
                })
    except Exception as e:
        print(f"[Wikipedia] Errore: {e}")
    return risultati


def cerca_wikisource(frase, max_risultati=4):
    """Cerca su Wikisource Italia (testi integrali e copioni teatrali)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://it.wikisource.org/w/api.php?action=query&list=search&srsearch={q}&format=json"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for item in resp.json().get('query', {}).get('search', [])[:max_risultati]:
                titolo = item.get('title', '')
                snippet = pulisci_snippet(item.get('snippet', ''))
                link = f"https://it.wikisource.org/wiki/{urllib.parse.quote(titolo.replace(' ', '_'))}"
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Testo Integrale / Copione Teatrale',
                    'editore': 'Wikisource (Biblioteca Libera)',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikisource Copioni & Testi',
                    'fonte_icona': '📜',
                })
    except Exception as e:
        print(f"[Wikisource] Errore: {e}")
    return risultati


def cerca_wikidata(frase, max_risultati=4):
    """Cerca su Wikidata (base di conoscenza libera, dati CC0)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = (
            "https://www.wikidata.org/w/api.php"
            f"?action=wbsearchentities&search={q}&language=it&uselang=it"
            f"&type=item&format=json&limit={max_risultati}"
        )
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for ent in resp.json().get('search', []):
                qid = ent.get('id', '')
                titolo = ent.get('label') or ent.get('id') or 'Elemento Wikidata'
                descrizione = (ent.get('description') or '').strip()
                link = f"https://www.wikidata.org/wiki/{qid}" if qid else "https://www.wikidata.org"
                snippet = (
                    f"{descrizione} — scheda di dati aperti (ID: {qid})."
                    if descrizione
                    else f"Scheda di dati aperti Wikidata (ID: {qid})."
                )
                risultati.append({
                    'titolo': titolo,
                    'autore': 'Opera o Voce Enciclopedica',
                    'editore': 'Wikidata (Dati Aperti CC0)',
                    'anno': '',
                    'snippet': snippet,
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Wikidata (Dati Aperti)',
                    'fonte_icona': '🔗',
                })
    except Exception as e:
        print(f"[Wikidata] Errore: {e}")
    return risultati
