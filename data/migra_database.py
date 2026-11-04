#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strumento di Migrazione e Importazione Dati - Memorie di Scena
Permette di importare in sicurezza tutti i libri, copioni, dischi, prestiti,
appunti e memorie da un database precedente (.db o .sqlite) al database attuale.

Caratteristiche:
- Salvaguardia automatica: crea una copia di backup prima di qualsiasi operazione.
- Compatibilità con schemi storici: rileva automaticamente le colonne presenti nel vecchio database.
- Integrità referenziale: rimappa correttamente gli ID di prestiti e ricordi per ogni volume.
- Zero duplicati fittizi e gestione delle transazioni atomiche (commit/rollback).
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

DIR_ATTUALE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(DIR_ATTUALE, ".."))
DB_ATTUALE = os.path.join(DIR_ATTUALE, "archivio.db")


def trova_vecchi_database():
    """Cerca automaticamente possibili database precedenti nella cartella data e nella radice."""
    candidati = []
    # Cerca nella cartella data
    for nome in os.listdir(DIR_ATTUALE):
        if (nome.endswith(".db") or nome.endswith(".sqlite")) and nome != "archivio.db":
            percorso = os.path.join(DIR_ATTUALE, nome)
            if os.path.isfile(percorso) and os.path.getsize(percorso) > 0:
                candidati.append(percorso)

    # Cerca nella radice
    for nome in os.listdir(BASE_DIR):
        if (nome.endswith(".db") or nome.endswith(".sqlite")) and nome != "archivio.db":
            percorso = os.path.join(BASE_DIR, nome)
            if os.path.isfile(percorso) and os.path.getsize(percorso) > 0:
                candidati.append(percorso)

    return candidati


def colonne_tabella(cursor, tabella):
    """Restituisce l'insieme dei nomi delle colonne di una tabella."""
    try:
        cursor.execute(f"PRAGMA table_info({tabella})")
        return [row[1] for row in cursor.fetchall()]
    except Exception:
        return []


