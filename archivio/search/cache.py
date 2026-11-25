# -*- coding: utf-8 -*-
"""
Cache su disco delle ricerche online (24 ore).

FORMATO
-------
Un file JSON per frase cercata: `data/cache/ricerca_<md5>.json`.
La chiave è l'MD5 della frase normalizzata (minuscole, spazi compattati):
la stessa domanda scritta in modo leggermente diverso riusa il risultato.

PERCHÉ SU DISCO E NON IN MEMORIA
--------------------------------
Il programma viene chiuso e riaperto spesso (è un taccuino di casa): la cache
su disco evita di interrogare di nuovo 13 servizi esterni per la stessa frase.

REGOLE
------
- La cache contiene SOLO risultati online, mai quelli locali (che cambiano).
- Ogni errore di lettura/scrittura viene ignorato: la cache è un'ottimizzazione,
  non un requisito. Se il disco è pieno o il file è corrotto, la ricerca
  funziona comunque.
- `pulisci_cache_scaduta()` viene chiamata all'avvio da `app.py`.
"""
import hashlib
import json
import os
from datetime import datetime

from .. import config


def cache_key(frase):
    """Genera una chiave di cache sicura e deterministica per una frase di ricerca."""
    normalizzata = " ".join(frase.lower().split())
    return hashlib.md5(normalizzata.encode('utf-8')).hexdigest()


def leggi_cache(chiave):
    """Legge un risultato dalla cache su disco, se esiste e non è scaduto."""
    path = os.path.join(config.CACHE_DIR, f"ricerca_{chiave}.json")
    try:
        if os.path.exists(path):
            eta_file = datetime.now().timestamp() - os.path.getmtime(path)
            if eta_file < config.CACHE_EXPIRY_SEC:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    except Exception:
        pass
    return None


def scrivi_cache(chiave, dati):
    """Salva un risultato nella cache su disco."""
    path = os.path.join(config.CACHE_DIR, f"ricerca_{chiave}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(dati, f, ensure_ascii=False)
    except Exception:
        pass


def pulisci_cache_scaduta():
    """Rimuove automaticamente i file temporanei di cache più vecchi di 24 ore."""
    try:
        if os.path.exists(config.CACHE_DIR):
            ora = datetime.now().timestamp()
            for f in os.listdir(config.CACHE_DIR):
                # Elimina solo i risultati di ricerca, mai aggiornamento.json.
                if f.startswith('ricerca_') and f.endswith('.json'):
                    fp = os.path.join(config.CACHE_DIR, f)
                    if ora - os.path.getmtime(fp) > config.CACHE_EXPIRY_SEC:
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
    except Exception:
        pass
