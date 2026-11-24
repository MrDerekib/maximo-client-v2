"""Native MD review for repair completion and irreparable assets."""
from threading import Event
from datetime import datetime
from PySide6.QtCore import QThread,Signal,QDateTime,QTime,QPoint,Qt,QSignalBlocker
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QTableWidget,QTableWidgetItem,QStyledItemDelegate,QPushButton,QComboBox,QDateTimeEdit,QPlainTextEdit,
    QCheckBox,QMessageBox,QScrollArea,QWidget,QSizePolicy,QHeaderView,QApplication,QProgressBar,QAbstractItemView,QStyle,QCalendarWidget,QFrame)
from failure_picker import FailurePathPicker
from preview_lifecycle import cancel_readonly_preview
from rounded_table import RoundedTableFrame
from worklog_limits import WORKLOG_SUMMARY_MAX_LENGTH,summary_length
from technician_repair import reviewed_repair,run_repair,RepairPreparer,inspect_repair_recovery,repair_plan_from_record
from technician_sat import incident_required
from warehouse_transport import WarehouseSession
from warehouse_recovery import RecoveryStore, repair_retry_allowed
from warehouse import WarehouseResult
from db import get_fault_description,fault_description_checked,apply_closed_repair,apply_warehouse_status
from dataclasses import asdict
import json,logging
from uuid import uuid4
from warehouse_diagnostics import WarehouseJournal
from app_paths import LOG_DIR, PROGRAM_DIR
from ui_activity_icon import RefreshIndicator
from task_priorities import scheduled,HIGH


@scheduled('Consultar reparación para revisión',HIGH)
def repair_defaults(item, *, stop=None):
    stop = stop or Event()
    def check_cancelled():
        if stop.is_set():raise RuntimeError('Consulta cancelada.')
    check_cancelled()
    session=WarehouseSession()
    try:
        state=session.open(item.ot)
        check_cancelled()
        if not state:
            raise RuntimeError('Maximo no devolvió el estado de la OT.')
        if state not in ('APPR', 'INPRG'):
            return {'state': state}
        identity=session.identity()
        if item.serial and identity.get('Nº de serie')!=item.serial:raise RuntimeError('El número de serie no coincide.')
        r=RepairPreparer(session.driver,item.ot,state);session.reader=r
        cached=get_fault_description(item.ot)
        fault=cached if cached or fault_description_checked(item.ot) else r.value('Resumen') or ''
        check_cancelled()
        r.tab('Consumos Actuales');duration=r.value('Horas totales de reparación') or ''
        check_cancelled()
        r.tab('Registro');snapshot=r.worklog_snapshot()
        if not snapshot['totals'] or len(set(snapshot['totals']))!=1 or snapshot['totals'][0]>len(snapshot['rows']):
            raise RuntimeError('Registro con paginación incompleta; requiere revisión antes de proponer entradas.')
        summaries=[]
        for row in snapshot['rows']:
            # The native worklog exposes summary in column 9; locate CLIENTNOTE before reading it.
            cells=row['cells']
            if len(cells)>9 and cells[8]=='CLIENTNOTE' and cells[9]:summaries.append(cells[9])
        from technician_repair import RepairEntry
        notes=[];reference=''
        for summary in summaries:
            check_cancelled()
            if summary.lower().startswith('inc:') and not reference:reference=summary;continue
            entry=RepairEntry(summary)
            if not r.open_entry(entry):raise RuntimeError('El registro cambió durante la consulta.')
            notes.append({'summary':summary,'details':r.details()})
        return {'state':state,'identity':identity,'fault':fault,'duration':duration,'reference':reference,'entries':notes}
    finally:session.close()


class WorklogSummaryDelegate(QStyledItemDelegate):
    def createEditor(self,parent,option,index):
        editor=QLineEdit(parent)
        editor.setMaxLength(WORKLOG_SUMMARY_MAX_LENGTH)
        editor.textChanged.connect(lambda text:editor.setToolTip(
            f"{summary_length(text)}/{WORKLOG_SUMMARY_MAX_LENGTH} caracteres. Usa Detalles para el texto extenso."))
        return editor

    def updateEditorGeometry(self,editor,option,index):
        # Qt's default delegate can widen a line editor to fit its contents,
        # covering the adjacent Details cell. Keep editing inside this cell.
        rect=option.rect.adjusted(1,1,-1,-1)
        editor.setMaximumWidth(max(0,rect.width()))
        editor.setGeometry(rect)

    def setEditorData(self,editor,index):
        text=str(index.data(Qt.EditRole) or '')
        # Preserve an already-entered oversized draft; review validation will reject
        # it until corrected. Opening the editor must never silently truncate it.
        editor.setMaxLength(max(WORKLOG_SUMMARY_MAX_LENGTH,summary_length(text)))
        editor.setText(text)


