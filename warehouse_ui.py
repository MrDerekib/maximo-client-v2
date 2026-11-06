"""Opt-in warehouse UI. Batch execution is a local simulation only."""
from collections import Counter
from dataclasses import replace
import logging
from threading import Event
from uuid import uuid4

from PySide6.QtCore import QEvent, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QProgressBar, QPushButton, QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app_paths import LOG_DIR
from warehouse import ACTIONS, RECEIPT_ACTIONS, SCENARIOS, STEPS, WarehouseItem, WarehouseResult, freeze_items, run_simulation, save_simulation_report

STATUS_LABELS = {
    'pending': 'Pendiente', 'running': 'En proceso', 'success': 'Simulación correcta',
    'failed': 'Fallida', 'uncertain': 'Pendiente de verificar', 'stopped': 'Sin procesar',
}
STATUS_COLORS = {'success': '#15803d', 'failed': '#dc2626', 'uncertain': '#b45309'}
STATUS_COLORS_DARK = {'success': '#4ade80', 'failed': '#f87171', 'uncertain': '#fbbf24'}


class SimulationThread(QThread):
    progress = Signal(int, object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, items, action, scenario, parent=None):
        super().__init__(parent)
        self.items, self.action, self.scenario = items, action, scenario
        self.stop_requested = Event()

    def run(self):
        try:
            results = run_simulation(self.items, self.action, self.scenario,
                                     stop=self.stop_requested, progress=self.progress.emit)
            self.completed.emit(results)
        except Exception as exc:
            logging.exception('Fallo en lote simulado de almacén')
            self.failed.emit(str(exc))


class WarehouseBatchDialog(QDialog):
    def __init__(self, items, action, open_ot, parent=None, report_folder=None):
        super().__init__(parent)
        if action not in ACTIONS:
            raise ValueError('Acción de almacén no válida.')
        self.items = freeze_items(items)
        self.action, self.open_ot = action, open_ot
        self.results = [WarehouseResult(item) for item in self.items]
        self.batch_id = uuid4().hex
        self.report_folder = report_folder or LOG_DIR / 'almacen-simulaciones'
        self.report_path = None
        self._worker = None
        self._has_started = False
        self.setWindowTitle(f'Almacén · {ACTIONS[action].label} · Simulación')
        self.resize(1000, 650)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        title = QLabel(f'{ACTIONS[action].label} · {len(self.items)} OT')
        title.setStyleSheet('font-size: 20px; font-weight: 600')
        layout.addWidget(title)
        banner = QLabel('SIMULACIÓN · No se conecta con Edge ni se envían operaciones a Maximo. '
                        'Revisa las OTs antes de comenzar. Los estados mostrados proceden del listado local.')
        banner.setWordWrap(True)
        banner.setObjectName('filterHint')
        layout.addWidget(banner)
        options = QHBoxLayout()
        options.addWidget(QLabel('Escenario de prueba'))
        self.scenario = QComboBox()
        for key, label in SCENARIOS.items():
            self.scenario.addItem(label, key)
        options.addWidget(self.scenario)
        options.addStretch()
        layout.addLayout(options)
        self.table = QTableWidget(len(self.items), 6)
        self.table.setHorizontalHeaderLabels(('OT', 'Equipo / Nº de serie', 'Estado del listado',
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
        self.current_step = QLabel('Revisa la selección y pulsa «Iniciar simulación».')
        self.current_step.setWordWrap(True)
        layout.addWidget(self.current_step)
        self.steps = QLabel(' → '.join(STEPS))
        self.steps.setWordWrap(True)
        layout.addWidget(self.steps)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.items))
        self.progress_bar.setFormat('Procesadas %v de %m')
        layout.addWidget(self.progress_bar)
        self.summary = QLabel('El resultado real de las acciones de almacén todavía no está validado.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Iniciar simulación', objectName='primary')
        self.stop_button = QPushButton('Detener después de esta OT')
        self.stop_button.setEnabled(False)
        self.close_button = QPushButton('Cerrar')
        self.start_button.clicked.connect(self.start_simulation)
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

    def start_simulation(self):
        if self._has_started:
            return
        self._has_started = True
        self.start_button.setEnabled(False)
        self.start_button.setText('Simulación en curso')
        self.scenario.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._worker = SimulationThread(self.items, self.action, self.scenario.currentData(), self)
        self._worker.progress.connect(self._progress)
        self._worker.completed.connect(self._completed)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(lambda: self.stop_button.setEnabled(False))
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
        self.current_step.setText('Simulación finalizada. El reporte permanece disponible en esta ventana.')
        self.summary.setText(f'Simulación: {counts["success"]} correctas · {counts["failed"]} fallidas · '
                             f'{counts["uncertain"]} pendientes de verificar · {counts["stopped"]} sin procesar.')
        self.stop_button.setEnabled(False)
        self.start_button.setText('Simulación finalizada')
        try:
            self.report_path = save_simulation_report(self.report_folder, self.batch_id, self.action,
                                                      self.scenario.currentData(), results)
            self.summary.setToolTip(f'Reporte de simulación: {self.report_path}')
        except OSError:
            logging.exception('No se pudo guardar el reporte de simulación de almacén')
            self.summary.setText(self.summary.text() + ' No se pudo guardar el reporte en disco.')

    def _failed(self, message):
        # Preserve confirmed results if an unexpected simulator failure interrupts a batch.
        for index, result in enumerate(self.results):
            if result.status == 'running':
                self._progress(index, replace(result, status='failed', detail=message))
            elif result.status == 'pending':
                self._progress(index, replace(result, status='stopped', detail='No procesada: simulación interrumpida.'))
        self._completed(tuple(self.results))
        self.current_step.setText(f'Simulación interrumpida: {message}')

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
        if not getattr(self.cfg, 'warehouse_enabled', False):
            return
        items = self.warehouse_items()
        menu.addSeparator()
        receipt = menu.addMenu(f'Dar entrada · {len(items)} OT (simulación)')
        for action in RECEIPT_ACTIONS:
            receipt.addAction(ACTIONS[action].label + '…', lambda checked=False, a=action, selection=items:
                              self.open_warehouse_batch(selection, a))
        menu.addAction(f'{ACTIONS["dispatch"].label} · {len(items)} OT… (simulación)',
                       lambda checked=False, selection=items: self.open_warehouse_batch(selection, 'dispatch'))

    def open_warehouse_batch(self, items, action):
        if not getattr(self.cfg, 'warehouse_enabled', False) or getattr(self, '_closing', False):
            return
        dialogs = getattr(self, '_warehouse_dialogs', [])
        active = next((dialog for dialog in dialogs if dialog.is_running()), None)
        if active is not None:
            active.show(); active.raise_(); active.activateWindow()
            return
        dialog = WarehouseBatchDialog(items, action, self.open_ot_number, self)
        self._warehouse_dialogs = [*dialogs, dialog]
        dialog.show()

    def warehouse_is_running(self):
        return any(dialog.is_running() for dialog in getattr(self, '_warehouse_dialogs', []))
