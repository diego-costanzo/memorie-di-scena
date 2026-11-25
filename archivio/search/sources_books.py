# -*- coding: utf-8 -*-
"""
Fonti di ricerca librarie digitali (aperte o di pubblico dominio):
Google Books, Open Library, Internet Archive, Project Gutenberg e LibriVox.

FONTE                  COSA AGGIUNGE                          LICENZA / DATI
Google Books           testo completo dei libri digitalizzati  metadati API
Open Library           catalogo mondiale + copertine           dati aperti
Internet Archive       scansioni e testi storici               pubblico dominio
Project Gutenberg      classici integrali                      pubblico dominio
LibriVox               audiolibri letti da volontari           pubblico dominio

Ogni funzione restituisce `[]` se il servizio non risponde: nessuna eccezione
arriva all'orchestratore. Il timeout è `config.API_TIMEOUT`, tranne Gutenberg
che usa 2 secondi perché il servizio gratuito può essere lento.
"""
import urllib.parse

from .. import config
from ..http import get_api_session
from ..utils import pulisci_snippet


def cerca_google_books(frase, max_risultati=5):
    """Cerca in Google Books (full-text nel corpo dei libri digitalizzati)."""
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q={query}&maxResults={max_risultati}&printType=books"
            "&langRestrict=it&orderBy=relevance"
        )
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            dati = resp.json()
            for item in dati.get('items') or []:
                info = item.get('volumeInfo') or {}
                ricerca_info = item.get('searchInfo') or {}
                snippet = pulisci_snippet(ricerca_info.get('textSnippet') or '')
                immagini = info.get('imageLinks') or {}
                copertina_url = immagini.get('thumbnail', '') or immagini.get('smallThumbnail', '')
                if copertina_url and copertina_url.startswith('http:'):
                    copertina_url = copertina_url.replace('http:', 'https:', 1)

                autori = info.get('authors') or ['Autore non indicato']
                risultati.append({
                    'titolo': info.get('title') or 'Titolo sconosciuto',
                    'autore': ', '.join(str(a) for a in autori if a) or 'Autore non indicato',
                    'editore': info.get('publisher') or '',
                    'anno': (info.get('publishedDate') or '')[:4],
                    'snippet': snippet,
                    'copertina_url': copertina_url,
                    'lingua': info.get('language') or '',
                    'pagine': info.get('pageCount') or '',
                    'link_info': info.get('infoLink') or '',
                    'anteprima_link': info.get('previewLink') or '',
                    'fonte': 'Google Books',
                    'fonte_icona': '📚',
                })
    except Exception as e:
        print(f"[Google Books] Errore: {e}")
    return risultati


def cerca_open_library(frase, max_risultati=5):
    """Cerca in Open Library (Internet Archive)."""
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            "https://openlibrary.org/search.json"
            f"?q={query}&limit={max_risultati}"
            "&fields=title,author_name,publisher,first_publish_year,cover_i,key,language,number_of_pages_median"
        )
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            dati = resp.json()
            for doc in dati.get('docs') or []:
                cover_id = doc.get('cover_i')
                copertina_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ''
                chiave_opera = doc.get('key') or ''
                link_info = f"https://openlibrary.org{chiave_opera}" if chiave_opera else ''
                autori = doc.get('author_name') or ['Autore non indicato']
                editori = doc.get('publisher') or []
                lingue = doc.get('language') or []
                risultati.append({
                    'titolo': doc.get('title') or 'Titolo sconosciuto',
                    'autore': ', '.join(str(a) for a in autori if a) or 'Autore non indicato',
                    'editore': ', '.join(str(e) for e in editori[:2] if e),
                    'anno': str(doc.get('first_publish_year')) if doc.get('first_publish_year') else '',
                    'snippet': '',
                    'copertina_url': copertina_url,
                    'lingua': ', '.join(str(l) for l in lingue[:3] if l),
                    'pagine': doc.get('number_of_pages_median') or '',
                    'link_info': link_info,
                    'anteprima_link': '',
                    'fonte': 'Open Library',
                    'fonte_icona': '🏛️',
                })
    except Exception as e:
        print(f"[Open Library] Errore: {e}")
    return risultati