class RepairProgressDialog(QDialog):
    STAGES=('Comprobar OT y estado','Preparar anomalías y Registro','Comprobar / iniciar OT',
            'Validar duración y fechas','Confirmar acción y justificación','Verificar resultado en Maximo')
    def __init__(self,owner):
        super().__init__(owner.parent());self.owner=owner;self.current=-1;self.succeeded=False
        self.setWindowTitle('Progreso de reparación · OT '+owner.item.ot)
        self.resize(760,510)
        layout=QVBoxLayout(self)
        title=QLabel('Reparación · OT '+owner.item.ot);title.setTextFormat(Qt.PlainText);layout.addWidget(title)
        self.message=QLabel('Esperando turno para iniciar…');self.message.setTextFormat(Qt.PlainText);self.message.setWordWrap(True);layout.addWidget(self.message)
        self.table=QTableWidget(len(self.STAGES),2);self.table.setHorizontalHeaderLabels(['Paso','Resultado'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        for i,text in enumerate(self.STAGES):
            self.table.setItem(i,0,QTableWidgetItem(text));self.table.setItem(i,1,QTableWidgetItem('Pendiente'));self.table.setRowHeight(i,42)
        self.table_frame=RoundedTableFrame(self.table,self)
        layout.addWidget(self.table_frame)
        self.bar=QProgressBar();self.bar.setRange(0,len(self.STAGES));self.bar.setValue(0);layout.addWidget(self.bar)
        self.print_status=QLabel('El parte se solicitará únicamente tras verificar la operación.');self.print_status.setWordWrap(True);layout.addWidget(self.print_status)
        buttons = QHBoxLayout()
        self.stop_button = QPushButton('Abortar')
        self.stop_button.setToolTip('Detiene el proceso después del paso actual.')
        self.stop_button.clicked.connect(self.stop)
        self.review_button = QPushButton('Atrás')
        self.review_button.clicked.connect(owner.show_reviewed_data)
        self.print_button = QPushButton('Imprimir parte')
        self.print_button.clicked.connect(lambda: owner.retry_print.click())
        self.close_button = QPushButton('Cerrar')
        self.close_button.clicked.connect(self.close)
        self.retry_button = QPushButton('Revisar y reintentar')
        self.retry_button.setToolTip('Comprueba qué quedó guardado y recupera los pasos pendientes.')
        self.retry_button.clicked.connect(owner.continue_repair)
        buttons.addWidget(self.review_button)
        buttons.addStretch()
        for button in (self.stop_button, self.retry_button, self.print_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.reset()

    def reset(self):
        self.current = -1
        self.succeeded = False
        self.has_failed = False
        self.failure_step = None
        for row in range(len(self.STAGES)):
            self.table.item(row,1).setText('Pendiente');self.table.item(row,1).setIcon(QIcon())
        self.bar.setValue(0)
        self.set_busy(can_abort=True)
        self.print_status.setText('El parte se solicitará únicamente tras verificar la operación.')
        self.message.setText('Esperando turno para iniciar…')

    @staticmethod
    def show_action(button, available):
        button.setEnabled(available)
        button.setVisible(available)

    def set_busy(self, *, can_abort):
        for button in (self.review_button, self.retry_button, self.print_button, self.close_button):
            self.show_action(button, False)
        self.show_action(self.stop_button, can_abort)
        self.set_primary(self.stop_button if can_abort else None)

    def set_primary(self, primary):
        for button in (self.review_button, self.stop_button, self.retry_button, self.print_button, self.close_button):
            button.setObjectName('primary' if button is primary else '')
            button.setAutoDefault(False)
            button.setDefault(button is primary)
            button.style().unpolish(button)
            button.style().polish(button)

    def refresh_recovery_actions(self):
        self.show_action(self.retry_button, False)
        self.set_primary(self.close_button)
        if self.owner.is_running():
            return
        try:
            record = RecoveryStore().get(self.owner.item.ot)
        except Exception:
            logging.exception('No se pudo consultar la recuperación de la reparación')
            return
        pending_save = self.succeeded and bool(record)
        pending_recovery = self.has_failed and (not self.owner._verified or bool(record))
        self.show_action(self.retry_button, pending_save or pending_recovery)
        self.set_primary(self.retry_button if self.retry_button.isEnabled() else self.close_button)

    def completed_row(self,index):
        cell=self.table.item(index,1);cell.setText('Completado');cell.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))

    def set_stage(self,index,text):
        if index<self.current:return
        if 'reverific' in text.lower():
            if self.failure_step is None and self.current >= 0:
                self.failure_step = self.current
            for row in range(index):
                cell=self.table.item(row,1)
                if cell.text()=='En curso':
                    cell.setText('Pendiente de verificar');cell.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
        else:
            for prior in range(index):self.completed_row(prior)
        self.current=index;self.table.item(index,1).setText('En curso')
        self.message.setText(text);self.bar.setValue(index)
        self.show_action(self.stop_button, index < 4)

    def stop(self):
        self.owner.request_stop()
        self.show_action(self.stop_button, False)
        self.message.setText('Se detendrá al terminar el paso actual.')

    def success(self,result):
        self.succeeded=True;self.has_failed=False
        for row in range(len(self.STAGES)):self.completed_row(row)
        self.bar.setValue(len(self.STAGES));self.message.setText('Operación verificada en Maximo: '+result['status']+'.')
        self.show_action(self.stop_button, False)
        self.print_status.setText('Preparación del parte solicitada a Edge.' if result.get('print_report') else 'Puedes preparar el parte cuando quieras, sin repetir la operación.')

    def failure(self,message):
        self.has_failed=True
        self.message.setText('Proceso detenido: '+message)
        if self.current>=0:
            cell=self.table.item(self.current,1);cell.setText('Revisar resultado');cell.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
        self.show_action(self.stop_button, False)
        self.print_status.setText('Revisa el resultado para recuperar los pasos pendientes.')

    def worker_finished(self):
        self.show_action(self.stop_button, False)
        self.show_action(self.review_button, True)
        self.show_action(self.print_button, self.succeeded)
        self.show_action(self.close_button, True)
        self.refresh_recovery_actions()

    def closeEvent(self,event):
        if self.owner.is_running():event.ignore();return
        super().closeEvent(event)

    def reject(self):
        if self.owner.is_running():return
        super().reject()


class RepairWorker(QThread):
    progress=Signal(str)
    stage=Signal(int,str)
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,item,plan=None,parent=None,*,retry_record=None):
        super().__init__(parent);self.item=item;self.plan=plan;self.retry_record=retry_record;self.stop_requested=Event()
    def run(self):
        try:
            if self.plan is None:result=repair_defaults(self.item,stop=self.stop_requested,job_waiting=self.progress.emit,job_cancel_event=self.stop_requested)
            else:
                folder=LOG_DIR/'almacen-operaciones';folder.mkdir(parents=True,exist_ok=True)
                batch='repair-'+uuid4().hex
                store=RecoveryStore(folder,origin_report=batch+'-result.json')
                with (folder/(batch+'-events.jsonl')).open('a',encoding='utf-8') as stream:
                    journal=WarehouseJournal(stream,batch)
                    result=run_repair(self.plan,progress=self.progress.emit,stop=self.stop_requested,
                        job_waiting=self.progress.emit,job_cancel_event=self.stop_requested,store=store,journal=journal,stage_progress=self.stage.emit,retry_record=self.retry_record)
                action='technician_discard' if self.plan.action=='discard' else 'technician_close'
                row=WarehouseResult(self.item,status='success',step='Reparación verificada',
                    completed_steps=5,verified_status=result['status'],operation_id=result['operation_id'])
                try:
                    (folder/(batch+'-result.json')).write_text(json.dumps({'action':action,'results':[asdict(row)]},ensure_ascii=False,indent=2),encoding='utf-8')
                except OSError:logging.exception('Reparación verificada; no se pudo guardar el reporte adicional')
            self.ready.emit(result)
        except Exception as exc:
            logging.exception('OT %s: fallo de revisión/finalización de reparación MD',self.item.ot)
            self.failed.emit(str(exc))


