from task_priorities import coordinator, scheduled, HIGH
"""Headless warehouse transport with explicit action gates and guarded submissions."""
from dataclasses import replace
import json
import logging
import re
import time
import traceback
from threading import Event
from selenium.common.exceptions import WebDriverException, TimeoutException

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

import maximo_client as client
from warehouse import ACTIONS, FINAL_STATES, WarehouseResult, freeze_items
from workorder_start import WorkorderStarter, normalized
from warehouse_diagnostics import sanitize, log_exception
from warehouse_recovery import RecoveryStore, recovery_item, PendingOperationError

SAT_ACTIONS = {'technician_sat_external': 'SAT Externo', 'receive_sat_external': 'SAT Externo', 'receive_sat_internal': 'SAT Interno'}


def unique_caption(options, caption):
    matches = [o for o in options if normalized(o['caption']) == normalized(caption)]
    if len(matches) != 1 or matches[0].get('disabled'):
        raise RuntimeError(f'No existe una única opción habilitada «{caption}».')
    return matches[0]


class WarehouseSession:
    def diagnostic_context(self):
        """Read bounded UI context only; no HTML, credentials, cookies or URL query."""
        ui = self.driver.execute_script(r"""
            const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
            return {path:location.pathname,title:document.title,
              fields:[...document.querySelectorAll('label[for]')].filter(e=>visible(e)&&
                /^(Orden de trabajo|Estado)[ *:]*$/i.test(e.textContent.trim())).map(l=>({
                  caption:l.textContent.trim(),value:document.getElementById(l.htmlFor)?.value})),
              dialogs:[...document.querySelectorAll('[role=dialog],#warndiv_inner')].filter(visible).slice(0,6).map(d=>({
                id:d.id,text:d.innerText.slice(0,3000),
                radios:[...d.querySelectorAll('input[type=radio]')].map(r=>({id:r.id,checked:r.checked,
                  caption:(r.getAttribute('aria-labelledby')||'').split(/\s+/)
                    .map(id=>document.getElementById(id)?.textContent||'').join(' ')}))}))};
        """)
        caps = self.driver.capabilities
        return {'ui': ui, 'browser': {k: caps.get(k) for k in ('browserName','browserVersion','platformName')},
                'driver_version': caps.get('msedge',{}).get('msedgedriverVersion','').split(' ')[0]}

    def __init__(self):
        self.profile = client.create_edge_profile('maximo-warehouse-')
        self.driver = None
        try:
            self.driver = client.setup_driver(headless=True, profile_dir=self.profile)
            client.login(self.driver, headless=True)
        except Exception:
            self.close()
            raise

    def close(self):
        try:
            if self.driver is not None:
                self.driver.quit()
        finally:
            client.cleanup_edge_profile(self.profile)

    def open(self, ot):
        client.open_workorders_app(self.driver, headless=True)
        status = client.read_workorder_status(self.driver, ot)
        self.reader = WorkorderStarter(self.driver, ot, timeout=45)
        self.reader.idle()
        self.reader.check_ot()
        return status

    def identity(self):
        self.reader.check_ot()
        # Keep label normalization consistent with Python's NFKD, including º/°.
        return self.driver.execute_script(r"""
            const norm=t=>String(t||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
              .replace(/\s+/g,' ').replace(/^[ *:]+|[ *:]+$/g,'').toLowerCase();
            const result={};
            for(const name of ['Activo','Nº de serie','Planta']) {
              const label=[...document.querySelectorAll('label[for]')].find(e=>
                e.getClientRects().length && norm(e.textContent)===norm(name));
              const field=label&&document.getElementById(label.htmlFor);
              result[name]=field?String(field.value||'').trim():null;
            }
            return result;
        """)

    def check(self, state, identity):
        self.reader.idle()
        self.reader.check_ot()
        actual = self.reader.value('Estado')
        if actual != state:
            raise RuntimeError(f'Estado real {actual}; se requiere {state}.')
        if self.identity() != identity:
            raise RuntimeError('La identidad del equipo ha cambiado.')

    def choice(self, caption):
        dialogs = self.reader.dialogs()
        if len(dialogs) != 1 or dialogs[0].get_attribute('id') != 'inputwf-dialog_inner':
            raise RuntimeError('Maximo no muestra el diálogo esperado; requiere revisión.')
        data = self.driver.execute_script("""
            return [...arguments[0].querySelectorAll('input[type=radio]')]
              .filter(r=>r.getClientRects().length).map(r=>({id:r.id,disabled:r.disabled,
                checked:r.checked,caption:(r.getAttribute('aria-labelledby')||'').split(/\\s+/)
                  .map(id=>document.getElementById(id)?.textContent||'').join(' ')}));
        """, dialogs[0])
        return unique_caption(data, caption)

    def accept_button(self):
        dialog = self.reader.dialogs()[0]
        buttons = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                   if b.is_displayed() and b.is_enabled() and normalized(b.text) == 'aceptar']
        if len(buttons) != 1:
            raise RuntimeError('No existe un único botón Aceptar habilitado.')
        return buttons[0]

    def verify(self, ot, expected, identity):
        # A fresh retrieval, not the transient post-click DOM, establishes success.
        self.reader.idle()
        if self.reader.dialog_snapshot():
            raise RuntimeError('Maximo requiere revisión de un diálogo posterior.')
        self.driver.refresh()
        WebDriverWait(self.driver, 45).until(
            lambda d: d.execute_script("return document.readyState==='complete'"))
        self.reader.idle()
        if self.reader.value('Orden de trabajo') != ot:
            self.open(ot)
        self.check(expected, identity)
        return expected

    def external_sat_details(self, text, initial_state, identity, before_accept):
        return self.sat_details('receive_sat_external', text, initial_state, identity, before_accept)

    def sat_details(self, action, text, initial_state, identity, before_accept):
        expected_title = SAT_ACTIONS[action]
        def matching_dialog():
            dialogs = self.reader.dialogs()
            return (len(dialogs) == 1 and
                    (action != 'technician_sat_external' or dialogs[0].get_attribute('id') == 'ENVIAR_SAT_EXT-dialog_inner') and
                    normalized(dialogs[0].text.strip().split('\n')[0]) == normalized(expected_title))
        self.reader.wait(lambda d: matching_dialog(), f'detalles de {expected_title}')
        self.check(initial_state, identity)
        dialogs = self.reader.dialogs()
        if not matching_dialog():
            raise RuntimeError('Diálogo SAT ambiguo o de otra acción.')
        dialog_id = dialogs[0].get_attribute('id')
        frames = dialogs[0].find_elements(By.TAG_NAME, 'iframe')
        if len(frames) != 1:
            raise RuntimeError('No se encontró un único editor de detalles SAT.')
        marker = self.reader.response_sequence()
        changed = False
        try:
            self.driver.switch_to.frame(frames[0])
            body = self.driver.find_element(By.ID, 'dijitEditorBody')
            if body.text.strip() != text.strip():
                changed = True
                body.click()
                body.send_keys(Keys.CONTROL, 'a')
                body.send_keys(Keys.BACKSPACE)
                if text:
                    body.send_keys(text)
                body.send_keys(Keys.TAB)
            if body.text.strip() != text.strip():
                raise RuntimeError('El editor SAT no contiene los detalles solicitados.')
        finally:
            self.driver.switch_to.default_content()
        if changed:
            self.reader.wait(lambda _: self.reader.response_sequence() > marker, 'validación del motivo SAT')
        self.check(initial_state, identity)
        dialogs = self.reader.dialogs()
        if len(dialogs) != 1 or dialogs[0].get_attribute('id') != dialog_id or not matching_dialog():
            raise RuntimeError('El diálogo SAT cambió antes de confirmar.')
        buttons = [b for b in dialogs[0].find_elements(By.TAG_NAME, 'button')
                   if b.is_displayed() and b.is_enabled() and normalized(b.text) == 'ok']
        if len(buttons) != 1:
            raise RuntimeError('No se encontró un único OK de SAT externo.')
        def ready(_):
            self.reader.idle()
            current = self.reader.dialogs()
            if len(current) != 1 or current[0].get_attribute('id') != dialog_id:
                raise RuntimeError('El diálogo SAT cambió antes del OK.')
            matches = [b for b in current[0].find_elements(By.TAG_NAME, 'button')
                       if b.is_displayed() and b.is_enabled() and normalized(b.text) == 'ok']
            if len(matches) != 1:
                return False
            button = matches[0]
            reachable = self.driver.execute_script("const b=arguments[0],r=b.getBoundingClientRect(),e=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return e===b||b.contains(e)", button)
            return button if reachable else False
        button = self.reader.wait(ready, 'OK SAT sin capa de carga')
        self.check(initial_state, identity)
        before_accept()
        button.click()  # Never retry this confirmation.

    def history_count(self, caption):
        """Read complete native history to distinguish SAT variants sharing ISSUE."""
        self.reader.check_ot()
        self.reader.reject_dialogs()
        link = self.driver.find_element(By.CSS_SELECTOR, 'a[eventtype="ASSIGNWF"]')
        self.driver.execute_script('arguments[0].click()', link)
        self.reader.wait(lambda d: bool(self.reader.dialogs()), 'asignaciones de consulta')
        self.reader.idle()
        dialog = self.reader.dialogs()[0]
        if dialog.get_attribute('id') != 'assignwf-dialog_inner':
            raise RuntimeError('No se abrió la consulta de asignaciones.')
        buttons = [b for b in dialog.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == 'Ver historial de flujo de trabajo']
        if len(buttons) != 1:
            raise RuntimeError('No se encontró el historial de consulta.')
        buttons[0].click()
        self.reader.wait(lambda d: any(e.get_attribute('id') == 'historywf-dialog_inner'
                                      for e in self.reader.dialogs()), 'historial de consulta')
        count = 0
        try:
            for page in range(100):
                self.reader.idle()
                self.reader.check_ot()
                dialog = self.driver.find_element(By.ID, 'historywf-dialog_inner')
                descriptions = self.driver.execute_script('return [...arguments[0].querySelectorAll("tr.tablerow")].map(r=>r.cells[4]?.innerText.trim())', dialog)
                count += sum(normalized(d) == normalized(caption) for d in descriptions)
                position = re.search(r'\d+\s*-\s*\d+\s+de\s+\d+', dialog.text)
                following = dialog.find_elements(By.CSS_SELECTOR, 'a[title^="Página siguiente"]')
                if not following or 'next_on' not in following[0].find_element(By.TAG_NAME, 'img').get_attribute('src'):
                    return count
                if not position:
                    raise RuntimeError('Paginación del historial no reconocida.')
                previous = position.group()
                following[0].click()
                self.reader.wait(lambda d: previous not in d.find_element(By.ID, 'historywf-dialog_inner').text,
                                 'siguiente página de historial')
            raise RuntimeError('Historial demasiado extenso; requiere revisión.')
        finally:
            if any(d.get_attribute('id') == 'historywf-dialog_inner' for d in self.reader.dialogs()):
                self.driver.execute_script("sendEvent('dialogcancel','historywf-dialog',null,null)")
                self.reader.wait(lambda d: not self.reader.dialogs(), 'cerrar consulta de historial')
                self.reader.idle()



