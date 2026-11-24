"""Technician SAT review uses the shared batch report, never warehouse reception."""
from threading import Event
from db import get_fault_description, fault_description_checked
from preview_lifecycle import cancel_readonly_preview
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QTableWidgetItem, QMessageBox, QHeaderView
from failure_picker import FailurePathPicker
from technician_sat import incident_required, reviewed_sat_plans, technician_sat_defaults
from warehouse_recovery import preparation_retry_allowed
from warehouse_ui import WarehouseBatchDialog
from warehouse_diagnostics import log_exception, sanitize


class TechnicianPreviewThread(QThread):
    ready = Signal(object)
    failed = Signal(str)
    waiting = Signal(str)

    def __init__(self, items, parent=None, *, read_reference=False):
        super().__init__(parent)
        self.items = items
        self.read_reference = read_reference
        self.stop_requested = Event()

    def run(self):
        try:
            data = technician_sat_defaults(self.items, stop=self.stop_requested,
                progress=self.waiting.emit, read_reference=self.read_reference, job_waiting=self.waiting.emit,
                job_cancel_event=self.stop_requested)
            self.ready.emit(data)
        except Exception as exc:
            log_exception('No se pudo consultar la preparación de SAT técnico')
            self.failed.emit(sanitize(str(exc)))


