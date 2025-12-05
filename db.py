# db.py
import sqlite3
from typing import List, Tuple, Optional
from config import load_config


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
    print(f"BD: nuevas entradas={new_entries}, actualizadas={updated_entries}")
    return new_entries, updated_entries



def fetch_data(filter_text: str, search_by: str, client_filter: Optional[str]) -> List[Tuple]:
    """
    Equivalente a fetch_data de tu GUI actual.
    """
    filter_words = filter_text.strip().split()
    query = "SELECT * FROM maximo"
    params = []

    conditions = []
    if filter_words:
        conditions.append(" AND ".join([f"LOWER({search_by}) LIKE ?" for _ in filter_words]))
        params.extend(f"%{word.lower()}%" for word in filter_words)

    if client_filter and client_filter != "Todos":
        conditions.append("Cliente = ?")
        params.append(client_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows
