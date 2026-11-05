"""Warehouse batch prototype. No Maximo or browser transport is implemented here."""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event
import time
from uuid import uuid4


@dataclass(frozen=True)
class WarehouseAction:
    label: str
    native_label: str
    initial_status: str


ACTIONS = {
    'receive': WarehouseAction('Confirmar recepción', 'Confirmar recepción', 'WAPPR'),
    'dispatch': WarehouseAction('Dar salida del almacén', 'Dar salida activo del almacén', 'ISSUE'),
}
STEPS = ('Abrir ficha', 'Comprobar OT y estado', 'Seleccionar acción',
         'Confirmar acción', 'Verificar resultado')
SCENARIOS = {'success': 'Todas correctas', 'incidents': 'Incluir fallo y resultado incierto'}


@dataclass(frozen=True)
class WarehouseItem:
    ot: str
    equipment: str = ''
    serial: str = ''
    status: str = ''
    client: str = ''


@dataclass(frozen=True)
class WarehouseResult:
    item: WarehouseItem
    status: str = 'pending'
    step: str = 'Pendiente'
    detail: str = ''
    completed_steps: int = 0


def freeze_items(items):
    """Freeze identifiers, deduplicate and reject empty OTs before starting a batch."""
    unique = {}
    for item in items:
        ot = item.ot.strip()
        if not ot:
            raise ValueError('El lote contiene una OT sin identificar.')
        clean = replace(item, ot=ot)
        if ot in unique and unique[ot] != clean:
            raise ValueError(f'La OT {ot} aparece con datos contradictorios.')
        unique[ot] = clean
    if not unique:
        raise ValueError('Selecciona al menos una OT visible.')
    return tuple(unique.values())


def run_simulation(items, action, scenario='success', *, stop=None, progress=None, delay=0.18):
    """Sequential, non-network simulation; never retries a submitted confirmation.

    Failures and uncertain results remain in the report while the next item runs.
    Cancellation is checked between OTs, not during confirmation.
    """
    if action not in ACTIONS or scenario not in SCENARIOS:
        raise ValueError('Acción o escenario de simulación no válido.')
    items = freeze_items(items)
    stop = stop if stop is not None else Event()
    progress = progress or (lambda index, result: None)
    results = []
    for index, item in enumerate(items):
        result = WarehouseResult(item)
        if stop.is_set():
            result = replace(result, status='stopped', step='Sin procesar',
                             detail='Detenido antes de comenzar esta OT.')
        else:
            for step_index, step in enumerate(STEPS):
                result = replace(result, status='running', step=step + ' (simulación)')
                progress(index, result)
                if delay:
                    time.sleep(delay)
                if step_index == 1 and item.status.strip().upper() != ACTIONS[action].initial_status:
                    result = replace(result, status='failed', detail=(
                        f'Estado del listado: {item.status or "sin indicar"}. '
                        f'La simulación requiere {ACTIONS[action].initial_status}. '
                        'No se ha consultado Maximo.'))
                    break
                if scenario == 'incidents' and index % 4 == 1 and step_index == 2:
                    result = replace(result, status='failed',
                                     detail='Fallo simulado: la opción de almacén no está disponible.')
                    break
                if scenario == 'incidents' and index % 4 == 2 and step_index == 4:
                    result = replace(result, status='uncertain',
                                     detail='Timeout simulado después de confirmar. No se repite la acción.')
                    break
                result = replace(result, completed_steps=step_index + 1)
            if result.status == 'running':
                result = replace(result, status='success', step='Simulación correcta',
                                 detail='Recorrido simulado completado. No se ha modificado ninguna OT en Maximo.')
        results.append(result)
        progress(index, result)
    return tuple(results)


def save_simulation_report(folder, batch_id, action, scenario, results):
    """Keep simulation reports separate and explicitly identified as non-real data."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        'schema_version': 1, 'simulation': True, 'batch_id': batch_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'action': action, 'scenario': scenario,
        'results': [asdict(result) for result in results],
    }
    path = folder / f'almacen-simulacion-{uuid4().hex}.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return path
