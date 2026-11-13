"""Native MD review for repair completion and irreparable assets."""
from threading import Event
from datetime import datetime
from PySide6.QtCore import QThread,Signal,QDateTime,QTime,QPoint,Qt,QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QTableWidget,QTableWidgetItem,QPushButton,QComboBox,QDateTimeEdit,QPlainTextEdit,
    QCheckBox,QMessageBox,QScrollArea,QWidget,QHeaderView,QApplication,QProgressBar,QAbstractItemView,QStyle,QCalendarWidget)
from failure_picker import FailurePathPicker
from technician_repair import reviewed_repair,run_repair,RepairPreparer
from warehouse_transport import WarehouseSession
from warehouse_recovery import RecoveryStore
from warehouse import WarehouseResult
from db import get_fault_description,apply_closed_repair,apply_warehouse_status
from dataclasses import asdict
import json,logging,sys
from uuid import uuid4
from warehouse_diagnostics import WarehouseJournal
from app_paths import LOG_DIR,PROGRAM_DIR
from task_priorities import scheduled,HIGH


@scheduled('Consultar reparación para revisión',HIGH)
def repair_defaults(item):
    session=WarehouseSession()
    try:
        state=session.open(item.ot)
        if state not in ('APPR','INPRG'):raise RuntimeError('Solo se puede finalizar una OT APPR o INPRG.')
        identity=session.identity()
        if item.serial and identity.get('Nº de serie')!=item.serial:raise RuntimeError('El número de serie no coincide.')
        r=RepairPreparer(session.driver,item.ot,state);session.reader=r
        fault=get_fault_description(item.ot) or r.value('Resumen') or ''
        r.tab('Consumos Actuales');duration=r.value('Horas totales de reparación') or ''
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
            if summary.lower().startswith('inc:') and not reference:reference=summary;continue
            entry=RepairEntry(summary)
            if not r.open_entry(entry):raise RuntimeError('El registro cambió durante la consulta.')
            notes.append({'summary':summary,'details':r.details()})
        return {'state':state,'identity':identity,'fault':fault,'duration':duration,'reference':reference,'entries':notes}
    finally:session.close()


def repair_style(colors):
    muted=colors.get('muted','#627d98');accent=colors.get('accent','#1976d2')
    track=colors.get('control','#e8eef5');hover=colors.get('hover','#d9e2ec')
    dark=colors.get('canvas','').lower()=='#121a26'
    arrow=(PROGRAM_DIR/'ui_assets'/('chevron-down-light.svg' if dark else 'chevron-down-dark.svg')).as_posix()
    return (f"QDialog, QWidget#repairReviewPanel {{background:{colors['canvas']};}} "
        f"QPlainTextEdit, QDateTimeEdit {{background:{colors['surface']};color:{colors['text']};border:1px solid {colors['border']};border-radius:6px;padding:6px;}} "
        f"QComboBox::drop-down,QDateTimeEdit::drop-down {{subcontrol-origin:padding;subcontrol-position:top right;width:32px;border-left:1px solid {muted};background:{track};border-top-right-radius:6px;border-bottom-right-radius:6px;}} "
        f"QComboBox::drop-down:hover,QDateTimeEdit::drop-down:hover {{background:{hover};}} "
        f'QComboBox::down-arrow,QDateTimeEdit::down-arrow {{image:url("{arrow}");width:14px;height:14px;}} '
        f"QComboBox QAbstractItemView {{background:{colors['surface']};color:{colors['text']};border:2px solid {muted};selection-background-color:{accent};selection-color:white;}} "
        "QComboBox QAbstractItemView::item {min-height:28px;padding:5px;} "
        f"QScrollBar:vertical {{background:{track};width:14px;margin:2px;border-radius:6px;}} "
        f"QScrollBar::handle:vertical {{background:{muted};min-height:32px;border-radius:5px;}} "
        f"QScrollBar::handle:vertical:hover {{background:{accent};}} "
        f"QScrollBar:horizontal {{background:{track};height:14px;margin:2px;border-radius:6px;}} "
        f"QScrollBar::handle:horizontal {{background:{muted};min-width:32px;border-radius:5px;}} "
        f"QScrollBar::handle:horizontal:hover {{background:{accent};}} "
        "QScrollBar::add-line,QScrollBar::sub-line {width:0;height:0;} "
        "QScrollBar::add-page,QScrollBar::sub-page {background:transparent;}")


