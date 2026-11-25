# -*- coding: utf-8 -*-
"""
Test di fumo (smoke test) per l'app modulare.

Eseguibili senza rete e senza toccare il database reale: la variabile
MEMORIE_DATA_DIR viene impostata PRIMA di importare il pacchetto, così tutta
l'app usa un database temporaneo isolato.

COME AGGIUNGERE UN TEST
-----------------------
1. Scegliere la classe adatta: `TestApplicazione` (rotte e HTTP),
   `TestUtilità` (funzioni pure) o `TestPuliziaOCR` (filtri OCR senza Tesseract).
2. Per una rotta: usare `self.client` e verificare codice di stato e contenuto.
   Le POST richiedono il token CSRF; per i test si può forzare la sessione:
       with self.client.session_transaction() as s:
           s["_csrf_token"] = "token-di-prova"
3. Mai usare la rete: i test devono restare veloci e funzionare offline.
4. Non usare il database reale: l'SQLite è già isolato da MEMORIE_DATA_DIR.

Esecuzione:
    venv/bin/python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest

# Isolamento totale: DB e cache temporanei, nessun effetto sui dati reali.
_TMP = tempfile.mkdtemp(prefix="memorie_test_")
os.environ["MEMORIE_DATA_DIR"] = os.path.join(_TMP, "data")
# Nessun test deve controllare o applicare aggiornamenti reali (rete/processi).
os.environ["MEMORIE_NO_UPDATE"] = "1"

from archivio import create_app  # noqa: E402
from archivio.db import get_db, init_db  # noqa: E402
from archivio.search.local import cerca_locale  # noqa: E402
from archivio.utils import normalizza_testo, pattern_ricerca  # noqa: E402


class TestApplicazione(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_home_risponde_200(self):
        risposta = self.client.get("/")
        self.assertEqual(risposta.status_code, 200)

    def test_route_principali_registrate(self):
        regole = {r.rule for r in self.app.url_map.iter_rules()}
        attese = [
            "/",
            "/acquisizione_ocr",
            "/ocr_upload",
            "/api/elementi",
            "/api/prestiti",
            "/api/ricerca_citazione",
            "/api/diario/lista",
            "/api/diario/cestino",
        ]
        for rotta in attese:
            self.assertIn(rotta, regole)

    def test_csrf_blocca_post_senza_token(self):
        risposta = self.client.post("/api/elementi", data={})
        self.assertEqual(risposta.status_code, 400)

    def test_ricerca_vuota_400(self):
        risposta = self.client.post("/api/ricerca_citazione", json={"frase": ""})
        self.assertEqual(risposta.status_code, 400)

    def test_ricerca_troppo_corta_400(self):
        risposta = self.client.post("/api/ricerca_citazione", json={"frase": "ab"})
        self.assertEqual(risposta.status_code, 400)

    def test_ricerca_locale_trova_volume_inserito(self):
        # Inserisce un volume direttamente nel DB temporaneo, poi lo cerca.
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO elementi (tipo, titolo, autore, data_inserimento) "
                "VALUES ('Libro', 'Divina Commedia', 'Dante Alighieri', '19/11/2026')"
            )
        risultati = cerca_locale("divina")
        self.assertTrue(risultati)
        self.assertEqual(risultati[0]["titolo"], "Divina Commedia")

    def test_esporta_inventario_csv(self):
        risposta = self.client.get("/esporta_inventario")
        self.assertEqual(risposta.status_code, 200)
        self.assertIn("text/csv", risposta.headers["Content-Type"])
        self.assertIn("attachment", risposta.headers["Content-Disposition"])
        testo = risposta.get_data(as_text=True)
        self.assertIn("Tipo;Titolo", testo)

    def test_copia_di_sicurezza_scaricabile(self):
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        with self.client.post("/backup", data={"csrf_token": "token-di-prova"}) as risposta:
            self.assertEqual(risposta.status_code, 200)
            self.assertIn("attachment", risposta.headers["Content-Disposition"])
            self.assertTrue(len(risposta.get_data()) > 0)

    def test_form_ocr_contiene_token_csrf(self):
        """Il form di salvataggio OCR deve includere il token, altrimenti ogni
        salvataggio verrebbe rifiutato dal server con 400."""
        risposta = self.client.get("/acquisizione_ocr")
        self.assertEqual(risposta.status_code, 200)
        self.assertIn('name="csrf_token"', risposta.get_data(as_text=True))

    def test_tipo_non_valido_diventa_libro(self):
        """Un `tipo` fuori dal CHECK SQLite non deve causare un errore 500:
        viene ricondotto a 'Libro' (Fix validazione tipo)."""
        from unittest import mock

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        # Evitiamo la rete: la ricerca copertina risponde con il fallback.
        with mock.patch(
            "archivio.routes.elementi.scarica_copertina_web",
            return_value="/static/covers/default_libro.svg",
        ):
            risposta = self.client.post(
                "/api/elementi",
                data={
                    "csrf_token": "token-di-prova",
                    "tipo": "VHS-inventato",
                    "titolo": "Volume con tipo errato",
                },
            )

        self.assertEqual(risposta.status_code, 302)
        with get_db() as conn:
            riga = conn.cursor().execute(
                "SELECT tipo FROM elementi WHERE titolo = ?",
                ("Volume con tipo errato",),
            ).fetchone()
        self.assertIsNotNone(riga)
        self.assertEqual(riga["tipo"], "Libro")

    def test_prestito_id_non_numerico_non_crasha(self):
        """Un ID non numerico deve produrre un avviso, non un errore 500."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        risposta = self.client.post(
            "/api/prestiti",
            data={"csrf_token": "token-di-prova", "elemento_id": "abc", "nome_persona": "Mario"},
        )
        self.assertEqual(risposta.status_code, 302)

    def test_prestito_su_volume_inesistente_non_crasha(self):
        """Un ID numerico ma assente non deve violare la chiave esterna (500),
        bensì ripiegare su un messaggio comprensibile."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        risposta = self.client.post(
            "/api/prestiti",
            data={"csrf_token": "token-di-prova", "elemento_id": "999999", "nome_persona": "Mario"},
        )
        self.assertEqual(risposta.status_code, 302)


    def test_modifica_non_contamina_campi_di_altro_tipo(self):
        """Modificando un Libro inviando campi da Copione/Musica, questi non
        devono essere salvati: il tipo salvato decide quali campi aggiornare."""
        with get_db() as conn:
            cursore = conn.cursor()
            cursore.execute(
                "INSERT INTO elementi (tipo, titolo, autore, data_inserimento) "
                "VALUES ('Libro', 'Libro Puro', 'Autore', '19/11/2026')"
            )
            elem_id = cursore.lastrowid

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        risposta = self.client.post(
            f"/api/elementi/{elem_id}/modifica",
            data={
                "csrf_token": "token-di-prova",
                "titolo": "Libro Puro",
                "autore": "Autore",
                "regista": "REGISTA-SBAGLIATO",
                "formato": "Vinile LP",
                "etichetta_anno": "ET",
            },
        )
        self.assertEqual(risposta.status_code, 302)

        with get_db() as conn:
            riga = conn.cursor().execute(
                "SELECT regista, formato, etichetta_anno FROM elementi WHERE id = ?",
                (elem_id,),
            ).fetchone()
        self.assertIsNone(riga["regista"])
        self.assertIsNone(riga["formato"])
        self.assertIsNone(riga["etichetta_anno"])

    def test_appunto_su_volume_inesistente_non_crasha(self):
        """L'aggiunta di un ricordo a un ID inesistente non deve violare la
        chiave esterna (500), ma ripiegare su un avviso."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        risposta = self.client.post(
            "/api/elementi/999999/appunti",
            data={"csrf_token": "token-di-prova", "testo": "Un ricordo"},
        )
        self.assertEqual(risposta.status_code, 302)

    def test_modifica_ed_elimina_id_inesistente_non_crasha(self):
        """Modifica/elimina su ID inesistente devono restare dei redirect,
        senza errori 500 e senza falsi messaggi di successo."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        r_mod = self.client.post(
            "/api/elementi/999999/modifica",
            data={"csrf_token": "token-di-prova", "titolo": "Inesistente"},
        )
        r_eli = self.client.post(
            "/api/elementi/999999/elimina",
            data={"csrf_token": "token-di-prova"},
        )
        self.assertEqual(r_mod.status_code, 302)
        self.assertEqual(r_eli.status_code, 302)

    def test_esporta_inventario_neutralizza_formule(self):
        """Un titolo che inizia con '=' non deve finire grezzo nel CSV,
        altrimenti LibreOffice/Excel lo eseguirebbe come formula."""
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO elementi (tipo, titolo, autore, data_inserimento) "
                "VALUES ('Libro', '=1+1', 'Autore', '19/11/2026')"
            )

        risposta = self.client.get("/esporta_inventario")
        testo = risposta.get_data(as_text=True)
        self.assertIn("'=1+1", testo)

    def test_backup_non_sovrascrive(self):
        """Due backup ravvicinati devono produrre file distinti."""
        from archivio.db import backup_database

        primo = backup_database()
        secondo = backup_database()
        self.assertIsNotNone(primo)
        self.assertIsNotNone(secondo)
        self.assertNotEqual(primo, secondo)

    def test_copia_di_sicurezza_e_integra(self):
        """La copia di sicurezza deve essere leggibile e superare integrity_check."""
        import sqlite3

        from archivio.db import backup_database

        percorso = backup_database()
        self.assertIsNotNone(percorso)
        conn = sqlite3.connect(percorso)
        try:
            esito = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(esito, "ok")

    def test_un_solo_prestito_attivo_per_volume(self):
        """Il vincolo a livello di database impedisce due prestiti attivi
        contemporanei sullo stesso volume."""
        import sqlite3

        with get_db() as conn:
            cursore = conn.cursor()
            cursore.execute(
                "INSERT INTO elementi (tipo, titolo, autore, data_inserimento) "
                "VALUES ('Libro', 'Volume Prestato', 'Autore', '19/11/2026')"
            )
            elem_id = cursore.lastrowid

        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO prestiti (elemento_id, nome_persona, data_prestito, stato) "
                "VALUES (?, 'Mario', '19/11/2026', 'In Prestito')",
                (elem_id,),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            with get_db() as conn:
                conn.cursor().execute(
                    "INSERT INTO prestiti (elemento_id, nome_persona, data_prestito, stato) "
                    "VALUES (?, 'Luigi', '19/11/2026', 'In Prestito')",
                    (elem_id,),
                )

    def test_host_header_non_consentito_403(self):
        """Richieste con Host esterno (DNS rebinding) devono essere respinte."""
        risposta_male = self.client.get("/", headers={"Host": "evil.example.com:5000"})
        self.assertEqual(risposta_male.status_code, 403)
        risposta_ok = self.client.get("/", headers={"Host": "127.0.0.1:5000"})
        self.assertEqual(risposta_ok.status_code, 200)

    def test_security_headers_presenti(self):
        """Le risposte devono includere gli header difensivi contro framing e sniffing."""
        risposta = self.client.get("/")
        self.assertEqual(risposta.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(risposta.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", risposta.headers.get("Content-Security-Policy", ""))

    def test_csrf_non_ascii_e_json_lista_non_crashano(self):
        """Token non-ASCII o body JSON non-oggetto devono restituire 400, mai 500."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        r_non_ascii = self.client.post(
            "/api/ricerca_citazione",
            json={"frase": "ciao"},
            headers={"X-CSRF-Token": "tòken-non-ascii"},
        )
        self.assertEqual(r_non_ascii.status_code, 400)

        r_lista = self.client.post(
            "/api/ricerca_citazione",
            json=["non", "un", "dizionario"],
            headers={"X-CSRF-Token": "token-di-prova"},
        )
        self.assertEqual(r_lista.status_code, 400)

    def test_ricerca_e_diario_json_malformato_non_crashano(self):
        """Campi non stringa nei payload JSON non devono generare errori 500."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        r_ric = self.client.post(
            "/api/ricerca_citazione",
            json={"frase": 12345, "csrf_token": "token-di-prova"},
        )
        self.assertEqual(r_ric.status_code, 400)

        r_diario = self.client.post(
            "/api/diario/nuovo",
            json={"testo": 12345, "csrf_token": "token-di-prova"},
        )
        self.assertEqual(r_diario.status_code, 400)

    def test_copertina_caricata_speciale_non_diventa_cartella(self):
        """Un nome copertina che si azzera con secure_filename (es. '???') non
        deve mai risolversi nella directory /static/covers/."""
        from unittest import mock

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        with mock.patch(
            "archivio.routes.elementi.scarica_copertina_web",
            return_value="/static/covers/default_libro.svg",
        ):
            risposta = self.client.post(
                "/api/elementi",
                data={
                    "csrf_token": "token-di-prova",
                    "tipo": "Libro",
                    "titolo": "Test Copertina Speciale",
                    "copertina_caricata": "???",
                },
            )
        self.assertEqual(risposta.status_code, 302)
        with get_db() as conn:
            riga = conn.cursor().execute(
                "SELECT copertina_path FROM elementi WHERE titolo = ?",
                ("Test Copertina Speciale",),
            ).fetchone()
        self.assertIsNotNone(riga)
        self.assertEqual(riga["copertina_path"], "/static/covers/default_libro.svg")

    def test_aggiorna_copertina_mantiene_foto_se_offline(self):
        """Se la ricerca online fallisce, aggiorna_copertina non deve sostituire
        una copertina locale esistente con il segnaposto SVG."""
        from unittest import mock
        from archivio import config

        covers_tmp = tempfile.mkdtemp(dir=_TMP, prefix="covers_")
        foto_nome = "foto_acquisita_test_1234.jpg"
        with open(os.path.join(covers_tmp, foto_nome), "wb") as f:
            f.write(b"fake-jpg-bytes")

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO elementi (tipo, titolo, autore, copertina_path, data_inserimento) "
                "VALUES ('Libro', 'Libro Con Foto', 'Autore', ?, '25/11/2026')",
                (f"/static/covers/{foto_nome}",),
            )
            elem_id = cur.lastrowid

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        with mock.patch.object(config, "COVERS_DIR", covers_tmp), mock.patch(
            "archivio.routes.elementi.scarica_copertina_web",
            return_value="/static/covers/default_libro.svg",
        ):
            risposta = self.client.post(
                f"/api/elementi/{elem_id}/aggiorna_copertina",
                data={"csrf_token": "token-di-prova"},
            )
        self.assertEqual(risposta.status_code, 302)
        with get_db() as conn:
            riga = conn.cursor().execute(
                "SELECT copertina_path FROM elementi WHERE id = ?",
                (elem_id,),
            ).fetchone()
        self.assertEqual(riga["copertina_path"], f"/static/covers/{foto_nome}")

    def test_diario_cestino_pulizia_scaduti_e_id_inesistente(self):
        """I fogli scaduti da >30 giorni vanno rimossi aprendo il cestino e un ID
        inesistente deve restituire 404."""
        from datetime import date, timedelta

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        r_404 = self.client.post(
            "/api/diario/999999/cestina",
            json={"csrf_token": "token-di-prova"},
        )
        self.assertEqual(r_404.status_code, 404)

        vecchia_data = (date.today() - timedelta(days=31)).strftime("%Y-%m-%d 10:00:00")
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO diario_pensieri (titolo, testo, data_creazione, eliminato, data_eliminazione) "
                "VALUES ('Vecchio', 'Scaduto', '01/01/2026', 1, ?)",
                (vecchia_data,),
            )

        r_cestino = self.client.get("/api/diario/cestino")
        self.assertEqual(r_cestino.status_code, 200)
        titoli = [el["titolo"] for el in r_cestino.get_json()["elementi"]]
        self.assertNotIn("Vecchio", titoli)

    def test_ocr_upload_png_salva_jpg(self):
        """Un PNG caricato via /ocr_upload viene salvato come JPEG reale (.jpg)."""
        import io
        from unittest import mock
        from PIL import Image
        from archivio import config

        covers_tmp = tempfile.mkdtemp(dir=_TMP, prefix="ocr_up_")
        buf = io.BytesIO()
        Image.new("RGBA", (60, 40), (10, 20, 30, 128)).save(buf, "PNG")
        buf.seek(0)

        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        with mock.patch.object(config, "COVERS_DIR", covers_tmp), mock.patch(
            "archivio.routes.main.estrai_testo_da_immagine",
            return_value={"linee": ["Amleto"], "confidenza": 90, "qualita": "alta"},
        ):
            risposta = self.client.post(
                "/ocr_upload",
                data={
                    "csrf_token": "token-di-prova",
                    "foto": (buf, "copertina.png"),
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(risposta.status_code, 200)
        dati = risposta.get_json()
        self.assertTrue(dati["success"])
        self.assertTrue(dati["filename"].endswith(".jpg"))
        self.assertTrue(os.path.isfile(os.path.join(covers_tmp, dati["filename"])))

    def test_segna_rientro_inesistente_mostra_errore(self):
        """Segnare rientrato un prestito inesistente deve mostrare un errore, non un falso successo."""
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"

        risposta = self.client.post(
            "/api/prestiti/999999/rientro",
            data={"csrf_token": "token-di-prova"},
            follow_redirects=True,
        )
        self.assertEqual(risposta.status_code, 200)
        self.assertIn("non esiste", risposta.get_data(as_text=True))

    def test_ricerca_virgolette_corte_400(self):
        """Una frase che diventa < 3 caratteri dopo aver rimosso le virgolette non interroga le API."""
        from archivio.search import ricerca_per_citazione

        self.assertEqual(ricerca_per_citazione("«ab»"), [])


class TestAggiornamenti(unittest.TestCase):
    """Verifiche sul sistema di aggiornamento: nessun processo o rete reale
    (MEMORIE_NO_UPDATE=1 impostata a livello di modulo)."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_versione_locale_legge_il_file_version(self):
        from archivio import config

        self.assertTrue(os.path.isfile(config.VERSION_FILE))
        self.assertRegex(config.versione_locale(), r"^\d+\.\d+")

    def test_script_aggiornamento_presente(self):
        from archivio import config

        self.assertTrue(os.path.isfile(config.UPDATE_SCRIPT), "manca aggiorna.sh")

    def test_rotte_aggiornamenti_registrate(self):
        regole = {r.rule for r in self.app.url_map.iter_rules()}
        self.assertIn("/api/aggiornamenti", regole)
        self.assertIn("/api/aggiornamenti/stato", regole)
        self.assertIn("/api/aggiornamenti/applica", regole)

    def test_controllo_neutro_quando_disattivato(self):
        risposta = self.client.get("/api/aggiornamenti")
        self.assertEqual(risposta.status_code, 200)
        dati = risposta.get_json()
        self.assertFalse(dati["disponibile"])
        self.assertTrue(dati["applicazione_disattivata"])

    def test_stato_restituisce_200(self):
        risposta = self.client.get("/api/aggiornamenti/stato")
        self.assertEqual(risposta.status_code, 200)
        self.assertIn("versione_locale", risposta.get_json())

    def test_applica_disattivata_409(self):
        with self.client.session_transaction() as sessione:
            sessione["_csrf_token"] = "token-di-prova"
        risposta = self.client.post(
            "/api/aggiornamenti/applica",
            headers={"X-CSRF-Token": "token-di-prova"},
        )
        self.assertEqual(risposta.status_code, 409)


