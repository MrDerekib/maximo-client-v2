"""Reviewed input for technician SAT dispatch; separate from warehouse reception."""
from copy import deepcopy
from dataclasses import dataclass
import re

from failure_catalog import resolve_selection
from warehouse import WarehouseItem, freeze_items
from workorder_close import repair_seconds


TECHNICIAN_SAT_LABEL = 'Enviar a SAT Externo'
TECHNICIAN_SAT_INITIAL_STATE = 'APPR'


@dataclass(frozen=True)
class TechnicianSatPlan:
    item: WarehouseItem
    duration: str
    incident: str
    reason: str
    anomaly_selection: dict

    @property
    def incident_summary(self):
        return 'inc: ' + self.incident


def reviewed_sat_plans(items, values, selection):
    """Validate the whole selection before opening or changing the first OT.

    Inputs are per OT, never inferred from an example or shared implicitly.
    The caller's mutable dictionaries are copied before the batch starts.
    """
    frozen_items = freeze_items(items)
    resolve_selection(selection)
    if not isinstance(values, dict):
        raise ValueError('Faltan los datos revisados de las OTs seleccionadas.')
    if set(values) != {item.ot for item in frozen_items}:
        raise ValueError('Los datos de envío no corresponden exactamente a las OTs seleccionadas.')
    plans = []
    for item in frozen_items:
        row = values[item.ot]
        if not isinstance(row, dict):
            raise ValueError(f'OT {item.ot}: faltan los datos de envío.')
        duration = str(row.get('duration') or '').strip()
        repair_seconds(duration)
        incident = str(row.get('incident') or '').strip()
        if not re.fullmatch(r'[0-9]+', incident):
            raise ValueError(f'OT {item.ot}: introduce un número de incidencia, sin el prefijo inc:.')
        # Native worklog Summary limit will also be checked before typing.
        reason = str(row.get('reason') or '').strip()
        if not reason:
            raise ValueError(f'OT {item.ot}: indica el motivo real del envío a SAT externo.')
        plans.append(TechnicianSatPlan(item, duration, incident, reason, deepcopy(selection)))
    return tuple(plans)
