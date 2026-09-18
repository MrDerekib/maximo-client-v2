# db.py
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from typing import List, Tuple, Optional
from config import load_config
from app_paths import BACKUP_DIR
from search_filters import normalize_filter_value


def get_connection():
    cfg = load_config()
    return sqlite3.connect(cfg.db_path)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS maximo (
            OT TEXT PRIMARY KEY,
            Descripción TEXT,
            Nº_de_serie TEXT,
            Fecha TEXT,
            Cliente TEXT,
            Tipo_de_trabajo TEXT,
            Seguimiento TEXT,
            Planta TEXT
        )
    """)
    conn.commit()
    try:
        _normalize_stored_categories(conn)
        _migrate_sync_status(conn)
        _migrate_reconciliation_status(conn)
    finally:
        conn.close()


def _normalize_stored_categories(conn):
    """Migración única, con backup previo y actualización atómica de tres campos."""
    migration = "normalize_categories_v1"
    conn.execute("CREATE TABLE IF NOT EXISTS client_migrations (name TEXT PRIMARY KEY)")
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM client_migrations WHERE name = ?", (migration,)).fetchone():
            conn.commit()
            return
        changes = []
        for ot, *values in conn.execute("SELECT OT, Cliente, Tipo_de_trabajo, Seguimiento FROM maximo"):
            normalized = [normalize_filter_value(value) if value is not None else None for value in values]
            if normalized != values:
                changes.append((*normalized, ot))
        if changes:
            database = Path(conn.execute("PRAGMA database_list").fetchone()[2]).resolve()
            folder = BACKUP_DIR
            folder.mkdir(parents=True, exist_ok=True)
            backup = folder / f"{database.stem}-before-normalization-{uuid4().hex}.db"
            # Otra conexión de lectura puede copiar el estado confirmado mientras
            # BEGIN IMMEDIATE impide que otro escritor cambie los datos originales.
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source, \
                 closing(sqlite3.connect(backup)) as destination:
                source.backup(destination)
            logging.info("Copia previa a normalización: %s", backup)
            conn.executemany("UPDATE maximo SET Cliente=?, Tipo_de_trabajo=?, Seguimiento=? WHERE OT=?", changes)
        conn.execute("INSERT INTO client_migrations (name) VALUES (?)", (migration,))
        conn.commit()
        logging.info("Normalización de categorías: %d OT actualizadas", len(changes))
    except Exception:
        conn.rollback()
        raise


def _migrate_sync_status(conn):
    """Añade el estado de presencia sin clasificar datos heredados aún."""
    migration = "sync_status_v1"
    conn.execute("CREATE TABLE IF NOT EXISTS client_migrations (name TEXT PRIMARY KEY)")
    if conn.execute("SELECT 1 FROM client_migrations WHERE name = ?", (migration,)).fetchone():
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(maximo)")}
    if "Activo" not in columns:
        conn.execute("ALTER TABLE maximo ADD COLUMN Activo INTEGER")
    if "Ultima_vez_visto" not in columns:
        conn.execute("ALTER TABLE maximo ADD COLUMN Ultima_vez_visto TEXT")
    conn.execute("INSERT INTO client_migrations (name) VALUES (?)", (migration,))
    conn.commit()


def _migrate_reconciliation_status(conn):
    """Registra cuándo se comprobó una OT histórica por última vez."""
    migration = "inactive_reconciliation_v1"
    conn.execute("CREATE TABLE IF NOT EXISTS client_migrations (name TEXT PRIMARY KEY)")
    if conn.execute("SELECT 1 FROM client_migrations WHERE name = ?", (migration,)).fetchone():
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(maximo)")}
    if "Ultima_comprobacion_estado" not in columns:
        conn.execute("ALTER TABLE maximo ADD COLUMN Ultima_comprobacion_estado TEXT")
    conn.execute("INSERT INTO client_migrations (name) VALUES (?)", (migration,))
    conn.commit()


def update_database_from_df(df):
    init_db()  # Incluye la migración antes de importar.
    conn = get_connection()
    cur = conn.cursor()

    new_entries = 0
    updated_entries = 0

    seen_at = datetime.now().isoformat(timespec="seconds")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in df.itertuples(index=False, name=None):
            ot = str(row[0]).replace('\u00a0', ' ').strip()
            cur.execute(
                "SELECT Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo, Seguimiento, Planta "
                "FROM maximo WHERE REPLACE(OT, ' ', ' ') = REPLACE(?, ' ', ' ')",
                (ot,),
            )
            existing = cur.fetchone()

            new_data = tuple("" if v is None else str(v).replace(' ', ' ').strip() for v in row[1:])
            new_data = tuple(normalize_filter_value(value) if index in (3, 4, 5) else value
                             for index, value in enumerate(new_data))

            if existing:
                existing_data = tuple("" if v is None else str(v).replace(' ', ' ').strip() for v in existing)
                if existing_data != new_data:
                    cur.execute(
                        """
                        UPDATE maximo SET
                            Descripción = ?, Nº_de_serie = ?, Fecha = ?, Cliente = ?,
                            Tipo_de_trabajo = ?, Seguimiento = ?, Planta = ?
                        WHERE OT = ?
                        """,
                        new_data + (ot,),
                    )
                    updated_entries += 1
                cur.execute("UPDATE maximo SET Activo = 1, Ultima_vez_visto = ? WHERE OT = ?", (seen_at, ot))
            else:
                cur.execute(
                    """INSERT INTO maximo (
                        OT, Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo,
                        Seguimiento, Planta, Activo, Ultima_vez_visto
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (ot,) + new_data + (seen_at,),
                )
                new_entries += 1

        # Solo una importación completa y correcta puede desactivar las OT ausentes.
        cur.execute("UPDATE maximo SET Activo = 0 WHERE Activo IS NULL OR Activo = 1 AND Ultima_vez_visto <> ?", (seen_at,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logging.info(f"BD: nuevas entradas={new_entries}, actualizadas={updated_entries}")
    return new_entries, updated_entries



def update_seguimiento(ot: str, value: str):
    value = normalize_filter_value(value)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE maximo SET Seguimiento = ? WHERE OT = ?", (value, ot))
    conn.commit()
    conn.close()
    logging.info(f"BD: Seguimiento actualizado OT={ot} -> {value}")


def delete_inactive_record(ot: str) -> bool:
    """Elimina solo una OT que ya no aparece en la última importación."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM maximo WHERE OT = ? AND Activo = 0", (ot,))
        conn.commit()
        deleted = cur.rowcount == 1
    finally:
        conn.close()
    if deleted:
        logging.info("BD: OT inactiva eliminada: %s", ot)
    return deleted


def inactive_record_count() -> int:
    """Cuenta los registros que ya no aparecieron en la última importación correcta."""
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM maximo WHERE Activo = 0").fetchone()[0]
    finally:
        conn.close()


def delete_all_inactive_records() -> int:
    """Elimina exclusivamente registros no activos de la base local."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM maximo WHERE Activo = 0")
        conn.commit()
        deleted = cur.rowcount
    finally:
        conn.close()
    logging.info("BD: %d registros no activos eliminados.", deleted)
    return deleted


INACTIVE_RECONCILIATION_TRACKING = ("PDTE CONFIRMAR", "EN TALLER", "APPR", "INPRG")


def inactive_tracking_candidates(limit: int | None = 5,
                                minimum_age_hours: int | None = 24) -> List[Tuple[str, str]]:
    """Devuelve OT históricas con seguimientos que deben contrastarse en Maximo."""
    conn = get_connection()
    try:
        placeholders = ", ".join("?" for _ in INACTIVE_RECONCILIATION_TRACKING)
        query = f"SELECT OT, Seguimiento FROM maximo WHERE Activo = 0 AND Seguimiento IN ({placeholders})"
        params = list(INACTIVE_RECONCILIATION_TRACKING)
        if minimum_age_hours is not None:
            cutoff = (datetime.now() - timedelta(hours=minimum_age_hours)).isoformat(timespec="seconds")
            query += " AND (Ultima_comprobacion_estado IS NULL OR Ultima_comprobacion_estado < ?)"
            params.append(cutoff)
        query += " ORDER BY COALESCE(Ultima_comprobacion_estado, ''), OT"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return rows
    finally:
        conn.close()


def inactive_tracking_candidate_count(minimum_age_hours: int | None = 24) -> int:
    """Cuenta las OT que una conciliación tendría que revisar."""
    return len(inactive_tracking_candidates(limit=None, minimum_age_hours=minimum_age_hours))


def apply_reconciled_status(ot: str, status: str, checked_at: str | None = None) -> bool:
    """Guarda el estado real solo si la OT sigue siendo histórica y es candidata."""
    checked_at = checked_at or datetime.now().isoformat(timespec="seconds")
    status = normalize_filter_value(status)
    conn = get_connection()
    try:
        placeholders = ", ".join("?" for _ in INACTIVE_RECONCILIATION_TRACKING)
        if status:
            cur = conn.execute(
                f"""UPDATE maximo
                   SET Seguimiento = ?, Ultima_comprobacion_estado = ?
                   WHERE OT = ? AND Activo = 0
                     AND Seguimiento IN ({placeholders})""",
                (status, checked_at, ot, *INACTIVE_RECONCILIATION_TRACKING),
            )
        else:
            cur = conn.execute(
                f"""UPDATE maximo SET Ultima_comprobacion_estado = ?
                   WHERE OT = ? AND Activo = 0
                     AND Seguimiento IN ({placeholders})""",
                (checked_at, ot, *INACTIVE_RECONCILIATION_TRACKING),
            )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


def fetch_data(filter_text: str, search_by: str, client_filter: Optional[str], advanced=None,
               include_sync: bool = False) -> List[Tuple]:
    from search_filters import validate_filters
    advanced = validate_filters(advanced or {})
    if search_by not in ("OT", "Nº_de_serie", "Descripción"):
        raise ValueError("Campo de búsqueda no válido")

    filter_words = filter_text.strip().split()
    columns = "Activo, Ultima_vez_visto, OT, Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo, Seguimiento, Planta" \
        if include_sync else "OT, Descripción, Nº_de_serie, Fecha, Cliente, Tipo_de_trabajo, Seguimiento, Planta"
    query = "SELECT " + columns + " FROM maximo"
    params = []

    conditions = []
    if filter_words:
        conditions.append(" AND ".join([f"LOWER({search_by}) LIKE ?" for _ in filter_words]))
        params.extend(f"%{word.lower()}%" for word in filter_words)

    if client_filter and client_filter != "Todos" and not advanced.get("clients"):
        conditions.append("FILTER_VALUE(Cliente) = ?")
        params.append(normalize_filter_value(client_filter))

    for key, column in (("clients", "Cliente"), ("types", "Tipo_de_trabajo"), ("tracking", "Seguimiento")):
        values = advanced.get(key, [])
        if values:
            conditions.append(f"FILTER_VALUE({column}) IN ({','.join('?' for _ in values)})")
            params.extend(values)
    for word in advanced.get("equipment", "").split():
        conditions.append("LOWER(Descripción) LIKE ? ESCAPE '\\'")
        escaped = word.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
    for key, operator in (("date_from", ">="), ("date_to", "<=")):
        if advanced.get(key):
            conditions.append(f"Fecha {operator} ?")
            params.append(advanced[key])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    conn = get_connection()
    cur = conn.cursor()
    conn.create_function("FILTER_VALUE", 1, normalize_filter_value)
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def filter_choices():
    conn = get_connection()
    try:
        conn.create_function("FILTER_VALUE", 1, normalize_filter_value)
        values = {key: [row[0] for row in conn.execute(
            f"SELECT DISTINCT FILTER_VALUE({column}) FROM maximo ORDER BY 1"
        )] for key, column in (("clients", "Cliente"), ("types", "Tipo_de_trabajo"), ("tracking", "Seguimiento"))}
        values["equipment"] = [row[0] for row in conn.execute(
            "SELECT DISTINCT Descripción FROM maximo WHERE Descripción IS NOT NULL AND Descripción <> '' ORDER BY 1"
        )]
        return values
    finally:
        conn.close()
