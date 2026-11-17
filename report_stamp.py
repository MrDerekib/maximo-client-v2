"""Positive, verified discard evidence for HTML report annotations.

CLOSE alone is deliberately insufficient. Evidence survives routine Maximo imports.
Existing successful MD operation reports are imported for older discarded OTs.
"""
import json
import logging
import re
from contextlib import closing
from app_paths import LOG_DIR
from db import get_connection


def _table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS report_discard_evidence "
                 "(ot TEXT PRIMARY KEY, source TEXT NOT NULL, verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")


def record_verified_discard(result):
    if (not isinstance(result, dict) or result.get('action') != 'discard'
            or result.get('status') != 'CLOSE' or result.get('cancelled')):
        return False
    ot = str(result.get('ot', '')).strip()
    if not re.fullmatch(r'\d{5,12}', ot):
        return False
    try:
        with closing(get_connection()) as conn, conn:
            _table(conn)
            conn.execute("INSERT OR IGNORE INTO report_discard_evidence (ot, source) VALUES (?, ?)",
                         (ot, 'verified_discard'))
        return True
    except Exception:
        logging.exception('OT %s: no se pudo conservar la evidencia de desecho para el sello', ot)
        return False


def verified_discard_ots():
    """Import only successful discard results, never pending or ordinary CLOSEs."""
    try:
        with closing(get_connection()) as conn, conn:
            _table(conn)
            for path in (LOG_DIR / 'almacen-operaciones').glob('repair-*-result.json'):
                try:
                    report = json.loads(path.read_text(encoding='utf-8'))
                    if report.get('action') != 'technician_discard':
                        continue
                    for row in report.get('results', []):
                        ot = str(row.get('item', {}).get('ot', '')).strip()
                        if (row.get('status') in ('success', 'already_completed')
                                and row.get('verified_status') == 'CLOSE'
                                and re.fullmatch(r'\d{5,12}', ot)):
                            conn.execute("INSERT OR IGNORE INTO report_discard_evidence (ot, source) VALUES (?, ?)",
                                         (ot, 'verified_operation_report'))
                except (OSError, ValueError, TypeError, AttributeError):
                    logging.warning('No se pudo leer evidencia de desecho en %s', path.name)
            return {row[0] for row in conn.execute('SELECT ot FROM report_discard_evidence')}
    except Exception:
        logging.exception('No se pudo consultar la evidencia de desecho; parte sin sello')
        return set()
