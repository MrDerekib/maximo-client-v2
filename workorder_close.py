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
        self.progress(f'OT {self.ot}: configurando {caption.lower()}…')
        def confirmed(d):
            self.reject_dialogs()
            snapshot=self.field_snapshot(caption)
            return actual_datetime(snapshot['value'],snapshot['title'])==value

        if current['readonly']:
            raise RuntimeError(f'Maximo no permite escribir {caption}. Revisa el campo manualmente; no se cerrará la OT.')
        # DateTime inputs with datatype=4 accept the localized date/time via
        # keyboard. Tab triggers Maximo's validation and change handlers.
        formatted=value.strftime('%d/%m/%y %H:%M:%S')
        for attempt in range(3):
            try:
                field=self.field(caption)
                field.click()
                field.send_keys(Keys.CONTROL,'a',Keys.BACKSPACE)
                field.send_keys(formatted)
                typed=field.get_attribute('value')
                if actual_datetime(typed)!=value:
                    raise RuntimeError(f'Maximo interpretó {typed!r} al escribir {caption}; '
                                       'se detuvo antes de guardar.')
                field.send_keys(Keys.TAB)
                break
            except StaleElementReferenceException:
                # A redraw after Tab can mean Maximo accepted the value. Check
                # the live field first, then safely reacquire only this input.
                if confirmed(self.driver):
                    break
                if attempt==2:
                    raise RuntimeError(f'Maximo actualizó la ficha al escribir {caption}; revisa el valor antes de continuar.')
        self.wait(confirmed,f'validación de {caption}')

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
        self.save()
        self.driver.refresh()
        verified=self.inspect_repair()
        if (repair_seconds(verified['duration'])!=plan['duration_seconds'] or
                actual_datetime(verified['start'])!=start or actual_datetime(verified['end'])!=end):
            raise RuntimeError('Maximo no guardó la duración y las fechas confirmadas. No se cerrará la OT.')
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
        document.documentElement.dataset.maximoCloseOtRequest=JSON.stringify({action:'prepare',ot:field('Orden de trabajo')});
      });
      document.body.appendChild(button);
    }
    if (button) {
      button.hidden=!/^\d{1,20}$/.test(ot||'');
      if (button.dataset.busy!=='true') {
        button.disabled=status!=='INPRG' || visibleDialogs.length>0;
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
    Object.assign(dialog.style,{border:'1px solid #b8cbe0',borderRadius:'12px',padding:'24px',
      width:'440px',maxWidth:'90vw',font:'14px Arial,sans-serif',color:'#122d48',background:'#fff',
      boxShadow:'0 12px 60px #0005'});
    dialog.innerHTML=`<form><h2 id="maximo-close-title" style="margin-top:0;font-size:20px"></h2>
      <p>Revisa las horas de reparación. El cierre deja la OT pendiente de salida del almacén (ISSUE).</p>
      <p><label>Duración en horas <input name="duration" type="text" inputmode="decimal" required
        placeholder="Ejemplo: 0,75" style="display:block;width:95%;padding:8px;margin-top:6px"></label>
        <small>Solo múltiplos de 0,25 h (15 minutos).</small></p>
      <p><label>Inicio real <input name="start" type="datetime-local" step="1" required
        style="display:block;width:95%;padding:8px;margin-top:6px"></label></p>
      <p><label>Finalización calculada <input name="end" type="datetime-local" step="1" readonly
        style="display:block;width:95%;padding:8px;margin-top:6px"></label></p>
      <p id="maximo-close-existing" style="font-size:12px;color:#526578"></p>
      <p id="maximo-close-error" role="alert" style="color:#a12727"></p>
      <p><strong>El cierre no es reversible. Confirma solo si el equipo está listo.</strong></p>
      <div style="display:flex;gap:10px;justify-content:flex-end"><button type="button" name="cancel">Cancelar</button>
        <button type="submit" name="confirm">Confirmar cierre</button></div></form>`;
    const form=dialog.querySelector('form'),duration=form.elements.duration,start=form.elements.start,end=form.elements.end;
    dialog.querySelector('h2').textContent='Cerrar OT '+data.ot;
    duration.value=data.duration;
    // Ask for the actual start; the automatically recorded time is only a reference.
    dialog.querySelector('#maximo-close-existing').textContent=
      'Inicio actual en Maximo (referencia): '+(data.start.replace('T',' ')||'sin indicar')+
      '. Finalización actual: '+(data.end.replace('T',' ')||'sin indicar');
    const calculate=()=>{
      end.value=''; const text=duration.value.trim().replace(',','.');
      const hours=Number(text),quarter=hours*4;
      let error='';
      if (!/^\d+(?:\.\d+)?$/.test(text) || !(hours>0) || !Number.isSafeInteger(quarter))
        error='Introduce una duración mayor que cero en múltiplos de 0,25 h.';
      if (!start.value) error=error||'Indica la fecha y hora de inicio real.';
      if (!error) {
        // Civil clock arithmetic, matching Python datetime even across DST.
        const p=start.value.split(/[-T:]/).map(Number),date=new Date(Date.UTC(p[0],p[1]-1,p[2],p[3],p[4],p[5]||0));
        date.setUTCSeconds(date.getUTCSeconds()+quarter*900);
        if (!Number.isFinite(date.getTime()) || date.getUTCFullYear()>9999) error='La duración está fuera de rango.';
        else {
          end.value=date.toISOString().slice(0,19);
          const now=new Date(),civilNow=Date.UTC(now.getFullYear(),now.getMonth(),now.getDate(),
            now.getHours(),now.getMinutes(),now.getSeconds());
          if(date.getTime()>civilNow)error='La finalización no puede ser posterior a la hora actual.';
        }
      }
      dialog.querySelector('#maximo-close-error').textContent=error;
      form.elements.confirm.disabled=!!error;
      return !error;
    };
    const cancel=event=>{
      event.preventDefault(); dialog.close(); dialog.remove();
      document.documentElement.dataset.maximoCloseOtRequest=JSON.stringify({action:'cancel',token});
    };
    duration.addEventListener('input',calculate); start.addEventListener('input',calculate);
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
            pending={'token':uuid4().hex,'snapshot':snapshot,'created':time.monotonic()}
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
