"""Warehouse review and progress UI; real transport is enabled through application settings."""
from collections import Counter
from dataclasses import asdict, replace
import json
import logging
import platform
from threading import Event
from uuid import uuid4

from PySide6.QtCore import QEvent, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QProgressBar, QPushButton, QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout, QMessageBox, QLineEdit, QInputDialog,
)

from app_paths import LOG_DIR
from warehouse import ACTIONS, RECEIPT_ACTIONS, STEPS, WarehouseItem, WarehouseResult, freeze_items
from warehouse_diagnostics import log_exception, sanitize
from warehouse_recovery import RecoveryStore, recovery_item, preparation_retry_allowed

STATUS_LABELS = {
    'pending': 'Pendiente', 'running': 'En proceso', 'success': 'Operación verificada',
    'already_done': 'Ya estaba completada',
    'failed': 'Fallida', 'uncertain': 'Pendiente de verificar', 'stopped': 'Sin procesar',
}
STATUS_COLORS = {'already_done': '#15803d', 'success': '#15803d', 'failed': '#dc2626', 'uncertain': '#b45309'}
STATUS_COLORS_DARK = {'already_done': '#4ade80', 'success': '#4ade80', 'failed': '#f87171', 'uncertain': '#fbbf24'}
LOCAL_TRACKING = {'technician_discard':'CLOSE','technician_close':'ISSUE','receive': 'EN TALLER', 'dispatch': 'CLOSE',
                  'receive_sat_internal': 'SAT INT', 'receive_sat_external': 'SAT EXT', 'technician_sat_external': 'SAT EXT'}


class WarehouseThread(QThread):
    progress = Signal(int, object)
    completed = Signal(object)
    failed = Signal(str)
    record_updated = Signal(str, str)
    waiting = Signal(str)

    def __init__(self, items, action, journal_path, parent=None, *, details=None, recoveries=None, previous_results=(), technician_plans=None, technician_retries=None):
        super().__init__(parent)
        self.items, self.action = items, action
        self.stop_requested = Event()
        self.journal_path = journal_path
        self.details = dict(details or {})
        self.recoveries = recoveries
        self.previous_results = tuple(previous_results)
        self.technician_plans = technician_plans
        self.technician_retries = dict(technician_retries or {})

    def run(self):
        try:
            from warehouse_transport import run_live, reverify_pending, FINAL_STATES
            from db import apply_warehouse_status
            from warehouse_diagnostics import WarehouseJournal
            from version import APP_VERSION
            recorded = dict(enumerate(self.previous_results))
            store = RecoveryStore(self.journal_path.parent, origin_report=self.journal_path.stem.removesuffix('-events')+'-result.json')
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open('a', encoding='utf-8') as stream:
                journal = WarehouseJournal(stream, self.journal_path.stem.removesuffix('-events'))
                journal({'event':'batch_started','action':self.action,'app_version':APP_VERSION,
                         'python_version':platform.python_version(),'platform':platform.platform(),
                         'item_count':len(self.items),'ots':[item.ot for item in self.items]})
                logging.info('Almacén lote %s: %s, %d OT. Diagnóstico: %s',
                             journal.batch_id,self.action,len(self.items),self.journal_path)
                saved = set()
                def progress(index, result):
                    if result.status in ('success','already_done'):
                        key = (result.operation_id, result.item.ot, result.verified_status)
                        try:
                            if result.verified_status != FINAL_STATES[self.action]:
                                raise RuntimeError('Falta el estado final verificado de Maximo.')
                            if key not in saved:
                                if result.operation_id:
                                    current = store.get(result.item.ot)
                                    if (not current or current['operation_id'] != result.operation_id or
                                            current['action'] != self.action or
                                            current.get('verified_status') != result.verified_status):
                                        raise RuntimeError('La evidencia pendiente ha cambiado; vuelve a abrir la revisión.')
                                tracking = LOCAL_TRACKING[self.action]
                                error = None
                                for attempt in range(2):
                                    try:
                                        journal({'event':'local_sync_attempt','ot':result.item.ot,'attempt':attempt+1,
                                                 'operation_id':result.operation_id})
                                        if not apply_warehouse_status(result.item.ot, tracking):
                                            raise RuntimeError('La OT no existe en la base de datos local.')
                                        error = None; break
                                    except Exception as exc:
                                        error = exc
                                if error is not None: raise error
                                journal({'ot': result.item.ot, 'local_tracking': tracking, 'local_status_saved': True,
                                         'operation_id':result.operation_id})
                                record = store.get(result.item.ot)
                                if record and record['operation_id'] == result.operation_id:
                                    store.update_report(record, replace(result, local_status_saved=True))
                                    store.complete(record)
                                saved.add(key)
                                self.record_updated.emit(result.item.ot, tracking)
                            result = replace(result, local_status_saved=True)
                        except Exception as exc:
                            log_exception('Operación verificada, pero falló la actualización local de %s', result.item.ot)
                            journal({'event':'local_status_error','ot':result.item.ot,'action':self.action,
                                     'error_type':type(exc).__name__,'message':sanitize(str(exc)),
                                     'operation_id':result.operation_id})
                            result = replace(result, local_status_saved=False, detail=result.detail +
                                ' Verificada en Maximo; pendiente de guardar en la copia local de MD. Usa Reverificar para reintentar solo el guardado.')
                    recorded[index] = result
                    self.progress.emit(index, result)
                options = dict(stop=self.stop_requested, journal=journal, recovery_store=store,
                               job_label=('Reverificar: ' if self.recoveries is not None else '')+ACTIONS[self.action].label,
                               job_waiting=self.waiting.emit, job_cancel_event=self.stop_requested)
                if self.recoveries is None:
                    results = run_live(self.items, self.action, progress=progress, details=self.details,
                                       technician_plans=self.technician_plans, technician_retries=self.technician_retries, **options)
                else:
                    positions = {item.ot:index for index,item in enumerate(self.items)}
                    recovered = reverify_pending(self.recoveries,
                        progress=lambda index,result: progress(positions[result.item.ot],result), **options)
                    results = tuple(recorded.get(index, WarehouseResult(item)) for index,item in enumerate(self.items))
                results = tuple(recorded.get(index, result) for index, result in enumerate(results))
                journal({'event':'batch_finished','action':self.action,'counts':dict(Counter(r.status for r in results)),
                         'stop_requested':self.stop_requested.is_set()})
            self.completed.emit(results)
        except Exception as exc:
            log_exception('Fallo en lote real de almacén')
            self.failed.emit(sanitize(str(exc)))


