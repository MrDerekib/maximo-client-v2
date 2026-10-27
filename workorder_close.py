"""Review of repair duration and dates before an explicit browser close action."""
import re
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from workorder_start import WorkorderStarter, VISIBLE_DIALOGS_SCRIPT, normalized, browser_error_message


def repair_seconds(value):
    text = str(value or '').strip()
    if not text:
        raise ValueError('Falta el tiempo de reparación en Consumos Actuales.')
    if not re.fullmatch(r'\d+(?:[.,]\d+)?',text):
        raise ValueError('El tiempo de reparación debe ser un número decimal de horas, por ejemplo 0,75.')
    try:
        hours = Decimal(text.replace(',','.'))
        remainder = hours % Decimal('0.25')
        seconds = int(hours * 3600)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ValueError('El tiempo de reparación no es válido.') from exc
    if seconds <= 0:
        raise ValueError('El tiempo de reparación debe ser mayor que cero.')
    if remainder:
        raise ValueError('El tiempo de reparación debe ser múltiplo de 0,25 h (15 minutos).')
    return seconds


def actual_datetime(value='', title=''):
    text = str(value or '').strip() or str(title or '').strip()
    if not text:
        return None
    for pattern in ('%d/%m/%y %H:%M:%S','%d/%m/%Y %H:%M:%S',
                    '%d/%m/%y %H:%M','%d/%m/%Y %H:%M','%Y-%m-%dT%H:%M:%S','%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(text,pattern)
        except ValueError:
            pass
    raise ValueError('La fecha de reparación no tiene un formato reconocido.')


def close_review(duration, start, end=None):
    seconds = repair_seconds(duration)
    if start is None:
        raise ValueError('Indica la fecha y hora de inicio real de la reparación.')
    try:
        expected_end = start + timedelta(seconds=seconds)
    except OverflowError as exc:
        raise ValueError('La duración de reparación está fuera de rango.') from exc
    return {'duration_seconds':seconds,'start':start,'expected_end':expected_end,
            'dates_match':end is not None and end == expected_end}


def iso_date(value):
    return value.isoformat(timespec='seconds') if value is not None else ''


def validate_close_times(plan, now=None):
    if plan['expected_end'] > (now or datetime.now()):
        raise ValueError('La finalización no puede ser posterior a la hora actual. Revisa el inicio y la duración.')


class WorkorderCloser(WorkorderStarter):
    """Only used by a reviewed, explicitly confirmed action in the visible browser."""
    active_status = 'INPRG'
    operation = 'cierre'

    def field_snapshot(self, caption):
        def read(d):
            field = self.field(caption)
            return d.execute_script("""
                const f=arguments[0]; return f ? {id:f.id,value:f.value,title:f.title,
                  readonly:f.readOnly,lookup:f.getAttribute('li')} : null;
            """, field) if field is not None else False
        return self.wait(read, f'campo {caption}')

    def require_in_progress(self):
        self.check_location()
        self.check_ot()
        status=self.wait(lambda d:self.value('Estado'),'estado de la OT')
        if status != 'INPRG':
            raise RuntimeError(f'La OT {self.ot} está en {status}. Solo se cierra una reparación en INPRG; no se enrutará.')
        self.reject_dialogs()

    def inspect_repair(self):
        self.require_in_progress()
        self.progress(f'OT {self.ot}: revisando horas de reparación…')
        self.tab('Consumos Actuales')
        duration=self.field_snapshot('Horas totales de reparación')
        self.tab('Orden de trabajo')
        start=self.field_snapshot('Inicio real')
        end=self.field_snapshot('Finalización real')
        try:
            start_value=iso_date(actual_datetime(start['value'],start['title']))
            end_value=iso_date(actual_datetime(end['value'],end['title']))
        except ValueError as exc:
            raise ValueError(f'Maximo muestra una fecha no reconocida en la OT {self.ot}: '
                             f'Inicio={start["value"]!r}/{start["title"]!r}, '
                             f'fin={end["value"]!r}/{end["title"]!r}.') from exc
        return {'ot':self.ot,'duration':str(duration['value'] or '').strip(),
                'start':start_value,'end':end_value}

    def set_duration(self, duration):
        seconds=repair_seconds(duration)
        self.require_in_progress()
        self.tab('Consumos Actuales')
        current=self.field_snapshot('Horas totales de reparación')
        try:
            if repair_seconds(current['value'])==seconds:
                return
        except ValueError:
            pass
        if current['readonly']:
            raise RuntimeError('Maximo no permite editar las horas de reparación. Revísalas manualmente antes de cerrar.')
        self.progress(f'OT {self.ot}: guardando {duration} h de reparación…')
        field=self.field('Horas totales de reparación')
        field.clear()
        field.send_keys(str(duration).replace('.',','),Keys.TAB)
        def validated(d):
            self.reject_dialogs()
            try:
                return repair_seconds(self.value('Horas totales de reparación'))==seconds
            except ValueError:
                return False
        self.wait(validated,'validación del tiempo de reparación')
        self.save()

    def set_actual_date(self, caption, value):
        self.require_in_progress()
        current=self.field_snapshot(caption)
        if actual_datetime(current['value'],current['title'])==value:
            return
        if not current['lookup']:
            raise RuntimeError(f'Maximo no ofrece el selector de {caption}. No se cambiará la OT.')
        self.progress(f'OT {self.ot}: configurando {caption.lower()}…')
        popup_id=current['id']+'_popup'
        def popup():
            return next((e for e in self.driver.find_elements(By.ID,popup_id) if e.is_displayed()),None)
        self.click_fresh(lambda:self.driver.find_element(By.ID,current['lookup']),
                         f'selector {caption}',completed=lambda:popup() is not None)
        self.wait(lambda d:popup(),f'calendario de {caption}')

        # Maximo's DateTimeCalendar has a separate time widget. Updating only
        # the calendar value lets its onChange handler restore the old time.
        # Set both widget values, then press its native OK button so Maximo
        # receives the normal date/time change event.
        ok=self.driver.execute_script("""
            const w=window.dijit?.byId(arguments[0]);
            if(!w || w.declaredClass!=='ibm.tivoli.mbs.dijit.DateTimeCalendar' ||
               !w.tNode || typeof w.tNode.set!=='function') return null;
            const p=arguments[1],date=new Date(p[0],p[1]-1,p[2],p[3],p[4],p[5]);
            w.tNode.set('value',new Date(date));
            w.set('value',date);
            const result=w.get('value');
            if(!(result instanceof Date) || result.getTime()!==date.getTime()) return null;
            return w.okButtonNode;
        """,popup_id,[value.year,value.month,value.day,value.hour,value.minute,value.second])
        if ok is None:
            raise RuntimeError(f'El calendario de Maximo no confirmó fecha y hora para {caption}. No se guardará ni cerrará la OT.')
        ok.click()

        def confirmed(d):
            self.reject_dialogs()
            snapshot=self.field_snapshot(caption)
            return popup() is None and actual_datetime(snapshot['value'],snapshot['title'])==value
        self.wait(confirmed,f'validación de {caption}')
        # Commit each date before opening the other Maximo date widget. The
        # widget can still have an in-flight change request after its popup
        # closes; changing the second date immediately can make Maximo drop it.
        self.save()
        saved=self.field_snapshot(caption)
        if actual_datetime(saved['value'],saved['title'])!=value:
            raise RuntimeError(f'Maximo no conservó {caption.lower()} después de guardar. '
                               'No se continuará con el cierre de la OT.')

    def prepare_close(self, approval, pending):
        """Persist the reviewed inputs and verify them before any routing click."""
        if not pending.get('approved') or approval.get('token')!=pending.get('token'):
            raise RuntimeError('Falta la confirmación explícita del cierre de esta OT.')
        if approval.get('ot')!=self.ot or pending['snapshot']['ot']!=self.ot:
            raise RuntimeError('La confirmación pertenece a otra OT.')
        if time.monotonic()-pending['created']>300:
            raise RuntimeError('La revisión ha caducado. Revisa de nuevo los datos de cierre.')
        start=actual_datetime(approval.get('start'))
        plan=close_review(approval.get('duration'),start)
        validate_close_times(plan)
        if actual_datetime(approval.get('end'))!=plan['expected_end']:
            raise RuntimeError('La finalización confirmada no coincide con la duración. Revisa el cierre.')
        self.driver.refresh()
        current=self.inspect_repair()
        if current!=pending['snapshot']:
            raise RuntimeError('Los datos de la OT cambiaron desde la revisión. Compruébalos antes de volver a cerrar.')
        self.set_duration(approval['duration'])
        self.tab('Orden de trabajo')
        end=plan['expected_end']
        old_end=actual_datetime(current['end'])
        if old_end is not None and start>old_end:
            self.set_actual_date('Finalización real',end)
            self.set_actual_date('Inicio real',start)
        else:
            self.set_actual_date('Inicio real',start)
            self.set_actual_date('Finalización real',end)
        self.driver.refresh()
        verified=self.inspect_repair()
        try:
            duration_ok=repair_seconds(verified['duration'])==plan['duration_seconds']
        except ValueError:
            duration_ok=False
        if (not duration_ok or actual_datetime(verified['start'])!=start or actual_datetime(verified['end'])!=end):
            raise RuntimeError('Maximo no guardó los valores confirmados. '
                               f'Recibido: duración={verified["duration"] or "vacía"}, '
                               f'inicio={verified["start"] or "vacío"}, fin={verified["end"] or "vacío"}. '
                               'No se cerrará la OT.')
        return verified

    def route_close(self):
        """Route only from INPRG to ISSUE, stopping at the first departure from INPRG."""
        submitted=False
        routes=0
        warnings=0
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            self.idle()
            self.check_ot()
            status=self.wait(lambda d:self.value('Estado'),'estado del cierre')
            if status=='ISSUE':
                return
            if status!='INPRG':
                raise RuntimeError(f'La OT pasó a {status}; se detuvo el enrutado sin realizar más acciones.')
            dialogs=self.dialog_snapshot()
            if dialogs:
                dialog=dialogs[-1]
                if dialog['id']=='alreadyreported-dialog_inner' and not submitted:
                    warnings+=1
                    if warnings>4:
                        raise RuntimeError('Maximo repitió el aviso de problema informado. Revisa el cierre manualmente.')
                    self.button(dialog['id'],'Continuar')
                    continue
                if dialog['id']!='inputwf-dialog_inner' or submitted:
                    raise RuntimeError(f'Maximo requiere revisión del cierre: {dialog["text"]}')
                choices=self.driver.execute_script(r"""
                    const root=document.getElementById('inputwf-dialog_inner');
                    const normalize=t=>String(t||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'')
                      .replace(/\s+/g,' ').trim().toLowerCase();
                    const allowed=['cerrar ot','cerrar orden','cerrar orden de trabajo'];
                    return [...root.querySelectorAll('input[type=radio]')].filter(r=>{
                      if(!r.getClientRects().length || getComputedStyle(r).visibility==='hidden')return false;
                      const captions=[r.getAttribute('aria-label'),...[...(r.labels||[])].map(l=>l.textContent)];
                      for(const id of (r.getAttribute('aria-labelledby')||'').split(/\s+/))
                        captions.push(document.getElementById(id)?.textContent);
                      let p=r; for(let i=0;i<3&&p.parentElement;i++){
                        p=p.parentElement;
                        if(p.querySelectorAll('input[type=radio]').length!==1)break;
                        captions.push(p.textContent);
                      }
                      return captions.some(t=>allowed.includes(normalize(t)));
                    });
                """)
                if len(choices)!=1:
                    raise RuntimeError('Maximo no ofrece una única opción «Cerrar OT». No se elegirá otra acción.')
                choices[0].click()
                root=self.driver.find_element(By.ID,'inputwf-dialog_inner')
                buttons=[e for e in root.find_elements(By.CSS_SELECTOR,'button') if normalized(e.text)=='aceptar']
                if len(buttons)!=1:
                    raise RuntimeError('No se encontró la confirmación nativa del cierre.')
                self.progress(f'OT {self.ot}: enviando cierre confirmado…')
                submitted=True
                try:
                    buttons[0].click()  # Never replay this irreversible confirmation.
                except StaleElementReferenceException:
                    logging.info('OT %s: comprobando resultado del cierre tras reemplazo del botón, sin repetirlo',self.ot)
                self.wait(lambda d:self.value('Estado') not in (None,'','INPRG') or
                          any(x['id']!='inputwf-dialog_inner' for x in self.dialog_snapshot()),'resultado del cierre')
                continue
            if submitted:
                raise RuntimeError('No se pudo confirmar el cierre. Revisa el estado en Maximo antes de repetir la operación.')
            if routes>=3:
                raise RuntimeError('Maximo no ofreció el cierre tras tres pulsaciones. No se seguirá enrutando.')
            self.progress(f'OT {self.ot}: abriendo flujo de cierre ({routes+1}/3)…')
            try:
                self.driver.find_element(By.ID,'ROUTEWF_WO-MAIN_-tbb_image').click()
            except StaleElementReferenceException:
                raise RuntimeError('Maximo actualizó la pantalla al solicitar el cierre. Revisa su estado antes de reintentarlo.')
            routes+=1
            try:
                WebDriverWait(self.driver,self.route_dialog_timeout,poll_frequency=0.25).until(
                    lambda d:self.dialog_snapshot() or self.value('Estado') not in (None,'','INPRG'))
            except TimeoutException:
                pass
        raise RuntimeError('No se pudo confirmar el cierre dentro del límite de espera.')

    def run_close(self, approval, pending):
        self.prepare_close(approval,pending)
        self.require_in_progress()
        self.route_close()
        self.driver.refresh()
        self.wait(lambda d:self.value('Orden de trabajo')==self.ot and self.value('Estado')=='ISSUE',
                  'confirmación guardada de ISSUE')
        if pending.get('return_tab'):
            self.tab(pending['return_tab'])
        logging.info('OT %s: cierre confirmado en ISSUE tras revisión explícita del usuario',self.ot)
        return {'ot':self.ot,'status':'ISSUE'}


BROWSER_BUTTON_SCRIPT = r"""
    if (location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')) return null;
""" + VISIBLE_DIALOGS_SCRIPT + r"""
    const field=caption=>{
      const label=[...document.querySelectorAll('label[for]')].find(e=>e.getClientRects().length &&
        e.textContent.trim().replace(/:$/,'')===caption);
      return label && document.getElementById(label.htmlFor)?.value;
    };
    const ot=field('Orden de trabajo'),status=field('Estado');
    let button=document.getElementById('maximo-desktop-close-ot');
    if (!button && ot) {
      button=document.createElement('button'); button.id='maximo-desktop-close-ot'; button.type='button';
      button.textContent='Cerrar OT';
      Object.assign(button.style,{position:'fixed',right:'20px',bottom:'110px',zIndex:'2147483646',
        padding:'9px 14px',border:'1px solid #1155a0',borderRadius:'6px',background:'#1769c2',
        color:'#fff',font:'600 13px Arial,sans-serif',boxShadow:'0 3px 12px #0004',cursor:'pointer'});
      button.addEventListener('click',event=>{
        if (!event.isTrusted || button.disabled) return;
        button.disabled=true; button.dataset.busy='true'; button.textContent='Revisando cierre…';
        const activeTab=[...document.querySelectorAll('a[role=tab]')]
          .find(e=>e.getClientRects().length&&e.getAttribute('aria-expanded')==='true');
        document.documentElement.dataset.maximoCloseOtRequest=JSON.stringify({
          action:'prepare',ot:field('Orden de trabajo'),returnTab:activeTab?.textContent.trim()||''
        });
      });
      document.body.appendChild(button);
    }
    if (button) {
      button.hidden=!/^\d{1,20}$/.test(ot||'') || status!=='INPRG';
      if (button.dataset.busy!=='true') {
        button.disabled=visibleDialogs.length>0;
        button.style.opacity=button.disabled?'0.6':'1';
        button.title='Revisar duración y fechas antes de confirmar el cierre de una OT en INPRG';
      }
    }
    const request=document.documentElement.dataset.maximoCloseOtRequest;
    delete document.documentElement.dataset.maximoCloseOtRequest;
    return request ? JSON.parse(request) : null;
"""


BROWSER_REVIEW_SCRIPT = r"""
    document.getElementById('maximo-close-review')?.remove();
    const data=arguments[0],token=arguments[1];
    const dialog=document.createElement('dialog'); dialog.id='maximo-close-review'; dialog.setAttribute('role','dialog');
    dialog.setAttribute('aria-labelledby','maximo-close-title');
    const style=document.createElement('style'); style.id='maximo-close-review-style';
    style.textContent=`
      #maximo-close-review{width:min(590px,calc(100vw - 32px));max-width:none;max-height:calc(100vh - 32px);
        padding:0;overflow-y:auto;overscroll-behavior:contain;
        border:1px solid #a9bfd7;border-radius:16px;background:#f7faff;color:#18344f;
        box-shadow:0 22px 72px #102c4b50;font:14px/1.45 "Segoe UI",Arial,sans-serif}
      #maximo-close-review::backdrop{background:#12283d80;backdrop-filter:blur(2px)}
      #maximo-close-review *{box-sizing:border-box}
      #maximo-close-review .close-head{padding:22px 26px 18px;background:linear-gradient(135deg,#eaf3ff,#fff);
        border-bottom:1px solid #d7e3f0}
      #maximo-close-review .close-kicker{margin:0 0 5px;color:#3974b7;font-size:11px;font-weight:700;
        letter-spacing:.09em;text-transform:uppercase}
      #maximo-close-review h2{margin:0;color:#17395d;font-size:21px;line-height:1.25}
      #maximo-close-review .close-intro{margin:8px 0 0;color:#526b83}
      #maximo-close-review .close-body{display:grid;gap:16px;padding:20px 26px}
      #maximo-close-review .close-card{padding:15px 16px;border:1px solid #d8e3ef;border-radius:11px;background:#fff}
      #maximo-close-review .close-label{display:block;margin:0 0 6px;color:#284b6b;font-weight:650}
      #maximo-close-review input[type=text],#maximo-close-review input[type=datetime-local]{
        display:block;width:100%;min-height:40px;padding:8px 10px;border:1px solid #b8cbe0;border-radius:7px;
        background:#fff;color:#18344f;font:14px "Segoe UI",Arial,sans-serif;outline:none}
      #maximo-close-review input:focus{border-color:#3783cf;box-shadow:0 0 0 3px #3783cf26}
      #maximo-close-review input[readonly]{background:#eff4fa;color:#597087}
      #maximo-close-review .close-hint{display:block;margin-top:6px;color:#637991;font-size:12px}
      #maximo-close-review fieldset{margin:0;padding:0;border:0}
      #maximo-close-review legend{margin-bottom:9px;color:#284b6b;font-weight:700}
      #maximo-close-review .close-choice-row{display:flex;flex-wrap:wrap;gap:9px}
      #maximo-close-review .close-choice{display:flex;align-items:center;gap:8px;min-height:40px;padding:8px 11px;
        border:1px solid #d2dfed;border-radius:8px;background:#fff;color:#284b6b;cursor:pointer}
      #maximo-close-review .close-choice:has(input:checked){border-color:#5592ce;background:#edf6ff;color:#174f86}
      #maximo-close-review .close-date-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:end}
      #maximo-close-review .close-date-field{min-width:0}
      #maximo-close-review .close-now{min-height:36px;margin-top:7px;padding:6px 12px;border:1px solid #7da9d4;
        border-radius:7px;background:#eff6fd;color:#235b91;font:600 13px "Segoe UI",Arial,sans-serif;cursor:pointer}
      #maximo-close-review .close-now:hover{background:#e1effd}
      #maximo-close-review .close-existing{margin:0;color:#637991;font-size:12px}
      #maximo-close-review .close-error{min-height:18px;margin:0;color:#a22d36;font-weight:600}
      #maximo-close-review .close-warning{margin:0;padding:10px 12px;border:1px solid #f0d3a5;border-radius:8px;
        background:#fff8ed;color:#835315;font-weight:600}
      #maximo-close-review .close-actions{display:flex;justify-content:flex-end;gap:10px;padding:14px 26px 20px;
        border-top:1px solid #e0e8f1;background:#fff}
      #maximo-close-review button.close-cancel,#maximo-close-review button.close-confirm{min-height:40px;padding:8px 15px;
        border:1px solid #b8cbe0;border-radius:8px;background:#fff;color:#284b6b;font:600 13px "Segoe UI",Arial,sans-serif;cursor:pointer}
      #maximo-close-review button.close-confirm{border-color:#2874bb;background:#2874bb;color:#fff}
      #maximo-close-review button.close-confirm:hover:not(:disabled){background:#1c609f}
      #maximo-close-review button.close-confirm:disabled{border-color:#c7d3df;background:#c7d3df;color:#f8fafc;cursor:not-allowed}
      @media(max-width:520px){#maximo-close-review .close-date-grid{grid-template-columns:1fr}}
    `;
    document.getElementById(style.id)?.remove(); document.head.appendChild(style);
    dialog.innerHTML=`<form>
      <header class="close-head"><p class="close-kicker">Revisión antes del cierre</p>
        <h2 id="maximo-close-title"></h2>
        <p class="close-intro">El cierre dejará la OT pendiente de salida del almacén (ISSUE).</p></header>
      <div class="close-body">
        <section class="close-card"><label class="close-label" for="maximo-close-duration">Duración de la reparación</label>
          <input id="maximo-close-duration" name="duration" type="text" inputmode="decimal" required placeholder="Ejemplo: 0,75">
          <small class="close-hint">Horas decimales en tramos de 0,25 h (15 minutos).</small></section>
        <section class="close-card"><fieldset><legend>¿Qué hora quieres indicar?</legend>
          <div class="close-choice-row">
            <label class="close-choice"><input type="radio" name="dateBasis" value="start" checked> Hora de inicio</label>
            <label class="close-choice"><input type="radio" name="dateBasis" value="end"> Hora de finalización</label>
          </div></fieldset>
          <div class="close-date-grid" style="margin-top:14px">
            <label class="close-date-field"><span class="close-label">Inicio real</span>
              <input name="start" type="datetime-local" step="60" aria-label="Inicio real"></label>
            <label class="close-date-field"><span class="close-label">Finalización real</span>
              <input name="end" type="datetime-local" step="60" aria-label="Finalización real">
              <button class="close-now" type="button" name="now">Ahora</button></label>
          </div>
        </section>
        <p id="maximo-close-existing" class="close-existing"></p>
        <p id="maximo-close-error" class="close-error" role="alert"></p>
        <p class="close-warning">El cierre no es reversible. Comprueba los datos antes de confirmar.</p>
      </div>
      <div class="close-actions"><button type="button" name="cancel" class="close-cancel">Cancelar</button>
        <button type="submit" name="confirm" class="close-confirm">Confirmar cierre</button></div></form>`;
    const form=dialog.querySelector('form'),duration=form.elements.duration,start=form.elements.start,end=form.elements.end;
    const nowButton=form.elements.now,basis=form.elements.dateBasis;
    dialog.querySelector('h2').textContent='Cerrar OT '+data.ot;
    duration.value=data.duration;
    dialog.querySelector('#maximo-close-existing').textContent=
      'Inicio actual en Maximo (referencia): '+(data.start.replace('T',' ')||'sin indicar')+
      '. Finalización actual: '+(data.end.replace('T',' ')||'sin indicar');
    const calculate=()=>{
      const useStart=basis.value==='start';
      start.readOnly=!useStart; end.readOnly=useStart; nowButton.hidden=useStart;
      if(useStart)end.value=''; else start.value='';
      const text=duration.value.trim().replace(',','.');
      const hours=Number(text),quarter=hours*4;
      let error='';
      if (!/^\d+(?:\.\d+)?$/.test(text) || !(hours>0) || !Number.isSafeInteger(quarter))
        error='Introduce una duración mayor que cero en múltiplos de 0,25 h.';
      const source=useStart?start:end;
      if (!source.value) error=error||(useStart?'Indica la fecha y hora de inicio.':'Indica la fecha y hora de finalización.');
      if (!error) {
        // Civil clock arithmetic, matching Python datetime even across DST.
        const p=source.value.split(/[-T:]/).map(Number),base=new Date(Date.UTC(p[0],p[1]-1,p[2],p[3],p[4],p[5]||0));
        const startDate=new Date(base),endDate=new Date(base);
        if(useStart)endDate.setUTCSeconds(endDate.getUTCSeconds()+quarter*900);
        else startDate.setUTCSeconds(startDate.getUTCSeconds()-quarter*900);
        if (!Number.isFinite(base.getTime()) || !Number.isFinite(startDate.getTime()) ||
            !Number.isFinite(endDate.getTime()) || startDate.getUTCFullYear()>9999 || endDate.getUTCFullYear()>9999)
          error='La duración está fuera de rango.';
        else {
          const toInput=date=>date.toISOString().slice(0,16);
          start.value=toInput(startDate); end.value=toInput(endDate);
          const now=new Date(),civilNow=Date.UTC(now.getFullYear(),now.getMonth(),now.getDate(),
            now.getHours(),now.getMinutes(),now.getSeconds());
          if(endDate.getTime()>civilNow)error='La finalización no puede ser posterior a la hora actual.';
        }
      }
      dialog.querySelector('#maximo-close-error').textContent=error;
      form.elements.confirm.disabled=!!error;
      return !error;
    };
    duration.addEventListener('input',calculate); start.addEventListener('input',calculate);
    end.addEventListener('input',calculate); basis.forEach(option=>option.addEventListener('change',calculate));
    nowButton.addEventListener('click',()=>{
      const now=new Date(); now.setSeconds(0,0);
      const pad=n=>String(n).padStart(2,'0');
      end.value=`${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
      basis.value='end'; calculate();
    });
    const cancel=event=>{
      event.preventDefault(); dialog.close(); dialog.remove();
      document.documentElement.dataset.maximoCloseOtRequest=JSON.stringify({action:'cancel',token});
    };
    form.elements.cancel.addEventListener('click',cancel); dialog.addEventListener('cancel',cancel);
    form.addEventListener('submit',event=>{
      event.preventDefault(); if (!event.isTrusted || !calculate()) return;
      const request={action:'approve',token,ot:data.ot,duration:duration.value.trim(),start:start.value,end:end.value};
      dialog.close(); dialog.remove();
      document.documentElement.dataset.maximoCloseOtRequest=JSON.stringify(request);
    });
    document.body.appendChild(dialog); calculate(); dialog.showModal();
    (duration.value ? start : duration).focus();
"""


def poll_browser_close(driver):
    """Read first, then accept exactly one human confirmation in this Edge session."""
    request=driver.execute_script(BROWSER_BUTTON_SCRIPT)
    if not request:
        return None

    def report(message):
        driver.execute_script("""
          const b=document.getElementById('maximo-desktop-close-ot');
          if(b){b.textContent=arguments[0];b.title=arguments[0];}
        """,message)

    keep_review=False
    try:
        action=request.get('action')
        if action=='cancel':
            driver._maximo_close_review=None
            report('Cierre cancelado; no se han cambiado los datos')
            return None
        if action=='prepare':
            driver._maximo_close_review=None
            snapshot=WorkorderCloser(driver,request.get('ot'),report).inspect_repair()
            return_tab=str(request.get('returnTab') or '').strip()
            if return_tab:
                WorkorderCloser(driver,request.get('ot'),report).tab(return_tab)
            pending={'token':uuid4().hex,'snapshot':snapshot,'created':time.monotonic(),
                     'return_tab':return_tab}
            driver._maximo_close_review=pending
            driver.execute_script(BROWSER_REVIEW_SCRIPT,snapshot,pending['token'])
            keep_review=True
            return None
        if action!='approve':
            raise RuntimeError('Acción de cierre no reconocida.')
        # Consume before execution: a failed or uncertain close is never replayed.
        pending=getattr(driver,'_maximo_close_review',None)
        driver._maximo_close_review=None
        if not pending or request.get('token')!=pending['token']:
            raise RuntimeError('La revisión del cierre ya no es válida. Revisa los datos otra vez.')
        pending['approved']=True
        result=WorkorderCloser(driver,request.get('ot'),report).run_close(request,pending)
        driver.execute_script(BROWSER_BUTTON_SCRIPT)
        report(f'OT {result["ot"]}: pendiente de salida del almacén (ISSUE)')
        return result
    except Exception as exc:
        pending_review=locals().get('pending') or getattr(driver,'_maximo_close_review',None)
        return_tab=request.get('returnTab') or (pending_review or {}).get('return_tab')
        if return_tab:
            try:
                WorkorderCloser(driver,request.get('ot'),report).tab(return_tab)
            except Exception:
                logging.info('No se pudo restaurar la pestaña de origen tras el error de cierre')
        driver._maximo_close_review=None
        logging.exception('No se pudo cerrar la OT desde Edge')
        driver.execute_script(BROWSER_BUTTON_SCRIPT)
        report(f'No se pudo cerrar: {browser_error_message(exc)}')
        return None
    finally:
        if not keep_review:
            driver.execute_script("""
                const b=document.getElementById('maximo-desktop-close-ot');
                if(b){b.dataset.busy='false';setTimeout(()=>{
                  if(b.dataset.busy!=='true')b.textContent='Cerrar OT';
                },15000);}
            """)
