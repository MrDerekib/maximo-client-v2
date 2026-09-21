"""Interfaz PySide6 en desarrollo para Maximo Desktop.

La lógica de Maximo y el almacenamiento permanecen en los módulos existentes.
Este archivo contiene solo la experiencia de escritorio nueva.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCalendarWidget, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem,
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
QGroupBox { margin-top: 12px; padding: 12px; font-weight: 600; color: #334e68; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QLineEdit, QComboBox, QListWidget, QSpinBox { border: 1px solid #bcccdc; border-radius: 6px; padding: 7px; background: white; min-height: 18px; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #2f80ed; }
QPushButton { border: 0; border-radius: 6px; padding: 8px 13px; background: #e8eef5; color: #243b53; font-weight: 600; }
QPushButton:hover { background: #d9e2ec; }
QPushButton#primary { background: #1976d2; color: white; }
QPushButton#primary:hover { background: #125ea7; }
QPushButton#danger { background: #fff1f0; color: #c53030; }
QTableWidget { background: white; border: 1px solid #d9e2ec; border-radius: 8px; gridline-color: #edf2f7; selection-background-color: #dbeafe; selection-color: #172033; }
QHeaderView::section { background: #f0f4f8; color: #486581; border: 0; border-bottom: 1px solid #d9e2ec; padding: 9px; font-weight: 700; }
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


class MaximoDesktopWindow(QMainWindow):
    columns = ("Sincronización", "OT", "Descripción", "Nº de serie", "Fecha", "Cliente", "Tipo de trabajo", "Seguimiento", "Planta", "Última vez visto")

    def __init__(self):
        super().__init__()
        self.cfg: AppConfig = load_config()
        self.update_lock = threading.Lock()
        self.reconcile_lock = threading.Lock()
        self.pool = QThreadPool.globalInstance()
        self.ot_sessions = []
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(lambda: self.update_now(automatic=True))
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
        for index, (text, icon) in enumerate((("▦  Listado", ""), ("⚙  Configuración", ""))):
            button = QPushButton(text, objectName="nav", checkable=True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked, page=index: self.pages.setCurrentIndex(page))
            self.nav_group.addButton(button)
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

    def _build_list_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(30, 0, 30, 18)
        update = QPushButton("↻  Actualizar Maximo", objectName="primary")
        update.clicked.connect(self.update_now)
        outer.addWidget(self._page_header("Órdenes de trabajo", "Consulta, filtra y gestiona el seguimiento local.", update))

        search_card = QFrame(objectName="filtersCard")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(18, 14, 18, 0)
        search_layout.setSpacing(10)
        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(12)
        toolbar.addWidget(QLabel("Cliente"), 0, 0)
        self.client_combo = QComboBox()
        self.client_combo.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.client_combo, 1, 0)
        toolbar.addWidget(QLabel("Buscar"), 0, 1)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Número de serie, OT o descripción…")
        self.search_edit.returnPressed.connect(self.refresh_table)
        toolbar.addWidget(self.search_edit, 1, 1)
        self.search_group = QButtonGroup(self)
        search_types = QWidget()
        types_layout = QHBoxLayout(search_types)
        types_layout.setContentsMargins(0, 0, 0, 0)
        for index, label in enumerate(("Nº de serie", "OT", "Descripción")):
            button = QPushButton(label, checkable=True)
            button.setProperty("field", ("Nº_de_serie", "OT", "Descripción")[index])
            button.setChecked(index == 0)
            button.clicked.connect(self.refresh_table)
            self.search_group.addButton(button)
            types_layout.addWidget(button)
        toolbar.addWidget(search_types, 1, 2)
        search_button = QPushButton("Buscar")
        search_button.clicked.connect(self.refresh_table)
        toolbar.addWidget(search_button, 1, 3)
        self.more_filters_button = QPushButton("☷  Más filtros", checkable=True)
        self.more_filters_button.toggled.connect(self.toggle_advanced_filters)
        toolbar.addWidget(self.more_filters_button, 1, 4)
        clear_button = QPushButton("Limpiar")
        clear_button.clicked.connect(self.clear_filters)
        toolbar.addWidget(clear_button, 1, 5)
        toolbar.setColumnStretch(1, 1)
        search_layout.addLayout(toolbar)
        self.filter_chips = QLabel("Sin filtros", objectName="filterChips")
        self.filter_chips.setVisible(False)
        search_layout.addWidget(self.filter_chips)

        self.advanced_content = QFrame(objectName="advancedFilters")
        form = QGridLayout(self.advanced_content)
        form.setContentsMargins(18, 14, 18, 14)
        form.setHorizontalSpacing(14)
        self.equipment_edit = QLineEdit()
        self.equipment_edit.setPlaceholderText("Contiene texto…")
        self.equipment_edit.returnPressed.connect(self.refresh_table)
        self.date_from = CalendarLineEdit()
        self.date_to = CalendarLineEdit()
        form.addWidget(QLabel("Equipo / descripción"), 0, 0)
        form.addWidget(QLabel("Desde"), 0, 1)
        form.addWidget(QLabel("Hasta"), 0, 2)
        form.addWidget(self.equipment_edit, 1, 0)
        form.addWidget(self.date_from, 1, 1)
        form.addWidget(self.date_to, 1, 2)
        self.filter_lists = {}
        for column, (key, label) in enumerate((("clients", "Clientes"), ("types", "Tipo de trabajo"), ("tracking", "Seguimiento"))):
            widget = QListWidget()
            widget.setSelectionMode(QListWidget.MultiSelection)
            widget.setMaximumHeight(116)
            self.filter_lists[key] = widget
            form.addWidget(QLabel(label), 2, column)
            form.addWidget(widget, 3, column)
        actions = QHBoxLayout()
        apply = QPushButton("Aplicar filtros", objectName="primary")
        apply.clicked.connect(self.refresh_table)
        actions.addWidget(QLabel("Combina cualquier filtro con la búsqueda principal.", objectName="filterHint")); actions.addStretch(); actions.addWidget(apply)
        form.addLayout(actions, 4, 0, 1, 3)
        self.advanced_content.setVisible(False)
        search_layout.addWidget(self.advanced_content)
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
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for column in range(len(self.columns)):
            if column != 2:
                header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        outer.addWidget(self.table, 1)
        return page

    def toggle_advanced_filters(self, expanded):
        self.advanced_content.setVisible(expanded)
        self.more_filters_button.setText("⌃  Ocultar filtros" if expanded else "☷  Más filtros")

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.addWidget(self._page_header("Configuración", "Acceso, actualización y mantenimiento de Maximo Desktop."))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); body = QVBoxLayout(content); body.setContentsMargins(30, 0, 30, 20)

        access = QGroupBox("Acceso a Maximo")
        form = QFormLayout(access)
        self.user_edit = QLineEdit(); self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password)
        self.auto_check = QCheckBox("Actualizar el listado automáticamente")
        self.interval_spin = QSpinBox(); self.interval_spin.setRange(1, 1440); self.interval_spin.setSuffix(" min")
        form.addRow("Usuario", self.user_edit); form.addRow("Contraseña", self.password_edit)
        form.addRow("", self.auto_check); form.addRow("Intervalo", self.interval_spin)
        access_actions = QHBoxLayout(); save = QPushButton("Guardar configuración", objectName="primary"); save.clicked.connect(self.save_settings)
        self.test_button = QPushButton("Probar credenciales"); self.test_button.clicked.connect(self.test_credentials)
        access_actions.addWidget(save); access_actions.addWidget(self.test_button); access_actions.addStretch(); form.addRow(access_actions)
        body.addWidget(access)

        maintenance = QGroupBox("Mantenimiento")
        mform = QFormLayout(maintenance)
        self.reconcile_check = QCheckBox("Actualizar estados de OT no activas en segundo plano")
        self.batch_spin = QSpinBox(); self.batch_spin.setRange(1, 100); self.batch_spin.setSuffix(" OT")
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
        body.addWidget(paths); body.addStretch()
        scroll.setWidget(content); layout.addWidget(scroll, 1)
        return page

    def refresh_choices(self):
        choices = filter_choices()
        current_client = self.client_combo.currentText() or "Todos"
        self.client_combo.blockSignals(True); self.client_combo.clear(); self.client_combo.addItems(["Todos", *choices["clients"]]); self.client_combo.setCurrentText(current_client); self.client_combo.blockSignals(False)
        self.equipment_edit.setCompleter(__import__("PySide6.QtWidgets", fromlist=["QCompleter"]).QCompleter(choices["equipment"], self))
        self.equipment_edit.completer().setFilterMode(Qt.MatchContains)
        for key, box in self.filter_lists.items():
            selected = {item.text() for item in box.selectedItems()}
            box.clear()
            for value in choices[key]:
                item = QListWidgetItem(value or "(Sin valor)"); item.setData(Qt.UserRole, value); box.addItem(item)
                item.setSelected(value in selected)

    def advanced_filters(self):
        values = {key: [item.data(Qt.UserRole) for item in box.selectedItems()] for key, box in self.filter_lists.items()}
        values.update({"equipment": self.equipment_edit.text().strip(), "date_from": self.date_from.text().strip(), "date_to": self.date_to.text().strip()})
        return values

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
        selected = self.search_group.checkedButton()
        return selected.property("field") if selected else "Nº_de_serie"

    def refresh_table(self):
        try:
            rows = fetch_data(self.search_edit.text(), self.search_field(), self.client_combo.currentText(), self.advanced_filters(), include_sync=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Filtros", str(exc)); return
        rows.sort(key=lambda row: row[2], reverse=True)
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for raw in rows:
            active, last_seen, *data = raw
            status = "● Activo" if active == 1 else "○ No activo" if active == 0 else "—"
            try: last_seen = datetime.fromisoformat(last_seen).strftime("%d/%m/%Y %H:%M") if last_seen else ""
            except (TypeError, ValueError): pass
            row = [status, *data, last_seen]
            index = self.table.rowCount(); self.table.insertRow(index)
            for column, value in enumerate(row):
                item = QTableWidgetItem(str(value or "")); item.setData(Qt.UserRole, raw[2])
                if active == 0: item.setForeground(QColor("#718096"))
                self.table.setItem(index, column, item)
        self.table.setSortingEnabled(True)
        summary = self.active_filter_summary()
        self.filter_chips.setVisible(bool(summary))
        self.filter_chips.setText("Filtros activos · " + "   •   ".join(summary))
        self.result_label.setText(f"{len(rows):,} resultados · {'Filtros aplicados' if summary else 'Sin filtros'}")

    def clear_filters(self):
        self.search_edit.clear(); self.client_combo.setCurrentText("Todos"); self.equipment_edit.clear(); self.date_from.clear(); self.date_to.clear()
        for box in self.filter_lists.values(): box.clearSelection()
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
        task = BackgroundTask(function); task.signals.completed.connect(completed)
        task.signals.failed.connect(failed or (lambda error: QMessageBox.critical(self, "Error", error)))
        self.pool.start(task)

    def _credentials_ready(self):
        if credentials_configured(): return True
        QMessageBox.information(self, "Credenciales necesarias", "Configura y guarda las credenciales de Maximo antes de continuar.")
        self.pages.setCurrentIndex(1); return False

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

    def save_settings(self):
        self.cfg.username = self.user_edit.text().strip(); self.cfg.password = self.password_edit.text(); self.cfg.auto_update_enabled = self.auto_check.isChecked(); self.cfg.auto_update_interval_min = self.interval_spin.value(); self.cfg.reconciliation_enabled = self.reconcile_check.isChecked(); self.cfg.reconciliation_batch_size = self.batch_spin.value()
        save_config(self.cfg); self.schedule_auto_update(); QMessageBox.information(self, "Configuración", "Configuración guardada correctamente."); self.status.showMessage("Configuración guardada.", 4000)

    def schedule_auto_update(self):
        self.auto_timer.stop()
        if self.cfg.auto_update_enabled:
            self.auto_timer.start(self.cfg.auto_update_interval_min * 60 * 1000)

    def test_credentials(self):
        user, password = self.user_edit.text().strip(), self.password_edit.text()
        if not user or not password: QMessageBox.warning(self, "Credenciales", "Introduce usuario y contraseña."); return
        self.test_button.setEnabled(False); self.status.showMessage("Comprobando credenciales…")
        def done(_): self.test_button.setEnabled(True); self.status.showMessage("Credenciales verificadas."); QMessageBox.information(self, "Credenciales válidas", "Acceso a Maximo comprobado. La prueba no guarda cambios.")
        def failed(error): self.test_button.setEnabled(True); QMessageBox.critical(self, "No se pudo comprobar el acceso", error)
        self._start_task(lambda: verify_credentials(user, password), done, failed)

    def open_data_folder(self):
        APP_ROOT.mkdir(parents=True, exist_ok=True)
        try: os.startfile(str(APP_ROOT))
        except AttributeError: webbrowser.open(APP_ROOT.as_uri())

    def closeEvent(self, event):
        for session in self.ot_sessions:
            try:
                driver, profile = session; driver.quit(); cleanup_edge_profile(profile)
            except Exception: logging.warning("No se pudo cerrar una sesión Edge", exc_info=True)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Maximo Desktop")
    app.setStyleSheet(STYLESHEET)
    window = MaximoDesktopWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