class RepairRecheckWorker(QThread):
    progress=Signal(str)
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,record,parent=None):
        super().__init__(parent);self.record=record;self.stop_requested=Event()
    def run(self):
        try:
            from warehouse_transport import reverify_pending
            folder=LOG_DIR/'almacen-operaciones';folder.mkdir(parents=True,exist_ok=True)
            batch='repair-recheck-'+uuid4().hex
            with (folder/(batch+'-events.jsonl')).open('a',encoding='utf-8') as stream:
                journal=WarehouseJournal(stream,batch)
                assessment=None
                if repair_retry_allowed(self.record):
                    assessment=inspect_repair_recovery(self.record,store=RecoveryStore(folder),stop=self.stop_requested,
                        journal=journal,job_waiting=self.progress.emit,job_cancel_event=self.stop_requested)
                if assessment and assessment['kind']!='verify_final':
                    result=assessment
                else:
                    results=reverify_pending([self.record],recovery_store=RecoveryStore(folder),
                        stop=self.stop_requested,progress=lambda i,row:self.progress.emit(row.step+': '+row.detail),
                        journal=journal,job_waiting=self.progress.emit,job_cancel_event=self.stop_requested)
                    result=results[0]
            self.ready.emit(result)
        except Exception as exc:
            logging.exception('Error de reverificación de reparación sin reenviar')
            self.failed.emit(str(exc))


class RepairDateTimePopup(QDialog):
    def __init__(self,editor):
        super().__init__(editor,Qt.Popup)
        self.editor=editor
        self.setObjectName('repairDateTimePopup')
        layout=QVBoxLayout(self)
        title=QLabel('Elegir fecha y hora');layout.addWidget(title)
        current=editor.dateTime()
        self.calendar=QCalendarWidget();self.calendar.setGridVisible(True)
        self.calendar.setSelectedDate(current.date());layout.addWidget(self.calendar)
        form=QFormLayout();self.hour=QComboBox();self.minute=QComboBox()
        for hour in range(24):self.hour.addItem(f'{hour:02d}',hour)
        # Preserve a current minute from Ahora; the remaining choices use five-minute steps.
        for minute in sorted(set(range(0,60,5))|{current.time().minute()}):
            self.minute.addItem(f'{minute:02d}',minute)
        self.hour.setCurrentIndex(self.hour.findData(current.time().hour()))
        self.minute.setCurrentIndex(self.minute.findData(current.time().minute()))
        form.addRow('Hora',self.hour);form.addRow('Minutos',self.minute);layout.addLayout(form)
        self.selection_label=QLabel();self.selection_label.setWordWrap(True)
        self.selection_label.setObjectName('repairDateSelection');layout.addWidget(self.selection_label)
        hint=QLabel('La fecha y hora se aplican al pulsar «Aplicar fecha y hora».')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.calendar.selectionChanged.connect(self.update_selection_feedback)
        self.calendar.currentPageChanged.connect(self.update_selection_feedback)
        self.hour.currentIndexChanged.connect(self.update_selection_feedback)
        self.minute.currentIndexChanged.connect(self.update_selection_feedback)
        self.update_selection_feedback()
        buttons=QHBoxLayout();cancel=QPushButton('Cancelar');self.apply_button=QPushButton('Aplicar fecha y hora',objectName='primary')
        cancel.clicked.connect(self.reject);self.apply_button.clicked.connect(self.apply)
        buttons.addStretch();buttons.addWidget(cancel);buttons.addWidget(self.apply_button);layout.addLayout(buttons)

    def update_selection_feedback(self,*args):
        selected=self.calendar.selectedDate()
        time=QTime(self.hour.currentData(),self.minute.currentData())
        selected_text=self.calendar.locale().toString(selected,'dddd d MMMM yyyy')
        text=f"Seleccionado: {selected_text} · {time.toString('HH:mm')}"
        if (selected.year(),selected.month()) != (self.calendar.yearShown(),self.calendar.monthShown()):
            shown=selected.__class__(self.calendar.yearShown(),self.calendar.monthShown(),1)
            text+=f"\nElige un día de {self.calendar.locale().toString(shown,'MMMM yyyy')} para cambiar la fecha."
        self.selection_label.setText(text)

    def apply(self):
        value=self.editor.dateTime()
        value.setDate(self.calendar.selectedDate())
        value.setTime(QTime(self.hour.currentData(),self.minute.currentData(),0))
        self.editor.setDateTime(value)
        self.accept()


