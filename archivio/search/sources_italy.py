# -*- coding: utf-8 -*-
"""
Fonti italiane: OPAC SBN (catalogo biblioteche) e Liber Liber (Progetto Manuzio).

OPAC SBN    catalogo ufficiale delle biblioteche italiane (ICCU). La ricerca
            parte da una query libera e, se non trova nulla, ripete sul titolo.
            Utile per identificare l'edizione esatta di un copione.
Liber Liber catalogo del Progetto Manuzio: testi, ePub e audiolibri liberi.

Entrambe restituiscono `[]` in caso di errore e non sollevano eccezioni.
"""
import html
import re
import urllib.parse

from .. import config
from ..http import get_api_session


def cerca_opac_sbn(frase, max_risultati=4):
    """Cerca nel Catalogo Ufficiale del Servizio Bibliotecario Nazionale (ICCU/OPAC SBN)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        url = "https://opac.sbn.it/o/opac-api/titles-search-post"
        pulita = frase.strip()
        headers = {'X-Requested-With': 'XMLHttpRequest'}

        # 1. Tentativo con keywords (ricerca generale multi-campo)
        payload = {'keywords': pulita, 'rows': max_risultati}
        resp = get_api_session().post(url, data=payload, headers=headers, timeout=config.API_TIMEOUT)
        raw_items = []
        if resp.status_code == 200:
            raw_items = resp.json().get('data', {}).get('results', [])

        # 2. Fallback su titolo se 0 risultati
        if not raw_items:
            parole = pulita.split()
            query_titolo = " ".join(parole[:5]) if len(parole) > 5 else pulita
            payload2 = {'titolo': query_titolo, 'rows': max_risultati}
            resp2 = get_api_session().post(url, data=payload2, headers=headers, timeout=config.API_TIMEOUT)
            if resp2.status_code == 200:
                raw_items = resp2.json().get('data', {}).get('results', [])

        for item in raw_items[:max_risultati]:
            bid = str(item.get('bid') or '').strip()
            t_obj = item.get('title') or {}
            titolo = t_obj.get('info') or t_obj.get('text') or 'Titolo non indicato'
            autore = t_obj.get('text') if t_obj.get('info') else 'Autore non indicato'
            infos = item.get('infos') or []
            editore_anno = infos[0] if infos else 'Servizio Bibliotecario Nazionale'

            m_anno = re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', str(editore_anno))
            anno = m_anno.group(1) if m_anno else ''

            link = f"https://opac.sbn.it/bid/{urllib.parse.quote(bid, safe='')}" if bid else "https://opac.sbn.it"
            risultati.append({
                'titolo': titolo,
                'autore': autore,
                'editore': f"SBN Biblioteche: {editore_anno}",
                'anno': anno,
                'snippet': f"Scheda ufficiale del Servizio Bibliotecario Nazionale (SBN). Codice BID: {bid}. Edizione: {editore_anno}",
                'copertina_url': '',
                'lingua': 'it',
                'pagine': '',
                'link_info': link,
                'anteprima_link': '',
                'fonte': 'OPAC SBN (Biblioteche Italiane)',
                'fonte_icona': '🏛️',
            })
    except Exception as e:
        print(f"[OPAC SBN] Errore: {e}")
    return risultati


def cerca_liber_liber(frase, max_risultati=3):
    """Cerca nel catalogo di Liber Liber (Progetto Manuzio)."""
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        q = urllib.parse.quote_plus(frase.strip())
        url = f"https://www.liberliber.it/wp-json/wp/v2/search?search={q}&per_page={max_risultati}"
        resp = get_api_session().get(url, timeout=config.API_TIMEOUT)
        if resp.status_code == 200:
            for it in resp.json():
                titolo_raw = it.get('title', 'Senza titolo')
                titolo = html.unescape(titolo_raw).replace('&#8220;', '«').replace('&#8221;', '»').replace('&#8217;', "'").strip()
                link = it.get('url', '')

                # Estrazione eventuale autore dal titolo (es. "... di Luigi Pirandello")
                autore = 'Letteratura & Teatro Italiano'
                m_autore = re.search(r'\bdi\s+([A-ZÀ-Ú][a-zà-ù]+(?:\s+[A-ZÀ-Ú][a-zà-ù]+)+)', titolo)
                if m_autore:
                    autore = m_autore.group(1)

                risultati.append({
                    'titolo': titolo,
                    'autore': autore,
                    'editore': 'Liber Liber (Progetto Manuzio)',
                    'anno': '',
                    'snippet': "Opera libera da diritti del Progetto Manuzio. Testo, ePub, PDF o audiolibro disponibili per il download gratuito.",
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': link,
                    'anteprima_link': '',
                    'fonte': 'Liber Liber (Progetto Manuzio)',
                    'fonte_icona': '📖',
                })
    except Exception as e:
        print(f"[Liber Liber] Errore: {e}")
    return risultati