def default_recovery_store():
    return RecoveryStore()


def _close_session(session):
    if session is not None:
        try:
            session.close()
        except Exception:
            log_exception('No se pudo cerrar la sesión de almacén')


def _identity(session, item):
    identity = session.identity()
    if (not isinstance(identity, dict) or not identity.get('Activo') or not identity.get('Planta') or
            not isinstance(identity.get('Nº de serie'), str)):
        raise RuntimeError('No se pudo identificar de forma fiable el equipo y su planta.')
    if item.serial and str(identity.get('Nº de serie') or '').strip() != item.serial.strip():
        raise RuntimeError('El número de serie de la ficha no coincide con la OT seleccionada.')
    return identity


def _recover_one(record, store, session_factory, journal, stop, attempts=2):
    item = recovery_item(record); action = record['action']
    result = WarehouseResult(item, status='uncertain', step='Reverificar resultado',
                             completed_steps=4, operation_id=record['operation_id'])
    try:
        current = store.get(item.ot)
        if not current or current['operation_id'] != record['operation_id']:
            return replace(result, detail='El registro pendiente ha cambiado o ya se resolvió. Vuelve a abrir la revisión.')
        record = current
    except Exception as exc:
        return replace(result, detail='No se pudo comprobar el registro pendiente: '+sanitize(str(exc))[:400])
    if stop.is_set():
        return replace(result, detail='Reverificación detenida; la operación sigue pendiente.')
    if record.get('verified_status') == FINAL_STATES[action]:
        journal({'event':'local_recovery_only','ot':item.ot,'action':action,'operation_id':record['operation_id']})
        return replace(result, status='success', step='Estado local pendiente', completed_steps=5,
                       verified_status=record['verified_status'], detail='Resultado ya verificado; solo se reintentará guardar en MD.')
    for attempt in range(attempts):
        if stop.is_set():
            return replace(result, detail='Reverificación detenida; la operación sigue pendiente.')
        session = None
        try:
            coordinator.checkpoint('Reverificación de almacén', item.ot, attempt, attempts)
            journal({'event':'recheck_started','ot':item.ot,'action':action,'attempt':attempt+1,
                     'operation_id':record['operation_id'],'confirmation_replayed':False})
            session = session_factory()
            actual = session.open(item.ot)
            identity = _identity(session, item)
            journal({'event':'recheck_observed','ot':item.ot,'action':action,'actual_state':actual,
                     'identity':identity,'operation_id':record['operation_id']})
            if identity != record['identity']:
                raise RuntimeError('La identidad no coincide con la registrada antes del envío.')
            if actual != FINAL_STATES[action]:
                raise RuntimeError(f'Estado actual {actual}; todavía no se confirma {FINAL_STATES[action]}.')
            final = session.verify(item.ot, FINAL_STATES[action], identity)
            if final != FINAL_STATES[action]:
                raise RuntimeError('La consulta no confirmó el estado final solicitado.')
            if action in SAT_ACTIONS:
                before = record.get('history_before')
                if type(before) is not int or before < 0:
                    raise RuntimeError('Falta la evidencia de historial previa al envío SAT; requiere revisión manual.')
                after = session.history_count(ACTIONS[action].native_label)
                journal({'event':'recheck_history','ot':item.ot,'action':action,'before':before,'after':after})
                if after <= before:
                    raise RuntimeError('No hay una nueva entrada de la acción SAT solicitada.')
            store.update(record, 'verified', verified_status=final)
            journal({'event':'recheck_verified','ot':item.ot,'action':action,'actual_state':final,
                     'operation_id':record['operation_id'],'confirmation_replayed':False})
            return replace(result, status='success', step='Operación verificada', completed_steps=5,
                           verified_status=final, detail=f'Reverificada desde una sesión independiente: {final}.')
        except Exception as exc:
            message = sanitize(str(exc)).split('Stacktrace:')[0][:600]
            journal({'event':'recheck_pending','ot':item.ot,'action':action,'attempt':attempt+1,
                     'error_type':type(exc).__name__,'message':message,'operation_id':record['operation_id']})
            result = replace(result, detail=message+' No se ha repetido la operación.')
        finally:
            _close_session(session)
    return result


