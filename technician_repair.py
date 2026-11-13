"""Reviewed repair completion, shared by normal closure and irreparable assets."""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from copy import deepcopy
from threading import Event
import json
import logging
import time
from uuid import uuid4
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from technician_sat import TechnicianSatPreparer,format_incident
from workorder_start import normalized
from workorder_close import WorkorderCloser, actual_datetime, repair_seconds, validate_close_times, close_review
from failure_catalog import resolve_selection
from task_priorities import scheduled, HIGH
from warehouse import WarehouseItem
from warehouse_transport import WarehouseSession
from warehouse_recovery import RecoveryStore
from warehouse_diagnostics import sanitize,log_exception


@dataclass(frozen=True)
class RepairEntry:
    summary: str
    details: str = ''


@dataclass(frozen=True)
class RepairPlan:
    item: WarehouseItem
    reference: str
    entries: tuple
    duration: str
    start: str
    end: str
    action: str
    justification: str
    selection: dict
    print_report: bool = True

    @property
    def incident_summary(self):
        return format_incident(self.reference)


def reviewed_repair(item, values, selection, now=None):
    if values.get('action') not in ('close','discard'):
        raise ValueError('Elige Cerrar OT o Desechar equipo.')
    reference=str(values.get('reference') or '').strip()
    format_incident(reference)
    duration=str(values.get('duration') or '').strip()
    seconds=repair_seconds(duration)
    mode=values.get('time_mode','end')
    if mode not in ('start','end'):raise ValueError('Elige indicar inicio o finalización.')
    chosen=actual_datetime(values.get('time'))
    if chosen is None:raise ValueError('Indica la fecha y hora de reparación.')
    start=chosen if mode=='start' else chosen-timedelta(seconds=seconds)
    plan=close_review(duration,start);validate_close_times(plan,now)
    entries=[]
    for value in values.get('entries',[]):
        summary=str(value.get('summary') or '').strip();details=str(value.get('details') or '').strip()
        if not summary and not details:continue
        if not summary:raise ValueError('Cada entrada de registro necesita un resumen.')
        entries.append(RepairEntry(summary,details))
    summaries=[format_incident(reference),*[entry.summary for entry in entries]]
    if len({normalized(s) for s in summaries})!=len(summaries):
        raise ValueError('Evita resúmenes repetidos en las entradas de esta petición.')
    justification=str(values.get('justification') or '').strip()
    if values['action']=='discard' and not justification:
        raise ValueError('Introduce la justificación de irreparable.')
    resolve_selection(selection)
    return RepairPlan(item,reference,tuple(entries),duration,start.isoformat(timespec='seconds'),
        plan['expected_end'].isoformat(timespec='seconds'),values['action'],justification,
        deepcopy(selection),bool(values.get('print_report',True)))


def verify_saved_repair(session, request):
    """Read-only verification of duration and dates, also on a discarded CLOSE OT."""
    reader=WorkorderCloser(session.driver,request['item']['ot']);session.reader=reader
    reader.check_ot();reader.reject_dialogs()
    reader.tab('Consumos Actuales');duration=reader.field_snapshot('Horas totales de reparación')
    reader.tab('Orden de trabajo')
    start=reader.field_snapshot('Inicio real');end=reader.field_snapshot('Finalización real')
    if (repair_seconds(duration['value'])!=repair_seconds(request['duration'])
            or actual_datetime(start['value'],start['title'])!=actual_datetime(request['start'])
            or actual_datetime(end['value'],end['title'])!=actual_datetime(request['end'])):
        raise RuntimeError('La duración o las fechas guardadas no coinciden con la petición revisada.')
    verify_repair_entries(session,request)


def verify_repair_entries(session, request):
    if 'reference' not in request:return
    registry=RepairPreparer(session.driver,request['item']['ot'],'INPRG')
    registry.active_status=session.reader.value('Estado')
    registry.require_approved()
    registry.verify_entries((RepairEntry(format_incident(request['reference'])),
        *(RepairEntry(item['summary'],item.get('details','')) for item in request.get('entries',[]))))


