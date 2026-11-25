# -*- coding: utf-8 -*-
"""
Accesso al database: unico punto di contatto con SQLite.

Tutte le connessioni passano da qui, garantendo:
- PRAGMA foreign_keys = ON
- funzione SQL 'normalizza' per ricerche insensibili ad accenti/maiuscole
- commit automatico e rollback in caso di errore
- chiusura immediata della connessione (zero memory leak)
- inizializzazione/migrazione dello schema
- backup rotante coerente
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from . import config
from .utils import normalizza_testo


def pulisci_cestino_scaduto(cursor):
    """
    Elimina definitivamente dal Diario i fogli cestinati da oltre 30 giorni.
    Usa sempre la data locale per restare coerente con `data_eliminazione` e
    con il calcolo dei giorni rimanenti mostrato nell'interfaccia.
    """
    limite = (date.today() - timedelta(days=30)).isoformat()
    cursor.execute("""
        DELETE FROM diario_pensieri
        WHERE eliminato = 1
          AND data_eliminazione IS NOT NULL
          AND length(data_eliminazione) >= 10
          AND substr(data_eliminazione, 1, 10) <= ?
    """, (limite,))


@contextmanager
def get_db():
    """
    Context manager sicuro e ultra-leggero per SQLite.
    """
    conn = sqlite3.connect(config.DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.create_function("normalizza", 1, normalizza_testo)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    Inizializza o aggiorna lo schema del database in modo sicuro e transazionale.

    È idempotente: viene richiamata a ogni avvio e deve poter essere eseguita
    su un database già popolato senza perdere dati. Le modifiche distruttive
    sono limitate alla migrazione storica del CHECK su `elementi` (descritta
    nel blocco seguente).
    """
    setup_conn = sqlite3.connect(config.DB_PATH, timeout=15.0)
    try:
        # Ottimizzazioni persistenti nel file SQLite (attive per sempre su tutte le sessioni)
        setup_conn.execute("PRAGMA journal_mode = WAL;")
        setup_conn.execute("PRAGMA synchronous = FULL;")
        setup_conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB zero-copy memory map
        setup_conn.commit()
    finally:
        setup_conn.close()
    try:
        os.chmod(config.DB_PATH, 0o600)
    except OSError:
        pass

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Tabella elementi (verifica e migrazione sicura CHECK constraint)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='elementi'")
        row = cursor.fetchone()

        if row is None:
            cursor.execute("""
                CREATE TABLE elementi (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL CHECK(tipo IN ('Libro', 'Copione', 'CD / Vinile')),
                    titolo TEXT NOT NULL,
                    autore TEXT,
                    collocazione_casa TEXT,
                    note TEXT,
                    copertina_path TEXT,
                    data_inserimento TEXT NOT NULL,
                    regista TEXT,
                    prima_esibizione_luogo TEXT,
                    data_ingaggio TEXT,
                    data_prima TEXT,
                    formato TEXT,
                    etichetta_anno TEXT
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_tipo ON elementi(tipo);")
        else:
            sql_creazione = row[0]
            # Migrazione storica: le prime versioni accettavano solo 'Libro' e
            # 'Copione'. SQLite non permette di modificare un CHECK, quindi si
            # ricostruisce la tabella copiando i dati. Le chiavi esterne vanno
            # spente durante la copia, altrimenti DROP TABLE cancellerebbe a
            # cascata prestiti e appunti collegati.
            if "CD / Vinile" not in sql_creazione:
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("""
                    CREATE TABLE elementi_migrazione (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL CHECK(tipo IN ('Libro', 'Copione', 'CD / Vinile')),
                        titolo TEXT NOT NULL,
                        autore TEXT,
                        collocazione_casa TEXT,
                        note TEXT,
                        copertina_path TEXT,
                        data_inserimento TEXT NOT NULL,
                        regista TEXT,
                        prima_esibizione_luogo TEXT,
                        data_ingaggio TEXT,
                        data_prima TEXT,
                        formato TEXT,
                        etichetta_anno TEXT
                    );
                """)
                cursor.execute("""
                    INSERT INTO elementi_migrazione (
                        id, tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                        regista, prima_esibizione_luogo, data_ingaggio, data_prima
                    )
                    SELECT id, tipo, titolo, autore, collocazione_casa, note, copertina_path, data_inserimento,
                           regista, prima_esibizione_luogo, data_ingaggio, data_prima
                    FROM elementi;
                """)
                cursor.execute("DROP TABLE elementi;")
                cursor.execute("ALTER TABLE elementi_migrazione RENAME TO elementi;")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_tipo ON elementi(tipo);")

                # ATTENZIONE: PRAGMA foreign_keys non ha alcun effetto dentro
                # una transazione. La copia dati qui sopra ha aperto una
                # transazione implicita, quindi la chiudiamo con un commit
                # esplicito e SOLO DOPO riattiviamo i vincoli. Senza questo
                # passaggio le chiavi esterne resterebbero spente per il resto
                # dell'inizializzazione.
                conn.commit()
                cursor.execute("PRAGMA foreign_keys = ON;")

            # Verifica colonne formato ed etichetta_anno
            cursor.execute("PRAGMA table_info(elementi);")
            colonne = [c[1] for c in cursor.fetchall()]
            if "formato" not in colonne:
                cursor.execute("ALTER TABLE elementi ADD COLUMN formato TEXT;")
            if "etichetta_anno" not in colonne:
                cursor.execute("ALTER TABLE elementi ADD COLUMN etichetta_anno TEXT;")

        # Indici per ricerche istantanee per titolo e autore
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_titolo ON elementi(titolo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_elementi_autore ON elementi(autore);")

        # 2. Tabella prestiti
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prestiti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elemento_id INTEGER NOT NULL REFERENCES elementi(id) ON DELETE CASCADE,
                nome_persona TEXT NOT NULL,
                data_prestito TEXT NOT NULL,
                data_rientro_prevista TEXT,
                data_rientro_effettiva TEXT,
                stato TEXT NOT NULL DEFAULT 'In Prestito' CHECK(stato IN ('In Prestito', 'Rientrato'))
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prestiti_stato ON prestiti(stato);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prestiti_elem ON prestiti(elemento_id);")
        # Un volume non può essere contemporaneamente in due prestiti attivi:
        # l'indice parziale lo impedisce a livello di database (difesa in
        # profondità, oltre ai controlli applicativi). Se un archivio già
        # esistente contiene duplicati storici, l'indice non viene creato ma
        # l'applicazione continua a funzionare.
        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_prestiti_attivo_unico
                ON prestiti(elemento_id) WHERE stato = 'In Prestito';
            """)
        except sqlite3.Error as e:
            print(f"[Prestiti] Indice univoco non creato (dati storici duplicati): {e}")

        # 3. Tabella appunti (Taccuino dei Ricordi)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appunti (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elemento_id INTEGER NOT NULL REFERENCES elementi(id) ON DELETE CASCADE,
                testo TEXT NOT NULL,
                data_creazione TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appunti_elem ON appunti(elemento_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_appunti_testo ON appunti(testo);")

        # 4. Tabelle Diario dei Pensieri e Cronologia Revisioni
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diario_pensieri (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titolo TEXT,
                testo TEXT NOT NULL,
                fonte_riferimento TEXT,
                data_creazione TEXT NOT NULL,
                data_ultima_modifica TEXT,
                eliminato INTEGER NOT NULL DEFAULT 0,
                data_eliminazione TEXT
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_diario_eliminato ON diario_pensieri(eliminato);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_diario_data ON diario_pensieri(data_creazione);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diario_cronologia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pensiero_id INTEGER NOT NULL REFERENCES diario_pensieri(id) ON DELETE CASCADE,
                testo_precedente TEXT NOT NULL,
                data_modifica TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_diario_cron_elem ON diario_cronologia(pensiero_id);")

        # Pulizia automatica Cestino a 30 giorni
        try:
            pulisci_cestino_scaduto(cursor)
        except Exception as e:
            print(f"[Diario] Pulizia 30gg: {e}")


def backup_database():
    """
    Crea un backup coerente del database all'avvio usando l'API SQLite backup()
    (sicura anche in modalità WAL) e conserva a rotazione gli ultimi BACKUP_KEEP.

    Restituisce il percorso della copia creata, oppure None se non è possibile
    (per esempio al primo avvio, quando il database non esiste ancora).
    """
    try:
        if not os.path.exists(config.DB_PATH):
            return None
        # Includiamo i microsecondi: due backup ravvicinati (es. doppio avvio
        # o doppio clic) non devono mai sovrascriversi lo stesso file.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destinazione = os.path.join(config.BACKUP_DIR, f"archivio_backup_{timestamp}.db")
        contatore = 1
        while os.path.exists(destinazione):
            destinazione = os.path.join(
                config.BACKUP_DIR, f"archivio_backup_{timestamp}_{contatore}.db"
            )
            contatore += 1

        origine = sqlite3.connect(config.DB_PATH)
        try:
            dest = sqlite3.connect(destinazione)
            try:
                origine.backup(dest)
            finally:
                dest.close()
        finally:
            origine.close()

        # Controllo di integrità della copia: meglio scoprire subito una copia
        # illeggibile che fidarsi di un file che sembra valido ma non lo è.
        try:
            verifica = sqlite3.connect(destinazione)
            try:
                esito = verifica.execute("PRAGMA integrity_check").fetchone()
            finally:
                verifica.close()
        except sqlite3.Error as e:
            print(f"[Backup] Copia non verificabile: {e}")
            esito = None
        if not esito or (esito[0] if isinstance(esito, tuple) else esito) != "ok":
            print("[Backup] La copia non ha superato il controllo di integrità: viene scartata.")
            try:
                os.remove(destinazione)
            except OSError:
                pass
            return None

        try:
            os.chmod(destinazione, 0o600)
        except OSError:
            pass

        # Rotazione: conserva solo gli ultimi BACKUP_KEEP backup
        backups = sorted(
            (f for f in os.listdir(config.BACKUP_DIR) if f.startswith("archivio_backup_") and f.endswith(".db")),
            reverse=True,
        )
        for vecchio in backups[config.BACKUP_KEEP:]:
            try:
                os.remove(os.path.join(config.BACKUP_DIR, vecchio))
            except Exception:
                pass
        return destinazione
    except Exception as e:
        print(f"[Backup] Impossibile creare il backup del database: {e}")
        return None
