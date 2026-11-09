from task_priorities import coordinator, scheduled, HIGH
"""Headless warehouse transport with explicit action gates and guarded submissions."""
from dataclasses import replace
import json
import logging
import re
import time
import traceback
from threading import Event

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

import maximo_client as client
from warehouse import ACTIONS, WarehouseResult, freeze_items
from workorder_start import WorkorderStarter, normalized
from warehouse_diagnostics import sanitize, log_exception

FINAL_STATES = {'receive': 'APPR', 'dispatch': 'CLOSE',
                'receive_sat_external': 'ISSUE', 'receive_sat_internal': 'ISSUE'}
SAT_ACTIONS = {'receive_sat_external': 'SAT Externo', 'receive_sat_internal': 'SAT Interno'}


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
            return len(dialogs) == 1 and normalized(dialogs[0].text.strip().split('\n')[0]) == normalized(expected_title)
        self.reader.wait(lambda d: matching_dialog(), f'detalles de {expected_title}')
        self.check(initial_state, identity)
        dialogs = self.reader.dialogs()
        if not matching_dialog():
            raise RuntimeError('Diálogo SAT ambiguo o de otra acción.')
        dialog_id = dialogs[0].get_attribute('id')
        frames = dialogs[0].find_elements(By.TAG_NAME, 'iframe')
        if len(frames) != 1:
            raise RuntimeError('No se encontró un único editor de detalles SAT.')
        try:
            self.driver.switch_to.frame(frames[0])
            body = self.driver.find_element(By.ID, 'dijitEditorBody')
            if body.text.strip() or text:
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
        self.check(initial_state, identity)
        dialogs = self.reader.dialogs()
        if len(dialogs) != 1 or dialogs[0].get_attribute('id') != dialog_id or not matching_dialog():
            raise RuntimeError('El diálogo SAT cambió antes de confirmar.')
        buttons = [b for b in dialogs[0].find_elements(By.TAG_NAME, 'button')
                   if b.is_displayed() and b.is_enabled() and normalized(b.text) == 'ok']
        if len(buttons) != 1:
            raise RuntimeError('No se encontró un único OK de SAT externo.')
        before_accept()
        buttons[0].click()  # Never retry this confirmation.

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