class TestUtilità(unittest.TestCase):
    def test_url_immagine_consentito_solo_servizi_previsti(self):
        """Solo https verso i domini noti: niente indirizzi interni o non sicuri."""
        from archivio.covers import _url_immagine_consentito

        self.assertTrue(_url_immagine_consentito("https://upload.wikimedia.org/a.jpg"))
        self.assertTrue(_url_immagine_consentito("https://covers.openlibrary.org/b/id/1-M.jpg"))
        self.assertFalse(_url_immagine_consentito("http://upload.wikimedia.org/a.jpg"))
        self.assertFalse(_url_immagine_consentito("http://127.0.0.1:5000/"))
        self.assertFalse(_url_immagine_consentito("https://evil.example.com/a.jpg"))
        self.assertFalse(_url_immagine_consentito("file:///etc/passwd"))

    def test_normalizza_testo_ignora_accenti(self):
        self.assertEqual(normalizza_testo("Perché"), "perche")
        self.assertEqual(normalizza_testo("È"), "e")

    def test_pattern_ricerca_neutralizza_jolly(self):
        pattern = pattern_ricerca("100%")
        self.assertIn("100\\%", pattern)

    def test_valore_csv_neutralizza_formule(self):
        """Titoli che iniziano con =, +, -, @ vanno prefissati con apostrofo per
        impedire l'esecuzione come formula in LibreOffice/Excel."""
        from archivio.routes.elementi import _valore_csv

        self.assertEqual(_valore_csv("=1+1"), "'=1+1")
        self.assertEqual(_valore_csv("+SOMMA(A1)"), "'+SOMMA(A1)")
        self.assertEqual(_valore_csv("@comando"), "'@comando")
        self.assertEqual(_valore_csv("Titolo normale"), "Titolo normale")
        self.assertEqual(_valore_csv(None), "")

    def test_punteggio_rilevanza_titolo_none(self):
        """Un risultato con titolo/snippet mancanti non deve far fallire
        l'ordinamento della ricerca."""
        from archivio.search import punteggio_rilevanza

        self.assertEqual(punteggio_rilevanza({"titolo": None, "snippet": None}, "frase"), 0)

    def test_scarica_immagine_sicura_blocca_redirect_locale(self):
        """Un redirect verso 127.0.0.1 non deve mai essere seguito."""
        from unittest import mock
        from archivio.covers import _scarica_immagine_sicura

        resp_redirect = mock.Mock()
        resp_redirect.status_code = 302
        resp_redirect.headers = {"Location": "http://127.0.0.1:5000/esporta_inventario"}
        fake_session = mock.Mock()
        fake_session.get.return_value = resp_redirect

        with mock.patch("archivio.covers.get_api_session", return_value=fake_session):
            esito = _scarica_immagine_sicura("https://upload.wikimedia.org/a.jpg", {})

        self.assertIsNone(esito)
        self.assertEqual(fake_session.get.call_count, 1)
        resp_redirect.close.assert_called_once()

    def test_copertina_scarta_contenuto_non_immagine_o_senza_mime(self):
        """Una risposta senza Content-Type o con HTML/SVG finto viene rifiutata."""
        import io
        from unittest import mock
        from archivio import covers

        covers_tmp = tempfile.mkdtemp(dir=_TMP, prefix="covers_dl_")

        def _fake_resp(ctype, payload):
            r = mock.Mock()
            r.status_code = 200
            r.headers = {"Content-Type": ctype} if ctype is not None else {}
            r.iter_content.return_value = [payload]
            return r

        fake_session = mock.Mock()
        # Prima chiamata: API Open Library con cover_i; seconda: immagine senza MIME.
        api_resp = mock.Mock(status_code=200)
        api_resp.json.return_value = {"docs": [{"cover_i": 12345}]}
        fake_session.get.side_effect = [
            api_resp,
            _fake_resp(None, b"<html>" + b"x" * 1500 + b"</html>"),
            mock.Mock(status_code=404),
        ]

        with mock.patch.object(covers.config, "COVERS_DIR", covers_tmp), mock.patch(
            "archivio.covers.get_api_session", return_value=fake_session
        ):
            esito = covers.scarica_copertina_web("Titolo", "Autore", "Libro", 1)

        self.assertEqual(esito, "/static/covers/default_libro.svg")
        self.assertEqual(os.listdir(covers_tmp), [])

        # Verifica che un'immagine PNG reale venga invece salvata in JPEG valido.
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (80, 120), (255, 0, 0, 128)).save(buf, "PNG")
        png_bytes = buf.getvalue()
        fake_session2 = mock.Mock()
        fake_session2.get.side_effect = [
            api_resp,
            _fake_resp("image/png", png_bytes if len(png_bytes) >= 1000 else png_bytes + b"\x00" * 1000),
        ]
        # Usa dimensioni maggiori per superare la soglia minima di 1000 byte naturalmente.
        buf2 = io.BytesIO()
        Image.effect_noise((120, 160), 40).convert("RGBA").save(buf2, "PNG")
        fake_session2.get.side_effect = [api_resp, _fake_resp("image/png", buf2.getvalue())]

        with mock.patch.object(covers.config, "COVERS_DIR", covers_tmp), mock.patch(
            "archivio.covers.get_api_session", return_value=fake_session2
        ):
            esito_ok = covers.scarica_copertina_web("Titolo", "Autore", "Libro", 1)

        self.assertTrue(esito_ok.startswith("/static/covers/copertina_1_"))
        self.assertTrue(esito_ok.endswith(".jpg"))

    def test_pulisci_cache_scaduta_preserva_aggiornamento(self):
        """pulisci_cache_scaduta deve rimuovere solo ricerca_*.json e mai aggiornamento.json."""
        import time
        from unittest import mock
        from archivio import config
        from archivio.search.cache import pulisci_cache_scaduta

        cache_tmp = tempfile.mkdtemp(dir=_TMP, prefix="cache_")
        vecchio_ts = time.time() - (config.CACHE_EXPIRY_SEC + 3600)
        f_ric = os.path.join(cache_tmp, "ricerca_1234.json")
        f_agg = os.path.join(cache_tmp, "aggiornamento.json")
        for fp in (f_ric, f_agg):
            with open(fp, "w", encoding="utf-8") as f:
                f.write("{}")
            os.utime(fp, (vecchio_ts, vecchio_ts))

        with mock.patch.object(config, "CACHE_DIR", cache_tmp):
            pulisci_cache_scaduta()

        self.assertFalse(os.path.exists(f_ric))
        self.assertTrue(os.path.exists(f_agg))

    def test_pulisci_snippet_decodifica_entita(self):
        from archivio.utils import pulisci_snippet

        self.assertEqual(pulisci_snippet("<b>L&#8217;amore &amp; il teatro</b>"), "L’amore & il teatro")

    def test_migra_database_su_destinazione_isolata(self):
        """La migrazione deve funzionare su un DB arbitrario senza duplicati né errori su prestiti."""
        import sqlite3
        from data.migra_database import migra_database

        src = os.path.join(_TMP, "vecchio_src.db")
        dst = os.path.join(_TMP, "nuovo_dst.db")
        c = sqlite3.connect(src)
        c.execute("CREATE TABLE elementi (id INTEGER PRIMARY KEY, tipo TEXT, titolo TEXT, autore TEXT)")
        c.execute("INSERT INTO elementi VALUES (1, 'Libro', 'Amleto', 'Shakespeare')")
        c.execute(
            "CREATE TABLE prestiti (id INTEGER PRIMARY KEY, elemento_id INTEGER, nome_persona TEXT, stato TEXT)"
        )
        c.execute("INSERT INTO prestiti VALUES (1, 1, 'Mario', 'In Prestito')")
        c.execute("INSERT INTO prestiti VALUES (2, 1, 'Luigi', 'In Prestito')")
        c.commit()
        c.close()

        self.assertTrue(migra_database(src, dst))
        # Seconda esecuzione idempotente: non deve duplicare il volume.
        self.assertTrue(migra_database(src, dst))

        cd = sqlite3.connect(dst)
        try:
            n_el = cd.execute("SELECT COUNT(*) FROM elementi").fetchone()[0]
            n_tot_prestiti = cd.execute("SELECT COUNT(*) FROM prestiti").fetchone()[0]
            n_attivi = cd.execute("SELECT COUNT(*) FROM prestiti WHERE stato='In Prestito'").fetchone()[0]
            data_ins = cd.execute("SELECT data_inserimento FROM elementi").fetchone()[0]
        finally:
            cd.close()

        self.assertEqual(n_el, 1)
        self.assertEqual(n_tot_prestiti, 2)
        self.assertEqual(n_attivi, 1)
        self.assertRegex(data_ins, r"^\d{2}/\d{2}/\d{4}$")


