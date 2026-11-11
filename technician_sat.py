"""Reviewed input for technician SAT dispatch; separate from warehouse reception."""
from copy import deepcopy
from dataclasses import dataclass
from threading import Event

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from workorder_start import WorkorderStarter, normalized
from task_priorities import coordinator, scheduled, HIGH

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
        if not incident or any(ord(ch) < 32 for ch in incident):
            raise ValueError(f'OT {item.ot}: introduce una incidencia o referencia, por ejemplo stock.')
        # Native worklog Summary limit will also be checked before typing.
        reason = str(row.get('reason') or '').strip()
        if not reason:
            raise ValueError(f'OT {item.ot}: indica el motivo real del envío a SAT externo.')
        plans.append(TechnicianSatPlan(item, duration, incident, reason, deepcopy(selection)))
    return tuple(plans)


class TechnicianSatPreparer(WorkorderStarter):
    """Prepare and freshly verify APPR data. This class never routes an OT."""
    active_status = TECHNICIAN_SAT_INITIAL_STATE
    operation = 'preparación de SAT externo'

    def require_approved(self):
        self.check_location()
        self.check_startable()
        self.reject_dialogs()

    def fault_reason(self):
        self.require_approved()
        self.tab('Orden de trabajo')
        return self.value('Resumen') or ''

    def _write_text(self, caption, value, equivalent=None):
        self.require_approved()
        field = self.field(caption)
        if field is None or field.get_property('readOnly') or not field.is_enabled():
            raise RuntimeError(f'Maximo no permite editar {caption}.')
        maximum = int(field.get_attribute('maxlength') or '-1')
        if maximum >= 0 and len(value) > maximum:
            raise ValueError(f'{caption} admite como máximo {maximum} caracteres.')
        field.click()
        field.send_keys(Keys.CONTROL, 'a')
        field.send_keys(value, Keys.TAB)
        def validated(_):
            self.reject_dialogs()
            actual = self.value(caption)
            try:
                return equivalent(actual) if equivalent else actual == value
            except ValueError:
                return False
        self.wait(validated, f'validación de {caption}')
        self.idle()
        self.reject_dialogs()

    def set_repair_duration(self, duration):
        expected = repair_seconds(duration)
        self.require_approved()
        self.tab('Consumos Actuales')
        try:
            if repair_seconds(self.value('Horas totales de reparación')) == expected:
                return
        except ValueError:
            pass
        self._write_text('Horas totales de reparación', duration.replace('.', ','),
                         equivalent=lambda value: repair_seconds(value) == expected)
        self.wait(lambda _: repair_seconds(self.value('Horas totales de reparación')) == expected,
                  'validación de horas de reparación')

    def worklog_snapshot(self):
        return self.driver.execute_script(r"""
            const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
            const rows=[...document.querySelectorAll('tr.tablerow')].filter(visible).map(row=>({
                id:row.id, cells:[...row.querySelectorAll('td')].map(cell=>
                    ([...cell.querySelectorAll('input,textarea')].map(f=>f.value).join(' ') ||
                    cell.innerText).trim())}));
            const totals=[...document.querySelectorAll('label')].filter(visible)
                .map(e=>e.textContent.trim().match(/^(\d+)\s*-\s*(\d+)\s+de\s+(\d+)$/))
                .filter(Boolean).map(m=>Number(m[3]));
            return {rows,totals};
        """)

    def incident_present(self, summary):
        data = self.worklog_snapshot()
        for row in data['rows']:
            cells = [normalized(cell) for cell in row['cells']]
            if normalized(summary) in cells and 'clientnote' in cells:
                return True
        if not data['totals'] or len(set(data['totals'])) != 1:
            raise RuntimeError('No se pudo comprobar la paginación del registro; no se añadirá una incidencia duplicada.')
        if data['totals'][0] > len(data['rows']):
            raise RuntimeError('El registro tiene más páginas; requiere revisión antes de añadir la incidencia.')
        return False

    def ensure_incident(self, summary):
        self.require_approved()
        self.tab('Registro')
        if self.incident_present(summary):
            return False
        before = len(self.worklog_snapshot()['rows'])
        buttons = [b for b in self.driver.find_elements(By.TAG_NAME, 'button')
                   if b.is_displayed() and b.is_enabled() and normalized(b.text) == 'fila nueva']
        if len(buttons) != 1:
            raise RuntimeError('No hay un único botón Fila Nueva para el registro.')
        buttons[0].click()  # No retry: an uncertain creation must not create another row.
        self.wait(lambda _: len(self.worklog_snapshot()['rows']) == before + 1 and
                  self.field('Resumen') is not None and self.field('Tipo') is not None,
                  'fila nueva del registro')
        self.require_approved()
        if self.value('Tipo') != 'CLIENTNOTE' or self.value('Resumen'):
            raise RuntimeError('La fila nueva no está vacía o no es CLIENTNOTE; revisa el registro.')
        self._write_text('Resumen', summary)
        return True

    def prepare_route(self):
        """Wait for the final native tab response, not just its optimistic ARIA flag."""
        self.require_approved()
        was_active = self.driver.execute_script("""
            return [...document.querySelectorAll('a[role=tab]')].some(a=>
                a.getClientRects().length && a.textContent.trim()==='Orden de trabajo' &&
                a.getAttribute('aria-expanded')==='true');
        """)
        marker = self.response_sequence()
        response = {'after':marker}
        self.tab('Orden de trabajo')
        if not was_active:
            def completed(_):
                response['after'] = self.response_sequence()
                return response['after'] > marker
            self.wait(completed, 'respuesta de Orden de trabajo antes de enrutar')
        self.idle()
        self.require_approved()
        def ready(_):
            snapshot = self.driver.execute_script(r"""
                const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
                const norm=t=>String(t||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'')
                    .replace(/^[ *:]+|[ *:]+$/g,'').toLowerCase();
                const value=name=>{
                    const label=[...document.querySelectorAll('label[for]')]
                        .find(l=>visible(l)&&norm(l.textContent)===name);
                    const field=label&&document.getElementById(label.htmlFor);
                    return visible(field)?field.value:null;
                };
                const tab=[...document.querySelectorAll('a[role=tab]')].find(a=>
                    visible(a)&&a.textContent.trim()==='Orden de trabajo');
                const button=document.getElementById('ROUTEWF_WO-MAIN_-tbb_image');
                let reachable=false;
                if(visible(button)){
                    const r=button.getBoundingClientRect();
                    const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                    reachable=top===button||button.contains(top);
                    for(let n=button;n;n=n.parentElement){
                        if(n.hasAttribute('disabled')||n.getAttribute('aria-disabled')==='true')reachable=false;
                    }
                }
                const result={ot:value('orden de trabajo'),status:value('estado'),
                    asset:value('activo'),plant:value('planta'),
                    active_tab:tab?.getAttribute('aria-expanded')==='true',route_reachable:reachable};
                result.ready=document.readyState==='complete'&&result.active_tab&&reachable&&
                    result.ot===arguments[0]&&result.status==='APPR'&&Boolean(result.asset)&&Boolean(result.plant);
                return result;
            """, self.ot)
            return snapshot if snapshot['ready'] else False
        snapshot = self.wait(ready, 'ficha y botón Enrutar listos')
        return {**snapshot, 'tab_was_active':bool(was_active),
                'response_before':marker, 'response_after':response['after']}

    def prepare(self, plan):
        # Revalidate the complete reviewed input before the first write.
        checked, = reviewed_sat_plans([plan.item], {plan.item.ot: {
            'duration':plan.duration, 'incident':plan.incident, 'reason':plan.reason}}, plan.anomaly_selection)
        if checked.item.ot != self.ot:
            raise ValueError('El plan de envío corresponde a otra OT.')
        self.require_approved()
        fault = self.fault_reason()
        resolved = self.apply_anomalies(checked.anomaly_selection)
        self.progress(f'OT {self.ot}: preparando horas de reparación…')
        self.set_repair_duration(checked.duration)
        self.progress(f'OT {self.ot}: preparando el registro de incidencia…')
        created = self.ensure_incident(checked.incident_summary)
        saved = self.save()
        if not saved and self._save_unavailable != 'disabled':
            raise RuntimeError('No se encontró una acción Guardar válida; no se enrutará.')
        self.driver.refresh()
        self.wait(lambda _: self.value('Orden de trabajo') == self.ot and self.value('Estado'),
                  'consulta nueva de la preparación guardada')
        self.require_approved()
        self.tab('Consumos Actuales')
        if repair_seconds(self.value('Horas totales de reparación')) != repair_seconds(checked.duration):
            raise RuntimeError('Maximo no guardó las horas de reparación; no se enrutará.')
        self.tab('Registro')
        if not self.incident_present(checked.incident_summary):
            raise RuntimeError('Maximo no guardó la incidencia; no se enrutará.')
        self.verify_failure_rows(resolved['path'])
        self.verify_solution_codes(resolved['path'])
        self.require_approved()
        return {'ot':self.ot, 'status':'APPR', 'prepared':True, 'incident_created':created,
                'fault_reason':fault}


