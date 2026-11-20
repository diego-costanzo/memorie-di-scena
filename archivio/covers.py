# -*- coding: utf-8 -*-
"""
Recupero copertine dal web, con fallback su eleganti SVG classici se offline.

ORDINE DEI TENTATIVI (si ferma al primo successo)
-------------------------------------------------
1. CD / Vinile  → MusicBrainz, poi Cover Art Archive (dati aperti CC0).
2. Libri e copioni → Open Library (copertine del pubblico dominio).
3. Qualunque tipo  → Wikipedia (immagine della voce).
4. Nessuna rete o nessun risultato → SVG locale in `static/covers/`, così
   l'interfaccia non mostra mai un riquadro rotto.

NOTE PER CHI MODIFICA
---------------------
- La funzione restituisce sempre un percorso utilizzabile in `<img src>`:
  un URL `/static/covers/...` oppure un URL remoto.
- Le immagini scaricate vengono salvate localmente con un nome che contiene
  l'ID dell'elemento: è questo nome che viene registrato in `elementi`.
- Ogni blocco è isolato in try/except: il guasto di un servizio esterno non
  deve mai impedire l'inserimento del volume.
- La chiamata è sincrona (può durare qualche secondo): avviene fuori dalla
  transazione del database per non tenere bloccato SQLite.
"""
import os
import secrets
import urllib.parse

from . import config
from .http import get_api_session

# Limite di sicurezza: una copertina oltre i 2 MB non viene salvata. Evita che
# un servizio esterno (o un errore di Content-Type) riempia il disco con un
# file enorme o non-immagine.
MAX_COVER_BYTES = 2 * 1024 * 1024


def scarica_copertina_web(titolo, autore, tipo, elemento_id):
    """Recupera la copertina online senza bloccare il database."""
    if tipo == 'Copione':
        fallback_path = "/static/covers/default_copione.svg"
    elif tipo == 'CD / Vinile':
        fallback_path = "/static/covers/default_musica.svg"
    else:
        fallback_path = "/static/covers/default_libro.svg"

    if not titolo:
        return fallback_path

    headers = {'User-Agent': 'MemorieDiScena/2.0 (Debian GNU/Linux)'}

    def _salva(img_content):
        """Salva l'immagine scaricata e restituisce il percorso servibile."""
        # Nome con suffisso casuale: due volumi creati nello stesso secondo
        # non si sovrascrivono la copertina.
        filename = f"copertina_{elemento_id}_{secrets.token_hex(6)}.jpg"
        file_path = os.path.join(config.COVERS_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(img_content)
        return f"/static/covers/{filename}"

    def _salva_da_risposta(resp):
        """
        Valida e salva il contenuto di una risposta HTTP come copertina.

        Restituisce il percorso, oppure None se la risposta non è
        un'immagine accettabile (Content-Type errato, file troppo piccolo
        o troppo grande). In caso di None il chiamante prosegue con la
        fonte successiva.
        """
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and not ctype.startswith("image/"):
            return None
        # Leggiamo a blocchi e ci fermiamo appena superiamo il limite: così un
        # file enorme (o una risposta malevola) non viene mai materializzato
        # interamente in RAM.
        blocchi = []
        totale = 0
        for blocco in resp.iter_content(chunk_size=64 * 1024):
            if not blocco:
                continue
            totale += len(blocco)
            if totale > MAX_COVER_BYTES:
                return None
            blocchi.append(blocco)
        if totale < 1000:
            return None
        return _salva(b"".join(blocchi))

    # Ricerca musicale su MusicBrainz + Cover Art Archive (servizi aperti, dati CC0)
    if tipo == 'CD / Vinile':
        try:
            termine = f"{titolo} {autore if autore else ''}".strip()
            url = (
                "https://musicbrainz.org/ws/2/release/"
                f"?query={urllib.parse.quote_plus(termine)}&fmt=json&limit=1"
            )
            resp = get_api_session().get(url, timeout=3.5, headers=headers)
            if resp.status_code == 200:
                releases = resp.json().get('releases', [])
                if releases:
                    mbid = releases[0].get('id')
                    if mbid:
                        art_url = f"https://coverartarchive.org/release/{mbid}/front-500"
                        img_resp = get_api_session().get(art_url, timeout=4, headers=headers, stream=True)
                        if img_resp.status_code == 200:
                            percorso = _salva_da_risposta(img_resp)
                            if percorso:
                                return percorso
        except Exception as e:
            print(f"[Musica] Errore recupero copertina '{titolo}': {e}")

    # Ricerca libri/copioni su Open Library
    try:
        q_titolo = urllib.parse.quote_plus(titolo.strip())
        url = f"https://openlibrary.org/search.json?title={q_titolo}&limit=1"
        if autore and autore.strip():
            url += f"&author={urllib.parse.quote_plus(autore.strip())}"

        resp = get_api_session().get(url, timeout=3.5, headers=headers)
        if resp.status_code == 200:
            dati = resp.json()
            docs = dati.get('docs', [])
            if docs and docs[0].get('cover_i'):
                cover_id = docs[0]['cover_i']
                img_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                img_resp = get_api_session().get(img_url, timeout=4, headers=headers, stream=True)
                if img_resp.status_code == 200:
                    percorso = _salva_da_risposta(img_resp)
                    if percorso:
                        return percorso
    except Exception as e:
        print(f"[OpenLibrary] Errore recupero copertina '{titolo}': {e}")

    # Ricerca di riserva su Wikipedia
    try:
        wiki_url = (
            "https://it.wikipedia.org/w/api.php?action=query&format=json"
            f"&prop=pageimages&pithumbsize=400&titles={urllib.parse.quote_plus(titolo.strip())}"
        )
        wiki_resp = get_api_session().get(wiki_url, timeout=3, headers=headers)
        if wiki_resp.status_code == 200:
            pagine = wiki_resp.json().get('query', {}).get('pages', {})
            for pdata in pagine.values():
                if 'thumbnail' in pdata and 'source' in pdata['thumbnail']:
                    src = pdata['thumbnail']['source']
                    img_resp = get_api_session().get(src, timeout=4, headers=headers, stream=True)
                    if img_resp.status_code == 200:
                        percorso = _salva_da_risposta(img_resp)
                        if percorso:
                            return percorso
    except Exception as e:
        print(f"[Wikipedia] Errore recupero copertina '{titolo}': {e}")

    return fallback_path