class TechnicianSatDialog(WarehouseBatchDialog):
    def __init__(self, items, open_ot, parent=None, *, selection=None, report_folder=None,
                 autoload=True, retry_records=()):
        records = tuple(retry_records)
        if records and (len(records)!=len(items) or {r['item']['ot'] for r in records}!={i.ot for i in items}
                        or not all(preparation_retry_allowed(r) for r in records)):
            raise ValueError('El reintento no corresponde a una preparación sin enrutado.')
        self.retry_records = records
        self.technician_retries = {r['item']['ot']:r['operation_id'] for r in records}
        self._preview_worker = None
        self._preview_closed = False
        self._preview_complete = False
        super().__init__(items, 'technician_sat_external', open_ot, parent, report_folder)
        self.technician_plans = None
        self.inputs = {}
        self._edited_fields = set()
        self._cached_reasons = {}
        self.table.setColumnCount(9)
        for column, caption in ((6,'Horas'),(7,'Incidencia'),(8,'Motivo SAT (editable)')):
            self.table.setHorizontalHeaderItem(column,QTableWidgetItem(caption))
        for row, item in enumerate(self.items):
            duration, incident, reason = QLineEdit(), QLineEdit(), QLineEdit()
            duration.setPlaceholderText('Ejemplo: 0,5')
            incident.setPlaceholderText('Número o sin incidencia' if incident_required(item.client) else 'Opcional')
            cached = get_fault_description(item.ot)
            self._cached_reasons[item.ot] = bool(cached) or fault_description_checked(item.ot)
            reason.setText(cached)
            reason.setPlaceholderText('Escribe el motivo del envío' if self._cached_reasons[item.ot] else 'Se consultará la avería si no está en MD')
            reason.setMinimumWidth(200)
            self.inputs[item.ot] = {'duration':duration,'incident':incident,'reason':reason}
            self.details_inputs[item.ot] = reason
            for key, field in self.inputs[item.ot].items():
                field.textEdited.connect(lambda _text, ot=item.ot, name=key: self._edited_fields.add((ot,name)))
                field.textChanged.connect(lambda _text, control=field: self._field_tooltip(control))
                self._field_tooltip(field)
            equipment = self.table.item(row,1)
            equipment.setText(f"N/S: {item.serial or 'Sin indicar'}\n{item.equipment}")
            for column in range(6):
                cell = self.table.item(row,column)
                if cell is not None:cell.setToolTip(cell.text())
            for column, field in zip((6,7,8),(duration,incident,reason)):
                self.table.setCellWidget(row,column,field)
        # During review, show editable inputs rather than empty report columns.
        for column in (3,4,5):
            self.table.setColumnHidden(column,True)
        header = self.table.horizontalHeader()
        for column,width in ((0,85),(1,280),(2,115),(6,115),(7,190)):
            header.setSectionResizeMode(column,QHeaderView.Interactive)
            self.table.setColumnWidth(column,width)
        header.setSectionResizeMode(8,QHeaderView.Interactive)
        self.table.setColumnWidth(8,420)
        header.setMinimumSectionSize(65)
        self.table.setWordWrap(True)
        self.table.itemChanged.connect(lambda item: item.setToolTip(item.text())
            if item.toolTip()!=item.text() else None)
        vertical = self.table.verticalHeader()
        vertical.setVisible(True)
        vertical.setSectionResizeMode(QHeaderView.Interactive)
        vertical.setMinimumSectionSize(42)
        vertical.setDefaultSectionSize(68)
        for row in range(self.table.rowCount()):self.table.setRowHeight(row,68)
        self.anomaly_label = QLabel('Combinación de anomalías para este lote')
        self.failure_picker = FailurePathPicker()
        if selection is not None:
            self.failure_picker.set_selection(selection)
        self.layout().insertWidget(2,self.anomaly_label)
        self.layout().insertWidget(3,self.failure_picker)
        for record in records:
            request=record.get('reviewed_request') or {}
            for key in ('duration','incident','reason'):
                value=request.get(key,'')
                if isinstance(value,str):self.inputs[record['item']['ot']][key].setText(value)
            if request.get('anomaly_selection'):
                self.failure_picker.set_selection(request['anomaly_selection'])
        self.start_button.setEnabled(False)
        self.start_button.setText('Consultar datos antes de enviar')
        self.steps.setText('Consultar → Revisar → Preparar anomalías, horas e incidencia → Enviar → Verificar')
        self.current_step.setText('Motivo propuesto desde MD cuando esté disponible. Se validarán estado, equipo y horas en Maximo, sin modificar las OTs.')
        self.resize(1250,780)
        if autoload:
            QTimer.singleShot(0,self,self.start_preview)

    @staticmethod
    def _field_tooltip(field):
        current = field.text()
        proposed = field.property('preview_value')
        origin = field.property('preview_origin') or 'Maximo'
        field.setToolTip(current + (f'\n\nPropuesta ({origin}): {proposed}' if proposed is not None else ''))

    def start_preview(self):
        if self._preview_closed or self.is_running():
            return
        self._preview_worker = TechnicianPreviewThread(self.items,self,read_reference=bool(self.retry_records))
        self._preview_worker.ready.connect(self._defaults_ready)
        self._preview_worker.failed.connect(self._preview_failed)
        self._preview_worker.waiting.connect(self.current_step.setText)
        self._preview_worker.finished.connect(lambda:self.stop_button.setEnabled(False))
        lock = getattr(self.parent(),'update_lock',None)
        if lock is not None:
            lock.acquire(False)
            self._preview_worker.finished.connect(lock.release)
        self.stop_button.setEnabled(True)
        self._preview_worker.start()

    def _defaults_ready(self, data):
        if self._preview_closed:return
        if self._preview_worker is not None and self._preview_worker.stop_requested.is_set():
            self.current_step.setText('Consulta detenida. No se ha enviado ninguna OT.')
            return
        complete = set(data) == {item.ot for item in self.items}
        unsuitable = [ot for ot, values in data.items() if values['status'] != 'APPR']
        self._preview_complete = complete and not unsuitable
        for row,item in enumerate(self.items):
            if item.ot not in data:
                continue
            defaults = data[item.ot]
            fields = self.inputs[item.ot]
            for key in ('duration','reason','incident'):
                if not fields[key].text() and (item.ot,key) not in self._edited_fields:
                    fields[key].setText(defaults.get(key,''))
                if defaults.get(key) is not None:
                    fields[key].setProperty('preview_value',str(defaults[key]))
                    fields[key].setProperty('preview_origin','MD' if key=='reason' and self._cached_reasons[item.ot] else 'Maximo')
                    self._field_tooltip(fields[key])
            self.table.item(row,3).setText('Datos consultados')
            self.table.item(row,5).setText('Estado real: '+defaults['status'])
        self.start_button.setEnabled(self._preview_complete)
        self.start_button.setText('Revisar y enviar…')
        if unsuitable:
            self.current_step.setText('Envío deshabilitado: estas OTs no están en APPR: '+', '.join(unsuitable)+'. Revisa la selección.')
        else:
            self.current_step.setText(('Reintento: revisa la petición recuperada. Los valores actuales de Maximo aparecen al situarte sobre los campos. ' if self.retry_records else '')+'Completa las horas y el motivo. Indica la incidencia donde se requiera.')

    def _preview_failed(self, message):
        if self._preview_closed:return
        self.current_step.setText('No se pudieron consultar los datos: '+message)
        self.start_button.setEnabled(False)

    def is_running(self):
        return super().is_running() or (self._preview_worker is not None and self._preview_worker.isRunning())

    def request_stop(self):
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_worker.stop_requested.set()
            self.stop_button.setEnabled(False)
            self.current_step.setText('Se detendrá la consulta al terminar la OT actual.')
        else:
            super().request_stop()

    def start_operation(self):
        if self.is_running() or self._has_started or not self._preview_complete:
            return
        try:
            values = {ot:{key:field.text() for key,field in fields.items()}
                      for ot,fields in self.inputs.items()}
            self.technician_plans = reviewed_sat_plans(self.items,values,self.failure_picker.selection())
        except ValueError as exc:
            QMessageBox.warning(self,'Revisar envío técnico',str(exc));return
        super().start_operation()

    def _launch_worker(self, recoveries=None):
        for fields in self.inputs.values():
            for field in fields.values():
                field.setEnabled(False)
        self.failure_picker.setEnabled(False)
        self.failure_picker.hide();self.anomaly_label.hide()
        for column in (3,4,5):
            self.table.setColumnHidden(column,False)
        for column in (6,7,8):
            self.table.setColumnHidden(column,True)
        header = self.table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column,QHeaderView.Interactive)
        header.setSectionResizeMode(5,QHeaderView.Stretch)
        super()._launch_worker(recoveries)

    def closeEvent(self,event):
        if cancel_readonly_preview(self,self._preview_worker):
            event.accept();return
        if not self.is_running():
            self._preview_closed = True
        super().closeEvent(event)

    def reject(self):
        if cancel_readonly_preview(self,self._preview_worker):return
        if not self.is_running():
            self._preview_closed = True
        super().reject()
