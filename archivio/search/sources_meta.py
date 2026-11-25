# -*- coding: utf-8 -*-
"""
Fonti di metadati e studi: MusicBrainz (dischi/vinili) e Crossref (saggi critici).

MusicBrainz  enciclopedia musicale aperta; richiede un User-Agent con contatto
             (vedi la funzione) e restituisce anche il collegamento alla
             copertina su Cover Art Archive.
Crossref     DOI e pubblicazioni accademiche: utile per saggi e studi critici
             su un autore o un'opera.

Entrambe restituiscono `[]` in caso di errore e non sollevano eccezioni.
"""
import urllib.parse

from .. import config
from ..http import get_api_session


def cerca_musicbrainz(frase, max_risultati=4):
    """Cerca su MusicBrainz (enciclopedia musicale libera mondiale)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://musicbrainz.org/ws/2/release?query={q}&fmt=json&limit={max_risultati}"
        # MusicBrainz richiede esplicitamente User-Agent con info contatto
        headers = {'User-Agent': 'MemorieDiScenaApp/2.3 (https://github.com/progetto; info@memoriediscena.local)'}
        resp = get_api_session().get(url, headers=headers, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for rel in resp.json().get('releases', [])[:max_risultati]:
                titolo = rel.get('title', 'Senza titolo')
                artist_list = [a.get('name', '') for a in rel.get('artist-credit', []) if isinstance(a, dict) and 'name' in a]
                artista = ', '.join(artist_list) or 'Artista non indicato'
                anno = (rel.get('date') or '')[:4]
                mbid = rel.get('id', '')
                media = rel.get('media', [])
                formato = media[0].get('format', 'Disco / Vinile') if media else 'Disco'

                label_info = rel.get('label-info-list', [])
                etichetta = ''
                if label_info and isinstance(label_info, list):
                    label_obj = label_info[0].get('label')
                    if label_obj and isinstance(label_obj, dict):
                        etichetta = label_obj.get('name', '')

                info_editore = f"{formato} • {etichetta}" if etichetta else formato
                copertina = f"https://coverartarchive.org/release/{mbid}/front-250" if mbid else ''
                link = f"https://musicbrainz.org/release/{mbid}" if mbid else ''

                risultati.append({
                    'titolo': titolo,
                    'autore': artista,
                    'editore': info_editore,
                    'anno': anno,
                    'snippet': f"Disco musicale ({formato}). Anno: {anno or 'non indicato'}. Interprete/Autore: {artista}.",
                    'copertina_url': copertina,
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'MusicBrainz (Dischi & Vinili)',
                    'fonte_icona': '🎵',
                })
    except Exception as e:
        print(f"[MusicBrainz] Errore: {e}")
    return risultati


def cerca_crossref(frase, max_risultati=3):
    """Cerca su Crossref (saggi critici, monografie e pubblicazioni accademiche)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://api.crossref.org/works?query.bibliographic={q}&rows={max_risultati}"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            items = (resp.json().get('message') or {}).get('items') or []
            for it in items:
                titles = it.get('title') or []
                titolo = titles[0] if titles else 'Titolo sconosciuto'
                authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in (it.get('author') or []) if isinstance(a, dict)]
                autore = ', '.join(a for a in authors if a) if authors else 'Autore / Critico teatrale'
                publisher = it.get('publisher') or ''
                pub_print = it.get('published-print') or {}
                pub_online = it.get('published-online') or {}
                date_parts = pub_print.get('date-parts') or pub_online.get('date-parts') or []
                anno = str(date_parts[0][0]) if date_parts and date_parts[0] else ''
                doi = it.get('DOI') or ''
                link = f"https://doi.org/{urllib.parse.quote(doi, safe='/:.-_')}" if doi else (it.get('URL') or '')

                risultati.append({
                    'titolo': titolo,
                    'autore': autore,
                    'editore': f"Studio critico: {publisher}" if publisher else 'Saggio / Monografia',
                    'anno': anno,
                    'snippet': f"Studio critico e saggio di approfondimento d'autore (DOI: {doi or 'N/D'}). Ideale per ricerca e studio drammaturgico.",
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Crossref (Saggi & Studi Critici)',
                    'fonte_icona': '🔬',
                })
    except Exception as e:
        print(f"[Crossref] Errore: {e}")
    return risultati