class RepairTimeEdit(QDateTimeEdit):
    def show_date_time_popup(self):
        previous=getattr(self,'_date_time_popup',None)
        if previous is not None:
            if previous.isVisible():previous.raise_();return
            previous.deleteLater()
        popup=RepairDateTimePopup(self);self._date_time_popup=popup
        popup.adjustSize()
        bounds=self.screen().availableGeometry()
        point=self.mapToGlobal(QPoint(0,self.height()))
        x=max(bounds.left(),min(point.x(),bounds.right()-popup.width()+1))
        y=point.y()
        if y+popup.height()>bounds.bottom()+1:
            y=self.mapToGlobal(QPoint(0,0)).y()-popup.height()
        popup.move(x,max(bounds.top(),y));popup.show()
        popup.hour.setFocus()

    def mousePressEvent(self,event):
        if (event.button()==Qt.LeftButton and self.calendarPopup() and not self.isReadOnly()
                and event.position().x()>=self.width()-36):
            event.accept();self.show_date_time_popup();return
        super().mousePressEvent(event)

    def keyPressEvent(self,event):
        if (event.key()==Qt.Key_F4 or
                (event.key()==Qt.Key_Down and event.modifiers()&Qt.AltModifier)):
            if self.calendarPopup() and not self.isReadOnly():
                event.accept();self.show_date_time_popup();return
        super().keyPressEvent(event)

    def stepBy(self,steps):
        if self.currentSection()==QDateTimeEdit.MinuteSection:
            value=self.dateTime().addSecs(steps*5*60)
            value=value.addSecs(-(value.time().minute()%5)*60)
            self.setDateTime(value)
        else:super().stepBy(steps)