class RepairProgressDialog(QDialog):
    STAGES=('Comprobar OT y estado','Preparar anomalías y Registro','Comprobar / iniciar OT',
            'Validar duración y fechas','Confirmar acción y justificación','Verificar resultado en Maximo')
    def __init__(self,owner):
        super().__init__(owner.parent());self.owner=owner;self.current=-1;self.succeeded=False
        self.setWindowTitle('Progreso de reparación · OT '+owner.item.ot)
        self.setStyleSheet(owner.styleSheet());self.resize(760,510)
        layout=QVBoxLayout(self)
        title=QLabel('Reparación · OT '+owner.item.ot);title.setTextFormat(Qt.PlainText);layout.addWidget(title)
        self.message=QLabel('Esperando turno para iniciar…');self.message.setTextFormat(Qt.PlainText);self.message.setWordWrap(True);layout.addWidget(self.message)
        self.table=QTableWidget(len(self.STAGES),2);self.table.setHorizontalHeaderLabels(['Paso','Resultado'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False);self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        for i,text in enumerate(self.STAGES):
            self.table.setItem(i,0,QTableWidgetItem(text));self.table.setItem(i,1,QTableWidgetItem('Pendiente'));self.table.setRowHeight(i,42)
        layout.addWidget(self.table)
        self.bar=QProgressBar();self.bar.setRange(0,len(self.STAGES));self.bar.setValue(0);layout.addWidget(self.bar)
        self.print_status=QLabel('El parte se solicitará únicamente tras verificar la operación.');self.print_status.setWordWrap(True);layout.addWidget(self.print_status)
        buttons=QHBoxLayout();self.stop_button=QPushButton('Detener antes de confirmar');self.stop_button.clicked.connect(self.stop)
        self.review_button=QPushButton('Ver datos revisados');self.review_button.clicked.connect(owner.show)
        self.print_button=QPushButton('Preparar impresión del parte');self.print_button.setEnabled(False);self.print_button.clicked.connect(lambda:owner.retry_print.click())
        self.close_button=QPushButton('Cerrar');self.close_button.setEnabled(False);self.close_button.clicked.connect(self.close)
        for button in (self.stop_button,self.review_button,self.print_button,self.close_button):buttons.addWidget(button)
        layout.addLayout(buttons)

    def completed_row(self,index):
        cell=self.table.item(index,1);cell.setText('Completado');cell.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))

    def set_stage(self,index,text):
        if index<self.current:return
        for prior in range(index):self.completed_row(prior)
        self.current=index;self.table.item(index,1).setText('En curso')
        self.message.setText(text);self.bar.setValue(index)
        self.stop_button.setEnabled(index<4)

    def stop(self):
        self.owner.request_stop()
        self.stop_button.setEnabled(False);self.message.setText('Se terminará el paso actual. No se interrumpirá una confirmación ya enviada.')

    def success(self,result):
        self.succeeded=True
        for row in range(len(self.STAGES)):self.completed_row(row)
        self.bar.setValue(len(self.STAGES));self.message.setText('Operación verificada en Maximo: '+result['status']+'.')
        self.stop_button.setEnabled(False);self.print_button.setEnabled(True)
        self.print_status.setText('Preparación del parte solicitada a Edge.' if result.get('print_report') else 'Puedes preparar el parte cuando quieras, sin repetir la operación.')

    def failure(self,message):
        self.message.setText('Proceso detenido: '+message)
        if self.current>=0:
            cell=self.table.item(self.current,1);cell.setText('Revisar resultado');cell.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
        self.stop_button.setEnabled(False)
        self.print_status.setText('No repitas el cierre o desecho. Revisa primero el resultado pendiente en MD.')

    def worker_finished(self):self.close_button.setEnabled(True);self.stop_button.setEnabled(False)

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
    def __init__(self,item,plan=None,parent=None):
        super().__init__(parent);self.item=item;self.plan=plan;self.stop_requested=Event()
    def run(self):
        try:
            if self.plan is None:result=repair_defaults(self.item,job_waiting=self.progress.emit,job_cancel_event=self.stop_requested)
            else:
                folder=LOG_DIR/'almacen-operaciones';folder.mkdir(parents=True,exist_ok=True)
                batch='repair-'+uuid4().hex
                store=RecoveryStore(folder,origin_report=batch+'-result.json')
                with (folder/(batch+'-events.jsonl')).open('a',encoding='utf-8') as stream:
                    journal=WarehouseJournal(stream,batch)
                    result=run_repair(self.plan,progress=self.progress.emit,stop=self.stop_requested,
                        job_waiting=self.progress.emit,job_cancel_event=self.stop_requested,store=store,journal=journal,stage_progress=self.stage.emit)
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


