# -*- coding: utf-8 -*-
"""
Ricerca locale: collezione personale, taccuino dei ricordi e diario.

COSA CERCA (in ordine, massimo 5 risultati per sezione)
-------------------------------------------------------
1. `elementi`  → titolo, autore, note, regista
2. `appunti`   → citazioni e ricordi salvati nel taccuino
3. `diario_pensieri` → fogli attivi del Diario (esclusi quelli nel cestino)

Ogni risultato ha `in_archivio: True`, così l'interfaccia mostra il pulsante
per aprire subito la scheda o il foglio, invece del link esterno.

NOTE TECNICHE
-------------
- Il confronto usa la funzione SQL `normalizza()` (registrata in `db.get_db`):
  accenti e maiuscole non contano, `%` e `_` sono trattati come testo.
- Qualunque errore viene registrato nel terminale e la funzione restituisce
  comunque una lista: la ricerca online deve poter proseguire anche se il
  database locale ha un problema.
"""
from ..db import get_db
from ..utils import pattern_ricerca


def cerca_locale(frase):
    """
    Cerca PRIMA DI TUTTO nella libreria personale e nel proprio taccuino.
    Se l'utente cerca una frase già presente nella collezione, lo segnala subito.
    """
    risultati = []
    if not frase or len(frase.strip()) < 3:
        return risultati

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            pattern = pattern_ricerca(frase)

            # 1. Cerca nei titoli, autori o note degli elementi
            cursor.execute("""
                SELECT id, tipo, titolo, autore, collocazione_casa, note, copertina_path
                FROM elementi
                WHERE normalizza(titolo) LIKE ? ESCAPE '\\'
                   OR normalizza(autore) LIKE ? ESCAPE '\\'
                   OR normalizza(note) LIKE ? ESCAPE '\\'
                   OR normalizza(regista) LIKE ? ESCAPE '\\'
                LIMIT 5
            """, (pattern, pattern, pattern, pattern))
            for row in cursor.fetchall():
                collocazione = row['collocazione_casa'] or 'In casa'
                risultati.append({
                    'titolo': row['titolo'],
                    'autore': row['autore'] or 'Autore non indicato',
                    'editore': f"📍 Posizione in casa: {collocazione}",
                    'anno': '',
                    'snippet': f"🏠 Questo volume è già nella tua libreria! ({collocazione}). Note: {row['note'] or 'Nessuna nota'}".strip(),
                    'copertina_url': row['copertina_path'],
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': '',
                    'anteprima_link': '',
                    'fonte': 'La Tua Libreria Personale',
                    'fonte_icona': '🏠',
                    'in_archivio': True,
                    'elemento_id': row['id']
                })

            # 2. Cerca nel taccuino dei ricordi (citazioni salvate)
            cursor.execute("""
                SELECT a.id, a.testo, a.data_creazione, e.id AS elem_id, e.titolo, e.autore, e.collocazione_casa, e.copertina_path
                FROM appunti a
                JOIN elementi e ON a.elemento_id = e.id
                WHERE normalizza(a.testo) LIKE ? ESCAPE '\\'
                LIMIT 5
            """, (pattern,))
            for row in cursor.fetchall():
                risultati.append({
                    'titolo': row['titolo'],
                    'autore': row['autore'] or 'Autore non indicato',
                    'editore': f"Annotato nel tuo Taccuino il {row['data_creazione']}",
                    'anno': '',
                    'snippet': f"📓 Trovato nel tuo Taccuino dei Ricordi: «{row['testo']}» (Collocazione: {row['collocazione_casa'] or 'in casa'})",
                    'copertina_url': row['copertina_path'],
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': '',
                    'anteprima_link': '',
                    'fonte': 'Il Tuo Taccuino dei Ricordi',
                    'fonte_icona': '📓',
                    'in_archivio': True,
                    'elemento_id': row['elem_id']
                })

            # 3. Cerca nel Diario dei Pensieri e Memorie (fogli di pergamena)
            cursor.execute("""
                SELECT id, titolo, testo, fonte_riferimento, data_creazione
                FROM diario_pensieri
                WHERE eliminato = 0 AND (
                    normalizza(testo) LIKE ? ESCAPE '\\'
                    OR normalizza(titolo) LIKE ? ESCAPE '\\'
                    OR normalizza(fonte_riferimento) LIKE ? ESCAPE '\\'
                )
                ORDER BY id DESC
                LIMIT 5
            """, (pattern, pattern, pattern))
            for row in cursor.fetchall():
                rif = (row['fonte_riferimento'] or '').strip()
                titolo_pensiero = row['titolo'] or (row['testo'][:45] + '…' if len(row['testo']) > 45 else row['testo'])
                autore_desc = f"Dal tuo Diario dei Pensieri ({rif})" if rif else "Dal tuo Diario dei Pensieri"
                risultati.append({
                    'titolo': titolo_pensiero,
                    'autore': autore_desc,
                    'editore': f"Scritto nel tuo Diario il {row['data_creazione']}",
                    'anno': '',
                    'snippet': f"📜 Trovato sul foglio di pergamena del tuo Diario: «{row['testo']}»",
                    'copertina_url': '',
                    'lingua': 'it',
                    'pagine': '',
                    'link_info': '',
                    'anteprima_link': '',
                    'fonte': 'Il Tuo Diario dei Pensieri',
                    'fonte_icona': '📜',
                    'in_archivio': True,
                    'diario_id': row['id']
                })
    except Exception as e:
        print(f"[Ricerca Locale] Errore: {e}")

    return risultati
