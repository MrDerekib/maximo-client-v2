"""Durable per-OT recovery records. No credentials, session objects or SAT details."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import threading
from uuid import uuid4

from app_paths import LOG_DIR, create_unique_file
from warehouse import WarehouseItem, FINAL_STATES

_guard = threading.RLock()
PHASES = {'route_attempted', 'confirmation_attempted', 'details_attempted', 'verified', 'complete'}
ACTIONS = {'receive', 'dispatch', 'receive_sat_internal', 'receive_sat_external'}


class PendingOperationError(RuntimeError):
    pass


class RecoveryStore:
    def __init__(self, folder=None, *, origin_report=''):
        self.origin_report = origin_report
        self.folder = Path(folder or LOG_DIR / 'almacen-operaciones') / 'pendientes'

    def _path(self, ot):
        return self.folder / (hashlib.sha256(str(ot).encode()).hexdigest() + '.json')

    def _read(self, path):
        if path.stat().st_size > 128_000:
            raise RuntimeError('Registro de recuperación demasiado grande; requiere revisión.')
        record = json.loads(path.read_text(encoding='utf-8'))
        if (record.get('schema_version') != 1 or record.get('action') not in ACTIONS or
                record.get('phase') not in PHASES or not record.get('operation_id') or
                not isinstance(record.get('item'), dict) or not record['item'].get('ot') or
                not isinstance(record.get('identity'), dict)):
            raise RuntimeError('Registro de recuperación inválido; no se enviará otra acción.')
        if path != self._path(record['item']['ot']):
            raise RuntimeError('El registro no corresponde a su OT.')
        identity = record['identity']
        if (not identity.get('Activo') or not identity.get('Planta') or
                not isinstance(identity.get('Nº de serie'), str) or
                any(not isinstance(record['item'].get(k, ''), str) for k in ('ot','equipment','serial','status','client')) or
                (record['phase'] in ('verified','complete') and record.get('verified_status') != FINAL_STATES[record['action']])):
            raise RuntimeError('Evidencias de recuperación incompletas; requiere revisión.')
        return record

    def get(self, ot):
        with _guard:
            path = self._path(ot)
            if not path.exists():
                return None
            record = self._read(path)
            return record if record['phase'] != 'complete' else None

    def pending(self):
        with _guard:
            records = [self._read(path) for path in sorted(self.folder.glob('*.json'))]
            return [record for record in records if record['phase'] != 'complete']

    def begin(self, item, action, identity, initial_state, history_before=None, *, verified_status=''):
        record = {'schema_version': 1, 'operation_id': uuid4().hex, 'item': asdict(item),
                  'action': action, 'identity': dict(identity), 'initial_state': initial_state,
                  'origin_report': self.origin_report,
                  'history_before': history_before, 'verified_status': verified_status,
                  'phase': 'verified' if verified_status else 'route_attempted',
                  'route_attempted': not bool(verified_status), 'confirmation_attempted': False,
                  'details_attempted': False, 'created_at': datetime.now(timezone.utc).isoformat()}
        payload = json.dumps(record, ensure_ascii=False)
        if len(payload.encode('utf-8')) > 128_000:
            raise RuntimeError('Registro de recuperación demasiado grande; no se enviará la acción.')
        with _guard:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self._path(item.ot)
            if path.exists() and self._read(path)['phase'] == 'complete':
                path.unlink()
            created = False
            try:
                with path.open('x', encoding='utf-8') as stream:
                    created = True
                    stream.write(payload)
                    stream.flush(); os.fsync(stream.fileno())
            except FileExistsError:
                raise PendingOperationError(f'La OT {item.ot} tiene una operación pendiente. Usa Reverificar.') from None
            except Exception:
                if created:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass
                raise
        return record

    def update(self, record, phase, **values):
        with _guard:
            path = self._path(record['item']['ot'])
            current = self._read(path)
            if current['operation_id'] != record['operation_id']:
                raise PendingOperationError('La operación pendiente ha cambiado; vuelve a consultar.')
            if phase not in PHASES:
                raise ValueError('Fase de recuperación inválida.')
            current.update(values, phase=phase, updated_at=datetime.now(timezone.utc).isoformat())
            if phase in ('verified','complete') and current.get('verified_status') != FINAL_STATES[current['action']]:
                raise ValueError('No hay un estado final verificado para esta acción.')
            temporary = create_unique_file(self.folder, 'recovery-', '.tmp')
            try:
                with temporary.open('w', encoding='utf-8') as stream:
                    json.dump(current, stream, ensure_ascii=False)
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return current

    def update_report(self, record, result):
        """Refresh an older report after recovery, without trusting paths from JSON."""
        name = record.get('origin_report', '')
        if not name:
            return
        if not re.fullmatch(r'[A-Za-z0-9_-]+-result\.json', name):
            raise RuntimeError('Ruta de reporte de recuperación inválida.')
        path = self.folder.parent / name
        if not path.exists():
            return  # Initial batches create their report when the worker finishes.
        with _guard:
            if path.stat().st_size > 8_000_000:
                raise RuntimeError('Reporte demasiado grande; requiere revisión.')
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('action') != record['action']:
                raise RuntimeError('El reporte corresponde a otra acción.')
            for index, row in enumerate(data['results']):
                if row['item']['ot'] == result.item.ot:
                    data['results'][index] = asdict(result)
                    break
            else:
                raise RuntimeError('La OT no está en el reporte original.')
            data['recovered_at'] = datetime.now(timezone.utc).isoformat()
            temporary = create_unique_file(path.parent, 'report-', '.tmp')
            try:
                with temporary.open('w', encoding='utf-8') as stream:
                    json.dump(data, stream, ensure_ascii=False, indent=2)
                    stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def complete(self, record):
        with _guard:
            if not self._path(record['item']['ot']).exists():
                return
            self.update(record, 'complete')
            self._path(record['item']['ot']).unlink(missing_ok=True)


def recovery_item(record):
    return WarehouseItem(**{key: record['item'].get(key, '') for key in ('ot','equipment','serial','status','client')})