def tabella_esiste(cursor, tabella):
    """Verifica se una tabella esiste nel database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabella,))
    return cursor.fetchone() is not None


def migra_database(percorso_sorgente, percorso_destinazione=DB_ATTUALE):
    """
    Esegue la migrazione transazionale e sicura dal database sorgente a quello di destinazione.
    """
    if not os.path.exists(percorso_sorgente):
        print(f"❌ Errore: Il file sorgente '{percorso_sorgente}' non esiste.")
        return False

    percorso_sorgente = os.path.abspath(percorso_sorgente)
    percorso_destinazione = os.path.abspath(percorso_destinazione)

    if percorso_sorgente == percorso_destinazione:
        print("❌ Errore: Il database sorgente coincide con il database di destinazione.")
        return False

    print("==================================================================")
    print("📦 AVVIO MIGRAZIONE DATI - MEMORIE DI SCENA")
    print("------------------------------------------------------------------")
    print(f"📖 Database Sorgente:      {percorso_sorgente}")
    print(f"🎯 Database Destinazione:  {percorso_destinazione}")
    print("==================================================================")

    # 1. Backup di sicurezza preventivo del database di destinazione se già esistente
    if os.path.exists(percorso_destinazione) and os.path.getsize(percorso_destinazione) > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{percorso_destinazione}.backup_pre_migrazione_{ts}.bak"
        shutil.copy2(percorso_destinazione, backup_path)
        print(f"🛡️  Copia di sicurezza creata: {os.path.basename(backup_path)}")

    # Assicurati che lo schema di destinazione sia inizializzato
    try:
        sys.path.insert(0, BASE_DIR)
        import app
        app.init_db()
    except Exception as e:
        print(f"ℹ️  Inizializzazione schema destinazione: {e}")

    conn_src = sqlite3.connect(percorso_sorgente)
    conn_src.row_factory = sqlite3.Row
    cur_src = conn_src.cursor()

    conn_dst = sqlite3.connect(percorso_destinazione)
    conn_dst.execute("PRAGMA foreign_keys = ON;")
    cur_dst = conn_dst.cursor()

    tot_elementi = 0
    tot_prestiti = 0
    tot_appunti = 0
    tot_pensieri = 0
    tot_cronologia = 0

    id_elem_map = {}      # vecchio_id -> nuovo_id
    id_diario_map = {}    # vecchio_id -> nuovo_id

    try:
        # ----------------------------------------------------------------------
        # 1. MIGRAZIONE TABELLA ELEMENTI (LIBRI, COPIONI, CD/VINILI)
        # ----------------------------------------------------------------------
        if tabella_esiste(cur_src, "elementi"):
            cols_src = colonne_tabella(cur_src, "elementi")
            print("\n📚 1. Migrazione Volumi, Copioni e Dischi...")

            cur_src.execute("SELECT * FROM elementi ORDER BY id ASC")
            righe_elementi = cur_src.fetchall()

            for r in righe_elementi:
                vecchio_id = r["id"]
                tipo = r["tipo"] if "tipo" in cols_src and r["tipo"] else "Libro"
                # Normalizza tipo se necessario
                if tipo not in ("Libro", "Copione", "CD / Vinile"):
                    tipo = "Libro"

                titolo = (r["titolo"] if "titolo" in cols_src else "") or "Senza Titolo"
                autore = r["autore"] if "autore" in cols_src else ""
                collocazione = r["collocazione_casa"] if "collocazione_casa" in cols_src else ""
                note = r["note"] if "note" in cols_src else ""
                copertina = r["copertina_path"] if "copertina_path" in cols_src else ""
                data_ins = r["data_inserimento"] if "data_inserimento" in cols_src else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                regista = r["regista"] if "regista" in cols_src else ""
                luogo = r["prima_esibizione_luogo"] if "prima_esibizione_luogo" in cols_src else ""
                data_ingaggio = r["data_ingaggio"] if "data_ingaggio" in cols_src else ""
                data_prima = r["data_prima"] if "data_prima" in cols_src else ""
                formato = r["formato"] if "formato" in cols_src else ""
                etichetta = r["etichetta_anno"] if "etichetta_anno" in cols_src else ""

                # Inserisci nel nuovo database
                cur_dst.execute("""
                    INSERT INTO elementi (
                        tipo, titolo, autore, collocazione_casa, note, copertina_path,
                        data_inserimento, regista, prima_esibizione_luogo, data_ingaggio,
                        data_prima, formato, etichetta_anno
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tipo, titolo, autore, collocazione, note, copertina,
                    data_ins, regista, luogo, data_ingaggio,
                    data_prima, formato, etichetta
                ))

                nuovo_id = cur_dst.lastrowid
                id_elem_map[vecchio_id] = nuovo_id
                tot_elementi += 1

            print(f"   ✅ Trasferiti {tot_elementi} elementi.")

        # ----------------------------------------------------------------------
        # 2. MIGRAZIONE TABELLA PRESTITI
        # ----------------------------------------------------------------------
        if tabella_esiste(cur_src, "prestiti"):
            cols_src_prest = colonne_tabella(cur_src, "prestiti")
            print("\n🤝 2. Migrazione Registro dei Prestiti...")

            cur_src.execute("SELECT * FROM prestiti ORDER BY id ASC")
            righe_prestiti = cur_src.fetchall()

            for r in righe_prestiti:
                vecchio_elem_id = r["elemento_id"]
                if vecchio_elem_id in id_elem_map:
                    nuovo_elem_id = id_elem_map[vecchio_elem_id]
                    
                    # Supporta sia il formato attuale (nome_persona) che eventuali varianti storiche (persona)
                    nome_persona = (
                        r["nome_persona"] if "nome_persona" in cols_src_prest 
                        else (r["persona"] if "persona" in cols_src_prest else "Sconosciuto")
                    ) or "Sconosciuto"

                    data_prest = (r["data_prestito"] if "data_prestito" in cols_src_prest else "") or datetime.now().strftime("%Y-%m-%d")
                    
                    data_rientro_p = (
                        r["data_rientro_prevista"] if "data_rientro_prevista" in cols_src_prest
                        else (r["data_rientro_previsto"] if "data_rientro_previsto" in cols_src_prest else "")
                    ) or ""

                    data_rientro_e = (
                        r["data_rientro_effettiva"] if "data_rientro_effettiva" in cols_src_prest
                        else (r["data_rientro_effettivo"] if "data_rientro_effettivo" in cols_src_prest else "")
                    ) or ""

                    if "stato" in cols_src_prest and r["stato"] in ("In Prestito", "Rientrato"):
                        stato = r["stato"]
                    else:
                        stato = "Rientrato" if data_rientro_e else "In Prestito"

                    cur_dst.execute("""
                        INSERT INTO prestiti (
                            elemento_id, nome_persona, data_prestito, data_rientro_prevista,
                            data_rientro_effettiva, stato
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (nuovo_elem_id, nome_persona, data_prest, data_rientro_p, data_rientro_e, stato))
                    tot_prestiti += 1

            print(f"   ✅ Trasferiti {tot_prestiti} prestiti.")

        # ----------------------------------------------------------------------
        # 3. MIGRAZIONE TABELLA APPUNTI (TACCUINO DEI RICORDI DELLE OPERE)
        # ----------------------------------------------------------------------
        if tabella_esiste(cur_src, "appunti"):
            cols_src_app = colonne_tabella(cur_src, "appunti")
            print("\n📝 3. Migrazione Appunti e Ricordi delle Opere...")

            cur_src.execute("SELECT * FROM appunti ORDER BY id ASC")
            righe_appunti = cur_src.fetchall()

            for r in righe_appunti:
                vecchio_elem_id = r["elemento_id"]
                if vecchio_elem_id in id_elem_map:
                    nuovo_elem_id = id_elem_map[vecchio_elem_id]
                    testo = r["testo"] if "testo" in cols_src_app else ""
                    data_c = r["data_creazione"] if "data_creazione" in cols_src_app else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    cur_dst.execute("""
                        INSERT INTO appunti (elemento_id, testo, data_creazione)
                        VALUES (?, ?, ?)
                    """, (nuovo_elem_id, testo, data_c))
                    tot_appunti += 1

            print(f"   ✅ Trasferiti {tot_appunti} ricordi e appunti.")

        # ----------------------------------------------------------------------
        # 4. MIGRAZIONE DIARIO DEI PENSIERI (se presente nel vecchio DB)
        # ----------------------------------------------------------------------
        if tabella_esiste(cur_src, "diario_pensieri"):
            cols_src_diario = colonne_tabella(cur_src, "diario_pensieri")
            print("\n📜 4. Migrazione Fogli del Diario dei Pensieri...")

            cur_src.execute("SELECT * FROM diario_pensieri ORDER BY id ASC")
            for r in cur_src.fetchall():
                vecchio_pid = r["id"]
                titolo = r["titolo"] if "titolo" in cols_src_diario else ""
                testo = r["testo"] if "testo" in cols_src_diario else ""
                fonte = r["fonte_riferimento"] if "fonte_riferimento" in cols_src_diario else ""
                data_c = r["data_creazione"] if "data_creazione" in cols_src_diario else ""
                data_m = r["data_ultima_modifica"] if "data_ultima_modifica" in cols_src_diario else ""
                eliminato = r["eliminato"] if "eliminato" in cols_src_diario else 0
                data_elim = r["data_eliminazione"] if "data_eliminazione" in cols_src_diario else None

                cur_dst.execute("""
                    INSERT INTO diario_pensieri (
                        titolo, testo, fonte_riferimento, data_creazione,
                        data_ultima_modifica, eliminato, data_eliminazione
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (titolo, testo, fonte, data_c, data_m, eliminato, data_elim))

                nuovo_pid = cur_dst.lastrowid
                id_diario_map[vecchio_pid] = nuovo_pid
                tot_pensieri += 1

            print(f"   ✅ Trasferiti {tot_pensieri} fogli del diario.")

            # Cronologia delle revisioni del diario
            if tabella_esiste(cur_src, "diario_cronologia"):
                cols_src_cron = colonne_tabella(cur_src, "diario_cronologia")
                cur_src.execute("SELECT * FROM diario_cronologia ORDER BY id ASC")
                for r in cur_src.fetchall():
                    vecchio_pid = r["pensiero_id"]
                    if vecchio_pid in id_diario_map:
                        nuovo_pid = id_diario_map[vecchio_pid]
                        testo_p = r["testo_precedente"] if "testo_precedente" in cols_src_cron else ""
                        data_m = r["data_modifica"] if "data_modifica" in cols_src_cron else ""

                        cur_dst.execute("""
                            INSERT INTO diario_cronologia (pensiero_id, testo_precedente, data_modifica)
                            VALUES (?, ?, ?)
                        """, (nuovo_pid, testo_p, data_m))
                        tot_cronologia += 1

                print(f"   ✅ Trasferite {tot_cronologia} revisioni storiche del diario.")

        # Commit atomico finale
        conn_dst.commit()
        cur_dst.execute("PRAGMA optimize;")

        print("\n------------------------------------------------------------------")
        print("🎉 MIGRAZIONE COMPLETATA CON SUCCESSO!")
        print("------------------------------------------------------------------")
        print(f"  • Volumi e copioni integrati:   {tot_elementi}")
        print(f"  • Prestiti riagganciati:        {tot_prestiti}")
        print(f"  • Appunti e ricordi trasferiti: {tot_appunti}")
        if tot_pensieri > 0:
            print(f"  • Fogli diario integrati:       {tot_pensieri}")
        print("------------------------------------------------------------------")
        print("Tutti i dati sono al loro posto nel nuovo database.")
        print("==================================================================")
        return True

    except Exception as e:
        conn_dst.rollback()
        print(f"\n❌ ERRORE durante la migrazione: {e}")
        print("La transazione è stata annullata e il database originale è intatto.")
        return False
    finally:
        conn_src.close()
        conn_dst.close()


def main():
    """Interfaccia interattiva a riga di comando per una migrazione semplice."""
    if len(sys.argv) > 1:
        sorgente = sys.argv[1].strip()
        migra_database(sorgente)
        return

    print("==================================================================")
    print("🎭 ASSISTENTE MIGRAZIONE DATI - MEMORIE DI SCENA")
    print("==================================================================")
    candidati = trova_vecchi_database()

    if candidati:
        print("Trovati i seguenti database precedenti nel sistema:\n")
        for i, c in enumerate(candidati, start=1):
            dim = os.path.getsize(c) // 1024
            print(f"  [{i}] {os.path.basename(c)}  ({dim} KB)")
        print("\n  [0] Inserisci manualmente un percorso diverso")

        scelta = input(f"\nScegli quale database importare [1-{len(candidati)}] o 0: ").strip()
        if scelta.isdigit():
            num = int(scelta)
            if 1 <= num <= len(candidati):
                migra_database(candidati[num - 1])
                return

    # Inserimento manuale
    percorso = input("\nTrascina qui il file del vecchio database (.db) o scrivi il percorso: ").strip()
    percorso = percorso.strip("'\"")
    if percorso:
        migra_database(percorso)
    else:
        print("Nessun percorso inserito. Operazione terminata.")


if __name__ == "__main__":
    main()
