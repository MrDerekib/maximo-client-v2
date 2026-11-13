"""Read-on-demand browser closure review; no background cache or implicit writes."""
import logging
import re
from collections import Counter
from selenium.webdriver.common.by import By
from technician_repair import RepairPreparer, RepairEntry
from technician_sat import format_incident
from workorder_start import normalized
from workorder_close import actual_datetime


class BrowserRecordReader(RepairPreparer):
    def __init__(self, closer):
        self.closer = closer
        super().__init__(closer.driver, closer.ot, 'INPRG', closer.progress)
        self.timeout = closer.timeout

    def check_location(self):
        self.closer.check_location()

    def response_sequence(self):
        return self.closer.response_sequence()

    def ensure_entry(self, entry):
        if self.active_status!='INPRG':
            raise RuntimeError('La lectura posterior al cierre no permite añadir registros.')
        # Scoped to this reviewed execution, never a background/persistent cache.
        before=getattr(self,'_reviewed_records',None)
        if before is None:before=self.read_records()
        existing=[row for row in before['entries'] if normalized(row['type'])=='clientnote' and normalized(row['summary'])==normalized(entry.summary)]
        if existing:
            if any(row['details'].strip()!=entry.details.strip() for row in existing):
                raise RuntimeError('El resumen ya existe con otros detalles. No se sobrescribirá.')
            return
        self.require_approved()
        self.tab('Registro')
        buttons=[button for button in self.driver.find_elements(By.TAG_NAME,'button')
                 if button.is_displayed() and button.is_enabled() and normalized(button.text)=='fila nueva']
        if len(buttons)!=1:raise RuntimeError('No hay un único botón Fila Nueva para Registro.')
        logging.info('OT %s: Registro, creando entrada; existentes=%s; resumen_len=%s; detalles_len=%s',
                     self.ot,len(before['entries']),len(entry.summary),len(entry.details))
        buttons[0].click()  # Never replay an uncertain row creation.
        self.wait(lambda _:self.page_position()[2]==len(before['entries'])+1 and self.field('Resumen') is not None
                  and self.field('Tipo') is not None,'fila nueva de Registro')
        if self.value('Tipo')!='CLIENTNOTE' or self.value('Resumen'):
            raise RuntimeError('La nueva entrada no está vacía o no es CLIENTNOTE.')
        self._write_text('Resumen',entry.summary)
        if entry.details:self.details(entry.details)
        self.idle();self.require_approved()
        # Keep native validated drafts in this same record. The explicitly
        # approved workflow transition performs the commit; never Save here.
        self._reviewed_records=None
        logging.info('OT %s: entrada de Registro validada; pendiente del enrutado, sin Guardar',self.ot)

    def page_position(self):
        result = self.driver.execute_script(r"""
          const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
          const pages=[...document.querySelectorAll('label')].filter(visible)
            .map(e=>e.textContent.trim().match(/^(\d+)\s*-\s*(\d+)\s+de\s+(\d+)$/))
            .filter(Boolean).map(m=>[+m[1],+m[2],+m[3]]);
          return [...new Map(pages.map(p=>[p.join(':'),p])).values()];
        """)
        if len(result) != 1:
            raise RuntimeError('No se pudo identificar una única paginación de Registro.')
        return tuple(result[0])

    def page(self, direction, before):
        title = 'Página anterior' if direction == 'previous' else 'Página siguiente'
        links = [e for e in self.driver.find_elements(By.CSS_SELECTOR, f'a[title^="{title}"]')
                 if e.is_displayed() and e.is_enabled() and e.get_attribute('aria-disabled') != 'true']
        if len(links) != 1:
            raise RuntimeError('No se pudo recorrer Registro de forma inequívoca; no se asumirá que está vacío.')
        links[0].click()
        self.wait(lambda _: self.page_position() != before, 'página de Registro')
        self.idle(); self.require_approved()

    def read_records(self):
        self.tab('Registro')
        for _ in range(100):
            position = self.page_position()
            if position[0] <= 1: break
            self.page('previous', position)
        else: raise RuntimeError('Registro demasiado extenso; requiere revisión manual.')
        entries = []; expected_total = position[2]
        for _ in range(100):
            first, last, total = self.page_position()
            if total != expected_total or (total and first != len(entries) + 1):
                raise RuntimeError('Registro cambió durante la lectura. Vuelve a revisarlo.')
            snapshot = self.worklog_snapshot()
            rows = snapshot['rows']
            if len(rows) != (last-first+1 if total else 0):
                raise RuntimeError('No se pudo comprobar el Registro completo; no se añadirá información a ciegas.')
            for row in rows:
                cells = row['cells']
                if len(cells) < 10:
                    raise RuntimeError('Formato de Registro no reconocido; requiere revisión.')
                kind, summary = cells[8].strip(), cells[9].strip()
                if not kind or not summary:
                    raise RuntimeError('Hay una entrada incompleta en Registro. Revísala antes de cerrar.')
                detail = ''
                if normalized(kind) == 'clientnote':
                    native = self.driver.find_element(By.ID, row['id'])
                    toggles = native.find_elements(By.CSS_SELECTOR, 'a[id*="_tgdet-ti"]')
                    if len(toggles) != 1:
                        raise RuntimeError('No se pudo leer el detalle de una entrada de Registro.')
                    if normalized(toggles[0].get_attribute('title')) == 'ver detalles':
                        toggles[0].click(); self.idle()
                    self.wait(lambda _: self.value('Resumen') == summary, 'entrada de Registro seleccionada')
                    detail = self.details()
                entries.append({'type':kind, 'summary':summary, 'details':detail,
                                'author':cells[5], 'date':cells[7]})
            if last >= total: break
            self.page('next', (first,last,total))
        else: raise RuntimeError('Registro demasiado extenso; requiere revisión manual.')
        if len(entries) != expected_total:
            raise RuntimeError('Lectura incompleta de Registro.')
        return {'complete':True, 'entries':entries, 'error':''}