class WarehouseBatchDialog(QDialog):
    record_updated = Signal(str, str)
    def __init__(self, items, action, open_ot, parent=None, report_folder=None, *, ask_sat_details=False, recovery_only=False):
        super().__init__(parent)
        from warehouse_transport import FINAL_STATES
        if action not in FINAL_STATES:
            raise ValueError('Esta acción de almacén está pendiente de validación.')
        self.items = freeze_items(items)
        self.action, self.open_ot = action, open_ot
        self.results = [WarehouseResult(item) for item in self.items]
        self.batch_id = uuid4().hex
        self.report_folder = report_folder or LOG_DIR / 'almacen-operaciones'
        self.report_path = None
        self._worker = None
        self._has_started = False
        self.recovery_only = recovery_only
        self.details_inputs = {}
        owner = 'Técnico' if ACTIONS[action].role == 'technician' else 'Almacén'
        self.setWindowTitle(f'{owner} · {ACTIONS[action].label}')
        self.resize(1000, 650)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        title = QLabel(f'{ACTIONS[action].label} · {len(self.items)} OT')
        title.setStyleSheet('font-size: 20px; font-weight: 600')
        layout.addWidget(title)
        banner = QLabel('Se ejecutarán operaciones reales con la cuenta de almacén. '
                        'Revisa la acción y las OTs antes de confirmar. Se comprobará su estado en Maximo.')
        if ACTIONS[action].role == 'technician':
            banner.setText('Envío técnico a SAT externo. Se prepararán anomalías, horas e incidencia antes de enrutar. Revisa los datos por OT y confirma antes de ejecutar.')
        if recovery_only:
            banner.setText('Solo se consultarán resultados pendientes o se reintentará su guardado local. La reverificación no ejecuta Enrutar ni Aceptar. Las preparaciones incompletas pueden reintentarse desde un formulario con nueva confirmación.')
        banner.setWordWrap(True)
        banner.setObjectName('filterHint')
        layout.addWidget(banner)
        self.table = QTableWidget(len(self.items), 6)
        self.table.setHorizontalHeaderLabels(('OT', 'Equipo / Nº de serie', 'Estado inicial',
                                             'Paso actual', 'Resultado', 'Detalle'))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.cellClicked.connect(self._open_row)
        for index, item in enumerate(self.items):
            values = (item.ot, f'{item.equipment} · {item.serial}', item.status,
                      'Pendiente', STATUS_LABELS['pending'], '')
            for column, text in enumerate(values):
                cell = QTableWidgetItem(text)
                if column == 0:
                    font = cell.font(); font.setUnderline(True); cell.setFont(font)
                    cell.setToolTip('Abrir esta OT en Edge para revisión manual. No ejecuta ninguna operación.')
                self.table.setItem(index, column, cell)
        layout.addWidget(self.table, 1)
        if not recovery_only and ask_sat_details and action in ('receive_sat_internal', 'receive_sat_external'):
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderItem(6, QTableWidgetItem('Detalles SAT (opcional)'))
            for row, item in enumerate(self.items):
                entry = QLineEdit()
                entry.setPlaceholderText('Dejar vacío o escribir detalles para esta OT')
                self.table.setCellWidget(row, 6, entry)
                self.details_inputs[item.ot] = entry
            details_hint = QLabel('Los detalles son opcionales y se aplican solo a la OT de su fila.')
            details_hint.setWordWrap(True)
            layout.addWidget(details_hint)
        self.current_step = QLabel('Revisa la selección y pulsa «Revisar y ejecutar».')
        self.current_step.setWordWrap(True)
        layout.addWidget(self.current_step)
        self.steps = QLabel(' → '.join(STEPS))
        self.steps.setWordWrap(True)
        layout.addWidget(self.steps)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.items))
        self.progress_bar.setFormat('Procesadas %v de %m')
        layout.addWidget(self.progress_bar)
        self.summary = QLabel('Los resultados aparecerán después de verificar cada OT en Maximo.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Reverificar (solo consulta)' if recovery_only else 'Revisar y ejecutar…', objectName='primary')
        self.recheck_button = QPushButton('Reverificar pendientes')
        self.recheck_button.setEnabled(False)
        self.recheck_button.clicked.connect(self.start_reverification)
        self.retry_button = QPushButton('Reintentar preparación…')
        self.retry_button.setVisible(action=='technician_sat_external')
        self.retry_button.clicked.connect(self.start_preparation_retry)
        self._retry_dialogs = []
        self._refresh_retry_button()
        self.stop_button = QPushButton('Detener después de esta OT')
        self.stop_button.setEnabled(False)
        self.close_button = QPushButton('Cerrar')
        self.start_button.clicked.connect(self.start_operation)
        self.stop_button.clicked.connect(self.request_stop)
        self.close_button.clicked.connect(self.close)
        buttons.addStretch()
        for button in (self.retry_button, self.recheck_button, self.stop_button, self.close_button, self.start_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._sync_table_palette()

    def _sync_table_palette(self):
        # The app's stylesheet colors labels, but its tables normally set cell
        # foregrounds explicitly. Follow the label palette for this live report.
        self.current_step.ensurePolished()
        palette = self.table.palette()
        palette.setColor(QPalette.Text, self.current_step.palette().color(QPalette.WindowText))
        self.table.setPalette(palette)
        colors = self._status_colors()
        for row, result in enumerate(self.results):
            if result.status in colors:
                self.table.item(row, 4).setForeground(QColor(colors['uncertain' if result.local_status_saved is False else result.status]))

    def _status_colors(self):
        return (STATUS_COLORS_DARK if self.current_step.palette().color(QPalette.WindowText).lightness() > 128
                else STATUS_COLORS)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.StyleChange, QEvent.PaletteChange) and hasattr(self, 'current_step'):
            QTimer.singleShot(0, self, self._sync_table_palette)

    def is_running(self):
        return self._worker is not None and self._worker.isRunning()

    def start_operation(self):
        if self._has_started or self.is_running():
            return
        if self.recovery_only:
            self.start_reverification()
            return
        if QMessageBox.question(self, 'Confirmar operación real',
                f'{ACTIONS[self.action].label}\n\nOTs: ' + ', '.join(i.ot for i in self.items) +
                '\n\nSe ejecutará en Maximo. Esta operación puede ser irreversible. ¿Continuar?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._launch_worker()

    def _retry_records(self):
        return [record for record in RecoveryStore(self.report_folder).pending()
                if record['item']['ot'] in {item.ot for item in self.items}
                and preparation_retry_allowed(record)]

    def _refresh_retry_button(self):
        try:self.retry_button.setEnabled(self.action=='technician_sat_external' and bool(self._retry_records()))
        except Exception:self.retry_button.setEnabled(False)

    def start_preparation_retry(self):
        if self.is_running() or any(dialog.is_running() for dialog in self._retry_dialogs):return
        try:
            records=self._retry_records()
            if not records:
                self._refresh_retry_button()
                QMessageBox.information(self,'Reintentar preparación','No hay preparaciones que puedan reintentarse sin riesgo de repetir un envío.')
                return
            record=records[0]
            if len(records)>1:
                ot,ok=QInputDialog.getItem(self,'Reintentar preparación','OT que quieres revisar:',
                    [r['item']['ot'] for r in records],0,False)
                if not ok:return
                record=next(r for r in records if r['item']['ot']==ot)
            from technician_sat_ui import TechnicianSatDialog
            selection=getattr(getattr(self.parent(),'cfg',None),'workorder_start_selection',None)
            dialog=TechnicianSatDialog([recovery_item(record)],self.open_ot,self.parent(),
                selection=selection,report_folder=self.report_folder,retry_records=[record])
            def updated(ot,status):
                self.record_updated.emit(ot,status)
                for index,result in enumerate(self.results):
                    if result.item.ot==ot:
                        self._progress(index,replace(result,status='success',step='Operación verificada',
                            completed_steps=5,verified_status='ISSUE',local_status_saved=True,
                            detail='Reintento revisado y envío verificado en Maximo.'))
                self._completed(tuple(self.results))
            dialog.record_updated.connect(updated)
            self._retry_dialogs.append(dialog)
            dialog.show()
        except Exception as exc:
            QMessageBox.warning(self,'Reintentar preparación',str(exc))

    def start_reverification(self):
        if self.is_running(): return
        try:
            records = [r for r in RecoveryStore(self.report_folder).pending()
                       if r['action'] == self.action and r['item']['ot'] in {i.ot for i in self.items}]
        except Exception as exc:
            QMessageBox.warning(self, 'Recuperación', str(exc)); return
        if not records:
            QMessageBox.information(self, 'Recuperación', 'No hay operaciones pendientes de este lote.'); return
        self._launch_worker(records)

    def _launch_worker(self, recoveries=None):
        lock = getattr(self.parent(), 'update_lock', None)
        if lock is not None and not lock.acquire(False):
            QMessageBox.information(self, 'Almacén', 'Hay otra tarea de Maximo en curso. Inténtalo al terminar.')
            return
        self._has_started = True
        self.start_button.setEnabled(False)
        self.start_button.setText('Reverificando…' if recoveries is not None else 'Proceso en curso')
        self.recheck_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        details = {ot: entry.text().strip() for ot, entry in self.details_inputs.items()}
        for entry in self.details_inputs.values():
            entry.setEnabled(False)
        self.stop_button.setEnabled(True)
        journal_id = self.batch_id if recoveries is None else self.batch_id+'-recheck-'+uuid4().hex
        self._worker = WarehouseThread(self.items, self.action,
            self.report_folder / f'{journal_id}-events.jsonl', self, details=details,
            recoveries=recoveries, previous_results=self.results if recoveries is not None else (),
            technician_plans=getattr(self, "technician_plans", None),
            technician_retries=getattr(self, "technician_retries", None))
        self._worker.progress.connect(self._progress)
        self._worker.waiting.connect(self.current_step.setText)
        self._worker.record_updated.connect(self.record_updated)
        self._worker.completed.connect(self._completed)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(lambda: self.stop_button.setEnabled(False))
        if lock is not None:
            self._worker.finished.connect(lock.release)
        self._worker.start()

    def request_stop(self):
        if self.is_running():
            self._worker.stop_requested.set()
            self.stop_button.setEnabled(False)
            self.current_step.setText('Se detendrá después de terminar la OT actual.')

    def _progress(self, index, result):
        self.results[index] = result
        self.table.item(index, 3).setText(result.step)
        outcome = self.table.item(index, 4)
        outcome.setText('Verificada; guardado pendiente' if result.local_status_saved is False else STATUS_LABELS[result.status])
        if result.status in STATUS_COLORS:
            outcome.setForeground(QColor(self._status_colors()['uncertain' if result.local_status_saved is False else result.status]))
            icon = {'success': QStyle.SP_DialogApplyButton, 'already_done': QStyle.SP_DialogApplyButton, 'failed': QStyle.SP_DialogCancelButton,
                    'uncertain': QStyle.SP_MessageBoxWarning}[result.status]
            outcome.setIcon(self.style().standardIcon(icon))
        self.table.item(index, 5).setText(result.detail)
        self.table.item(index, 5).setToolTip(result.detail)
        processed = sum(r.status in ('success', 'already_done', 'failed', 'uncertain') for r in self.results)
        self.progress_bar.setValue(processed)
        if result.status == 'running':
            self.current_step.setText(f'OT {result.item.ot} · {result.step}')
            self.steps.setText(' → '.join(('✓ ' if i < result.completed_steps else '') + step
                                          for i, step in enumerate(STEPS)))

    def _completed(self, results):
        self.results = list(results)
        counts = Counter(result.status for result in results)
        self.current_step.setText('Proceso finalizado. Revisa el resultado de cada OT.')
        count=results[0].completed_steps if len(results)==1 else 0
        self.steps.setText(' → '.join(('✓ ' if i<count else '')+step for i,step in enumerate(STEPS)))
        self._refresh_retry_button()
        local_pending = sum(r.local_status_saved is False for r in results)
        self.summary.setText(f'{counts["success"]} verificadas · {counts["already_done"]} ya completadas · {counts["failed"]} fallidas · '
                             f'{counts["uncertain"]} pendientes de verificar · {local_pending} guardados pendientes · {counts["stopped"]} sin procesar.')
        try:
            self.recheck_button.setEnabled(any(r['action']==self.action and r['item']['ot'] in {i.ot for i in self.items}
                for r in RecoveryStore(self.report_folder).pending()))
        except Exception:
            log_exception('No se pudo leer la recuperación pendiente')
        self.stop_button.setEnabled(False)
        self.start_button.setText('Proceso finalizado')
        self.report_path = self.report_folder / f'{self.batch_id}-result.json'
        diagnostic = self._worker.journal_path if self._worker is not None else self.report_folder / (self.batch_id+'-events.jsonl')
        self.summary.setToolTip(f'Reporte: {self.report_path}\nDiagnóstico: {diagnostic}')
        try:
            self.report_folder.mkdir(parents=True, exist_ok=True)
            self.report_path.write_text(json.dumps({'simulation': False, 'batch_id': self.batch_id,
                'action': self.action, 'results': [asdict(r) for r in results]},
                ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            log_exception('No se pudo guardar el reporte de almacén')
            self.summary.setText(self.summary.text() + ' No se pudo guardar el reporte.')

    def _failed(self, message):
        # Preserve confirmed results if an unexpected worker failure interrupts a batch.
        for index, result in enumerate(self.results):
            if result.status == 'running':
                self._progress(index, replace(result, status='uncertain', detail=message))
            elif result.status == 'pending':
                self._progress(index, replace(result, status='stopped', detail='No procesada: proceso interrumpido.'))
        self._completed(tuple(self.results))
        self.current_step.setText(f'Proceso interrumpido: {message}')

    def _open_row(self, row, column):
        if column == 0:
            self.open_ot(self.items[row].ot)

    def closeEvent(self, event):
        if self.is_running():
            self.request_stop()
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self):
        if self.is_running():
            self.request_stop()
            return
        super().reject()


class WarehouseWindowMixin:
    """Small integration surface so warehouse work can be discarded independently."""
    def warehouse_items(self):
        table = self.table
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()})
        def text(row, column):
            cell = table.item(row, column)
            return cell.text().strip() if cell else ''
        return freeze_items(WarehouseItem(text(row, 1), text(row, 2), text(row, 3),
                                          text(row, 7), text(row, 5))
                            for row in rows if not table.isRowHidden(row))

    def add_role_action_menus(self,menu):
        technical_close=getattr(self.cfg,'workorder_close_enabled',False)
        technical_sat=getattr(self.cfg,'technician_sat_enabled',False)
        warehouse=getattr(self.cfg,'warehouse_enabled',False)
        if not (technical_close or technical_sat or warehouse):return
        if menu.actions():menu.addSeparator()
        if technical_close or technical_sat:
            technical=menu.addMenu('Técnico')
            if technical_close:self.add_repair_completion_action(technical)
            if technical_sat:self.add_technician_sat_action(technical)
        if warehouse:
            self.add_warehouse_actions(menu.addMenu('Almacén'))

    def add_warehouse_actions(self, menu):
        if not getattr(self.cfg, 'warehouse_enabled', False):
            return
        items = self.warehouse_items()
        if menu.actions():menu.addSeparator()
        from warehouse_transport import FINAL_STATES
        receipt = menu.addMenu(f'Dar entrada · {len(items)} OT')
        for action in RECEIPT_ACTIONS:
            label = ACTIONS[action].label + ('…' if action in FINAL_STATES else ' · pendiente de validar')
            entry = receipt.addAction(label, lambda checked=False, a=action, selection=items:
                                      self.open_warehouse_batch(selection, a))
            entry.setEnabled(action in FINAL_STATES)
        menu.addAction(f'{ACTIONS["dispatch"].label} · {len(items)} OT…',
                       lambda checked=False, selection=items: self.open_warehouse_batch(selection, 'dispatch'))

    def open_warehouse_batch(self, items, action):
        if not getattr(self.cfg, 'warehouse_enabled', False) or getattr(self, '_closing', False):
            return
        dialogs = getattr(self, '_warehouse_dialogs', [])
        active = next((dialog for dialog in dialogs if dialog.is_running()), None)
        if active is not None:
            active.show(); active.raise_(); active.activateWindow()
            return
        from warehouse_transport import FINAL_STATES
        if action not in FINAL_STATES:
            return
        dialog = WarehouseBatchDialog(items, action, self.open_ot_number, self,
            report_folder=LOG_DIR / 'almacen-operaciones',
            ask_sat_details=getattr(self.cfg, 'warehouse_ask_sat_details', False))
        if hasattr(self, 'warehouse_row_updated'):
            dialog.record_updated.connect(self.warehouse_row_updated)
        self._warehouse_dialogs = [*dialogs, dialog]
        dialog.show()

    def warehouse_is_running(self):
        return any(dialog.is_running() for dialog in getattr(self, '_warehouse_dialogs', []))

    def _operation_allowed(self, action):
        flag = 'workorder_close_enabled' if action in ('technician_discard','technician_close') else 'technician_sat_enabled' if ACTIONS[action].role == 'technician' else 'warehouse_enabled'
        return bool(getattr(self.cfg, flag, False))

    def open_warehouse_recovery(self):
        if getattr(self, '_closing', False): return
        if not (getattr(self.cfg, 'warehouse_enabled', False) or getattr(self.cfg, 'technician_sat_enabled', False) or getattr(self.cfg,'workorder_close_enabled',False)): return
        try:
            records = [r for r in RecoveryStore().pending() if self._operation_allowed(r['action'])]
        except Exception as exc:
            QMessageBox.warning(self, 'Recuperación de operaciones', str(exc)); return
        if not records:
            QMessageBox.information(self, 'Recuperación de operaciones', 'No hay operaciones pendientes.'); return
        groups = {action:[r for r in records if r['action']==action] for action in ACTIONS}
        groups = {action:values for action,values in groups.items() if values}
        action = next(iter(groups))
        if len(groups)>1:
            labels = {f'{ACTIONS[a].label} · {len(v)} OT':a for a,v in groups.items()}
            selected,ok = QInputDialog.getItem(self,'Recuperación de operaciones','Acción pendiente:',list(labels),0,False)
            if not ok:return
            action = labels[selected]
        dialogs = getattr(self, '_warehouse_dialogs', [])
        if any(d.is_running() for d in dialogs):
            QMessageBox.information(self,'Almacén','Espera a que termine la operación activa.');return
        dialog = WarehouseBatchDialog([recovery_item(r) for r in groups[action]],action,self.open_ot_number,self,recovery_only=True)
        if hasattr(self,'warehouse_row_updated'):dialog.record_updated.connect(self.warehouse_row_updated)
        self._warehouse_dialogs = [*dialogs,dialog];dialog.show()

    def offer_warehouse_recovery(self):
        if getattr(self,'_closing',False) or not (getattr(self.cfg,'warehouse_enabled',False) or getattr(self.cfg,'technician_sat_enabled',False) or getattr(self.cfg,'workorder_close_enabled',False)):return
        try:count = sum(self._operation_allowed(r['action']) for r in RecoveryStore().pending())
        except Exception:
            log_exception('No se pudo consultar la recuperación de almacén');return
        if count and QMessageBox.question(self,'Operaciones pendientes',
            f'Hay {count} operaciones pendientes de verificar o guardar. ¿Abrir su revisión? No se reenviarán acciones.',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            self.open_warehouse_recovery()


    def add_technician_sat_action(self, menu):
        if not getattr(self.cfg, 'technician_sat_enabled', False):
            return
        items = self.warehouse_items()
        if menu.actions():menu.addSeparator()
        menu.addAction(f'Enviar a SAT Externo · Técnico · {len(items)} OT…',
                       lambda checked=False, selection=items: self.open_technician_sat_batch(selection))

    def add_repair_completion_action(self, menu):
        items=self.warehouse_items()
        for label,action,hint in (
            ('Declarar irreparable · Técnico…','discard','Desecha el equipo tras revisar Registro, duración y fechas.'),
            ('Dar salida · Técnico…','close','Finaliza la reparación y la deja pendiente de salida de almacén (ISSUE).')):
            entry=menu.addAction(label,lambda checked=False,a=action:self.open_repair_completion(items[0],a))
            entry.setEnabled(len(items)==1)
            entry.setToolTip(hint)

    def open_repair_completion(self,item,default_action='discard'):
        if not getattr(self.cfg,'workorder_close_enabled',False) or getattr(self,'_closing',False):return
        dialogs=getattr(self,'_warehouse_dialogs',[])
        active=next((d for d in dialogs if d.is_running()),None)
        if active:active.show();active.raise_();return
        from technician_repair_ui import RepairDialog
        dialog=RepairDialog(item,self.cfg.workorder_start_selection,self,default_action=default_action)
        dialog.print_requested.connect(lambda ot:self.open_repair_report(ot,'print'))
        dialog.repair_verified.connect(self.workorder_closed.emit)
        self._warehouse_dialogs=[*dialogs,dialog];dialog.show()

    def open_technician_sat_batch(self, items):
        if not getattr(self.cfg, 'technician_sat_enabled', False) or getattr(self, '_closing', False):
            return
        dialogs = getattr(self, '_warehouse_dialogs', [])
        active = next((d for d in dialogs if d.is_running()), None)
        if active:
            active.show(); active.raise_(); active.activateWindow(); return
        from technician_sat_ui import TechnicianSatDialog
        dialog = TechnicianSatDialog(items, self.open_ot_number, self,
            selection=self.cfg.workorder_start_selection)
        if hasattr(self, 'warehouse_row_updated'):
            dialog.record_updated.connect(self.warehouse_row_updated)
        self._warehouse_dialogs = [*dialogs, dialog]
        dialog.show()