class RepairPreparer(TechnicianSatPreparer):
    def __init__(self,driver,ot,status,progress=None):
        super().__init__(driver,ot,progress)
        if status not in ('APPR','INPRG'):raise RuntimeError('Solo se preparan reparaciones APPR o INPRG.')
        self.active_status=status

    def _write_text(self, caption, value, equivalent=None):
        marker=self.response_sequence()
        super()._write_text(caption,value,equivalent)
        self.wait(lambda _:self.response_sequence()>marker or self.dialogs(),
                  f'respuesta de Maximo al validar {caption}')
        self.idle();self.require_approved()
        actual=self.value(caption)
        if not (equivalent(actual) if equivalent else actual==value):
            raise RuntimeError(f'Maximo no confirmó {caption}. No se continuará el proceso.')

    def save_anomalies(self, path, class_code=None):
        """Validate drafts; only native removal of an old hierarchy needs Save."""
        self.require_approved()
        self.tab('Informes de anomalías')
        rows=self.failure_rows()
        if rows is None:raise RuntimeError('No se pudo comprobar la jerarquía de anomalías.')
        if any('deshacer suprimir' in normalized(row.get('toggleTitle')) for row in rows):
            logging.info('OT %s: guardado necesario para eliminar la jerarquía anterior antes de reemplazarla',self.ot)
            return super().save_anomalies(path,class_code)
        if class_code is not None and self.value('Clase de anomalía')!=class_code:
            return False
        self.verify_failure_rows(path)
        self.verify_solution_codes(path)
        logging.info('OT %s: anomalías validadas sin Guardar; se confirmarán al enrutar',self.ot)
        return True

    def reload_workorder(self):
        import maximo_client as client
        self.require_approved()
        client.open_workorders_app(self.driver,headless=True)
        status=client.read_workorder_status(self.driver,self.ot)
        if status!=self.active_status:raise RuntimeError('La OT cambió de estado durante la preparación.')
        self.require_approved()

    def open_entry(self, entry):
        self.tab('Registro')
        snapshot=self.worklog_snapshot()
        matches=[row for row in snapshot['rows'] if entry.summary in row['cells']
                 and any(normalized(cell)=='clientnote' for cell in row['cells'])]
        if len(matches)>1:raise RuntimeError('Hay varias entradas con el mismo resumen; revisa Registro.')
        if not matches:
            if not snapshot['totals'] or len(set(snapshot['totals']))!=1 or snapshot['totals'][0]>len(snapshot['rows']):
                raise RuntimeError('No se pudo comprobar el registro completo; no se añadirá una entrada duplicada.')
            return False
        row=self.driver.find_element(By.ID,matches[0]['id'])
        toggles=row.find_elements(By.CSS_SELECTOR,'a[id*="_tgdet-ti"]')
        if len(toggles)!=1:raise RuntimeError('No se encontró un único selector de detalles del registro.')
        if normalized(toggles[0].get_attribute('title'))=='ver detalles':toggles[0].click();self.idle()
        self.wait(lambda _:self.value('Resumen')==entry.summary,'resumen de la entrada seleccionada')
        return True

    def details(self, text=None):
        frames=[f for f in self.driver.find_elements(By.CSS_SELECTOR,'iframe[id$="rte_iframe"]') if f.is_displayed()]
        if len(frames)!=1:raise RuntimeError('No hay un único editor de detalles del registro.')
        marker=self.response_sequence()
        try:
            self.driver.switch_to.frame(frames[0]);body=self.driver.find_element(By.ID,'dijitEditorBody')
            if text is None:return body.text.strip()
            body.click();body.send_keys(Keys.CONTROL,'a');body.send_keys(text,Keys.TAB)
            if body.text.strip()!=text.strip():raise RuntimeError('El editor no contiene los detalles revisados.')
        finally:self.driver.switch_to.default_content()
        self.wait(lambda _:self.response_sequence()>marker,'validación de detalles del registro')
        self.require_approved()

    def ensure_entry(self,entry):
        if self.active_status not in ('APPR','INPRG'):
            raise RuntimeError('No se permite añadir registros después de finalizar la reparación.')
        if self.open_entry(entry):
            if self.details()!=entry.details.strip():
                raise RuntimeError('El resumen ya existe con otros detalles; revísalo antes de continuar.')
            return
        self.ensure_incident(entry.summary)
        self.wait(lambda _:self.value('Resumen')==entry.summary,'nueva entrada de registro')
        if entry.details:self.details(entry.details)
        self.idle();self.require_approved()
        if self.value('Resumen')!=entry.summary or self.details()!=entry.details.strip():
            raise RuntimeError('Maximo no validó la entrada de Registro. No se continuará el proceso.')
        logging.info('OT %s: Registro validado sin Guardar; pendiente del enrutado',self.ot)

    def verify_entries(self, entries):
        """Read-only confirmation after the workflow committed its drafts."""
        for entry in entries:
            if not self.open_entry(entry) or self.details()!=entry.details.strip():
                raise RuntimeError('El flujo finalizó, pero no se confirmó todo el Registro; revisa la OT sin repetir la acción.')


