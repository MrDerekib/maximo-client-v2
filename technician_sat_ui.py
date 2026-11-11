"""Technician SAT review uses the shared batch report, never warehouse reception."""
from threading import Event
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QTableWidgetItem, QMessageBox, QHeaderView
from failure_picker import FailurePathPicker
from technician_sat import reviewed_sat_plans, technician_sat_defaults
from warehouse_ui import WarehouseBatchDialog
from warehouse_diagnostics import log_exception, sanitize


class TechnicianPreviewThread(QThread):
    ready = Signal(object)
    failed = Signal(str)
    waiting = Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self.stop_requested = Event()

    def run(self):
        try:
            data = technician_sat_defaults(self.items, stop=self.stop_requested,
                progress=self.waiting.emit, job_waiting=self.waiting.emit,
                job_cancel_event=self.stop_requested)
            self.ready.emit(data)
        except Exception as exc:
            log_exception('No se pudo consultar la preparación de SAT técnico')
            self.failed.emit(sanitize(str(exc)))


class TechnicianSatDialog(WarehouseBatchDialog):
    def __init__(self, items, open_ot, parent=None, *, selection=None, report_folder=None,
                 autoload=True):
        self._preview_worker = None
        self._preview_closed = False
        self._preview_complete = False
        super().__init__(items, 'technician_sat_external', open_ot, parent, report_folder)
        self.technician_plans = None
        self.inputs = {}
        self.table.setColumnCount(9)
        for column, caption in ((6,'Horas'),(7,'Incidencia / referencia'),(8,'Motivo SAT (editable)')):
            self.table.setHorizontalHeaderItem(column,QTableWidgetItem(caption))
        for row, item in enumerate(self.items):
            duration, incident, reason = QLineEdit(), QLineEdit(), QLineEdit()
            duration.setPlaceholderText('Ejemplo: 0,5')
            incident.setPlaceholderText('Número o stock')
            reason.setPlaceholderText('Se consultará la avería en Maximo')
            reason.setMinimumWidth(200)
            self.inputs[item.ot] = {'duration':duration,'incident':incident,'reason':reason}
            self.details_inputs[item.ot] = reason
            for column, field in zip((6,7,8),(duration,incident,reason)):
                self.table.setCellWidget(row,column,field)
        # During review, show editable inputs rather than empty report columns.
        for column in (3,4,5):
            self.table.setColumnHidden(column,True)
        header = self.table.horizontalHeader()
        for column,width in ((0,80),(1,240),(2,90),(6,90),(7,170)):
            header.setSectionResizeMode(column,QHeaderView.Fixed)
            self.table.setColumnWidth(column,width)
        header.setSectionResizeMode(8,QHeaderView.Stretch)
        self.anomaly_label = QLabel('Combinación de anomalías para este lote')
        self.failure_picker = FailurePathPicker()
        if selection is not None:
            self.failure_picker.set_selection(selection)
        self.layout().insertWidget(2,self.anomaly_label)
        self.layout().insertWidget(3,self.failure_picker)
        self.start_button.setEnabled(False)
        self.start_button.setText('Consultar datos antes de enviar')
        self.steps.setText('Consultar → Revisar → Preparar anomalías, horas e incidencia → Enviar → Verificar')
        self.current_step.setText('Se consultarán las OTs sin modificarlas para proponer el motivo y las horas actuales.')
        self.resize(1250,780)
        if autoload:
            QTimer.singleShot(0,self,self.start_preview)

    def start_preview(self):
        if self._preview_closed or self.is_running():
            return
        self._preview_worker = TechnicianPreviewThread(self.items,self)
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
            for key in ('duration','reason'):
                if not fields[key].text():
                    fields[key].setText(defaults[key])
            self.table.item(row,3).setText('Datos consultados')
            self.table.item(row,5).setText('Estado real: '+defaults['status'])
        self.start_button.setEnabled(self._preview_complete)
        self.start_button.setText('Revisar y enviar…')
        if unsuitable:
            self.current_step.setText('Envío deshabilitado: estas OTs no están en APPR: '+', '.join(unsuitable)+'. Revisa la selección.')
        else:
            self.current_step.setText('Completa horas e incidencia por OT y revisa el motivo propuesto desde Maximo.')

    def _preview_failed(self, message):
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
            header.setSectionResizeMode(column,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5,QHeaderView.Stretch)
        super()._launch_worker(recoveries)

    def closeEvent(self,event):
        if not self.is_running():
            self._preview_closed = True
        super().closeEvent(event)

    def reject(self):
        if not self.is_running():
            self._preview_closed = True
        super().reject()
