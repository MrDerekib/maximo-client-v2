"""Interfaz PySide6 en desarrollo para Maximo Desktop.

La lógica de Maximo y el almacenamiento permanecen en los módulos existentes.
Este archivo contiene solo la experiencia de escritorio nueva.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QPointF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCalendarWidget, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QCompleter, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QProgressDialog, QSpinBox, QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app_paths import APP_ROOT, BACKUP_DIR, CONFIG_PATH, DB_PATH, DOWNLOAD_DIR, EDGE_PROFILE_DIR, EXPORT_DIR, LOG_DIR
from config import AppConfig, credentials_configured, load_config, save_config
from db import (
    delete_all_inactive_records, delete_inactive_record, fetch_data, filter_choices,
    inactive_tracking_candidate_count, init_db, update_seguimiento,
)
from maximo_client import cleanup_edge_profile, open_ot, verify_credentials
from updater import reconcile_inactive_tracking, run_update
import version

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=(
        RotatingFileHandler(
            LOG_DIR / "maximo_client.log", maxBytes=5 * 1024 * 1024,
            backupCount=3, encoding="utf-8", delay=True,
        ),
        logging.StreamHandler(),
    ),
    force=True,
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.info("UI Preview v%s iniciada. Datos: %s", version.APP_VERSION, APP_ROOT)


STYLESHEET = """
QMainWindow { background: #f5f7fb; color: #172033; }
QFrame#sidebar { background: #102a43; }
QLabel#brand { color: white; font-size: 20px; font-weight: 700; }
QLabel#subtitle { color: #9fb3c8; font-size: 11px; }
QPushButton#nav { border: 1px solid transparent; border-radius: 8px; background: transparent; color: #e6f0ff; padding: 11px 14px; text-align: left; font-size: 13px; }
QPushButton#nav:hover:!checked { background: #1e446b; border-color: #315a82; color: white; }
QPushButton#nav:checked { background: #2f80ed; border-color: #4d9cff; color: white; font-weight: 700; }
QFrame#card, QGroupBox { background: white; border: 1px solid #d9e2ec; border-radius: 10px; }
QFrame#filtersCard { background: white; border: 1px solid #d9e2ec; border-radius: 10px; }
QFrame#advancedFilters { background: #f8fafc; border-top: 1px solid #d9e2ec; }
QLabel#filterHint { color: #627d98; font-size: 12px; }
QLabel#filterChips { color: #1976d2; font-size: 12px; font-weight: 600; }
QGroupBox { margin-top: 12px; padding: 12px; font-size: 16px; font-weight: 700; color: #334e68; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #102a43; }
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QLineEdit, QGroupBox QSpinBox { font-size: 12px; font-weight: 400; }
QGroupBox QPushButton { font-size: 12px; font-weight: 600; }
QLineEdit, QComboBox, QListWidget, QSpinBox { border: 1px solid #bcccdc; border-radius: 7px; padding: 7px 10px; background: white; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #2f80ed; }
QComboBox { padding-right: 36px; }
QComboBox:hover, QSpinBox:hover { border-color: #829ab1; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border-left: 1px solid #d9e2ec; background: #f8fafc; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QComboBox::drop-down:hover { background: #e8eef5; }
QComboBox QAbstractItemView { border: 1px solid #bcccdc; border-radius: 7px; padding: 4px; background: white; selection-background-color: #dbeafe; selection-color: #102a43; outline: 0; }
QSpinBox { padding-right: 34px; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 28px; background: #f8fafc; border-left: 1px solid #d9e2ec; }
QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 6px; border-bottom: 1px solid #d9e2ec; }
QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 6px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #e8eef5; }
QPushButton { border: 0; border-radius: 6px; padding: 8px 13px; background: #e8eef5; color: #243b53; font-weight: 600; }
QPushButton:hover { background: #d9e2ec; }
QPushButton#primary { background: #1976d2; color: white; }
QPushButton#primary:hover { background: #125ea7; }
QPushButton#danger { background: #fff1f0; color: #c53030; }
QTableWidget { background: white; border: 1px solid #d9e2ec; border-radius: 8px; gridline-color: #edf2f7; selection-background-color: #dbeafe; selection-color: #172033; }
QHeaderView::section { background: #f0f4f8; color: #486581; border: 0; border-right: 1px solid #cbd5e1; border-bottom: 1px solid #d9e2ec; padding: 9px; font-weight: 700; }
QHeaderView::section:hover { background: #e2e8f0; }
QStatusBar { background: white; border-top: 1px solid #d9e2ec; color: #486581; }
"""


class TaskSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class BackgroundTask(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            self.signals.completed.emit(self.function())
        except Exception as exc:  # El detalle completo queda en el log.
            logging.exception("Tarea de interfaz fallida")
            self.signals.failed.emit(str(exc))


def _draw_chevron(painter: QPainter, center_x: float, center_y: float, up: bool) -> None:
    """Dibuja una flecha nítida sin depender de temas ni rutas de recursos."""
    # En coordenadas Qt el eje Y crece hacia abajo: para la punta superior
    # el vértice central debe tener una Y menor que los extremos.
    offset = 2.5 if up else -2.5
    painter.drawLine(QPointF(center_x - 4, center_y + offset), QPointF(center_x, center_y - offset))
    painter.drawLine(QPointF(center_x, center_y - offset), QPointF(center_x + 4, center_y + offset))


class DecoratedComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#486581"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        _draw_chevron(painter, self.width() - 15, self.height() / 2, up=False)


class DecoratedSpinBox(QSpinBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#486581"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 14
        _draw_chevron(painter, x, self.height() * 0.30, up=True)
        _draw_chevron(painter, x, self.height() * 0.70, up=False)


class CalendarLineEdit(QLineEdit):
    """Fecha ISO que puede escribirse o elegirse desde un calendario."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("AAAA-MM-DD")
        self.setMaximumWidth(150)
        calendar_action = QAction("▾", self)
        calendar_action.setToolTip("Elegir fecha")
        calendar_action.triggered.connect(self._show_calendar)
        self.addAction(calendar_action, QLineEdit.TrailingPosition)

    def _show_calendar(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Seleccionar fecha")
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setGridVisible(True)
        try:
            calendar.setSelectedDate(QDate.fromString(self.text(), "yyyy-MM-dd"))
        except Exception:
            pass
        layout.addWidget(calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.setText(calendar.selectedDate().toString("yyyy-MM-dd"))


class AdvancedFiltersDialog(QDialog):
    """Filtros secundarios en un diálogo, sin fragmentar la barra de búsqueda."""
    def __init__(self, choices, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtros")
        self.setMinimumWidth(820)
        layout = QVBoxLayout(self)
        intro = QLabel("Refina el listado. Estos filtros se combinan con la búsqueda y el cliente.")
        intro.setObjectName("filterHint")
        layout.addWidget(intro)
        form = QGridLayout()
        self.equipment = QLineEdit(state.get("equipment", ""))
        self.equipment.setPlaceholderText("Descripción que contenga…")
        self.equipment.setCompleter(QCompleter(choices["equipment"], self))
        self.equipment.completer().setFilterMode(Qt.MatchContains)
        self.date_from, self.date_to = CalendarLineEdit(), CalendarLineEdit()
        self.date_from.setText(state.get("date_from", ""))
        self.date_to.setText(state.get("date_to", ""))
        for column, (label, widget) in enumerate((("Equipo / descripción", self.equipment), ("Desde", self.date_from), ("Hasta", self.date_to))):
            form.addWidget(QLabel(label), 0, column)
            form.addWidget(widget, 1, column)
        self.lists = {}
        for column, (key, label) in enumerate((("clients", "Clientes"), ("types", "Tipo de trabajo"), ("tracking", "Seguimiento"))):
            box = QListWidget()
            box.setSelectionMode(QListWidget.MultiSelection)
            box.setMinimumHeight(180)
            self.lists[key] = box
            for value in choices[key]:
                item = QListWidgetItem(value or "(Sin valor)")
                item.setData(Qt.UserRole, value)
                item.setSelected(value in state.get(key, []))
                box.addItem(item)
            form.addWidget(QLabel(label), 2, column)
            form.addWidget(box, 3, column)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        reset = buttons.addButton("Restablecer", QDialogButtonBox.ResetRole)
        reset.clicked.connect(self.reset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def reset(self):
        self.equipment.clear()
        self.date_from.clear()
        self.date_to.clear()
        for box in self.lists.values():
            box.clearSelection()

    def filters(self):
        return {
            "equipment": self.equipment.text().strip(),
            "date_from": self.date_from.text().strip(),
            "date_to": self.date_to.text().strip(),
            **{key: [item.data(Qt.UserRole) for item in box.selectedItems()] for key, box in self.lists.items()},
        }


class MaximoDesktopWindow(QMainWindow):
    columns = ("Estado en Maximo", "OT", "Descripción", "Nº de serie", "Fecha", "Cliente", "Tipo de trabajo", "Seguimiento", "Planta", "Última vez visto")
    max_column_widths = (180, 140, 600, 240, 160, 220, 220, 240, 160, 1200)
    close_progress = Signal(str)
    close_finished = Signal()

    def __init__(self):
        super().__init__()
        self.cfg: AppConfig = load_config()
        self.update_lock = threading.Lock()
        self.reconcile_lock = threading.Lock()
        self.pool = QThreadPool.globalInstance()
        self._running_tasks = set()
        self.ot_sessions = []
        self.advanced_state = {"equipment": "", "date_from": "", "date_to": "", "clients": [], "types": [], "tracking": []}
        self.filter_choices_cache = {"equipment": [], "clients": [], "types": [], "tracking": []}
        self._closing = False
        self._close_finalized = False
        self._restoring_column_widths = False
        self._column_widths = None
        self._column_resize_guard = False
        self._column_width_save_timer = QTimer(self)
        self._column_width_save_timer.setSingleShot(True)
        self._column_width_save_timer.timeout.connect(self._save_column_widths)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(lambda: self.update_now(automatic=True))
        self.close_progress.connect(self._set_close_progress)
        self.close_finished.connect(self._finish_close)
        self.setWindowTitle(f"Maximo Desktop · UI Preview · v{version.APP_VERSION}")
        self.setMinimumSize(1150, 700)
        self.resize(1500, 900)
        icon = Path(__file__).resolve().parent / "icon.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self._build_ui()
        init_db()
        self.refresh_choices()
        self.refresh_table()
        self._load_config()
        self._restore_window_state()
        self._restore_column_widths()
        QTimer.singleShot(0, self._fit_columns_to_viewport)
        self.schedule_auto_update()

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_list_page())
        self.pages.addWidget(self._build_settings_page())
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.status = QStatusBar()
        self.status.showMessage("Listo para consultar la base local.")
        self.setStatusBar(self.status)

    def _build_sidebar(self):
        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(226)
        box = QVBoxLayout(sidebar)
        box.setContentsMargins(16, 24, 16, 18)
        brand = QLabel("Maximo\nDesktop", objectName="brand")
        box.addWidget(brand)
        subtitle = QLabel("SEGUIMIENTO DE REPARACIONES", objectName="subtitle")
        box.addWidget(subtitle)
        box.addSpacing(30)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for index, (text, icon) in enumerate((("▦  Listado", ""), ("⚙  Configuración", ""))):
            button = QPushButton(text, objectName="nav", checkable=True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked, page=index: self.navigate_to(page))
            self.nav_group.addButton(button)
            self.nav_buttons[index] = button
            box.addWidget(button)
        box.addStretch(1)
        mode = QLabel("MODO DESARROLLO\nDatos aislados", objectName="subtitle")
        mode.setStyleSheet("padding: 10px; border: 1px solid #486581; border-radius: 8px;")
        box.addWidget(mode)
        return sidebar

    def _page_header(self, title, description, action=None):
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 24, 0, 12)
        texts = QVBoxLayout()
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 26px; font-weight: 700; color: #102a43;")
        texts.addWidget(heading)
        detail = QLabel(description)
        detail.setStyleSheet("color: #627d98;")
        texts.addWidget(detail)
        row.addLayout(texts)
        row.addStretch()
        if action:
            row.addWidget(action)
        return header

    def navigate_to(self, page: int) -> bool:
        """Cambia de sección sin perder ajustes aún no aplicados."""
        current = self.pages.currentIndex()
        if current == page:
            return True
        if current == 1 and page != 1 and self.settings_dirty():
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Cambios sin guardar")
            dialog.setText("Hay cambios de configuración que todavía no se han aplicado.")
            dialog.setInformativeText("¿Qué quieres hacer antes de volver al listado?")
            save = dialog.addButton("Guardar cambios", QMessageBox.AcceptRole)
            discard = dialog.addButton("Descartar", QMessageBox.DestructiveRole)
            cancel = dialog.addButton("Cancelar", QMessageBox.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is save:
                self.save_settings(show_feedback=False)
            elif dialog.clickedButton() is discard:
                self._load_config()
            else:
                self.nav_buttons[current].setChecked(True)
                return False
        self.pages.setCurrentIndex(page)
        self.nav_buttons[page].setChecked(True)
        return True

    def _build_list_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(30, 0, 30, 18)
        update = QPushButton("↻  Actualizar Maximo", objectName="primary")
        update.clicked.connect(self.update_now)
        outer.addWidget(self._page_header("Órdenes de trabajo", "Consulta, filtra y gestiona el seguimiento local.", update))

        search_card = QFrame(objectName="filtersCard")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(18, 14, 18, 14)
        search_layout.setSpacing(10)
        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(12)
        toolbar.addWidget(QLabel("Cliente"), 0, 0)
        self.client_combo = DecoratedComboBox()
        self.client_combo.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.client_combo, 1, 0)
        toolbar.addWidget(QLabel("Buscar"), 0, 1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Número de serie, OT o descripción…")
        self.search_edit.returnPressed.connect(self.refresh_table)
        toolbar.addWidget(self.search_edit, 1, 1)
        toolbar.addWidget(QLabel("Buscar por"), 0, 2)
        self.search_by_combo = DecoratedComboBox()
        self.search_by_combo.addItem("Nº de serie", "Nº_de_serie")
        self.search_by_combo.addItem("OT", "OT")
        self.search_by_combo.addItem("Descripción", "Descripción")
        self.search_by_combo.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.search_by_combo, 1, 2)
        self.filter_button = QPushButton("☷  Filtros")
        self.filter_button.clicked.connect(self.open_advanced_filters)
        toolbar.addWidget(self.filter_button, 1, 3)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.clicked.connect(self.clear_filters)
        self.clear_button.setVisible(False)
        toolbar.addWidget(self.clear_button, 1, 4)
        toolbar.setColumnStretch(1, 1)
        search_layout.addLayout(toolbar)
        self.filter_chips = QLabel("Sin filtros", objectName="filterChips")
        self.filter_chips.setVisible(False)
        search_layout.addWidget(self.filter_chips)

        outer.addWidget(search_card)

        self.result_label = QLabel()
        self.result_label.setStyleSheet("color: #627d98; padding: 5px 2px;")
        outer.addWidget(self.result_label)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(lambda row, _col: self.open_ot_for_row(row))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(60)
        header.setCursor(Qt.SplitHCursor)
        header.sectionResized.connect(self._column_resized)
        for column, width in enumerate((180, 110, 340, 145, 135, 140, 180, 130, 105, 140)):
            header.resizeSection(column, width)
        self._column_widths = self._current_column_widths()
        outer.addWidget(self.table, 1)
        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            QTimer.singleShot(0, self._fit_columns_to_viewport)

    def showEvent(self, event):
        super().showEvent(event)
        # La tabla conoce aquí su ancho final; restaurar antes hace que Qt
        # recalcule las secciones al mostrar la ventana.
        QTimer.singleShot(0, self._fit_columns_to_viewport)

    def _current_column_widths(self):
        header = self.table.horizontalHeader()
        return [max(60, header.sectionSize(index)) for index in range(len(self.columns))]

    def _fit_columns_to_viewport(self):
        if not self._column_widths or not self.table.viewport().width():
            return
        available = max(600, self.table.viewport().width())
        widths = [min(limit, max(60, int(width))) for width, limit in zip(self._column_widths, self.max_column_widths)]
        total = sum(widths)
        if total > available:
            scale = available / total
            widths = [max(60, int(round(width * scale))) for width in widths]
        # La última columna absorbe siempre el espacio restante para que no
        # quede una franja vacía al final de la tabla.
        widths[-1] = max(60, available - sum(widths[:-1]))
        self._restoring_column_widths = True
        try:
            header = self.table.horizontalHeader()
            for index, width in enumerate(widths):
                header.resizeSection(index, width)
        finally:
            self._restoring_column_widths = False

    def _column_resized(self, _logical_index, _old_size, _new_size):
        if self._column_resize_guard or self._restoring_column_widths:
            return
        header = self.table.horizontalHeader()
        if _new_size > self.max_column_widths[_logical_index]:
            self._column_resize_guard = True
            try:
                header.resizeSection(_logical_index, self.max_column_widths[_logical_index])
            finally:
                self._column_resize_guard = False
        last_column = len(self.columns) - 1
        if _logical_index != last_column:
            delta = header.sectionSize(_logical_index) - _old_size
            target = max(60, header.sectionSize(last_column) - delta)
            self._column_resize_guard = True
            try:
                header.resizeSection(last_column, target)
            finally:
                self._column_resize_guard = False
        else:
            target = max(60, self.table.viewport().width() - sum(header.sectionSize(index) for index in range(last_column)))
            self._column_resize_guard = True
            try:
                header.resizeSection(last_column, target)
            finally:
                self._column_resize_guard = False
        self._column_widths = self._current_column_widths()
        self._column_width_save_timer.start(400)

    def _restore_column_widths(self):
        widths = self.cfg.table_column_widths or {}
        if not widths or not self.cfg.table_layout_initialized:
            return
        values = []
        for index in range(len(self.columns)):
            value = widths.get(str(index), widths.get(index))
            try:
                values.append(max(0.01, float(value)))
            except (TypeError, ValueError):
                values.append(1.0)
        # Las primeras versiones de la preview guardaban proporciones. Se
        # convierten una vez a píxeles para conservar compatibilidad.
        if max(values) <= 1:
            reference_width = max(1150, self.table.viewport().width() or 1500)
            values = [max(60, int(round(value * reference_width))) for value in values]
        self._column_widths = values
        self._restoring_column_widths = True
        try:
            self._fit_columns_to_viewport()
        finally:
            self._restoring_column_widths = False

    def _save_column_widths(self):
        header = self.table.horizontalHeader()
        self.cfg.table_column_widths = {
            str(index): width for index, width in enumerate(self._current_column_widths())
        }
        self.cfg.table_layout_initialized = True
        save_config(self.cfg)
        logging.info("Anchos de columnas guardados.")

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 0, 30, 18)
        layout.addWidget(self._page_header("Configuración", "Acceso, actualización y mantenimiento de Maximo Desktop."))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(0, 0, 0, 20)

        access = QGroupBox("Acceso a Maximo")
        form = QFormLayout(access)
        self.user_edit = QLineEdit(); self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password)
        self.auto_check = QCheckBox("Actualizar el listado automáticamente")
        self.interval_spin = DecoratedSpinBox(); self.interval_spin.setRange(1, 1440); self.interval_spin.setSuffix(" min")
        form.addRow("Usuario", self.user_edit); form.addRow("Contraseña", self.password_edit)
        form.addRow("", self.auto_check); form.addRow("Intervalo", self.interval_spin)
        self.auto_update_summary = QLabel()
        self.auto_update_summary.setObjectName("filterHint")
        form.addRow("Estado", self.auto_update_summary)
        access_actions = QHBoxLayout()
        self.test_button = QPushButton("Probar y guardar credenciales")
        self.test_button.clicked.connect(self.test_credentials)
        access_actions.addWidget(self.test_button); access_actions.addStretch(); form.addRow(access_actions)
        body.addWidget(access)

        maintenance = QGroupBox("Mantenimiento")
        mform = QFormLayout(maintenance)
        self.reconcile_check = QCheckBox("Actualizar estados de OT no activas en segundo plano")
        self.batch_spin = DecoratedSpinBox(); self.batch_spin.setRange(1, 100); self.batch_spin.setSuffix(" OT")
        priority = QPushButton("Revisar todas las OT pendientes ahora")
        priority.clicked.connect(self.start_priority_reconcile)
        clean = QPushButton("Eliminar registros no activos…", objectName="danger")
        clean.clicked.connect(self.delete_all_inactive)
        mform.addRow("", self.reconcile_check); mform.addRow("Tamaño de lote", self.batch_spin); mform.addRow(priority); mform.addRow(clean)
        body.addWidget(maintenance)

        paths = QGroupBox("Datos de desarrollo")
        paths_form = QFormLayout(paths)
        for label, path in (("Carpeta principal", APP_ROOT), ("Base de datos", DB_PATH), ("Logs", LOG_DIR), ("Caché y perfiles Edge", EDGE_PROFILE_DIR), ("Copias de seguridad", BACKUP_DIR)):
            value = QLabel(str(path)); value.setTextInteractionFlags(Qt.TextSelectableByMouse); value.setWordWrap(True)
            paths_form.addRow(label, value)
        open_folder = QPushButton("Abrir carpeta de datos")
        open_folder.clicked.connect(self.open_data_folder)
        paths_form.addRow(open_folder)
        body.addWidget(paths)
        save_row = QHBoxLayout()
        save_hint = QLabel("Los cambios de esta página se aplican al guardar.")
        save_hint.setObjectName("filterHint")
        self.save_settings_button = QPushButton("Guardar cambios", objectName="primary")
        self.save_settings_button.clicked.connect(self.save_settings)
        save_row.addWidget(save_hint); save_row.addStretch(); save_row.addWidget(self.save_settings_button)
        body.addLayout(save_row)
        body.addStretch()
        scroll.setWidget(content); layout.addWidget(scroll, 1)
        return page

    def refresh_choices(self):
        choices = filter_choices()
        self.filter_choices_cache = choices
        current_client = self.client_combo.currentText() or "Todos"
        self.client_combo.blockSignals(True); self.client_combo.clear(); self.client_combo.addItems(["Todos", *choices["clients"]]); self.client_combo.setCurrentText(current_client); self.client_combo.blockSignals(False)

    def advanced_filters(self):
        return self.advanced_state

    def open_advanced_filters(self):
        dialog = AdvancedFiltersDialog(self.filter_choices_cache, self.advanced_state, self)
        if dialog.exec() == QDialog.Accepted:
            self.advanced_state = dialog.filters()
            self.refresh_table()

    def active_filter_summary(self):
        advanced = self.advanced_filters()
        summary = []
        if self.client_combo.currentText() != "Todos":
            summary.append(f"Cliente: {self.client_combo.currentText()}")
        if self.search_edit.text().strip():
            summary.append(f"{self.search_field().replace('_', ' ')}: {self.search_edit.text().strip()}")
        if advanced["equipment"]:
            summary.append(f"Equipo: {advanced['equipment']}")
        if advanced["date_from"] or advanced["date_to"]:
            summary.append(f"Fechas: {advanced['date_from'] or '…'} — {advanced['date_to'] or '…'}")
        for key, label in (("clients", "Clientes"), ("types", "Tipo"), ("tracking", "Seguimiento")):
            if advanced[key]:
                summary.append(f"{label}: {', '.join(advanced[key])}")
        return summary

    def search_field(self):
        return self.search_by_combo.currentData() or "Nº_de_serie"

    def refresh_table(self):
        try:
            rows = fetch_data(self.search_edit.text(), self.search_field(), self.client_combo.currentText(), self.advanced_filters(), include_sync=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Filtros", str(exc)); return
        def ot_sort_key(row):
            value = str(row[2] or "").strip()
            return (0, int(value)) if value.isdigit() else (1, value)
        rows.sort(key=ot_sort_key, reverse=True)
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for raw in rows:
            active, last_seen, *data = raw
            status = "✓ Activo en Maximo" if active == 1 else "× No activo en Maximo" if active == 0 else "? Estado desconocido"
            try: last_seen = datetime.fromisoformat(last_seen).strftime("%d/%m/%Y %H:%M") if last_seen else ""
            except (TypeError, ValueError): pass
            row = [status, *data, last_seen]
            index = self.table.rowCount(); self.table.insertRow(index)
            for column, value in enumerate(row):
                item = QTableWidgetItem(str(value or "")); item.setData(Qt.UserRole, raw[2])
                if column == 0:
                    item.setToolTip("Activo en Maximo: aparece en el listado de reparaciones y recibe actualizaciones.\nNo activo en Maximo: ya no aparece en ese listado y no recibe nuevas actualizaciones.")
                    item.setForeground(QColor("#2f855a" if active == 1 else "#718096"))
                elif active == 0:
                    item.setForeground(QColor("#718096"))
                self.table.setItem(index, column, item)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(1, Qt.DescendingOrder)
        summary = self.active_filter_summary()
        self.filter_chips.setVisible(bool(summary))
        self.filter_chips.setText("Filtros activos · " + "   •   ".join(summary))
        advanced_count = sum(bool(value) for value in self.advanced_state.values())
        self.filter_button.setText(f"☷  Filtros ({advanced_count})" if advanced_count else "☷  Filtros")
        self.clear_button.setVisible(bool(summary))
        self.result_label.setText(f"{len(rows):,} resultados · {'Filtros aplicados' if summary else 'Sin filtros'}")

    def clear_filters(self):
        self.search_edit.clear()
        self.client_combo.setCurrentText("Todos")
        self.advanced_state = {"equipment": "", "date_from": "", "date_to": "", "clients": [], "types": [], "tracking": []}
        self.refresh_table()

    def selected_ot(self, row=None):
        if row is None: row = self.table.currentRow()
        if row < 0: return None
        return self.table.item(row, 1).text()

    def show_context_menu(self, position):
        row = self.table.indexAt(position).row()
        if row < 0: return
        column = self.table.indexAt(position).column()
        self.table.selectRow(row); self.table.setCurrentCell(row, column); ot = self.selected_ot(row)
        menu = QMenu(self); menu.addAction("Copiar valor", lambda: QApplication.clipboard().setText(self.table.currentItem().text()))
        menu.addAction("Copiar OT", lambda: QApplication.clipboard().setText(ot))
        menu.addAction("Copiar número de serie", lambda: QApplication.clipboard().setText(self.table.item(row, 3).text()))
        menu.addSeparator(); menu.addAction("Abrir OT en Maximo", lambda: self.open_ot_for_row(row))
        tracking = menu.addMenu("Cambiar seguimiento")
        try: values = [line.strip() for line in (Path(__file__).resolve().parent / "seguimiento_options.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError: values = []
        for value in values: tracking.addAction(value, lambda new=value: self.change_tracking(ot, new))
        if self.table.item(row, 0).text() == "○ No activo":
            menu.addAction("Eliminar registro local…", lambda: self.delete_inactive(ot))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def change_tracking(self, ot, value):
        update_seguimiento(ot, value); self.refresh_table(); self.status.showMessage(f"OT {ot}: seguimiento actualizado a {value}.", 5000)

    def delete_inactive(self, ot):
        if QMessageBox.question(self, "Eliminar registro", f"¿Eliminar la OT no activa {ot} de la base local?") == QMessageBox.Yes:
            delete_inactive_record(ot); self.refresh_table()

    def delete_all_inactive(self):
        count = sum(1 for row in range(self.table.rowCount()) if self.table.item(row, 0).text() == "○ No activo")
        if QMessageBox.question(self, "Eliminar registros", f"¿Eliminar todos los registros no activos?\n\nSe eliminarán de la base local.") == QMessageBox.Yes:
            deleted = delete_all_inactive_records(); self.refresh_table(); self.status.showMessage(f"{deleted} registros no activos eliminados.", 5000)

    def _start_task(self, function, completed, failed=None):
        """Mantiene viva la señal de Qt hasta que la tarea responde.

        QThreadPool conserva el QRunnable nativo, pero no necesariamente el
        QObject de señales de Python. Retenerlo aquí evita perder la llamada de
        fin y dejar bloqueados los candados de Maximo.
        """
        task = BackgroundTask(function)
        self._running_tasks.add(task)

        def on_completed(result):
            try:
                completed(result)
            finally:
                self._running_tasks.discard(task)

        def on_failed(error):
            try:
                (failed or (lambda message: QMessageBox.critical(self, "Error", message)))(error)
            finally:
                self._running_tasks.discard(task)

        task.signals.completed.connect(on_completed)
        task.signals.failed.connect(on_failed)
        self.pool.start(task)

    def _credentials_ready(self):
        if credentials_configured(): return True
        QMessageBox.information(self, "Credenciales necesarias", "Configura y guarda las credenciales de Maximo antes de continuar.")
        self.navigate_to(1)
        return False

    def update_now(self, automatic=False):
        if not self._credentials_ready() or not self.update_lock.acquire(False): return
        self.status.showMessage("Actualizando listado desde Maximo…" if not automatic else "Actualización automática en curso…")
        def done(result):
            self.update_lock.release(); new, changed = result; self.refresh_choices(); self.refresh_table(); self.status.showMessage(f"Actualización completada: {new} nuevas, {changed} actualizadas.")
            self.start_background_reconcile()
        def failed(error): self.update_lock.release(); QMessageBox.critical(self, "Actualización", f"No se pudo actualizar:\n{error}"); self.status.showMessage("La actualización falló.")
        self._start_task(lambda: run_update(headless=True), done, failed)

    def start_background_reconcile(self):
        if not self.cfg.reconciliation_enabled or not self.reconcile_lock.acquire(False): return
        batch = self.cfg.reconciliation_batch_size; self.status.showMessage(f"Revisando hasta {batch} OT históricas en segundo plano…")
        def done(changed): self.reconcile_lock.release(); self.refresh_table(); self.status.showMessage(f"Conciliación finalizada: {changed} seguimientos actualizados.")
        def failed(error): self.reconcile_lock.release(); logging.warning("Conciliación fallida: %s", error); self.status.showMessage("La conciliación falló; consulta el log.")
        self._start_task(lambda: reconcile_inactive_tracking(limit=batch), done, failed)

    def start_priority_reconcile(self):
        if not self._credentials_ready(): return
        count = inactive_tracking_candidate_count(minimum_age_hours=None)
        if not count: QMessageBox.information(self, "Mantenimiento", "No hay OT no activas pendientes de revisar."); return
        if QMessageBox.question(self, "Revisión prioritaria", f"Se revisarán {count} OT. La operación puede tardar varios minutos.\n\n¿Continuar?") != QMessageBox.Yes: return
        if not self.update_lock.acquire(False): QMessageBox.information(self, "Mantenimiento", "Hay otra tarea de Maximo en curso."); return
        if not self.reconcile_lock.acquire(False):
            self.update_lock.release(); QMessageBox.information(self, "Mantenimiento", "Ya hay una revisión en curso."); return
        self.status.showMessage(f"Revisión prioritaria en curso: {count} OT…")
        def done(changed): self.reconcile_lock.release(); self.update_lock.release(); self.refresh_table(); QMessageBox.information(self, "Mantenimiento", f"Revisión completada. Seguimientos actualizados: {changed}.")
        def failed(error): self.reconcile_lock.release(); self.update_lock.release(); QMessageBox.critical(self, "Mantenimiento", error)
        self._start_task(lambda: reconcile_inactive_tracking(limit=None, minimum_age_hours=None), done, failed)

    def open_ot_for_row(self, row):
        ot = self.selected_ot(row)
        if not ot or not self._credentials_ready(): return
        self.status.showMessage(f"Abriendo OT {ot} en Maximo…")
        def done(session):
            if session: self.ot_sessions.append(session)
            self.status.showMessage(f"OT {ot} abierta en Microsoft Edge.")
        self._start_task(lambda: open_ot(ot, headless=False), done)

    def _load_config(self):
        self.user_edit.setText(self.cfg.username); self.password_edit.setText(self.cfg.password)
        self.auto_check.setChecked(self.cfg.auto_update_enabled); self.interval_spin.setValue(self.cfg.auto_update_interval_min)
        self.reconcile_check.setChecked(self.cfg.reconciliation_enabled); self.batch_spin.setValue(self.cfg.reconciliation_batch_size)
        self._refresh_auto_update_summary()

    def _restore_window_state(self):
        if self.cfg.window_size:
            try:
                width, height = (int(value) for value in self.cfg.window_size)
                self.resize(max(self.minimumWidth(), width), max(self.minimumHeight(), height))
            except (TypeError, ValueError):
                pass
        if self.cfg.window_maximized:
            self.showMaximized()

    def _save_window_state(self):
        self._column_width_save_timer.stop()
        self.cfg.table_column_widths = {
            str(index): width for index, width in enumerate(self._current_column_widths())
        }
        self.cfg.table_layout_initialized = True
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.cfg.window_size = [geometry.width(), geometry.height()]
        self.cfg.window_maximized = self.isMaximized()
        save_config(self.cfg)
        logging.info("Estado de ventana y anchos de columnas guardados.")

    def settings_dirty(self):
        return (
            self.user_edit.text().strip() != self.cfg.username
            or self.password_edit.text() != self.cfg.password
            or self.auto_check.isChecked() != self.cfg.auto_update_enabled
            or self.interval_spin.value() != self.cfg.auto_update_interval_min
            or self.reconcile_check.isChecked() != self.cfg.reconciliation_enabled
            or self.batch_spin.value() != self.cfg.reconciliation_batch_size
        )

    def save_settings(self, show_feedback=True):
        self.cfg.username = self.user_edit.text().strip(); self.cfg.password = self.password_edit.text(); self.cfg.auto_update_enabled = self.auto_check.isChecked(); self.cfg.auto_update_interval_min = self.interval_spin.value(); self.cfg.reconciliation_enabled = self.reconcile_check.isChecked(); self.cfg.reconciliation_batch_size = self.batch_spin.value()
        save_config(self.cfg)
        self.schedule_auto_update()
        self._refresh_auto_update_summary()
        logging.info(
            "Configuración UI guardada: auto_update=%s, intervalo=%d, conciliación=%s, lote=%d.",
            self.cfg.auto_update_enabled, self.cfg.auto_update_interval_min,
            self.cfg.reconciliation_enabled, self.cfg.reconciliation_batch_size,
        )
        if show_feedback:
            QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
        self.status.showMessage("Configuración guardada y aplicada.", 4000)

    def _refresh_auto_update_summary(self):
        if self.cfg.auto_update_enabled:
            self.auto_update_summary.setText(
                f"Activa: próxima comprobación en {self.cfg.auto_update_interval_min} min."
            )
        else:
            self.auto_update_summary.setText("Desactivada: no se programarán nuevas actualizaciones.")

    def schedule_auto_update(self):
        self.auto_timer.stop()
        if self.cfg.auto_update_enabled:
            self.auto_timer.start(self.cfg.auto_update_interval_min * 60 * 1000)
            logging.info("Actualización automática UI programada cada %d min.", self.cfg.auto_update_interval_min)
        else:
            logging.info("Actualización automática UI desactivada.")

    def test_credentials(self):
        user, password = self.user_edit.text().strip(), self.password_edit.text()
        if not user or not password: QMessageBox.warning(self, "Credenciales", "Introduce usuario y contraseña."); return
        self.test_button.setEnabled(False); self.status.showMessage("Comprobando credenciales…")
        def done(_):
            self.test_button.setEnabled(True)
            self.cfg.username, self.cfg.password = user, password
            save_config(self.cfg)
            logging.info("Credenciales UI verificadas y guardadas.")
            self.status.showMessage("Credenciales verificadas y guardadas.")
            QMessageBox.information(
                self, "Credenciales válidas",
                "El acceso a Maximo se ha comprobado y las credenciales se han guardado.\n\n"
                "Los demás cambios de la página siguen pendientes hasta pulsar «Guardar cambios»."
            )
        def failed(error): self.test_button.setEnabled(True); QMessageBox.critical(self, "No se pudo comprobar el acceso", error)
        self._start_task(lambda: verify_credentials(user, password), done, failed)

    def open_data_folder(self):
        APP_ROOT.mkdir(parents=True, exist_ok=True)
        try: os.startfile(str(APP_ROOT))
        except AttributeError: webbrowser.open(APP_ROOT.as_uri())

    def closeEvent(self, event):
        if self._close_finalized:
            event.accept()
            return
        event.ignore()
        if self._closing:
            return
        self._closing = True
        self._save_window_state()
        self.auto_timer.stop()
        self.close_dialog = QProgressDialog("Preparando cierre ordenado…", None, 0, 0, self)
        self.close_dialog.setWindowTitle("Cerrando Maximo Desktop")
        self.close_dialog.setWindowModality(Qt.ApplicationModal)
        self.close_dialog.setCancelButton(None)
        self.close_dialog.setMinimumDuration(0)
        self.close_dialog.setAutoClose(False)
        self.close_dialog.show()
        threading.Thread(target=self._close_worker, daemon=True).start()

    def _set_close_progress(self, message):
        if hasattr(self, "close_dialog"):
            self.close_dialog.setLabelText(message)

    def _close_worker(self):
        started = time.monotonic()
        labels = (
            (self.update_lock, "Esperando a que termine la actualización de Maximo…"),
            (self.reconcile_lock, "Esperando a que termine la conciliación de OT…"),
        )
        while pending := [label for lock, label in labels if lock.locked()]:
            self.close_progress.emit(pending[0])
            time.sleep(0.25)
        sessions = list(self.ot_sessions)
        for index, (driver, profile) in enumerate(sessions, start=1):
            self.close_progress.emit(f"Cerrando sesión de Edge {index} de {len(sessions)}…")
            try:
                driver.quit()
            except Exception:
                logging.warning("No se pudo cerrar una sesión Edge", exc_info=True)
            self.close_progress.emit(f"Eliminando perfil temporal de Edge {index} de {len(sessions)}…")
            try:
                cleanup_edge_profile(profile)
            except Exception:
                logging.warning("No se pudo eliminar un perfil Edge", exc_info=True)
        remaining = 0.8 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
        self.close_finished.emit()

    def _finish_close(self):
        self.close_progress.emit("Cierre completado.")
        if hasattr(self, "close_dialog"):
            self.close_dialog.close()
        self._close_finalized = True
        self.close()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Maximo Desktop")
    app.setStyleSheet(STYLESHEET)
    window = MaximoDesktopWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