@scheduled('Reverificar operaciones de almacén', HIGH)
def reverify_pending(records, *, recovery_store=None, stop=None, progress=None, journal=None,
                     session_factory=WarehouseSession):
    store = recovery_store or default_recovery_store()
    stop, progress = stop or Event(), progress or (lambda i,r: None)
    journal = journal or (lambda e: logging.info('Almacén recuperación: %s', json.dumps(e,ensure_ascii=False)))
    results=[]
    for index, record in enumerate(records):
        progress(index, WarehouseResult(recovery_item(record), status='running', step='Reverificando sin reenviar',
                                       operation_id=record['operation_id'], completed_steps=4))
        result = _recover_one(record, store, session_factory, journal, stop)
        results.append(result); progress(index,result)
    return tuple(results)


@scheduled('Operaciones de almacén', HIGH)
def run_live(items, action, *, stop=None, progress=None, journal=None, details=None,
             session_factory=WarehouseSession, recovery_store=None, auto_recheck=True, technician_plans=None):
    """Retry reads before routing; after any possible effect, only query the result."""
    if action not in FINAL_STATES:
        raise ValueError('Esta acción todavía no está validada para ejecución real.')
    items=freeze_items(items);store=recovery_store or default_recovery_store()
    plans = {}
    if action == 'technician_sat_external':
        from technician_sat import reviewed_sat_plans
        supplied = tuple(technician_plans or ())
        if len(supplied) != len(items) or {p.item for p in supplied} != set(items):
            raise ValueError('Falta revisar los datos de todas las OTs del envío técnico.')
        for plan in supplied:
            checked, = reviewed_sat_plans([plan.item], {plan.item.ot: {
                'duration':plan.duration, 'incident':plan.incident, 'reason':plan.reason}}, plan.anomaly_selection)
            plans[plan.item.ot] = checked
        details = {ot:p.reason for ot,p in plans.items()}
    details={str(ot):str(text).strip() for ot,text in (details or {}).items()}
    stop,progress=stop or Event(),progress or (lambda i,r:None)
    journal=journal or (lambda e:logging.info('Almacén: %s',json.dumps(e,ensure_ascii=False)))
    results=[]; session=None
    try:
        for index,item in enumerate(items):
            def retire():
                nonlocal session
                old=session;session=None;_close_session(old)
            coordinator.checkpoint(ACTIONS[action].label,item.ot,index,len(items),on_pause=retire)
            started=time.monotonic();result=WarehouseResult(item);submitted=routed=False;record=None
            journal({'event':'ot_started','ot':item.ot,'action':action,'position':index+1,'total':len(items),
                     'cached_status':item.status,'expected_initial_state':ACTIONS[action].initial_status,
                     'expected_final_state':FINAL_STATES[action],'has_details':bool(details.get(item.ot,''))})
            def step(name,count):
                nonlocal result
                result=replace(result,status='running',step=name,completed_steps=count)
                progress(index,result)
                journal({'event':'step_changed','ot':item.ot,'action':action,'step':name,
                         'elapsed_seconds':round(time.monotonic()-started,3)})
            for attempt in range(2):
                try:
                    if stop.is_set():
                        result=replace(result,status='stopped',detail='Detenida antes de comenzar.');break
                    existing=store.get(item.ot)
                    if existing:
                        result=replace(result,status='uncertain',step='Operación anterior pendiente',
                            detail='Esta OT tiene una operación pendiente. Usa Reverificar; no se enviará otra acción.')
                        journal({'event':'duplicate_blocked','ot':item.ot,'action':action,
                                 'pending_action':existing['action'],'operation_id':existing['operation_id']})
                        break
                    step('Abrir ficha',0)
                    if session is None:session=session_factory()
                    actual=session.open(item.ot)
                    journal({'event':'live_status_read','ot':item.ot,'action':action,'actual_state':actual})
                    step('Comprobar OT y estado',1)
                    identity=_identity(session,item)
                    if actual==FINAL_STATES[action] and action not in SAT_ACTIONS:
                        final=session.verify(item.ot,FINAL_STATES[action],identity)
                        if final != FINAL_STATES[action]:raise RuntimeError('No se confirmó el estado final.')
                        record=store.begin(item,action,identity,actual,verified_status=final)
                        result=replace(result,status='already_done',step='Ya estaba completada',completed_steps=5,
                            verified_status=final,operation_id=record['operation_id'],
                            detail=f'La OT ya estaba en {final}; no se ha enviado ninguna acción.')
                        journal({'event':'already_completed','ot':item.ot,'action':action,'actual_state':final})
                        break
                    if actual!=ACTIONS[action].initial_status:
                        raise RuntimeError(f'Estado real {actual}; se requiere {ACTIONS[action].initial_status}.')
                    prior=session.history_count(ACTIONS[action].native_label) if action in SAT_ACTIONS else None
                    if action in SAT_ACTIONS and (type(prior) is not int or prior<0):
                        raise RuntimeError('No se pudo leer el historial previo de SAT.')
                    journal({'ot':item.ot,'action':action,'initial_state':actual,'identity':identity,'history_before':prior})
                    session.check(actual,identity);session.reader.reject_dialogs()
                    if action == 'technician_sat_external':
                        record=store.begin(item,action,identity,actual,prior,preparing=True)
                        result=replace(result,operation_id=record['operation_id'])
                        step('Preparar anomalías, horas e incidencia',2)
                        from technician_sat import TechnicianSatPreparer
                        preparer = TechnicianSatPreparer(session.driver,item.ot,
                            progress=lambda text: step(text,2))
                        preparer.prepare(plans[item.ot])
                        session.reader = preparer
                        session.reader.tab('Orden de trabajo')
                        session.check(actual,identity)
                        journal({'event':'technician_preparation_verified','ot':item.ot,'action':action,
                                 'operation_id':record['operation_id']})
                        record=store.update(record,'route_attempted',route_attempted=True)
                    else:
                        record=store.begin(item,action,identity,actual,prior)
                    step('Seleccionar acción',2)
                    result=replace(result,operation_id=record['operation_id'])
                    journal({'event':'route_attempt','ot':item.ot,'action':action,'operation_id':record['operation_id']})
                    routed=True
                    session.driver.find_element(By.ID,'ROUTEWF_WO-MAIN_-tbb_image').click()
                    session.reader.wait(lambda d:bool(session.reader.dialogs()),'selector de almacén')
                    session.check(actual,identity)
                    option=session.choice(ACTIONS[action].native_label)
                    journal({'event':'option_located','ot':item.ot,'action':action,'option':option})
                    if not option['checked']:
                        session.driver.find_element(By.ID,option['id']).click();session.reader.idle()
                    option=session.choice(ACTIONS[action].native_label)
                    if not option['checked']:raise RuntimeError('Maximo no confirmó la selección de la acción.')
                    session.check(actual,identity);step('Confirmar acción',3)
                    button=session.accept_button()
                    record=store.update(record,'confirmation_attempted',confirmation_attempted=True)
                    journal({'ot':item.ot,'action':action,'confirmation':'sending_once','operation_id':record['operation_id']})
                    submitted=True;button.click()
                    if action in SAT_ACTIONS:
                        step('Completar detalles SAT',3)
                        def mark_details():
                            nonlocal record
                            record=store.update(record,'details_attempted',details_attempted=True)
                            journal({'ot':item.ot,'action':action,'details_confirmation':'sending_once','operation_id':record['operation_id']})
                        session.sat_details(action,details.get(item.ot,''),actual,identity,mark_details)
                    step('Verificar resultado',4)
                    session.reader.wait(lambda d:session.reader.value('Estado')!=actual or not session.reader.dialogs(),
                                        'respuesta de almacén')
                    final=session.verify(item.ot,FINAL_STATES[action],identity)
                    if final != FINAL_STATES[action]:raise RuntimeError('No se confirmó el estado final.')
                    if action in SAT_ACTIONS:
                        after=session.history_count(ACTIONS[action].native_label)
                        journal({'event':'sat_history_checked','ot':item.ot,'action':action,'before':prior,'after':after})
                        if after<=prior:raise RuntimeError('No se confirmó una nueva derivación SAT en el historial.')
                    record=store.update(record,'verified',verified_status=final)
                    journal({'event':'final_state_verified','ot':item.ot,'action':action,'actual_state':final,'operation_id':record['operation_id']})
                    result=replace(result,status='success',step='Operación verificada',completed_steps=5,
                        verified_status=final,operation_id=record['operation_id'],detail=f'Estado real: {actual} → {final}.')
                    break
                except Exception as exc:
                    try:context=session.diagnostic_context() if session is not None else None
                    except Exception as diagnostic_error:context={'unavailable':type(diagnostic_error).__name__}
                    message=sanitize(str(exc))
                    journal({'event':'ot_error','ot':item.ot,'action':action,'step':result.step,
                        'error_type':type(exc).__name__,'message':message,'traceback':sanitize(traceback.format_exc()),
                        'maximo_codes':re.findall(r'BMX[A-Z0-9]+',message),'context':sanitize(context),
                        'route_attempted':routed,'confirmation_attempted':submitted})
                    retire()
                    transient=isinstance(exc,(TimeoutError,ConnectionError,WebDriverException)) or message.startswith('Tiempo agotado:')
                    if not routed and not submitted and record is None and transient and attempt==0:
                        journal({'event':'preparation_retry','ot':item.ot,'action':action,'attempt':2});continue
                    result=replace(result,status='uncertain' if routed or submitted or record else 'failed',
                        detail=message.split('Stacktrace:')[0][:600],operation_id=record['operation_id'] if record else '')
                    break
            results.append(result)
            journal({'ot':item.ot,'action':action,'outcome':result.status,'detail':result.detail,
                     'confirmation_attempted':submitted,'verified_status':result.verified_status,
                     'operation_id':result.operation_id,'elapsed_seconds':round(time.monotonic()-started,3)})
            progress(index,result)
        retire()
        if auto_recheck and not stop.is_set():
            for index,result in enumerate(results):
                if result.status!='uncertain' or not result.operation_id:continue
                record=store.get(result.item.ot)
                if record and record['operation_id']==result.operation_id:
                    journal({'event':'second_pass','ot':result.item.ot,'action':action})
                    progress(index,replace(result,status='running',step='Reverificando sin reenviar'))
                    results[index]=_recover_one(record,store,session_factory,journal,stop)
                    progress(index,results[index])
        return tuple(results)
    finally:
        _close_session(session)