class RepairCloser(WorkorderCloser):
    def __init__(self, session, plan, mark, progress, identity, stage=None, stop=None):
        super().__init__(session.driver,plan.item.ot,progress)
        self.session,self.plan,self.mark=session,plan,mark
        self.expected_identity=identity
        self.stage=stage or (lambda index,text:None)
        self.stop=stop or Event()

    def reload_workorder(self):
        import maximo_client as client
        client.open_workorders_app(self.driver,headless=True)
        status=client.read_workorder_status(self.driver,self.ot)
        expected='CLOSE' if self.plan.action=='discard' else 'ISSUE'
        if status not in ('INPRG',expected):raise RuntimeError(f'Estado inesperado al consultar la reparación: {status}; se esperaba {expected}.')
        self.idle();self.check_ot();self.reject_dialogs()

    def before_route_click(self):
        self.session.check('INPRG',self.expected_identity)
        self.mark('route_attempted',route_attempted=True)
    def before_route_accept(self):
        self.session.check('INPRG',self.expected_identity)
        self.mark('confirmation_attempted',confirmation_attempted=True)

    def after_prepare_close(self):
        if self.stop.is_set():raise RuntimeError('Detenido antes de confirmar el cierre/desecho.')
        self.stage(4,'Confirmar la acción y su justificación')

    def before_final_verification(self):
        self.stage(5,'Verificar estado, fechas e historial guardados')

    def handle_discard_details(self, dialog):
        if not self.is_discard_details_dialog(dialog):return False
        self.session.reader=self
        self.session.rich_details('Desechar Activo',self.plan.justification,'INPRG',
            self.expected_identity,lambda:self.mark('details_attempted',details_attempted=True),
            expected_id=dialog['id'])
        self.wait(lambda _:self.value('Estado')=='CLOSE','resultado de Desechar Activo en CLOSE')
        return True


