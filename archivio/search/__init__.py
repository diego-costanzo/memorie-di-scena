# -*- coding: utf-8 -*-
"""
Orchestratore della "Bussola Culturale".

Interroga in parallelo la ricerca locale e 13 fonti esterne, poi raggruppa,
deduplica e ordina i risultati per rilevanza.

CONTRATTO DI UN RISULTATO
-------------------------
Ogni funzione di ricerca restituisce una lista di dizionari con queste chiavi
(le mancanti possono essere stringa vuota):

    titolo, autore, editore, anno, snippet,
    copertina_url, lingua, pagine, link_info, anteprima_link,
    fonte, fonte_icona,
    in_archivio (solo locale: True se è già nella collezione),
    elemento_id / diario_id (solo locale: per aprire la scheda giusta)

Il browser riceve questi campi così come sono: `static/js/app.js` li scappa
prima di inserirli nella pagina (escapeHtml / urlSicuro).

COME AGGIUNGERE UNA FONTE ESTERNA
---------------------------------
1. Creare la funzione in un modulo `sources_*.py` con firma
   `cerca_nome(frase, max_risultati=4)`; restituire `[]` in caso di errore e
   non sollevare eccezioni.
2. Usare `get_api_session()` e `config.API_TIMEOUT` (vedi `http.py`).
3. Aggiungere una riga nel dizionario `futures` qui sotto: da quel momento la
   fonte viene interrogata in parallelo, con deduplica e ordinamento automatici.
4. Scegliere solo servizi aperti o con dati liberi: niente API proprietarie.

ORDINE DI RISPOSTA
------------------
1. Risultati locali (collezione, taccuino, diario): sempre in cima.
2. Risultati online: ordinati per `punteggio_rilevanza`, poi per titolo.

CACHE
-----
Si salvano in cache SOLO i risultati online (24 ore, vedi `cache.py`). I
risultati locali vengono ricalcolati a ogni ricerca, perché cambiano quando
l'utente modifica la propria collezione.
"""
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import config
from ..utils import normalizza_testo
from .cache import cache_key, leggi_cache, scrivi_cache
from .local import cerca_locale
from .sources_books import (
    cerca_google_books,
    cerca_gutenberg,
    cerca_internet_archive,
    cerca_librivox,
    cerca_open_library,
)
from .sources_italy import cerca_liber_liber, cerca_opac_sbn
from .sources_meta import cerca_crossref, cerca_musicbrainz
from .sources_wiki import (
    cerca_wikidata,
    cerca_wikipedia,
    cerca_wikiquote,
    cerca_wikisource,
)

# Pool persistente condiviso: permette a `http.py` di riusare le sessioni HTTP
# per-thread tra ricerche successive invece di crearne e abbandonarne di nuove.
_POOL_LOCK = threading.Lock()
_EXECUTOR = None


def _get_executor():
    global _EXECUTOR
    if _EXECUTOR is None:
        with _POOL_LOCK:
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(
                    max_workers=config.MAX_WORKERS,
                    thread_name_prefix="bussola",
                )
                atexit.register(_EXECUTOR.shutdown, wait=False)
    return _EXECUTOR


def punteggio_rilevanza(r, frase_norm):
    """
    Assegna un punteggio di rilevanza: premia i risultati con un frammento di testo
    effettivo e quelli in cui la frase cercata compare (tutta o nel titolo).
    """
    punteggio = 0
    titolo = normalizza_testo(r.get('titolo') or '')
    snippet = normalizza_testo(r.get('snippet') or '')

    if snippet:
        punteggio += 40
    if frase_norm and frase_norm in snippet:
        punteggio += 30
    if frase_norm and frase_norm in titolo:
        punteggio += 20

    return punteggio


def ricerca_per_citazione(frase, max_per_fonte=4):
    """
    1. Cerca immediatamente nella libreria e nel taccuino locale.
    2. Interroga in parallelo 13 fonti esterne (tutte open source / dati aperti).
    3. Deduplica, ordina per rilevanza e salva in cache su disco per 24h.
    """
    if not frase:
        return []

    # Pulizia frase da virgolette tipografiche accidentali prima di verificarne la lunghezza.
    frase_pulita = frase.strip().strip('«»""''“”').strip()
    if len(frase_pulita) < 3:
        return []

    # Controlla cache su disco per query online
    chiave = cache_key(frase_pulita)
    cached = leggi_cache(chiave)
    if cached is not None:
        locali = cerca_locale(frase_pulita)
        return locali + [r for r in cached if not r.get('in_archivio')]

    # 1. Ricerca locale immediata (0 ms)
    risultati_locali = cerca_locale(frase_pulita)

    # 2. Ricerca in parallelo sui database esterni tramite pool persistente
    risultati_online = []
    executor = _get_executor()
    futures = {
        executor.submit(cerca_wikiquote, frase_pulita, max_per_fonte): 'Wikiquote',
        executor.submit(cerca_wikipedia, frase_pulita, max_per_fonte): 'Wikipedia',
        executor.submit(cerca_wikisource, frase_pulita, max_per_fonte): 'Wikisource',
        executor.submit(cerca_wikidata, frase_pulita, max_per_fonte): 'Wikidata',
        executor.submit(cerca_opac_sbn, frase_pulita, max_per_fonte): 'OPAC SBN',
        executor.submit(cerca_musicbrainz, frase_pulita, max_per_fonte): 'MusicBrainz',
        executor.submit(cerca_liber_liber, frase_pulita, max_per_fonte): 'Liber Liber',
        executor.submit(cerca_crossref, frase_pulita, max_per_fonte): 'Crossref',
        executor.submit(cerca_gutenberg, frase_pulita, max_per_fonte): 'Project Gutenberg',
        executor.submit(cerca_librivox, frase_pulita, max_per_fonte): 'LibriVox',
        executor.submit(cerca_google_books, frase_pulita, max_per_fonte): 'Google Books',
        executor.submit(cerca_open_library, frase_pulita, max_per_fonte): 'Open Library',
        executor.submit(cerca_internet_archive, frase_pulita, max_per_fonte): 'Internet Archive',
    }

    for future in as_completed(futures):
        nome_fonte = futures[future]
        try:
            risultati_fonte = future.result()
            risultati_online.extend(risultati_fonte)
        except Exception as e:
            print(f"[Ricerca {nome_fonte}] Errore: {e}")

    # Deduplicazione risultati online: usa titolo normalizzato (e non un prefisso
    # corto che farebbe collidere sottotitoli o record senza titolo).
    visti = {}
    online_unici = []
    for r in risultati_online:
        titolo_norm = " ".join((r.get('titolo') or '').lower().split())
        chiave_dedup = titolo_norm if titolo_norm else f"__vuoto_{len(online_unici)}"

        if chiave_dedup not in visti:
            visti[chiave_dedup] = r
            online_unici.append(r)
        elif r.get('snippet') and not visti[chiave_dedup].get('snippet'):
            idx = online_unici.index(visti[chiave_dedup])
            online_unici[idx] = r
            visti[chiave_dedup] = r

    # Ordina per rilevanza: prima i frammenti di testo che contengono davvero la frase
    # cercata (anche senza accenti), poi i risultati con snippet, infine per titolo.
    frase_norm = normalizza_testo(frase_pulita)
    online_unici.sort(
        key=lambda x: (-punteggio_rilevanza(x, frase_norm), (x.get('titolo') or '').lower())
    )

    # Salva i soli risultati online in cache
    scrivi_cache(chiave, online_unici)

    # I risultati locali compaiono SEMPRE in cima!
    return risultati_locali + online_unici
