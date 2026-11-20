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

        risposta = self.client.post("/backup", data={"csrf_token": "token-di-prova"})
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
