"""Warehouse actions and immutable batch data."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class WarehouseAction:
    label: str
    native_label: str
    initial_status: str
    role: str = "warehouse"


ACTIONS = {
    'receive': WarehouseAction('Confirmar recepción', 'Confirmar recepción', 'WAPPR'),
    'reject_receive': WarehouseAction('Rechazar recepción', 'Rechazar recepción', 'WAPPR'),
    'receive_sat_internal': WarehouseAction('Confirmar y enviar a SAT Interno', 'Confirmar y enviar a SAT Interno', 'WAPPR'),
    'receive_sat_external': WarehouseAction('Confirmar y enviar a SAT Externo', 'Confirmar y enviar a SAT Externo', 'WAPPR'),
    'technician_sat_external': WarehouseAction('Enviar a SAT Externo · Técnico', 'Enviar a SAT Externo', 'APPR', 'technician'),
    'technician_discard': WarehouseAction('Declarar irreparable · Técnico','Desechar equipo','INPRG','technician'),
    'technician_close': WarehouseAction('Finalizar reparación · Técnico','Cerrar OT','INPRG','technician'),
    'dispatch': WarehouseAction('Dar salida del almacén', 'Dar salida activo del almacén', 'ISSUE'),
}
FINAL_STATES = {'technician_discard':'CLOSE','technician_close':'ISSUE','receive': 'APPR', 'dispatch': 'CLOSE', 'technician_sat_external': 'ISSUE',
                'receive_sat_external': 'ISSUE', 'receive_sat_internal': 'ISSUE'}
RECEIPT_ACTIONS = ('receive', 'reject_receive', 'receive_sat_internal', 'receive_sat_external')
STEPS = ('Abrir ficha', 'Comprobar OT y estado', 'Seleccionar acción',
         'Confirmar acción', 'Verificar resultado')
LIST_STATUS_CODES = {'PDTE CONFIRMAR': 'WAPPR', 'DAR SALIDA': 'ISSUE'}


def warehouse_status_code(value):
    """Compare known MD labels and Edge codes without changing the source value."""
    status = ' '.join(str(value or '').split()).upper()
    return LIST_STATUS_CODES.get(status, status)


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
    verified_status: str = ''
    operation_id: str = ''
    local_status_saved: bool | None = None


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