def reference_of(entry):
    if normalized(entry.get('type')) != 'clientnote': return None
    text = str(entry.get('summary') or '').strip()
    if not re.match(r'^inc\s*:',text,re.I): return None
    try: return format_incident(text)
    except ValueError: return None


def summarize_records(records):
    entries = records.get('entries', [])
    references = list(dict.fromkeys(value for entry in entries if (value := reference_of(entry))))
    notes = [entry for entry in entries if normalized(entry.get('type')) == 'clientnote' and not re.match(r'^inc\s*:',str(entry.get('summary') or '').strip(),re.I)]
    return {**records, 'references':references, 'notes':notes}


def signature(records):
    # Preserve duplicates, but don't treat display sort changes as edits.
    return Counter(tuple(str(row.get(key) or '') for key in ('type','summary','details','author','date'))
                   for row in records.get('entries', []))


def read_anomalies(closer):
    closer.tab('Informes de anomalías')
    class_code = str(closer.value('Clase de anomalía') or '').strip()
    closer.tab('Soluciones')
    codes = closer.solution_codes()
    return {'class':class_code, 'codes':codes, 'complete':bool(class_code and all(codes.values()))}


def inspect_browser_review(closer):
    closer.require_in_progress()
    snapshot = closer.inspect_repair()
    closer.progress(f'OT {closer.ot}: leyendo incidencia y trabajos de Registro…')
    try:
        records = BrowserRecordReader(closer).read_records()
    except RuntimeError as exc:
        records = {'complete':False, 'entries':[], 'error':str(exc)}
        logging.warning('OT %s: Registro no verificable para el cierre: %s',closer.ot,exc)
    closer.progress(f'OT {closer.ot}: comprobando anomalías y soluciones…')
    anomalies = read_anomalies(closer)
    return snapshot, summarize_records(records), anomalies


