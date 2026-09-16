# db.py
import sqlite3
import logging
from typing import List, Tuple, Optional
from config import load_config
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
    conn.close()


def update_database_from_df(df):
    conn = get_connection()
    cur = conn.cursor()

    init_db()  # por si acaso

    new_entries = 0
    updated_entries = 0

    for row in df.itertuples(index=False, name=None):
        ot = str(row[0]).replace('\u00a0', ' ').strip()

        cur.execute("SELECT * FROM maximo WHERE REPLACE(OT, ' ', ' ') = REPLACE(?, ' ', ' ')", (ot,))
        existing = cur.fetchone()

        new_data = tuple("" if v is None else str(v).replace(' ', ' ').strip() for v in row[1:])

        if existing:
            existing_data = tuple("" if v is None else str(v).replace(' ', ' ').strip() for v in existing[1:])
            if existing_data != new_data:
                cur.execute(
                    """
                    UPDATE maximo SET
                        Descripción = ?,
                        Nº_de_serie = ?,
                        Fecha = ?,
                        Cliente = ?,
                        Tipo_de_trabajo = ?,
                        Seguimiento = ?,
                        Planta = ?
                    WHERE OT = ?
                    """,
                    new_data + (ot,)
                )
                updated_entries += 1
        else:
            cur.execute(
                "INSERT INTO maximo VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ot,) + new_data
            )
            new_entries += 1

    conn.commit()
    conn.close()
    logging.info(f"BD: nuevas entradas={new_entries}, actualizadas={updated_entries}")
    return new_entries, updated_entries



def update_seguimiento(ot: str, value: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE maximo SET Seguimiento = ? WHERE OT = ?", (value, ot))
    conn.commit()
    conn.close()
    logging.info(f"BD: Seguimiento actualizado OT={ot} -> {value}")


def fetch_data(filter_text: str, search_by: str, client_filter: Optional[str], advanced=None) -> List[Tuple]:
    from search_filters import validate_filters
    advanced = validate_filters(advanced or {})
    if search_by not in ("OT", "Nº_de_serie", "Descripción"):
        raise ValueError("Campo de búsqueda no válido")

    filter_words = filter_text.strip().split()
    query = "SELECT * FROM maximo"
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
        return {key: [row[0] for row in conn.execute(
            f"SELECT DISTINCT FILTER_VALUE({column}) FROM maximo ORDER BY 1"
        )] for key, column in (("clients", "Cliente"), ("types", "Tipo_de_trabajo"), ("tracking", "Seguimiento"))}
    finally:
        conn.close()