class RepairDialog(QDialog):
    print_requested=Signal(str)
    repair_verified=Signal(object)
    def __init__(self,item,selection,parent=None,*,autoload=True,default_action='discard'):
        if default_action not in ('close','discard'):raise ValueError('Acción de reparación no válida.')
        super().__init__(parent);self.item=item;self._worker=None;self._reviewed=False;self._verified=None;self.progress_dialog=None;self._retry_record=None
        self._preview_closed=False
        self._resume_assessment=None
        self._preview_state = None
        self._preview_edited=set();self._applying_preview=False
        self.setWindowTitle('Finalizar reparación · OT '+item.ot)
        self.setObjectName('repairReview')
        root=QVBoxLayout(self);scroll=QScrollArea();self.review_scroll=scroll;scroll.setWidgetResizable(True)
        panel=QWidget();panel.setObjectName("repairReviewPanel");self.review_panel=panel;body=QVBoxLayout(panel);body.setAlignment(Qt.AlignTop);scroll.setWidget(panel);root.addWidget(scroll)
        body.addWidget(QLabel('<h2>Finalizar reparación · OT '+item.ot+'</h2>'))
        cached_fault=get_fault_description(item.ot)
        self.fault=QLabel('Avería: '+(cached_fault or 'se consultará si no está en MD'));self.fault.setWordWrap(True);body.addWidget(self.fault)
        form=QFormLayout();self.review_form=form;body.addLayout(form)
        self.action=QComboBox();self.action.addItem('Declarar irreparable — Desechar equipo','discard');self.action.addItem('Cerrar OT — reparación finalizada','close')
        self.action.setCurrentIndex(self.action.findData(default_action))
        form.addRow('Acción final',self.action)
        self.reference = QLineEdit()
        self.reference.setMaxLength(WORKLOG_SUMMARY_MAX_LENGTH)
        required = incident_required(item.client)
        self.reference.setPlaceholderText('Número o sin incidencia' if required else 'Opcional')
        form.addRow('Incidencia' if required else 'Incidencia (opcional)', self.reference)
        self.duration=QLineEdit();self.duration.setPlaceholderText('Horas en tramos de 0,25; ejemplo: 1');form.addRow('Tiempo de reparación (h)',self.duration)
        timing=QHBoxLayout();self.time_mode=QComboBox();self.time_mode.addItem('Finalización','end');self.time_mode.addItem('Inicio','start')
        self.time=RepairTimeEdit(QDateTime.currentDateTime());self.time.setDisplayFormat('dd/MM/yyyy HH:mm');self.time.setCalendarPopup(True)
        self.now=QPushButton('Ahora');self.now.setMaximumWidth(90);self.time_mode.setMaximumWidth(180);self.now.clicked.connect(self.set_now)
        timing.addWidget(self.time_mode);timing.addWidget(self.time);timing.addWidget(self.now);form.addRow('Fecha y hora',timing)
        self.dates=QLabel();self.dates.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed);form.addRow('Fechas calculadas',self.dates)
        self.justification=QPlainTextEdit();self.justification.setPlaceholderText('Motivo de irreparable que se registrará en Maximo');self.justification.setMaximumHeight(76);form.addRow('Motivo por el que se desecha',self.justification)
        self.justification.setPlainText(cached_fault)
        self._justification_edited=False
        self.justification.textChanged.connect(lambda:setattr(self,'_justification_edited',True))
        body.addWidget(QLabel('Registro de reparaciones, pruebas y procesos (una entrada por fila)'))
        self.entries=QTableWidget(0,2);self.entries.setHorizontalHeaderLabels(['Resumen (máx. 100)','Detalles']);self.entries.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.entries.setItemDelegateForColumn(0,WorklogSummaryDelegate(self.entries))
        self.entries.horizontalHeaderItem(0).setToolTip('Maximo admite 100 caracteres. Usa Detalles para el texto extenso.')
        self.entries_frame=RoundedTableFrame(self.entries)
        self.entries_frame.setMinimumHeight(150);self.entries_frame.setMaximumHeight(180);body.addWidget(self.entries_frame)
        rowbuttons=QHBoxLayout();add=QPushButton('Añadir entrada');remove=QPushButton('Quitar entrada');add.clicked.connect(lambda:self.add_entry());remove.clicked.connect(lambda:self.entries.removeRow(self.entries.currentRow()));rowbuttons.addWidget(add);rowbuttons.addWidget(remove);rowbuttons.addStretch();body.addLayout(rowbuttons)
        body.addWidget(QLabel('Anomalías y soluciones que se aplicarán'))
        self.picker=FailurePathPicker();self.picker.set_selection(selection);body.addWidget(self.picker)
        self.print_check=QCheckBox('Imprimir parte una vez verificado');self.print_check.setChecked(True);body.addWidget(self.print_check)
        self.confirm=QCheckBox('He revisado la OT y confirmo la acción irreversible seleccionada.');body.addWidget(self.confirm)
        self.preview_banner = QFrame(objectName='repairPreviewBanner')
        banner_row = QHBoxLayout(self.preview_banner)
        banner_row.setContentsMargins(14, 10, 14, 10)
        self.preview_indicator = RefreshIndicator(PROGRAM_DIR / 'ui_assets' / 'refresh-white.svg', self.preview_banner)
        banner_row.addWidget(self.preview_indicator)
        banner_text = QVBoxLayout()
        banner_text.setSpacing(2)
        banner_text.addWidget(QLabel('Consultando Maximo', objectName='repairPreviewTitle'))
        hint = QLabel('Comprobando el estado y el Registro de la OT. Puedes ir rellenando los datos.')
        hint.setWordWrap(True)
        banner_text.addWidget(hint)
        banner_row.addLayout(banner_text, 1)
        root.addWidget(self.preview_banner)
        self.preview_banner.hide()

        self.status = QLabel(objectName='repairReviewStatus')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons=QHBoxLayout();self.retry_print=QPushButton('Volver a preparar el parte');self.retry_print.setEnabled(False);self.retry_print.clicked.connect(lambda:self.print_requested.emit(self.item.ot));self.cancel=QPushButton('Cerrar');self.cancel.clicked.connect(self.close);self.submit=QPushButton('Revisar y ejecutar…');self.submit.setEnabled(False);self.submit.clicked.connect(self.execute);self.retry_print.hide();buttons.addStretch();buttons.addWidget(self.cancel);buttons.addWidget(self.submit);root.addLayout(buttons)
        self.duration.textChanged.connect(self.update_dates);self.time.dateTimeChanged.connect(self.update_dates);self.time_mode.currentIndexChanged.connect(self.update_dates)
        self.reference.textChanged.connect(lambda:self.mark_preview_edit('reference'))
        self.duration.textChanged.connect(lambda:self.mark_preview_edit('duration'))
        self.entries.itemChanged.connect(lambda *_:self.mark_preview_edit('entries'))
        self.entries.model().rowsInserted.connect(lambda *_:self.mark_preview_edit('entries'))
        self.entries.model().rowsRemoved.connect(lambda *_:self.mark_preview_edit('entries'))
        self.action.currentIndexChanged.connect(lambda:self.confirm.setChecked(False));self.action.currentIndexChanged.connect(lambda:self.update_dates())
        self.action.currentIndexChanged.connect(self.update_action_fields)
        self.update_action_fields()
        self.fit_initial_size()
        self.set_now()
        if autoload:self.launch()

    def fit_initial_size(self, available=None):
        """Use the available monitor height; keep scrolling as a small-screen fallback."""
        if available is None:
            screen=self.parent().screen() if self.parent() else self.screen()
            available=screen.availableGeometry()
        self.resize(min(1050,available.width()-48),min(1000,available.height()-48))

    def update_action_fields(self,*args):
        self.review_form.setRowVisible(self.justification,self.action.currentData()=='discard')

    def mark_preview_edit(self,field):
        if not self._applying_preview:self._preview_edited.add(field)

    def add_entry(self,summary='',details=''):
        row=self.entries.rowCount();self.entries.insertRow(row)
        self.entries.setItem(row,0,QTableWidgetItem(summary))
        editor=QPlainTextEdit();editor.setPlainText(details);editor.setPlaceholderText('Detalles de la reparación o prueba')
        editor.textChanged.connect(lambda:self.mark_preview_edit('entries'))
        self.entries.setCellWidget(row,1,editor);self.entries.setRowHeight(row,72)

    def set_now(self):
        self.time_mode.setCurrentIndex(0)
        self.time.setDateTime(QDateTime.currentDateTime())
        self.update_dates()

    def values(self):
        return {'reference':self.reference.text(),'duration':self.duration.text(),'action':self.action.currentData(),
            'time_mode':self.time_mode.currentData(),'time':self.time.dateTime().toString('yyyy-MM-ddTHH:mm:00'),
            'justification':self.justification.toPlainText() if self.action.currentData()=='discard' else '',
            'print_report':self.print_check.isChecked(),
            'entries':[{'summary':self.entries.item(row,0).text() if self.entries.item(row,0) else '',
                        'details':self.entries.cellWidget(row,1).toPlainText() if self.entries.cellWidget(row,1) else ''} for row in range(self.entries.rowCount())]}

    def update_dates(self,*args):
        try:
            plan=reviewed_repair(self.item,{**self.values(),'reference':self.reference.text() or '(pendiente)',
                'justification':self.justification.toPlainText() or '(pendiente)'},self.picker.selection())
            self.dates.setText(plan.start.replace('T',' ')+' → '+plan.end.replace('T',' '))
        except (ValueError,OverflowError):self.dates.setText('Introduce una duración y unas fechas válidas.')

    def is_running(self):return self._worker is not None and self._worker.isRunning()

    def launch(self,plan=None):
        if self._preview_closed:return
        if self.is_running():return
        self._worker=RepairWorker(self.item,plan,self,retry_record=self._retry_record)
        self._worker.progress.connect(self.progress_message)
        self._worker.ready.connect(self.preview_ready if plan is None else self.finished_repair)
        self._worker.failed.connect(self.failed)
        if plan is None:
            self._reviewed = False
            self.submit.setEnabled(False)
            self._mark_preview_blocked(False)
            self.status.hide()
            self.preview_banner.setToolTip('')
            self.preview_banner.show()
            self.preview_indicator.set_running(True)
            self._worker.finished.connect(self._stop_preview_indicator)
        else:
            self._resume_assessment=None
            if self.progress_dialog is None:self.progress_dialog=RepairProgressDialog(self)
            else:self.progress_dialog.reset()
            self._worker.stage.connect(self.progress_dialog.set_stage)
            self._show_failure_prompt = False
            self.progress_dialog.show();self.hide()
        lock=getattr(self.parent(),'update_lock',None)
        if lock is not None:lock.acquire(False);self._worker.finished.connect(lock.release)
        if plan is not None:
            self._worker.finished.connect(self._repair_worker_finished)
        self._worker.start()

    def open_saved_recovery(self, record):
        """Restore the reviewed form while routing all retries through the saved attempt."""
        self._retry_record = record
        try:
            plan = repair_plan_from_record(record)
        except (KeyError, TypeError, ValueError, RuntimeError):
            if repair_retry_allowed(record):
                logging.exception('No se pudo reconstruir la reparación pendiente de la OT %s', self.item.ot)
        else:
            self.reference.setText(plan.reference)
            self.duration.setText(plan.duration)
            self.time_mode.setCurrentIndex(self.time_mode.findData('start'))
            self.time.setDateTime(QDateTime.fromString(plan.start, Qt.ISODate))
            self.justification.setPlainText(plan.justification)
            self.print_check.setChecked(plan.print_report)
            self.picker.set_selection(plan.selection)
            for entry in plan.entries:
                self.add_entry(entry.summary, entry.details)
            self._reviewed = True
        self.review_panel.setEnabled(False)
        self.status.setText('Datos del intento guardado.')
        self.progress_dialog = RepairProgressDialog(self)
        self.progress_dialog.failure(record.get('last_error') or 'Resultado pendiente de revisar.')
        self.progress_dialog.worker_finished()
        self.progress_dialog.show()
        self.continue_repair()

    def recheck_repair(self):
        if self.is_running():return
        try:
            record=RecoveryStore().get(self.item.ot)
            if not record:raise RuntimeError('No hay una operación pendiente para esta OT.')
            if record['action'] not in ('technician_close','technician_discard'):
                raise RuntimeError('La operación pendiente pertenece a otro proceso.')
            self._resume_assessment=None
            self._worker=RepairRecheckWorker(record,self)
            self._worker.progress.connect(self.progress_message)
            self._worker.ready.connect(self.recheck_ready)
            self._worker.failed.connect(self.failed)
            self.progress_dialog.set_busy(can_abort=True)
            checking = ('Guardando el resultado en MD…' if record.get('verified_status')
                        else 'Comprobando estado y resultado en Maximo…')
            self.progress_dialog.message.setText(checking)
            lock = getattr(self.parent(), 'update_lock', None)
            if lock is not None:
                lock.acquire(False)
                self._worker.finished.connect(lock.release)
            self._worker.finished.connect(self._recheck_worker_finished)
            self._worker.start()
        except Exception as exc:
            self.failed(str(exc))
            if self.progress_dialog:self.progress_dialog.refresh_recovery_actions()

    def recheck_ready(self,row):
        if isinstance(row,dict):
            self._preview_state = row.get('state')
            self._resume_assessment=row
            self.progress_dialog.has_failed=True
            self.progress_dialog.message.setText(row['detail'])
            self.status.setText(row['detail'])
            if row.get('state')=='INPRG':
                self.progress_dialog.completed_row(0);self.progress_dialog.completed_row(2)
                self.progress_dialog.table.item(5,1).setText('Pendiente')
                self.progress_dialog.table.item(5,1).setIcon(QIcon())
                self.progress_dialog.bar.setValue(3)
            self.progress_dialog.print_status.setText('')
            return
        if row.status=='success':
            self.finished_repair({'ot':self.item.ot,'status':row.verified_status,
                                 'operation_id':row.operation_id,'print_report':False})
        else:self.failed(row.detail or 'El resultado continúa pendiente de verificar. No se ha repetido la acción.')

    def _repair_worker_finished(self):
        self.progress_dialog.worker_finished()
        if not self._show_failure_prompt:
            return
        self._show_failure_prompt = False
        progress = self.progress_dialog
        stage = progress.failure_step if progress.failure_step is not None else progress.current
        step = progress.STAGES[stage] if stage >= 0 else progress.STAGES[0]
        prompt = QMessageBox(progress)
        prompt.setIcon(QMessageBox.Warning)
        prompt.setWindowTitle('Reparación interrumpida')
        prompt.setTextFormat(Qt.PlainText)
        prompt.setText(f'Paso pendiente: {step}')
        prompt.setInformativeText(progress.message.text())
        retry = None
        if progress.retry_button.isEnabled():
            retry = prompt.addButton('Revisar y reintentar', QMessageBox.ActionRole)
        back = prompt.addButton('Atrás', QMessageBox.ActionRole)
        dismiss = prompt.addButton('Cerrar aviso', QMessageBox.RejectRole)
        prompt.setDefaultButton(dismiss)
        prompt.exec()
        if retry is not None and prompt.clickedButton() is retry:
            self.continue_repair()
        elif prompt.clickedButton() is back:
            self.show_reviewed_data()

    def _recheck_worker_finished(self):
        self.progress_dialog.worker_finished()
        assessment = self._resume_assessment
        self._resume_assessment = None
        if (assessment and assessment['kind'] == 'resume'
                and not self._worker.stop_requested.is_set()):
            self._confirm_resume(assessment)

    def show_reviewed_data(self):
        if self.is_running():
            return
        try:
            record = RecoveryStore().get(self.item.ot)
        except Exception:
            logging.exception('No se pudo leer el intento de reparación')
            record = None
            can_edit = False
        else:
            can_edit = not self._verified and (record is None or repair_retry_allowed(record))
        if can_edit and self.progress_dialog and self.progress_dialog.has_failed:
            self.review_retry()
            return
        self.review_panel.setEnabled(False)
        self.submit.setEnabled(False)
        if self.progress_dialog:
            self.progress_dialog.hide()
        self.show()
        self.raise_()

    def continue_repair(self):
        if self.is_running():
            return
        try:
            record = RecoveryStore().get(self.item.ot)
            if record is None:
                self.review_retry()
            else:
                self.recheck_repair()
        except Exception as exc:
            QMessageBox.warning(self.progress_dialog, 'No se puede revisar el intento', str(exc))

    def _confirm_resume(self, assessment):
        try:
            record = RecoveryStore().get(self.item.ot)
            if (not repair_retry_allowed(record) or
                    assessment['operation_id'] != record['operation_id']):
                raise RuntimeError('La operación pendiente cambió. Vuelve a revisar el resultado.')
            plan=repair_plan_from_record(record)
            label='Desechar equipo' if plan.action=='discard' else 'Cerrar OT'
            prompt=(f"OT {plan.item.ot} · {plan.item.serial}\nEstado comprobado: {assessment['state']}\n"
                    f"{assessment['detail']}\n\nAcción pendiente: {label}\nIncidencia: {plan.incident_summary or '—'}"
                    f"\nTiempo: {plan.duration} h\nInicio: {plan.start}\nFin: {plan.end}"
                    f"\nTrabajos: {', '.join(entry.summary for entry in plan.entries)}"
                    + (f"\nMotivo: {plan.justification}" if plan.action=='discard' else '')
                    + "\n\nSe comprobarán de nuevo el estado, la identidad y los registros existentes. ¿Continuar?")
            if QMessageBox.question(self.progress_dialog,'Continuar reparación pendiente',prompt,
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            self._retry_record={**record,'resume_state':assessment['state']}
            self.submit.setEnabled(False);self.review_panel.setEnabled(False)
            self.launch(plan)
        except Exception as exc:
            self._resume_assessment=None
            QMessageBox.warning(self.progress_dialog,'No se puede continuar',str(exc))
            self.progress_dialog.refresh_recovery_actions()

    def review_retry(self):
        if self.is_running() or self._verified:return
        try:
            record=RecoveryStore().get(self.item.ot)
            if record and not repair_retry_allowed(record):
                raise RuntimeError('La acción final ya pudo enviarse. Usa Revisar y reintentar para comprobar el resultado.')
            self._retry_record=record
            self._resume_assessment=None
            self.review_panel.setEnabled(True);self.confirm.setChecked(False)
            # A recovery cannot silently change the action whose evidence is on disk.
            if record:
                self.action.setCurrentIndex(self.action.findData('discard' if record['action']=='technician_discard' else 'close'))
                self.action.setEnabled(False)
            self.submit.setEnabled(self._reviewed)
            self.status.setText('Revisa tus datos y vuelve a confirmar. Se comprobará el estado actual y no se duplicarán registros existentes.')
            if self.progress_dialog:self.progress_dialog.hide()
            self.show();self.raise_()
        except Exception as exc:
            QMessageBox.warning(self,'Reintento bloqueado',str(exc))

    def progress_message(self,text):
        if self._preview_closed:
            return
        if self.preview_indicator.animation.running:
            self.preview_banner.setToolTip(text)
            return
        self.status.setText(text)
        if self.progress_dialog:self.progress_dialog.message.setText(text)

    def _stop_preview_indicator(self):
        self.preview_indicator.set_running(False)
        self.preview_banner.hide()
        self.status.show()

    def _mark_preview_blocked(self, blocked):
        if bool(self.status.property('blocked')) == blocked:
            return
        self.status.setProperty('blocked', blocked)
        style = self.status.style()
        style.unpolish(self.status)
        style.polish(self.status)
        self.status.updateGeometry()
        self.status.update()

    def preview_ready(self,data):
        self._stop_preview_indicator()
        if self._preview_closed:return
        self._preview_state = data['state']
        blocked = self._preview_state not in ('APPR', 'INPRG')
        self._mark_preview_blocked(blocked)
        if blocked:
            self._reviewed = False
            self.submit.setEnabled(False)
            self.status.setText(
                f'Maximo muestra la OT en {self._preview_state}. '
                'Solo se puede dar salida o desechar una OT en APPR o INPRG.'
            )
            return
        self._reviewed=True;self.submit.setEnabled(True)
        self.fault.setText('Avería: '+data['fault'])
        if data['fault'] and not self._justification_edited:
            with QSignalBlocker(self.justification):
                self.justification.setPlainText(data['fault'])
        self._applying_preview=True
        try:
            for field,widget in (('reference',self.reference),('duration',self.duration)):
                if field not in self._preview_edited:
                    with QSignalBlocker(widget):widget.setText(data[field])
            if 'entries' not in self._preview_edited:
                self.entries.setRowCount(0)
                for entry in data['entries']:self.add_entry(entry['summary'],entry['details'])
        finally:self._applying_preview=False
        self.update_dates()
        state_message = ('OT aprobada (APPR). MD la iniciará antes de finalizar.'
                         if self._preview_state == 'APPR'
                         else 'OT ya iniciada (INPRG). Revisa los datos antes de finalizar.')
        preserved = ' Se han conservado tus cambios.' if self._preview_edited else ''
        self.status.setText(state_message + preserved)

    def execute(self):
        if self.is_running() or not self._reviewed or self._verified:return
        if not self.confirm.isChecked():QMessageBox.warning(self,'Confirmación requerida','Marca que has revisado la acción irreversible.');return
        try:plan=reviewed_repair(self.item,self.values(),self.picker.selection())
        except (ValueError,OverflowError) as exc:QMessageBox.warning(self,'Revisar reparación',str(exc));return
        label='DESECHAR POR IRREPARABLE' if plan.action=='discard' else 'CERRAR OT'
        reason_line='\nMotivo por el que se desecha: '+plan.justification if plan.action=='discard' else ''
        start_note = {
            'APPR': 'La OT está aprobada. MD la iniciará antes de finalizar. ',
            'INPRG': '',
        }.get(self._preview_state, 'Si la OT está aprobada, MD la iniciará antes de finalizar. ')
        if QMessageBox.question(self,'Confirmar acción irreversible',
            f'OT {self.item.ot} · {self.item.serial}\n{label}\nIncidencia: {plan.incident_summary or "—"}\nTiempo: {plan.duration} h\nInicio: {plan.start}\nFin: {plan.end}{reason_line}\n\n{start_note}No es reversible. ¿Continuar?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.submit.setEnabled(False);self.review_panel.setEnabled(False);self.status.setText('Preparando la reparación…')
        self.launch(plan)

    def finished_repair(self,result):
        from report_stamp import record_verified_discard
        record_verified_discard(result)
        self._verified=result;self.retry_print.setEnabled(True)
        result=dict(result,local_status_saved=False)
        store=RecoveryStore()
        try:
            record=store.get(self.item.ot)
            if record and record['operation_id']!=result['operation_id']:
                raise RuntimeError('La operación pendiente cambió antes de guardar en MD.')
            saved=apply_warehouse_status(self.item.ot,'CLOSE') if result['status']=='CLOSE' else apply_closed_repair(self.item.ot)
            if not saved:raise RuntimeError('No se pudo actualizar el seguimiento local.')
            report=WarehouseResult(self.item,status='success',completed_steps=5,step='Reparación verificada',
                verified_status=result['status'],operation_id=result['operation_id'],local_status_saved=True)
            if record:store.update_report(record,report);store.complete(record)
            result['local_status_saved']=True
        except Exception:
            logging.exception('Reparación verificada; guardado local pendiente')
        self.repair_verified.emit(result)
        self.status.setText('Operación verificada en '+result['status']+'. El parte se prepara por separado; un fallo de impresión no repetirá la operación.')
        if self.progress_dialog:
            self.progress_dialog.success(result)
            if not result['local_status_saved']:
                self.progress_dialog.message.setText('Operación verificada en Maximo. Guardado en MD pendiente; usa Revisar y reintentar para guardar el resultado.')
        if result.get('print_report'):self.print_requested.emit(self.item.ot)

    def failed(self,message):
        self._stop_preview_indicator()
        if self._preview_closed:return
        self.submit.setEnabled(False)
        if getattr(self._worker, 'plan', False) is None:
            self.status.setText('No se pudo consultar Maximo. ' + message)
            return
        self.status.setText('Proceso detenido: '+message+'. Revisa el registro de operaciones pendientes antes de repetir.')
        if self.progress_dialog:
            self.progress_dialog.failure(message)
            if getattr(self._worker, 'plan', None) is not None and not self._worker.stop_requested.is_set():
                self._show_failure_prompt = True

    def request_stop(self):
        if self._worker is not None:self._worker.stop_requested.set()
        message='Se terminará el paso actual antes de detenerse. No se repetirá ninguna confirmación.'
        self.status.setText(message)
        if self.progress_dialog:
            self.progress_dialog.message.setText(message);self.progress_dialog.stop_button.setEnabled(False)
            self.progress_dialog.show();self.progress_dialog.raise_()

    def closeEvent(self,event):
        if getattr(self._worker,'plan',False) is None and cancel_readonly_preview(self,self._worker):
            self._stop_preview_indicator()
            event.accept();return
        if self.is_running():
            self.request_stop();event.ignore();return
        self._preview_closed=True
        super().closeEvent(event)

    def reject(self):
        if getattr(self._worker,'plan',False) is None and cancel_readonly_preview(self,self._worker):
            self._stop_preview_indicator()
            return
        if self.is_running():self.request_stop();return
        self._preview_closed=True
        super().reject()