def validate_record_approval(approval, records, anomalies):
    if not records.get('complete'):
        raise ValueError('Registro no verificado. No se cerrará la OT.')
    if not anomalies.get('complete'):
        raise ValueError('Completa la clase de anomalía y las soluciones antes de cerrar.')
    reference = format_incident(approval.get('reference'))
    if any(ord(char)<32 for char in reference): raise ValueError('La incidencia contiene caracteres no válidos.')
    references = records.get('references', [])
    if references and reference not in references and approval.get('new_reference_confirmed') is not True:
        raise ValueError('Confirma expresamente que quieres añadir otra incidencia; las existentes no se sustituirán.')
    values = approval.get('entries', [])
    if not isinstance(values,list) or len(values)>30: raise ValueError('Entradas de Registro no válidas.')
    additions = []; seen = set(); matched_activity = False
    for value in values:
        if not isinstance(value,dict): raise ValueError('Entrada de Registro no válida.')
        summary=str(value.get('summary') or '').strip(); details=str(value.get('details') or '').strip()
        if not summary and not details: continue
        if not summary or len(summary)>100 or any(ord(char)<32 for char in summary):
            raise ValueError('Cada entrada necesita un resumen válido de hasta 100 caracteres.')
        if len(details)>20000: raise ValueError('Los detalles de la entrada son demasiado extensos.')
        if re.match(r'^inc\s*:',summary,re.I): raise ValueError('Introduce la incidencia en su campo, no como reparación.')
        key=normalized(summary)
        if key in seen: raise ValueError('No repitas resúmenes en las entradas nuevas.')
        seen.add(key)
        existing=[row for row in records['entries'] if normalized(row['type'])=='clientnote' and normalized(row['summary'])==key]
        if existing:
            if any(row['details'].strip()!=details for row in existing):
                raise ValueError('Ese resumen ya existe con otros detalles. No se sobrescribirá el Registro.')
            matched_activity = True
            continue  # Exact existing entry: no duplicate on a retry.
        additions.append(RepairEntry(summary,details))
    if not additions and not matched_activity and not (records.get('notes') and approval.get('activity_confirmed') is True):
        raise ValueError('Añade los trabajos o pruebas realizados, o confirma que las entradas existentes los documentan.')
    if len(reference)>100: raise ValueError('La incidencia es demasiado larga para el resumen de Registro.')
    return reference, additions


def prepare_browser_records(closer, approval, pending):
    records=pending['records']; anomalies=pending['anomalies']
    reference, additions=validate_record_approval(approval,records,anomalies)
    # Token, OT, action, dates and expiry are validated by prepare_close BEFORE this call.
    closer.progress(f'OT {closer.ot}: comprobando la ficha revisada antes de preparar el cierre…')
    current=closer.inspect_repair()
    if current!=pending['snapshot']: raise RuntimeError('La duración o las fechas cambiaron desde la revisión.')
    reader=BrowserRecordReader(closer)
    fresh=summarize_records(reader.read_records())
    if signature(fresh)!=signature(records) or read_anomalies(closer)!=anomalies:
        raise RuntimeError('Registro, anomalías o soluciones cambiaron desde la revisión. Revisa los datos otra vez.')
    reader._reviewed_records=fresh
    if reference not in records['references']:
        closer.progress(f'OT {closer.ot}: añadiendo la incidencia revisada…')
        reader.ensure_entry(RepairEntry(reference))
    for index, entry in enumerate(additions,1):
        closer.progress(f'OT {closer.ot}: preparando trabajo {index}/{len(additions)}…')
        reader.ensure_entry(entry)
    pending['expected_reference']=reference
    pending['expected_entries']=[{'summary':entry.summary,'details':entry.details} for entry in additions]
    return current


def verify_browser_closed_records(closer, pending, status):
    """Read only after the workflow confirms its state change; never replays it."""
    if (not pending['expected_entries'] and
            pending['expected_reference'] in pending['records']['references']):
        return
    closer.progress(f'OT {closer.ot}: comprobando el Registro tras finalizar el flujo…')
    reader=BrowserRecordReader(closer)
    reader.active_status=status  # Read-only now: ensure_entry explicitly refuses writes.
    records=summarize_records(reader.read_records())
    if pending['expected_reference'] not in records['references']:
        raise RuntimeError('El flujo finalizó, pero no se confirmó la incidencia. Revisa Registro; no se repetirá el cierre.')
    expected=signature(pending['records'])
    actual=signature(records)
    if any(actual[key]<count for key,count in expected.items()):
        raise RuntimeError('El flujo finalizó, pero cambió una entrada existente. Revisa Registro; no se repetirá el cierre.')
    for entry in pending['expected_entries']:
        if not any(row['summary']==entry['summary'] and row['details']==entry['details']
                   and normalized(row['type'])=='clientnote' for row in records['entries']):
            raise RuntimeError('El flujo finalizó, pero no se confirmaron todos los trabajos. Revisa Registro; no se repetirá el cierre.')
    logging.info('OT %s: Registro confirmado tras el enrutado; %s trabajos nuevos, sin guardados intermedios',
                 closer.ot,len(pending['expected_entries']))