@scheduled("Operaciones de almacén", HIGH)
def run_live(items, action, *, stop=None, progress=None, journal=None, details=None, session_factory=WarehouseSession):
    """Sequential single-submit batches. No final confirmation is ever retried."""
    if action not in FINAL_STATES:
        raise ValueError('Esta acción todavía no está validada para ejecución real.')
    items = freeze_items(items)
    details = {str(ot): str(text).strip() for ot, text in (details or {}).items()}
    stop, progress = stop or Event(), progress or (lambda i, r: None)
    journal = journal or (lambda entry: logging.info('Almacén: %s', json.dumps(entry, ensure_ascii=False)))
    results, session = [], None
    try:
        for index, item in enumerate(items):
            def retire_session():
                nonlocal session
                if session is not None:
                    try: session.close()
                    finally: session = None
            coordinator.checkpoint(ACTIONS[action].label, item.ot, index, len(items), on_pause=retire_session)
            started = time.monotonic()
            stage_started = started
            result, submitted, routed = WarehouseResult(item), False, False
            journal({'event':'ot_started','ot':item.ot,'action':action,'position':index+1,'total':len(items),
                     'cached_status':item.status,'expected_initial_state':ACTIONS[action].initial_status,
                     'expected_final_state':FINAL_STATES[action],'has_details':bool(details.get(item.ot,''))})
            def step(name, count):
                nonlocal result, stage_started
                now = time.monotonic()
                journal({'event':'step_changed','ot':item.ot,'action':action,'step':name,
                         'previous_step':result.step,'previous_step_seconds':round(now-stage_started,3),
                         'elapsed_seconds':round(now-started,3)})
                stage_started = now
                result = replace(result, status='running', step=name, completed_steps=count)
                progress(index, result)
                journal({'ot': item.ot, 'action': action, 'step': name})
            try:
                if stop.is_set():
                    result = replace(result, status='stopped', detail='Detenida antes de comenzar.')
                else:
                    step('Abrir ficha', 0)
                    if session is None:
                        session = session_factory()
                        journal({'event':'session_created','ot':item.ot,'action':action})
                    else:
                        journal({'event':'session_reused','ot':item.ot,'action':action})
                    actual = session.open(item.ot)
                    journal({'event':'live_status_read','ot':item.ot,'action':action,'actual_state':actual})
                    step('Comprobar OT y estado', 1)
                    if actual != ACTIONS[action].initial_status:
                        raise RuntimeError(f'Estado real {actual}; se requiere {ACTIONS[action].initial_status}.')
                    identity = session.identity()
                    prior_history = session.history_count(ACTIONS[action].native_label) if action in SAT_ACTIONS else None
                    journal({'ot': item.ot, 'action': action, 'initial_state': actual, 'identity': identity})
                    session.check(actual, identity)
                    session.reader.reject_dialogs()
                    step('Seleccionar acción', 2)
                    routed = True
                    session.driver.find_element(By.ID, 'ROUTEWF_WO-MAIN_-tbb_image').click()
                    session.reader.wait(lambda d: bool(session.reader.dialogs()), 'selector de almacén')
                    session.check(actual, identity)
                    option = session.choice(ACTIONS[action].native_label)
                    journal({'event':'option_located','ot':item.ot,'action':action,'option':option})
                    if not option['checked']:
                        session.driver.find_element(By.ID, option['id']).click()
                        session.reader.idle()
                    option = session.choice(ACTIONS[action].native_label)
                    if not option['checked']:
                        raise RuntimeError('Maximo no confirmó la selección de la acción.')
                    journal({'event':'option_selected','ot':item.ot,'action':action,'option':option})
                    session.check(actual, identity)
                    step('Confirmar acción', 3)
                    button = session.accept_button()
                    journal({'ot': item.ot, 'action': action, 'confirmation': 'sending_once'})
                    submitted = True
                    button.click()
                    if action in SAT_ACTIONS:
                        step('Completar detalles SAT', 3)
                        session.sat_details(action, details.get(item.ot, ''), actual, identity,
                            lambda: journal({'ot': item.ot, 'action': action,
                                'details_confirmation': 'sending_once', 'has_details': bool(details.get(item.ot, ''))}))
                    step('Verificar resultado', 4)
                    session.reader.wait(lambda d: session.reader.value('Estado') != actual
                        or not session.reader.dialogs(), 'respuesta de almacén')
                    final = session.verify(item.ot, FINAL_STATES[action], identity)
                    journal({'event':'final_state_verified','ot':item.ot,'action':action,'actual_state':final})
                    if action in SAT_ACTIONS:
                        after_history = session.history_count(ACTIONS[action].native_label)
                        journal({'event':'sat_history_checked','ot':item.ot,'action':action,
                                 'before':prior_history,'after':after_history})
                        if after_history <= prior_history:
                            raise RuntimeError('El estado cambió, pero no se confirmó una nueva derivación SAT en el historial.')
                    result = replace(result, status='success', step='Operación verificada',
                                     completed_steps=5, verified_status=final,
                                     detail=f'Estado real: {actual} → {final}.')
            except Exception as exc:
                context = None
                if session is not None:
                    try:
                        context = session.diagnostic_context()
                    except Exception as diagnostic_error:
                        context = {'unavailable':type(diagnostic_error).__name__}
                message = sanitize(str(exc))
                journal({'event':'ot_error','ot':item.ot,'action':action,'step':result.step,
                         'error_type':type(exc).__name__,'message':message,
                         'maximo_codes':re.findall(r'BMX[A-Z0-9]+',message),
                         'traceback':sanitize(traceback.format_exc()),'context':sanitize(context),
                         'route_attempted':routed,'confirmation_attempted':submitted,
                         'elapsed_seconds':round(time.monotonic()-started,3)})
                # Routing can itself advance an assignment. Retire uncertain sessions;
                # never navigate another OT in a browser with an unresolved submission.
                result = replace(result, status='uncertain' if submitted or routed else 'failed',
                                 detail=message.split('Stacktrace:')[0][:600])
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        log_exception('No se pudo cerrar la sesión de almacén')
                    session = None
            results.append(result)
            journal({'ot': item.ot, 'action': action, 'outcome': result.status, 'detail': result.detail,
                     'confirmation_attempted': submitted,'verified_status':result.verified_status,
                     'elapsed_seconds':round(time.monotonic()-started,3)})
            progress(index, result)
        return tuple(results)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                log_exception('No se pudo cerrar la sesión final de almacén')
