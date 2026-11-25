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
import io
import os
import re
import secrets
import urllib.parse

from . import config
from .http import get_api_session

# Limite di sicurezza: una copertina oltre i 2 MB non viene salvata. Evita che
# un servizio esterno (o un errore di Content-Type) riempia il disco con un
# file enorme o non-immagine.
MAX_COVER_BYTES = 2 * 1024 * 1024

# Massimo numero di redirect HTTP seguiti dopo verifica preventiva di ogni hop.
MAX_COVER_REDIRECTS = 3

# Tipi MIME raster ammessi per le copertine (esclude SVG e tipi non-immagine).
MIME_IMMAGINI_CONSENTITI = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

# Formati validati per gli ID interpolati negli URL delle API esterne.
_RE_MBID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_RE_COVER_ID = re.compile(r"^\d{1,20}$")

# Domini da cui è ammesso scaricare un'immagine. Serve a impedire che un URL
# inatteso (per esempio una risposta alterata o un redirect) faccia scaricare
# contenuti da indirizzi interni alla macchina o da servizi non previsti.
DOMINI_IMMAGINI_CONSENTITI = (
    "coverartarchive.org",
    "archive.org",
    "openlibrary.org",
    "wikimedia.org",
)


def _url_immagine_consentito(url):
    """True solo per URL https verso i servizi di immagini previsti."""
    try:
        parti = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parti.scheme != "https" or not parti.hostname:
        return False
    host = parti.hostname.lower()
    return any(host == dominio or host.endswith("." + dominio) for dominio in DOMINI_IMMAGINI_CONSENTITI)


def _scarica_immagine_sicura(url, headers):
    """
    Scarica l'immagine verificando OGNI redirect prima di seguirlo, così nessun
    hop può raggiungere indirizzi locali o domini esterni alla allowlist.

    Restituisce la `requests.Response` aperta con `stream=True` (il chiamante
    deve chiuderla) oppure `None`.
    """
    url_corrente = url
    sessione = get_api_session()
    for _ in range(MAX_COVER_REDIRECTS + 1):
        if not _url_immagine_consentito(url_corrente):
            return None
        resp = sessione.get(
            url_corrente,
            timeout=4,
            headers=headers,
            stream=True,
            allow_redirects=False,
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            destinazione = resp.headers.get("Location")
            resp.close()
            if not destinazione:
                return None
            url_corrente = urllib.parse.urljoin(url_corrente, destinazione)
            continue
        if resp.status_code == 200:
            return resp
        resp.close()
        return None
    return None


def _valida_e_converti_jpeg(img_bytes):
    """
    Verifica tramite Pillow che i byte siano davvero un'immagine valida (con
    limite anti-decompression-bomb) e li normalizza in JPEG pulito.
    """
    from .ocr import get_ocr_tools, immagine_rgb_su_bianco

    Image, ImageOps, filtro = get_ocr_tools()
    with Image.open(io.BytesIO(img_bytes)) as check_img:
        check_img.verify()

    with Image.open(io.BytesIO(img_bytes)) as img:
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        img = immagine_rgb_su_bianco(img, Image)
        if max(img.size) > config.MAX_IMAGE_DIM:
            img.thumbnail((config.MAX_IMAGE_DIM, config.MAX_IMAGE_DIM), filtro)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()


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

    headers_img = {'Accept': 'image/*'}

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
        un'immagine accettabile (Content-Type assente/errato, file troppo
        piccolo, troppo grande o immagine corrotta). In caso di None il
        chiamante prosegue con la fonte successiva.
        """
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in MIME_IMMAGINI_CONSENTITI:
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
        try:
            jpeg_pulito = _valida_e_converti_jpeg(b"".join(blocchi))
        except Exception:
            return None
        return _salva(jpeg_pulito)

    # Ricerca musicale su MusicBrainz + Cover Art Archive (servizi aperti, dati CC0)
    if tipo == 'CD / Vinile':
        try:
            termine = f"{titolo} {autore if autore else ''}".strip()
            url = (
                "https://musicbrainz.org/ws/2/release/"
                f"?query={urllib.parse.quote_plus(termine)}&fmt=json&limit=1"
            )
            resp = get_api_session().get(url, timeout=3.5)
            if resp.status_code == 200:
                releases = resp.json().get('releases') or []
                if releases:
                    mbid = str(releases[0].get('id') or '').strip()
                    if _RE_MBID.match(mbid):
                        art_url = f"https://coverartarchive.org/release/{mbid}/front-500"
                        img_resp = _scarica_immagine_sicura(art_url, headers_img)
                        if img_resp is not None:
                            try:
                                percorso = _salva_da_risposta(img_resp)
                            finally:
                                img_resp.close()
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

        resp = get_api_session().get(url, timeout=3.5)
        if resp.status_code == 200:
            dati = resp.json()
            docs = dati.get('docs') or []
            if docs and docs[0].get('cover_i'):
                cover_id = str(docs[0]['cover_i']).strip()
                if _RE_COVER_ID.match(cover_id):
                    img_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                    img_resp = _scarica_immagine_sicura(img_url, headers_img)
                    if img_resp is not None:
                        try:
                            percorso = _salva_da_risposta(img_resp)
                        finally:
                            img_resp.close()
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
        wiki_resp = get_api_session().get(wiki_url, timeout=3)
        if wiki_resp.status_code == 200:
            pagine = wiki_resp.json().get('query', {}).get('pages', {})
            for pdata in pagine.values():
                if 'thumbnail' in pdata and 'source' in pdata['thumbnail']:
                    src = pdata['thumbnail']['source']
                    img_resp = _scarica_immagine_sicura(src, headers_img)
                    if img_resp is not None:
                        try:
                            percorso = _salva_da_risposta(img_resp)
                        finally:
                            img_resp.close()
                        if percorso:
                            return percorso
    except Exception as e:
        print(f"[Wikipedia] Errore recupero copertina '{titolo}': {e}")

    return fallback_path
