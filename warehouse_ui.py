"""Warehouse review and progress UI; real transport is opt-in in the isolated app."""
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
    QProgressBar, QPushButton, QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout, QMessageBox, QLineEdit,
)

from app_paths import LOG_DIR, WAREHOUSE_DEVELOPMENT_MODE
from warehouse import ACTIONS, RECEIPT_ACTIONS, STEPS, WarehouseItem, WarehouseResult, freeze_items
from warehouse_diagnostics import log_exception, sanitize

STATUS_LABELS = {
    'pending': 'Pendiente', 'running': 'En proceso', 'success': 'Operación verificada',
    'failed': 'Fallida', 'uncertain': 'Pendiente de verificar', 'stopped': 'Sin procesar',
}
STATUS_COLORS = {'success': '#15803d', 'failed': '#dc2626', 'uncertain': '#b45309'}
STATUS_COLORS_DARK = {'success': '#4ade80', 'failed': '#f87171', 'uncertain': '#fbbf24'}
LOCAL_TRACKING = {'receive': 'EN TALLER', 'dispatch': 'CLOSE',
                  'receive_sat_internal': 'SAT INT', 'receive_sat_external': 'SAT EXT'}


class WarehouseThread(QThread):
    progress = Signal(int, object)
    completed = Signal(object)
    failed = Signal(str)
    record_updated = Signal(str, str)
    waiting = Signal(str)

    def __init__(self, items, action, journal_path, parent=None, *, details=None):
        super().__init__(parent)
        self.items, self.action = items, action
        self.stop_requested = Event()
        self.journal_path = journal_path
        self.details = dict(details or {})

    def run(self):
        try:
            from warehouse_transport import run_live, FINAL_STATES
            from db import apply_warehouse_status
            from warehouse_diagnostics import WarehouseJournal
            from version import APP_VERSION
            recorded = {}
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open('a', encoding='utf-8') as stream:
                journal = WarehouseJournal(stream, self.journal_path.stem.removesuffix('-events'))
                journal({'event':'batch_started','action':self.action,'app_version':APP_VERSION,
                         'python_version':platform.python_version(),'platform':platform.platform(),
                         'item_count':len(self.items),'ots':[item.ot for item in self.items]})
                logging.info('Almacén lote %s: %s, %d OT. Diagnóstico: %s',
                             journal.batch_id,self.action,len(self.items),self.journal_path)
                def progress(index, result):
                    if result.status == 'success':
                        try:
                            if result.verified_status != FINAL_STATES[self.action]:
                                raise RuntimeError('Falta el estado final verificado de Maximo.')
                            tracking = LOCAL_TRACKING[self.action]
                            if not apply_warehouse_status(result.item.ot, tracking):
                                raise RuntimeError('La OT no existe en la base de datos local.')
                            journal({'ot': result.item.ot, 'local_tracking': tracking, 'local_status_saved': True})
                            self.record_updated.emit(result.item.ot, tracking)
                        except Exception as exc:
                            log_exception('Operación verificada, pero falló la actualización local de %s', result.item.ot)
                            journal({'event':'local_status_error','ot':result.item.ot,'action':self.action,
                                     'error_type':type(exc).__name__,'message':sanitize(str(exc))})
                            result = replace(result, detail=result.detail +
                                ' Operación verificada en Maximo; no se pudo actualizar la copia local. Actualiza el listado.')
                    recorded[index] = result
                    self.progress.emit(index, result)
                results = run_live(self.items, self.action, stop=self.stop_requested,
                                   progress=progress, journal=journal, details=self.details,
                                   job_label=ACTIONS[self.action].label, job_waiting=self.waiting.emit,
                                   job_cancel_event=self.stop_requested)
                results = tuple(recorded.get(index, result) for index, result in enumerate(results))
                journal({'event':'batch_finished','action':self.action,'counts':dict(Counter(r.status for r in results)),
                         'stop_requested':self.stop_requested.is_set()})
            self.completed.emit(results)
        except Exception as exc:
            log_exception('Fallo en lote real de almacén')
            self.failed.emit(sanitize(str(exc)))