@scheduled('Finalizar reparación desde MD',HIGH)
def run_repair(plan, *, progress=None, stop=None, session_factory=WarehouseSession, store=None, journal=None, stage_progress=None):
    """No unattended retry after any route/confirmation; printing is a separate UI action."""
    progress=progress or (lambda text:None);stop=stop or Event();store=store or RecoveryStore()
    stage_progress=stage_progress or (lambda index,text:None)
    action='technician_discard' if plan.action=='discard' else 'technician_close'
    # Revalidate the frozen, reviewed input before opening a browser.
    plan=reviewed_repair(plan.item,{'reference':plan.reference,'entries':[asdict(e) for e in plan.entries],
        'duration':plan.duration,'time_mode':'start','time':plan.start,'action':plan.action,
        'justification':plan.justification,'print_report':plan.print_report and not stop.is_set()},plan.selection)
    journal=journal or (lambda event:logging.info('Reparación MD: %s',json.dumps(sanitize(event),ensure_ascii=False)))
    session=None;record=None
    journal({'event':'repair_started','ot':plan.item.ot,'action':action})
    def mark(phase,**values):
        nonlocal record
        record=store.update(record,phase,**values)
        logging.info('Reparación MD: OT=%s operación=%s fase=%s',plan.item.ot,record['operation_id'],phase)
        journal({'event':phase,'ot':plan.item.ot,'operation_id':record['operation_id']})
        caption={'route_attempted':'Abriendo el flujo de trabajo…','confirmation_attempted':'Confirmando la acción seleccionada…','details_attempted':'Guardando la justificación…'}.get(phase,'Comprobando el resultado…')
        progress('OT '+plan.item.ot+' · '+caption)
    try:
        if stop.is_set():raise RuntimeError('Operación detenida antes de comenzar.')
        if store.get(plan.item.ot):raise RuntimeError('Esta OT tiene una operación pendiente. Revisa su resultado antes de otra acción.')
        stage_progress(0,'Abrir OT y comprobar estado e identidad')
        progress('Abriendo OT y comprobando estado e identidad…')
        session=session_factory();state=session.open(plan.item.ot)
        if state not in ('APPR','INPRG'):raise RuntimeError('La OT debe estar en APPR o INPRG.')
        identity=session.identity()
        journal({'event':'initial_state_read','ot':plan.item.ot,'state':state,'identity':identity})
        if not identity.get('Activo') or not identity.get('Planta') or (plan.item.serial and identity.get('Nº de serie')!=plan.item.serial):
            raise RuntimeError('No se pudo contrastar la identidad del equipo.')
        record=store.begin(plan.item,action,identity,state,preparing=True,reviewed_request=asdict(plan))
        preparer=RepairPreparer(session.driver,plan.item.ot,state,progress);session.reader=preparer
        stage_progress(1,'Preparar anomalías y entradas de Registro')
        preparer.apply_anomalies(plan.selection)
        for entry in (RepairEntry(plan.incident_summary),*plan.entries):
            if stop.is_set():raise RuntimeError('Preparación detenida antes de continuar.')
            progress('Preparando Registro: '+entry.summary)
            preparer.ensure_entry(entry)
        stage_progress(2,'Comprobar el inicio de la OT'+(' — ya iniciada' if state=='INPRG' else ''))
        if state=='APPR':
            if stop.is_set():raise RuntimeError('Detenido antes de iniciar la OT.')
            mark('route_attempted',route_attempted=True,start_attempted=True)
            progress('Iniciando la OT para completar la reparación…')
            preparer.run(anomaly_mode='only')
        closer=RepairCloser(session,plan,mark,progress,identity,stage_progress,stop);session.reader=closer
        closer.require_in_progress();closer.tab('Orden de trabajo');session.check('INPRG',identity)
        prior=session.history_count('Desechar equipo' if plan.action=='discard' else 'Cerrar OT')
        if type(prior) is not int or prior<0:raise RuntimeError('No se pudo comprobar el historial previo.')
        record=store.update(record,record['phase'],history_before=prior)
        stage_progress(3,'Validar duración e inicio y finalización reales')
        snapshot=closer.inspect_repair();token=uuid4().hex
        pending={'approved':True,'token':token,'created':time.monotonic(),'snapshot':snapshot,'prepared_in_place':True}
        approval={'ot':plan.item.ot,'token':token,'duration':plan.duration,'start':plan.start,
            'end':plan.end,'route_action':plan.action,'action_confirmed':True}
        if stop.is_set():raise RuntimeError('Detenido antes del cierre de la reparación.')
        result=closer.run_close(approval,pending)
        expected='CLOSE' if plan.action=='discard' else 'ISSUE'
        if result.get('cancelled') or result.get('status')!=expected:raise RuntimeError(f'No se confirmó la finalización en {expected}.')
        session.check(expected,identity)
        verify_repair_entries(session,asdict(plan))
        after=session.history_count('Desechar equipo' if plan.action=='discard' else 'Cerrar OT')
        if after<=prior:raise RuntimeError('El historial no confirmó la acción de reparación solicitada.')
        record=store.update(record,'verified',verified_status=expected,history_after=after)
        journal({'event':'repair_verified','ot':plan.item.ot,'state':expected,'history_before':prior,'history_after':after,'operation_id':record['operation_id']})
        return {**result,'operation_id':record['operation_id'],'print_report':plan.print_report}
    except Exception as exc:
        log_exception('Reparación MD: OT %s detenida sin repetir confirmaciones',plan.item.ot)
        try:context=session.diagnostic_context() if session else None
        except Exception:context=None
        journal({'event':'repair_error','ot':plan.item.ot,'error_type':type(exc).__name__,'message':str(exc)[:1200],
                 'phase':record['phase'] if record else 'before_preparation','context':context})
        if record:
            store.update(record,record['phase'],last_error=str(exc)[:600])
        raise
    finally:
        if session:session.close()
