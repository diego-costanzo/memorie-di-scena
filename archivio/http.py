# -*- coding: utf-8 -*-
"""
Sessione HTTP per-thread.

requests.Session NON è thread-safe: ogni thread (server multi-thread + pool per
le ricerche parallele) usa la propria sessione con pooling delle connessioni,
senza rischi di corruzione dello stato.

USO NEI MODULI DI RICERCA
-------------------------
    from ..http import get_api_session
    risposta = get_api_session().get(url, timeout=config.API_TIMEOUT)

Non creare `requests.get(...)` diretti: si perderebbe il pooling delle
connessioni e l'User-Agent identificativo richiesto da alcuni servizi
(MusicBrainz in particolare). Il timeout va sempre passato dal chiamante.
"""
import threading

import requests

_local = threading.local()


def get_api_session():
    sessione = getattr(_local, "sessione", None)
    if sessione is None:
        sessione = requests.Session()
        sessione.headers.update({
            'User-Agent': 'MemorieDiScena/2.3 (Debian GNU/Linux; Archivio Teatrale; https://github.com; info@memoriediscena.local)',
            'Accept': 'application/json',
        })
        _local.sessione = sessione
    return sessione
