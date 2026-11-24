from dataclasses import dataclass
from datetime import datetime
import json
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QPlainTextEdit,
)

from rounded_table import RoundedTableFrame
from warehouse import ACTIONS


@dataclass(frozen=True)
class Operation:
    ot: str
    action: str
    result: str
    step: str
    detail: str
    state: str
    at: datetime
    operation_id: str = ''
    pending: bool = False
    muted: bool = False


RESULTS = {
    'success': 'Verificada', 'already_done': 'Ya completada',
    'failed': 'Fallida', 'uncertain': 'Pendiente de comprobar',
    'stopped': 'Sin procesar', 'pending': 'Sin procesar',
}
PHASE_LABELS = {
    'preparing': 'Preparación',
    'route_attempted': 'Flujo de trabajo solicitado',
    'confirmation_attempted': 'Confirmación enviada',
    'details_attempted': 'Detalles enviados',
    'verified': 'Guardar resultado en MD',
}


def _operation_time(value, fallback):
    try:
        return datetime.fromisoformat(value).astimezone()
    except (TypeError, ValueError, OverflowError):
        return fallback


def _pending_row(record):
    verified = record.get('verified_status', '')
    phase = record['phase']
    step = PHASE_LABELS.get(phase, 'Comprobar resultado')
    if (phase == 'route_attempted' and record.get('start_attempted')
            and record.get('final_route_attempted') is False):
        step = 'Preparación tras solicitar el inicio'
    return Operation(
        ot=record['item']['ot'], action=record['action'],
        result='Pendiente de guardar' if verified else 'Pendiente de revisar',
        step=step, detail=record.get('last_error') or '', state=verified,
        at=_operation_time(record.get('updated_at') or record.get('created_at'),
                           datetime.now().astimezone()),
        operation_id=record['operation_id'], pending=True,
        muted=bool(record.get('mute_startup')),
    )


def read_operations(store, pending, *, history=False):
    if not history:
        return sorted((_pending_row(record) for record in pending), key=lambda row: row.at, reverse=True)

    rows = {}
    root = store.folder.parent
    sources = []
    for pattern in ('*-result.json', 'resueltas/*.json'):
        for path in root.glob(pattern):
            try:
                sources.append((path.stat().st_mtime, path))
            except OSError:
                continue
    for stamp, path in sorted(sources, reverse=True)[:150]:
        try:
            if path.stat().st_size > 8_000_000:
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('action') not in ACTIONS or data.get('simulation'):
                continue
            action = data['action']
            fallback = datetime.fromtimestamp(stamp).astimezone()
            if path.parent.name == 'resueltas':
                if data.get('resolution') != 'closed_elsewhere':
                    continue
                row = _pending_row(data)
                rows[row.operation_id] = Operation(
                    row.ot, action, 'Resuelta por otra vía', 'Revisión en Maximo',
                    row.detail, data.get('observed_status', ''), row.at, row.operation_id,
                )
                continue
            for index, result in enumerate(data['results']):
                identity = result['item']['ot']
                status = result['status']
                if not isinstance(identity, str) or not identity or status not in RESULTS:
                    continue
                operation_id = result.get('operation_id') or ''
                key = operation_id or (path.name, index)
                label = ('Pendiente de guardar' if result.get('local_status_saved') is False
                         else RESULTS[status])
                rows.setdefault(key, Operation(
                    identity, action, label, result.get('step', ''),
                    result.get('detail', ''), result.get('verified_status', ''),
                    _operation_time(data.get('recovered_at'), fallback), operation_id,
                ))
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            logging.debug('No se pudo leer el informe local %s', path.name, exc_info=True)
    for record in pending:
        row = _pending_row(record)
        rows[row.operation_id] = row
    return sorted(rows.values(), key=lambda row: (not row.pending, -row.at.timestamp()))


class OperationsDialog(QDialog):
    def __init__(self, parent, store, review, mute, pending_records):
        super().__init__(parent)
        self.store = store
        self.review = review
        self.mute = mute
        self.pending_records = pending_records
        self.rows = []
        self._all_rows = []
        self.setWindowTitle('Operaciones de Maximo')
        self.resize(950, 535)
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.view = QComboBox()
        self.view.addItems(('Pendientes', 'Historial reciente'))
        self.view.currentIndexChanged.connect(self.reload)
        tools.addWidget(self.view)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar por número de OT')
        self.search.textChanged.connect(self._render)
        tools.addWidget(self.search, 1)
        refresh = QPushButton('Actualizar')
        refresh.setToolTip('Volver a leer los resultados guardados en este equipo.')
        refresh.clicked.connect(self.reload)
        tools.addWidget(refresh)
        layout.addLayout(tools)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(('Fecha', 'OT', 'Operación', 'Resultado', 'Estado confirmado'))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setObjectName('workorderHeader')
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_details)
        layout.addWidget(RoundedTableFrame(self.table, self), 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.detail = QPlainTextEdit(readOnly=True)
        self.detail.setPlaceholderText('Selecciona una operación para ver el último paso.')
        self.detail.setMaximumHeight(90)
        layout.addWidget(self.detail)
        buttons = QHBoxLayout()
        self.mute_button = QPushButton('Silenciar aviso al iniciar')
        self.mute_button.clicked.connect(self._mute_current)
        buttons.addWidget(self.mute_button)
        buttons.addStretch()
        self.retry_button = QPushButton('Revisar y reintentar', objectName='primary')
        self.retry_button.clicked.connect(self._review_current)
        buttons.addWidget(self.retry_button)
        close = QPushButton('Cerrar')
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._update_details()

    def reload(self, *_):
        try:
            pending = self.pending_records()
            self._all_rows = read_operations(self.store, pending, history=self.view.currentIndex() == 1)
        except (OSError, ValueError, KeyError, RuntimeError):
            logging.exception('No se pudo leer el historial de operaciones')
            self._all_rows = []
            self._render()
            self.summary.setText('No se pudieron leer las operaciones guardadas.')
        else:
            self._render()

    def _render(self, *_):
        previous = self._current()
        query = self.search.text().strip()
        self.rows = [row for row in self._all_rows if query in row.ot]
        self.table.setRowCount(len(self.rows))
        selected = -1
        for index, row in enumerate(self.rows):
            values = (row.at.strftime('%d/%m/%Y %H:%M'), row.ot, ACTIONS[row.action].label, row.result, row.state or '—')
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
            if previous and row.operation_id and row.operation_id == previous.operation_id:
                selected = index
        if selected >= 0 or (self.rows and previous is None):
            self.table.selectRow(max(0, selected))
        else:
            self.table.setCurrentCell(-1, -1)
            self.table.clearSelection()
        self.summary.setText(
            f'{len(self.rows)} operaciones' if self.rows else
            'No hay operaciones que coincidan con el filtro.' if query else
            'No hay operaciones pendientes.' if self.view.currentIndex() == 0 else 'Todavía no hay operaciones en el historial.'
        )
        self._update_details()

    def _current(self):
        index = self.table.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _update_details(self):
        row = self._current()
        self.retry_button.setEnabled(bool(row and row.pending))
        self.mute_button.setEnabled(bool(row and row.pending and not row.muted))
        self.detail.setPlainText('\n'.join(part for part in (row.step, row.detail) if part) if row else '')

    def _review_current(self):
        row = self._current()
        if row and row.pending:
            self.review(row.ot, row.operation_id)

    def _mute_current(self):
        row = self._current()
        if row and row.pending:
            self.mute(row.ot, row.operation_id)
            self.reload()