class WarehouseBatchDialog(QDialog):
    record_updated = Signal(str, str)
    def __init__(self, items, action, open_ot, parent=None, report_folder=None, *, ask_sat_details=False):
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
        self.details_inputs = {}
        self.setWindowTitle(f'Almacén · {ACTIONS[action].label}')
        self.resize(1000, 650)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        title = QLabel(f'{ACTIONS[action].label} · {len(self.items)} OT')
        title.setStyleSheet('font-size: 20px; font-weight: 600')
        layout.addWidget(title)
        banner = QLabel('Se ejecutarán operaciones reales con la cuenta de almacén. '
                        'Revisa la acción y las OTs antes de confirmar. Se comprobará su estado en Maximo.')
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
                    cell.setToolTip('Abrir esta OT en Edge para revisión manual. No ejecuta acciones de almacén.')
                self.table.setItem(index, column, cell)
        layout.addWidget(self.table, 1)
        if ask_sat_details and action in ('receive_sat_internal', 'receive_sat_external'):
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
        self.start_button = QPushButton('Revisar y ejecutar…', objectName='primary')
        self.stop_button = QPushButton('Detener después de esta OT')
        self.stop_button.setEnabled(False)
        self.close_button = QPushButton('Cerrar')
        self.start_button.clicked.connect(self.start_operation)
        self.stop_button.clicked.connect(self.request_stop)
        self.close_button.clicked.connect(self.close)
        buttons.addStretch()
        for button in (self.stop_button, self.close_button, self.start_button):
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
                self.table.item(row, 4).setForeground(QColor(colors[result.status]))

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
        if self._has_started:
            return
        if QMessageBox.question(self, 'Confirmar operación real',
                f'{ACTIONS[self.action].label}\n\nOTs: ' + ', '.join(i.ot for i in self.items) +
                '\n\nSe ejecutará en Maximo. Esta operación puede ser irreversible. ¿Continuar?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        lock = getattr(self.parent(), 'update_lock', None)
        if lock is not None and not lock.acquire(False):
            QMessageBox.information(self, 'Almacén', 'Hay otra tarea de Maximo en curso. Inténtalo al terminar.')
            return
        self._has_started = True
        self.start_button.setEnabled(False)
        self.start_button.setText('Proceso en curso')
        details = {ot: entry.text().strip() for ot, entry in self.details_inputs.items()}
        for entry in self.details_inputs.values():
            entry.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._worker = WarehouseThread(self.items, self.action,
            self.report_folder / f'{self.batch_id}-events.jsonl', self, details=details)
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
        outcome.setText(STATUS_LABELS[result.status])
        if result.status in STATUS_COLORS:
            outcome.setForeground(QColor(self._status_colors()[result.status]))
            icon = {'success': QStyle.SP_DialogApplyButton, 'failed': QStyle.SP_DialogCancelButton,
                    'uncertain': QStyle.SP_MessageBoxWarning}[result.status]
            outcome.setIcon(self.style().standardIcon(icon))
        self.table.item(index, 5).setText(result.detail)
        self.table.item(index, 5).setToolTip(result.detail)
        processed = sum(r.status in ('success', 'failed', 'uncertain') for r in self.results)
        self.progress_bar.setValue(processed)
        if result.status == 'running':
            self.current_step.setText(f'OT {result.item.ot} · {result.step}')
            self.steps.setText(' → '.join(('✓ ' if i < result.completed_steps else '') + step
                                          for i, step in enumerate(STEPS)))

    def _completed(self, results):
        self.results = list(results)
        counts = Counter(result.status for result in results)
        self.current_step.setText('Proceso finalizado. Revisa el resultado de cada OT.')
        self.summary.setText(f'{counts["success"]} verificadas · {counts["failed"]} fallidas · '
                             f'{counts["uncertain"]} pendientes de verificar · {counts["stopped"]} sin procesar.')
        self.stop_button.setEnabled(False)
        self.start_button.setText('Proceso finalizado')
        self.report_path = self.report_folder / f'{self.batch_id}-result.json'
        self.summary.setToolTip(f'Reporte: {self.report_path}\nDiagnóstico: {self.report_folder / (self.batch_id + "-events.jsonl")}')
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

    def add_warehouse_actions(self, menu):
        if not WAREHOUSE_DEVELOPMENT_MODE or not getattr(self.cfg, 'warehouse_enabled', False):
            return
        items = self.warehouse_items()
        menu.addSeparator()
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
        if not WAREHOUSE_DEVELOPMENT_MODE or not getattr(self.cfg, 'warehouse_enabled', False) or getattr(self, '_closing', False):
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