@scheduled('Consultar envío técnico a SAT', HIGH)
def technician_sat_defaults(items, *, stop=None, progress=None, session_factory=None):
    """Read fresh defaults for review; never save, prepare or route."""
    from warehouse_transport import WarehouseSession
    stop = stop or Event()
    progress = progress or (lambda text: None)
    session_factory = session_factory or WarehouseSession
    session = None
    values = {}
    try:
        session = session_factory()
        for index, item in enumerate(freeze_items(items)):
            if stop.is_set():
                break
            coordinator.checkpoint('Consulta SAT técnico', item.ot, index, len(items))
            progress(f'Consultando datos reales · OT {item.ot} ({index + 1}/{len(items)})')
            state = session.open(item.ot)
            reader = session.reader
            reader.tab('Orden de trabajo')
            identity = session.identity()
            if not identity.get('Activo') or not identity.get('Planta'):
                raise RuntimeError(f'OT {item.ot}: no se pudo contrastar equipo y planta.')
            if item.serial and item.serial.strip() != (identity.get('Nº de serie') or '').strip():
                raise RuntimeError(f'OT {item.ot}: el número de serie no coincide.')
            reason = reader.value('Resumen') or ''
            reader.tab('Consumos Actuales')
            duration = reader.value('Horas totales de reparación') or ''
            values[item.ot] = {'reason':reason, 'duration':duration, 'status':state}
        return values
    finally:
        if session is not None:
            session.close()