class TestPuliziaOCR(unittest.TestCase):
    """Verifiche sui filtri OCR: non richiedono Tesseract, solo logica pura."""

    def test_pulisce_spazi_e_decorazioni(self):
        from archivio.ocr import _pulisci_riga

        self.assertEqual(_pulisci_riga("  DANTE    Alighieri |"), "DANTE Alighieri")

    def test_scarta_righe_di_rumore_e_poco_credibili(self):
        from archivio.ocr import _riga_utile

        self.assertTrue(_riga_utile("Dante Alighieri", 90))
        self.assertFalse(_riga_utile("|~_^", 90))
        self.assertFalse(_riga_utile("Dante Alighieri", 10))

    def test_riconosce_la_stessa_riga_letta_in_modo_diverso(self):
        from archivio.ocr import _simili

        self.assertTrue(_simili("Giuseppe Tomasi", "Giuseppe Tomasi di Lampedusa"))
        self.assertFalse(_simili("Il nome della rosa", "Il gatto con gli stivali"))

    def test_autodiagnostica_lingua_ocr(self):
        """Deve sempre rispondere, anche se Tesseract o il pacchetto italiano mancano."""
        from archivio.ocr import stato_lingua_ocr

        esito = stato_lingua_ocr()
        self.assertIn("italiano", esito)
        self.assertIsInstance(esito["italiano"], bool)
        self.assertIn("lingue", esito)
        # Se l'italiano manca, deve esserci un messaggio comprensibile per l'utente.
        if not esito["italiano"]:
            self.assertTrue(esito["messaggio"])

    def test_combo_lingue_preferisce_italiano(self):
        from archivio import ocr

        precedente = ocr._LINGUE_INSTALLATE
        try:
            ocr._LINGUE_INSTALLATE = ("ita", "eng", "fra")
            principale, estesa = ocr._combo_lingue(None)
            self.assertEqual(principale, "ita")
            self.assertEqual(estesa, "ita+eng+fra")
        finally:
            ocr._LINGUE_INSTALLATE = precedente

    def test_combo_lingue_senza_italiano(self):
        from archivio import ocr

        precedente = ocr._LINGUE_INSTALLATE
        try:
            ocr._LINGUE_INSTALLATE = ("eng", "fra")
            principale, estesa = ocr._combo_lingue(None)
            self.assertEqual(principale, "eng")
            self.assertEqual(estesa, "eng+fra")
        finally:
            ocr._LINGUE_INSTALLATE = precedente

    def test_combo_lingue_nessun_dizionario(self):
        from archivio import ocr

        precedente = ocr._LINGUE_INSTALLATE
        try:
            ocr._LINGUE_INSTALLATE = ()
            self.assertEqual(ocr._combo_lingue(None), ("", ""))
        finally:
            ocr._LINGUE_INSTALLATE = precedente


if __name__ == "__main__":
    unittest.main()