def cerca_internet_archive(frase, max_risultati=5):
    """Cerca nei testi scansionati dell'Internet Archive."""
    risultati = []
    try:
        query = urllib.parse.quote_plus(frase.strip())
        url = (
            "https://archive.org/advancedsearch.php"
            f"?q={query}+AND+mediatype%3Atexts"
            "&fl[]=title&fl[]=creator&fl[]=publisher&fl[]=year"
            "&fl[]=identifier&fl[]=description"
            f"&rows={max_risultati}&output=json"
        )
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            docs = (resp.json().get('response') or {}).get('docs') or []
            for doc in docs:
                identifier = str(doc.get('identifier') or '').strip()
                id_enc = urllib.parse.quote(identifier, safe='') if identifier else ''
                link_info = f"https://archive.org/details/{id_enc}" if id_enc else ''
                copertina_url = f"https://archive.org/services/img/{id_enc}" if id_enc else ''
                desc_raw = doc.get('description') or ''
                if isinstance(desc_raw, list):
                    desc_raw = ' '.join(str(x) for x in desc_raw)
                descrizione = pulisci_snippet(desc_raw)
                if len(descrizione) > 200:
                    descrizione = descrizione[:200].rsplit(' ', 1)[0] + '…'
                autore = doc.get('creator') or 'Autore non indicato'
                if isinstance(autore, list):
                    autore = ', '.join(str(a) for a in autore[:3] if a) or 'Autore non indicato'
                editore = doc.get('publisher') or ''
                if not isinstance(editore, str):
                    editore = ''
                risultati.append({
                    'titolo': doc.get('title') or 'Titolo sconosciuto',
                    'autore': autore,
                    'editore': editore,
                    'anno': str(doc.get('year')) if doc.get('year') else '',
                    'snippet': descrizione,
                    'copertina_url': copertina_url,
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link_info,
                    'anteprima_link': f"https://archive.org/stream/{id_enc}" if id_enc else '',
                    'fonte': 'Internet Archive',
                    'fonte_icona': '🗄️',
                })
    except Exception as e:
        print(f"[Internet Archive] Errore: {e}")
    return risultati


def cerca_gutenberg(frase, max_risultati=3):
    """Cerca nel catalogo di Project Gutenberg (classici di pubblico dominio)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://gutendex.com/books/?search={q}"
        # Timeout breve a 2 secondi per salvaguardare la fluidità complessiva
        resp = get_api_session().get(url, timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            for b in (data.get('results') or [])[:max_risultati]:
                titolo = b.get('title') or 'Senza titolo'
                authors = [a.get('name', '') for a in (b.get('authors') or []) if isinstance(a, dict) and a.get('name')]
                autore = ', '.join(authors) if authors else 'Autore non indicato'
                formats = b.get('formats') or {}
                copertina = formats.get('image/jpeg', '')
                ebook_id = b.get('id')
                link = f"https://www.gutenberg.org/ebooks/{ebook_id}" if ebook_id else ''
                read_link = formats.get('text/html') or formats.get('text/plain; charset=utf-8') or ''
                lingue = b.get('languages') or ['it']

                risultati.append({
                    'titolo': titolo,
                    'autore': autore,
                    'editore': 'Project Gutenberg (Pubblico Dominio)',
                    'anno': '',
                    'snippet': "Opera classica mondiale di pubblico dominio. Testo integrale scaricabile e consultabile online gratuitamente.",
                    'copertina_url': copertina,
                    'lingua': ', '.join(str(l) for l in lingue if l) or 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': read_link,
                    'fonte': 'Project Gutenberg',
                    'fonte_icona': '🌐',
                })
    except Exception:
        # Se il server gratuito Gutendex è momentaneamente lento, cede il passo alle altre fonti
        pass
    return risultati


def cerca_librivox(frase, max_risultati=3):
    """Cerca su LibriVox (audiolibri di pubblico dominio letti da voci umane)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    pulita = frase.strip()
    # LibriVox usa "^" come "titolo che inizia con": prima prova con tutta la frase,
    # poi ripiega sulla prima parola significativa (es. «Divina» per «Divina Commedia»).
    prima_parola = pulita.split()[0] if pulita.split() else ''
    articoli = {"il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "the", "a", "an"}
    tentativi = [pulita]
    if prima_parola and prima_parola.lower() not in articoli and prima_parola != pulita:
        tentativi.append(prima_parola)

    try:
        for tentativo in tentativi:
            q = urllib.parse.quote_plus("^" + tentativo)
            url = f"https://librivox.org/api/feed/audiobooks?format=json&title={q}&limit={max_risultati}"
            resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
            if resp.status_code != 200:
                continue
            for b in resp.json().get('books', [])[:max_risultati]:
                titolo = b.get('title', 'Senza titolo')
                authors = b.get('authors', [])
                nomi = []
                if isinstance(authors, list):
                    for a in authors:
                        if isinstance(a, dict):
                            nome = f"{a.get('first_name', '')} {a.get('last_name', '')}".strip()
                            if nome:
                                nomi.append(nome)
                autore = ', '.join(nomi) if nomi else 'Autore non indicato'
                lingua = b.get('language', '') or 'it'
                durata = b.get('totaltime', '')
                link = b.get('url_librivox', '')
                testo_link = b.get('url_text_source', '')

                risultati.append({
                    'titolo': titolo,
                    'autore': autore,
                    'editore': f"Audiolibro di pubblico dominio • {lingua}",
                    'anno': '',
                    'snippet': f"Audiolibro gratuito di pubblico dominio (LibriVox). Durata: {durata}. Ascoltabile online o scaricabile liberamente.",
                    'copertina_url': '',
                    'lingua': lingua,
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': testo_link,
                    'fonte': 'LibriVox (Audiolibri Liberi)',
                    'fonte_icona': '🎧',
                })
            if risultati:
                break
    except Exception as e:
        print(f"[LibriVox] Errore: {e}")
    return risultati