class RepairDateTimePopup(QDialog):
    def __init__(self,editor):
        super().__init__(editor,Qt.Popup)
        self.editor=editor
        self.setObjectName('repairDateTimePopup')
        self.setStyleSheet(editor.window().styleSheet())
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
        buttons=QHBoxLayout();cancel=QPushButton('Cancelar');self.apply_button=QPushButton('Aceptar',objectName='primary')
        cancel.clicked.connect(self.reject);self.apply_button.clicked.connect(self.apply)
        buttons.addStretch();buttons.addWidget(cancel);buttons.addWidget(self.apply_button);layout.addLayout(buttons)

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
        super().__init__(parent);self.item=item;self._worker=None;self._reviewed=False;self._verified=None;self.progress_dialog=None
        self._preview_edited=set();self._applying_preview=False
        self.setWindowTitle('Finalizar reparación · OT '+item.ot)
        self.setObjectName('repairReview')
        colors=getattr(sys.modules.get('ui_qt'),'ACTIVE_COLORS',
            {'canvas':'#f5f7fb','surface':'#ffffff','text':'#172033','border':'#d9e2ec'})
        self.setStyleSheet(repair_style(colors))
        root=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True)
        panel=QWidget();panel.setObjectName("repairReviewPanel");self.review_panel=panel;body=QVBoxLayout(panel);scroll.setWidget(panel);root.addWidget(scroll)
        body.addWidget(QLabel('<h2>Finalizar reparación · OT '+item.ot+'</h2>'))
        cached_fault=get_fault_description(item.ot)
        self.fault=QLabel('Avería: '+(cached_fault or 'se consultará si no está en MD'));self.fault.setWordWrap(True);body.addWidget(self.fault)
        form=QFormLayout();self.review_form=form;body.addLayout(form)
        self.action=QComboBox();self.action.addItem('Declarar irreparable — Desechar equipo','discard');self.action.addItem('Cerrar OT — reparación finalizada','close')
        self.action.setCurrentIndex(self.action.findData(default_action))
        form.addRow('Acción final',self.action)
        self.reference=QLineEdit();self.reference.setPlaceholderText('Número o texto libre de la etiqueta');form.addRow('Incidencia',self.reference)
        self.duration=QLineEdit();self.duration.setPlaceholderText('Horas en tramos de 0,25; ejemplo: 1');form.addRow('Tiempo de reparación (h)',self.duration)
        timing=QHBoxLayout();self.time_mode=QComboBox();self.time_mode.addItem('Finalización','end');self.time_mode.addItem('Inicio','start')
        self.time=RepairTimeEdit(QDateTime.currentDateTime());self.time.setDisplayFormat('dd/MM/yyyy HH:mm');self.time.setCalendarPopup(True)
        self.now=QPushButton('Ahora');self.now.setMaximumWidth(90);self.time_mode.setMaximumWidth(180);self.now.clicked.connect(self.set_now)
        timing.addWidget(self.time_mode);timing.addWidget(self.time);timing.addWidget(self.now);form.addRow('Fecha y hora',timing)
        self.dates=QLabel();form.addRow('Fechas calculadas',self.dates)
        self.justification=QPlainTextEdit();self.justification.setPlaceholderText('Motivo de irreparable que se registrará en Maximo');self.justification.setMaximumHeight(90);form.addRow('Motivo por el que se desecha',self.justification)
        self.justification.setPlainText(cached_fault)
        self._justification_edited=False
        self.justification.textChanged.connect(lambda:setattr(self,'_justification_edited',True))
        body.addWidget(QLabel('Registro de reparaciones, pruebas y procesos (una entrada por fila)'))
        self.entries=QTableWidget(0,2);self.entries.setHorizontalHeaderLabels(['Resumen','Detalles']);self.entries.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.entries.setMinimumHeight(180);body.addWidget(self.entries)
        rowbuttons=QHBoxLayout();add=QPushButton('Añadir entrada');remove=QPushButton('Quitar entrada');add.clicked.connect(lambda:self.add_entry());remove.clicked.connect(lambda:self.entries.removeRow(self.entries.currentRow()));rowbuttons.addWidget(add);rowbuttons.addWidget(remove);rowbuttons.addStretch();body.addLayout(rowbuttons)
        body.addWidget(QLabel('Anomalías y soluciones que se aplicarán'))
        self.picker=FailurePathPicker();self.picker.set_selection(selection);body.addWidget(self.picker)
        self.print_check=QCheckBox('Imprimir parte una vez verificado');self.print_check.setChecked(True);body.addWidget(self.print_check)
        self.confirm=QCheckBox('He revisado la OT y confirmo la acción irreversible seleccionada.');body.addWidget(self.confirm)
        self.status=QLabel('Consultando el estado y Registro de Maximo…');self.status.setWordWrap(True);root.addWidget(self.status)
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
        screen=QApplication.primaryScreen().availableGeometry();self.resize(min(1050,screen.width()-70),min(850,screen.height()-70))
        self.set_now()
        if autoload:self.launch()

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
        if self.is_running():return
        self._worker=RepairWorker(self.item,plan,self)
        self._worker.progress.connect(self.progress_message)
        self._worker.ready.connect(self.preview_ready if plan is None else self.finished_repair)
        self._worker.failed.connect(self.failed)
        if plan is not None:
            self.progress_dialog=RepairProgressDialog(self)
            self._worker.stage.connect(self.progress_dialog.set_stage)
            self._worker.finished.connect(self.progress_dialog.worker_finished)
            self.progress_dialog.show();self.hide()
        lock=getattr(self.parent(),'update_lock',None)
        if lock is not None:lock.acquire(False);self._worker.finished.connect(lock.release)
        self._worker.start()

    def progress_message(self,text):
        self.status.setText(text)
        if self.progress_dialog:self.progress_dialog.message.setText(text)

    def preview_ready(self,data):
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
        preserved=' Se han conservado los datos que escribiste durante la consulta.' if self._preview_edited else ''
        self.status.setText('Estado real: '+data['state']+'. Revisa los datos. Si está en APPR, se iniciará antes de finalizar.'+preserved)

    def execute(self):
        if self.is_running() or not self._reviewed or self._verified:return
        if not self.confirm.isChecked():QMessageBox.warning(self,'Confirmación requerida','Marca que has revisado la acción irreversible.');return
        try:plan=reviewed_repair(self.item,self.values(),self.picker.selection())
        except (ValueError,OverflowError) as exc:QMessageBox.warning(self,'Revisar reparación',str(exc));return
        label='DESECHAR POR IRREPARABLE' if plan.action=='discard' else 'CERRAR OT'
        reason_line='\nMotivo por el que se desecha: '+plan.justification if plan.action=='discard' else ''
        if QMessageBox.question(self,'Confirmar acción irreversible',
            f'OT {self.item.ot} · {self.item.serial}\n{label}\nIncidencia: {plan.incident_summary}\nTiempo: {plan.duration} h\nInicio: {plan.start}\nFin: {plan.end}{reason_line}\n\nSi está en APPR, también se iniciará. No es reversible. ¿Continuar?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.submit.setEnabled(False);self.review_panel.setEnabled(False);self.status.setText('Preparando la reparación…')
        self.launch(plan)

    def finished_repair(self,result):
        self._verified=result;self.retry_print.setEnabled(True)
        store=RecoveryStore();record=store.get(self.item.ot)
        try:
            saved=apply_warehouse_status(self.item.ot,'CLOSE') if result['status']=='CLOSE' else apply_closed_repair(self.item.ot)
            if not saved:raise RuntimeError('No se pudo actualizar el seguimiento local.')
            report=WarehouseResult(self.item,status='success',completed_steps=5,step='Reparación verificada',
                verified_status=result['status'],operation_id=result['operation_id'],local_status_saved=True)
            if record:store.update_report(record,report);store.complete(record)
        except Exception:
            logging.exception('Reparación verificada; guardado local pendiente')
        self.repair_verified.emit(result)
        self.status.setText('Operación verificada en '+result['status']+'. El parte se prepara por separado; un fallo de impresión no repetirá la operación.')
        if self.progress_dialog:self.progress_dialog.success(result)
        if result.get('print_report'):self.print_requested.emit(self.item.ot)

    def failed(self,message):
        self.submit.setEnabled(False)
        self.status.setText('Proceso detenido: '+message+'. Revisa el registro de operaciones pendientes antes de repetir.')
        if self.progress_dialog:self.progress_dialog.failure(message)

    def request_stop(self):
        if self._worker is not None:self._worker.stop_requested.set()
        message='Se terminará el paso actual antes de detenerse. No se repetirá ninguna confirmación.'
        self.status.setText(message)
        if self.progress_dialog:
            self.progress_dialog.message.setText(message);self.progress_dialog.stop_button.setEnabled(False)
            self.progress_dialog.show();self.progress_dialog.raise_()

    def closeEvent(self,event):
        if self.is_running():
            self.request_stop();event.ignore();return
        super().closeEvent(event)

    def reject(self):
        if self.is_running():self.request_stop();return
        super().reject()
