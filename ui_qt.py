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
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QDate, QObject, QPointF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCalendarWidget, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QCompleter, QDateEdit, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QProgressDialog, QSizePolicy, QSpinBox, QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QWidgetAction,
)

from app_paths import APP_ROOT, BACKUP_DIR, CONFIG_PATH, DB_PATH, DOWNLOAD_DIR, EDGE_PROFILE_DIR, EXPORT_DIR, LOG_DIR, PROFILES_PATH
from config import AppConfig, credentials_configured, load_config, save_config
from db import (
    clear_current_priority_snapshot, current_priority_ots, current_priority_snapshots,
    delete_all_inactive_records, delete_inactive_record, fetch_data, filter_choices,
    fault_description_candidate_count, inactive_tracking_candidate_count, init_db, update_seguimiento,
    replace_priority_snapshot, update_priority_expiration,
)
from maximo_client import cleanup_edge_profile, open_ot, verify_credentials
from updater import enrich_fault_descriptions, reconcile_inactive_tracking, run_update
from search_filters import load_profiles, save_profiles
from update_checker import fetch_latest_release, format_version_tag, is_newer
from priority_importer import read_priority_files
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
QLabel#sidebarSection { color: #9fb3c8; font-size: 10px; font-weight: 700; padding: 0 4px; }
QListWidget#profileList { background: #163854; border: 1px solid #315a82; border-radius: 7px; color: #e6f0ff; padding: 4px; outline: 0; }
QListWidget#profileList::item { padding: 7px 8px; border-radius: 5px; }
QListWidget#profileList::item:hover { background: #1e446b; }
QListWidget#profileList::item:selected { background: #2f80ed; color: white; }
QPushButton#sidebarAction { background: #1e446b; border: 1px solid #315a82; color: #e6f0ff; text-align: left; padding: 7px 10px; }
QPushButton#sidebarAction:hover { background: #315a82; color: white; }
QFrame#card, QGroupBox { background: #ffffff; border: 1px solid #d9e2ec; border-radius: 10px; }
QFrame#filtersCard { background: #ffffff; border: 1px solid #d9e2ec; border-radius: 10px; }
QFrame#advancedFilters { background: #f8fafc; border-top: 1px solid #d9e2ec; }
QWidget#settingsContent { background: #f5f7fb; }
QLabel#filterHint { color: #627d98; font-size: 12px; }
QLabel#filterChips { color: #1976d2; font-size: 12px; font-weight: 600; }
QLabel#developmentMode { color: #9fb3c8; padding: 10px; border: 1px solid #486581; border-radius: 8px; }
QLabel#pageTitle { font-size: 26px; font-weight: 700; color: #102a43; }
QLabel#pageSubtitle, QLabel#resultLabel { color: #627d98; }
QLabel#resultLabel { padding: 5px 2px; }
QGroupBox { margin-top: 12px; padding: 12px; font-size: 16px; font-weight: 700; color: #334e68; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #102a43; }
QGroupBox QLabel, QGroupBox QCheckBox { font-size: 12px; font-weight: 400; color: #172033; }
QGroupBox QLineEdit, QGroupBox QSpinBox { font-size: 12px; font-weight: 400; color: #172033; }
QGroupBox QPushButton { font-size: 12px; font-weight: 600; }
QLineEdit, QComboBox, QListWidget, QSpinBox, QDateEdit { border: 1px solid #bcccdc; border-radius: 7px; padding: 7px 10px; background: #ffffff; color: #172033; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus { border: 2px solid #2f80ed; }
QComboBox { padding-right: 36px; }
QComboBox:hover, QSpinBox:hover, QDateEdit:hover { border-color: #829ab1; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border-left: 1px solid #d9e2ec; background: #f8fafc; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QComboBox::drop-down:hover { background: #e8eef5; }
QComboBox QAbstractItemView { border: 1px solid #bcccdc; border-radius: 7px; padding: 4px; background: #ffffff; color: #172033; selection-background-color: #dbeafe; selection-color: #102a43; outline: 0; }
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
QPushButton#multiSelect { border: 1px solid #bcccdc; border-radius: 7px; padding: 7px 10px; background: #ffffff; min-height: 18px; text-align: left; font-weight: 400; }
QPushButton#multiSelect:hover { border-color: #829ab1; background: #f8fafc; }
QTableWidget { background: #ffffff; border: 1px solid #d9e2ec; border-radius: 8px; gridline-color: #edf2f7; selection-background-color: #dbeafe; selection-color: #172033; }
QHeaderView::section { background: #f0f4f8; color: #486581; border: 0; border-right: 1px solid #cbd5e1; border-bottom: 1px solid #d9e2ec; padding: 9px; font-weight: 700; }
QHeaderView::section:hover { background: #e2e8f0; }
QTableCornerButton::section { background: #f0f4f8; border: 0; border-right: 1px solid #cbd5e1; border-bottom: 1px solid #d9e2ec; }
QStatusBar { background: #ffffff; border-top: 1px solid #d9e2ec; color: #486581; }
"""

# Toda la interfaz parte de estos roles, no de colores de Windows.  Mantener
# la paleta aquí permite que claro y oscuro cambien de forma coherente.
THEME_PALETTES = {
    "light": {
        "canvas": "#f5f7fb", "surface": "#ffffff", "subtle": "#f8fafc", "text": "#172033",
        "heading": "#102a43", "muted": "#627d98", "border": "#d9e2ec", "border_strong": "#bcccdc",
        "control": "#e8eef5", "hover": "#d9e2ec", "accent": "#1976d2", "accent_hover": "#125ea7",
        "accent_light": "#dbeafe", "sidebar": "#102a43", "sidebar_surface": "#163854",
        "sidebar_hover": "#1e446b", "nav": "#2f80ed", "nav_border": "#4d9cff",
        "sidebar_text": "#e6f0ff", "sidebar_muted": "#9fb3c8", "danger_bg": "#fff1f0",
        "danger": "#c53030", "grid": "#edf2f7", "header": "#f0f4f8", "header_text": "#486581",
        "header_hover": "#e2e8f0", "separator": "#cbd5e1", "soft_border": "#829ab1",
        "check_hover": "#eef5ff", "success": "#2f855a", "inactive": "#718096",
        "priority": "#b7791f", "button_text": "#243b53",
    },
    "dark": {
        "canvas": "#121a26", "surface": "#1b2635", "subtle": "#223044", "text": "#edf2f7",
        "heading": "#f7fafc", "muted": "#a8bed4", "border": "#344861", "border_strong": "#526b86",
        "control": "#2a3b50", "hover": "#334a63", "accent": "#4595f5", "accent_hover": "#74b4ff",
        "accent_light": "#244d78", "sidebar": "#0b1828", "sidebar_surface": "#142d47",
        "sidebar_hover": "#204969", "nav": "#287ce4", "nav_border": "#67a8ff",
        "sidebar_text": "#f3f7fc", "sidebar_muted": "#adc6df", "danger_bg": "#512c33",
        "danger": "#ff9a9a", "grid": "#2a3b50", "header": "#233247", "header_text": "#aac4dd",
        "header_hover": "#30465e", "separator": "#45617c", "soft_border": "#7190ae",
        "check_hover": "#294b6f", "success": "#60d394", "inactive": "#a0b5c8",
        "priority": "#f6c85f", "button_text": "#e6eef8",
    },
}
_LIGHT_HEX_ROLES = {
    "#f5f7fb": "canvas", "#ffffff": "surface", "#f8fafc": "subtle",
    "#172033": "text", "#102a43": "heading", "#627d98": "muted", "#d9e2ec": "border",
    "#bcccdc": "border_strong", "#e8eef5": "control", "#1976d2": "accent", "#125ea7": "accent_hover",
    "#dbeafe": "accent_light", "#163854": "sidebar_surface", "#1e446b": "sidebar_hover",
    "#2f80ed": "nav", "#4d9cff": "nav_border", "#e6f0ff": "sidebar_text", "#9fb3c8": "sidebar_muted",
    "#fff1f0": "danger_bg", "#c53030": "danger", "#edf2f7": "grid", "#f0f4f8": "header",
    "#486581": "header_text", "#e2e8f0": "header_hover", "#cbd5e1": "separator",
    "#829ab1": "soft_border", "#eef5ff": "check_hover", "#2f855a": "success",
    "#718096": "inactive", "#b7791f": "priority", "#243b53": "button_text",
}
ACTIVE_THEME = "light"
ACTIVE_COLORS = THEME_PALETTES[ACTIVE_THEME]


def _resolve_theme(preference: str) -> str:
    if preference in {"light", "dark"}:
        return preference
    try:
        scheme = QApplication.styleHints().colorScheme()
        return "dark" if "dark" in str(scheme).lower() else "light"
    except Exception:
        return "light"


def _theme_css(css: str, colors=None) -> str:
    colors = colors or ACTIVE_COLORS
    for source, role in _LIGHT_HEX_ROLES.items():
        css = css.replace(source, colors[role])
    # El azul oscuro se usaba tanto para el encabezado como para la barra
    # lateral; en oscuro son superficies distintas.
    css = css.replace(f"QFrame#sidebar {{ background: {colors['heading']}; }}", f"QFrame#sidebar {{ background: {colors['sidebar']}; }}")
    return css


def apply_application_theme(app, preference: str) -> str:
    global ACTIVE_THEME, ACTIVE_COLORS
    ACTIVE_THEME = _resolve_theme(preference)
    ACTIVE_COLORS = THEME_PALETTES[ACTIVE_THEME]
    app.setStyleSheet(_theme_css(STYLESHEET, ACTIVE_COLORS))
    return ACTIVE_THEME


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
        painter.setPen(QPen(QColor(ACTIVE_COLORS["header_text"]), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        _draw_chevron(painter, self.width() - 15, self.height() / 2, up=False)


class DecoratedSpinBox(QSpinBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(ACTIVE_COLORS["header_text"]), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 14
        _draw_chevron(painter, x, self.height() * 0.30, up=True)
        _draw_chevron(painter, x, self.height() * 0.70, up=False)


class MultiSelectButton(QPushButton):
    """Selector compacto con checkboxes persistentes para varios clientes."""
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("multiSelect")
        self._options = []
        self._selected = set()
        self._menu = QMenu(self)
        self._apply_menu_style()
        self._menu.aboutToShow.connect(self._prepare_menu)
        self.setMenu(self._menu)
        self._refresh_text()

    def _apply_menu_style(self):
        self._menu.setStyleSheet(_theme_css("""
            QMenu { background: #ffffff; color: #172033; border: 1px solid #bcccdc;
                    border-radius: 8px; padding: 5px; }
            QCheckBox { color: #172033; background: transparent; border: 0; border-radius: 6px;
                        padding: 7px 10px; spacing: 9px; min-width: 190px; font-size: 12px; }
            QCheckBox:hover { color: #102a43; background: #f0f4f8; }
            QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #829ab1;
                                   border-radius: 4px; background: #ffffff; }
            QCheckBox::indicator:hover { border-color: #2f80ed; background: #eef5ff; }
            QCheckBox::indicator:checked { border-color: #1976d2; background: #2f80ed; }
        """))

    def refresh_theme(self):
        self._apply_menu_style()

    def _prepare_menu(self):
        """Mantiene el desplegable legible y alineado con el control."""
        self._menu.setMinimumWidth(max(self.width(), 230))

    def set_options(self, options, selected=()):
        self._options = list(options)
        self._selected = set(selected).intersection(self._options)
        self._menu.clear()
        for option in self._options:
            checkbox = QCheckBox(option, self._menu)
            checkbox.setChecked(option in self._selected)
            checkbox.toggled.connect(lambda checked, value=option: self._set_checked(value, checked))
            action = QWidgetAction(self._menu)
            action.setDefaultWidget(checkbox)
            self._menu.addAction(action)
        self._refresh_text()

    def selected_values(self):
        return [option for option in self._options if option in self._selected]

    def clear_selection(self):
        self.set_options(self._options)

    def _set_checked(self, value, checked):
        if checked:
            self._selected.add(value)
        else:
            self._selected.discard(value)
        self._refresh_text()
        self.selection_changed.emit()

    def _refresh_text(self):
        selected = self.selected_values()
        text = "Todos" if not selected else selected[0] if len(selected) == 1 else f"{len(selected)} clientes"
        self.setText(text)


def _priority_expiration(effective: date, validity: str) -> date:
    if validity == "weekly":
        days_until_friday = (4 - effective.weekday()) % 7 or 7
        return effective + timedelta(days=days_until_friday)
    return effective


class PriorityImportDialog(QDialog):
    """Confirma la foto local antes de sustituir las prioridades de un proyecto."""
    def __init__(self, reports, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar prioridades")
        self.setMinimumWidth(620)
        self.setStyleSheet(_theme_css("""
            QDialog { background: #f5f7fb; color: #172033; }
            QLabel { color: #172033; font-size: 12px; }
            QLabel#muted { color: #627d98; }
            QGroupBox { background: #ffffff; border: 1px solid #d9e2ec; border-radius: 9px;
                        margin-top: 12px; padding: 14px 12px 10px; color: #102a43;
                        font-size: 14px; font-weight: 700; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px;
                                background: #f5f7fb; }
            QFrame#priorityReport { background: #f8fafc; border: 1px solid #e2e8f0;
                                    border-radius: 7px; }
            QDateEdit { border: 1px solid #bcccdc; border-radius: 6px; padding: 6px 9px;
                        background: #ffffff; color: #172033; min-height: 18px; }
            QDateEdit:focus { border: 2px solid #2f80ed; }
            QPushButton { border: 0; border-radius: 6px; padding: 8px 13px;
                          background: #e8eef5; color: #243b53; font-weight: 600; }
            QPushButton:hover { background: #d9e2ec; }
            QPushButton#dialogPrimary { background: #1976d2; color: white; }
            QPushButton#dialogPrimary:hover { background: #125ea7; }
        """))
        self._reports = reports
        self._expiry_edits = {}
        grouped = {}
        for report in reports:
            grouped.setdefault(report.project, []).append(report)
        self._grouped = grouped
        layout = QVBoxLayout(self)
        intro = QLabel("Revisa la vigencia antes de sustituir las prioridades locales de los proyectos detectados.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.effective_date = QDateEdit(QDate.currentDate())
        self.effective_date.setCalendarPopup(True)
        self.effective_date.dateChanged.connect(self._reset_default_dates)
        form.addRow("Vigentes desde", self.effective_date)
        layout.addLayout(form)
        self.projects_box = QGroupBox("Informes detectados")
        projects_layout = QVBoxLayout(self.projects_box)
        projects_layout.setSpacing(8)
        for project, project_reports in grouped.items():
            total = sum(len(report.items) for report in project_reports)
            sections = ", ".join(report.section or project for report in project_reports)
            validity = getattr(cfg, {"TMB": "priority_tmb_validity", "Línea 9": "priority_l9_validity", "RENFE": "priority_renfe_validity"}[project])
            expiry = QDateEdit()
            expiry.setCalendarPopup(True)
            expiry.setDate(QDate.currentDate())
            self._expiry_edits[project] = (expiry, validity)
            report_card = QFrame(objectName="priorityReport")
            report_layout = QVBoxLayout(report_card)
            report_layout.setContentsMargins(10, 8, 10, 9)
            report_layout.setSpacing(5)
            heading = QHBoxLayout()
            title = QLabel(project)
            title.setStyleSheet(_theme_css("font-size: 13px; font-weight: 700; color: #102a43;"))
            detail = QLabel(f"{total} OT · {sections}")
            detail.setObjectName("muted")
            heading.addWidget(title); heading.addStretch(); heading.addWidget(detail)
            sources = QLabel(f"{len(project_reports)} archivo{'s' if len(project_reports) != 1 else ''} seleccionado{'s' if len(project_reports) != 1 else ''}")
            sources.setObjectName("muted")
            sources.setToolTip("\n".join(report.path.name for report in project_reports))
            expiry_row = QHBoxLayout()
            expiry_row.addWidget(QLabel("Vigente hasta")); expiry_row.addWidget(expiry, 1)
            report_layout.addLayout(heading); report_layout.addWidget(sources); report_layout.addLayout(expiry_row)
            projects_layout.addWidget(report_card)
        layout.addWidget(self.projects_box)
        self._reset_default_dates()
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Importar prioridades")
        buttons.button(QDialogButtonBox.Ok).setObjectName("dialogPrimary")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_default_dates(self):
        effective = self.effective_date.date().toPython()
        for expiry, validity in self._expiry_edits.values():
            expiration = _priority_expiration(effective, validity)
            expiry.setDate(QDate(expiration.year, expiration.month, expiration.day))

    def import_plans(self):
        effective = self.effective_date.date().toPython().isoformat()
        plans = []
        for project, reports in self._grouped.items():
            expiry, _validity = self._expiry_edits[project]
            items = [item for report in reports for item in report.items]
            dates = sorted({report.source_report_date for report in reports if report.source_report_date})
            plans.append({
                "project": project, "effective_date": effective,
                "expires_on": expiry.date().toPython().isoformat(),
                "source_report_date": dates[-1] if dates else None,
                "source_files": [report.path.name for report in reports], "items": items,
            })
        return plans


class CalendarLineEdit(QWidget):
    """Fecha ISO que puede escribirse o elegirse desde un calendario."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("AAAA-MM-DD")
        self.edit.setMaximumWidth(150)
        layout.addWidget(self.edit)
        calendar_button = QPushButton("Calendario")
        calendar_button.setToolTip("Elegir fecha en un calendario")
        calendar_button.clicked.connect(self._show_calendar)
        layout.addWidget(calendar_button)

    def text(self):
        return self.edit.text()

    def setText(self, text):
        self.edit.setText(text)

    def clear(self):
        self.edit.clear()

    def _show_calendar(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Seleccionar fecha")
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget(dialog)
        calendar.setGridVisible(True)
        try:
            calendar.setSelectedDate(QDate.fromString(self.edit.text(), "yyyy-MM-dd"))
        except Exception:
            pass
        layout.addWidget(calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.edit.setText(calendar.selectedDate().toString("yyyy-MM-dd"))


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
        self.equipment_completer = QCompleter(choices["equipment"], self)
        self.equipment_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.equipment_completer.setFilterMode(Qt.MatchContains)
        self.equipment_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.equipment.setCompleter(self.equipment_completer)
        self.equipment.textEdited.connect(self._show_equipment_suggestions)
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
                box.addItem(item)
                item.setSelected(value in state.get(key, []))
            form.addWidget(QLabel(label), 2, column)
            form.addWidget(box, 3, column)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        reset = buttons.addButton("Restablecer", QDialogButtonBox.ResetRole)
        reset.clicked.connect(self.reset)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_equipment_suggestions(self, text):
        if text.strip():
            self.equipment_completer.complete()

    def reset(self):
        self.equipment.clear()
        self.date_from.clear()
        self.date_to.clear()
        for box in self.lists.values():
            box.clearSelection()

    def filters(self):
        date_from = self.date_from.text().strip()
        date_to = self.date_to.text().strip()
        if date_from and not date_to:
            date_to = date.today().isoformat()
        return {
            "equipment": self.equipment.text().strip(),
            "date_from": date_from,
            "date_to": date_to,
            **{key: [item.data(Qt.UserRole) for item in box.selectedItems()] for key, box in self.lists.items()},
        }


class MaximoDesktopWindow(QMainWindow):
    columns = ("Estado en Maximo", "OT", "Descripción", "Nº de serie", "Fecha", "Cliente", "Tipo de trabajo", "Seguimiento", "Planta", "Última vez visto", "Avería")
    default_column_widths = (180, 110, 340, 145, 135, 140, 180, 130, 105, 140, 340)
    max_column_widths = (180, 140, 600, 240, 160, 220, 220, 240, 160, 1200, 700)
    close_progress = Signal(str)
    close_finished = Signal()

    def __init__(self):
        super().__init__()
        self.cfg: AppConfig = load_config()
        self.update_lock = threading.Lock()
        self.reconcile_lock = threading.Lock()
        self.fault_description_lock = threading.Lock()
        self.pool = QThreadPool.globalInstance()
        self._running_tasks = set()
        self._latest_release = None
        self._app_update_checking = False
        self.ot_sessions = []
        self.profiles = {}
        self.profiles_error = None
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
        self.refresh_profiles()
        self.refresh_table()
        self._load_config()
        self._restore_window_state()
        self._restore_column_widths()
        QTimer.singleShot(0, self._fit_columns_to_viewport)
        self.schedule_auto_update()
        # No bloquea la apertura ni muestra avisos intrusivos: actualiza el
        # estado persistente de Configuración cuando la red esté disponible.
        QTimer.singleShot(1200, lambda: self.check_app_updates(automatic=True))

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
        box.addSpacing(26)
        box.addWidget(QLabel("BÚSQUEDAS GUARDADAS", objectName="sidebarSection"))
        self.profile_list = QListWidget(objectName="profileList")
        self.profile_list.setMinimumHeight(140)
        self.profile_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.profile_list.currentItemChanged.connect(self.load_selected_profile)
        self.profile_list.itemClicked.connect(self.load_selected_profile)
        # La lista ocupa todo el alto libre del lateral. Solo necesitará
        # desplazamiento cuando la ventana no pueda mostrar más entradas.
        box.addWidget(self.profile_list, 1)
        save_profile = QPushButton("＋  Guardar búsqueda", objectName="sidebarAction")
        save_profile.clicked.connect(self.save_current_profile)
        box.addWidget(save_profile)
        self.delete_profile_button = QPushButton("Eliminar búsqueda", objectName="sidebarAction")
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.delete_profile_button.setEnabled(False)
        box.addWidget(self.delete_profile_button)
        mode = QLabel("MODO DESARROLLO\nDatos aislados", objectName="developmentMode")
        box.addWidget(mode)
        return sidebar

    def _page_header(self, title, description, action=None):
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 24, 0, 12)
        texts = QVBoxLayout()
        heading = QLabel(title, objectName="pageTitle")
        texts.addWidget(heading)
        detail = QLabel(description, objectName="pageSubtitle")
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
        if page == 1:
            # Esta página puede haber estado oculta al calcularse por primera
            # vez; ahora sí conocemos el ancho final del panel principal.
            QTimer.singleShot(0, self._update_settings_content_width)
        return True

    def _build_list_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(30, 0, 30, 18)
        update = QPushButton("Actualizar Maximo", objectName="primary")
        update_icon = Path(__file__).resolve().parent / "ui_assets" / "refresh-white.svg"
        update.setIcon(QIcon(str(update_icon)))
        update.setIconSize(QSize(22, 22))
        update.clicked.connect(self.update_now)
        outer.addWidget(self._page_header("Órdenes de trabajo", "Consulta, filtra y gestiona el seguimiento local.", update))

        search_card = QFrame(objectName="filtersCard")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(18, 14, 18, 14)
        search_layout.setSpacing(10)
        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(12)
        toolbar.addWidget(QLabel("Cliente"), 0, 0)
        self.client_combo = MultiSelectButton()
        self.client_combo.selection_changed.connect(self.refresh_table)
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
        self.priority_only_button = QPushButton("▲  Solo prioritarias")
        self.priority_only_button.setCheckable(True)
        self.priority_only_button.setVisible(False)
        self.priority_only_button.toggled.connect(self.refresh_table)
        toolbar.addWidget(self.priority_only_button, 1, 5)
        toolbar.setColumnStretch(1, 1)
        search_layout.addLayout(toolbar)
        self.filter_chips = QLabel("Sin filtros", objectName="filterChips")
        self.filter_chips.setVisible(False)
        search_layout.addWidget(self.filter_chips)

        outer.addWidget(search_card)

        self.result_label = QLabel(objectName="resultLabel")
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
        for column, width in enumerate(self.default_column_widths):
            header.resizeSection(column, width)
        self.table.setColumnHidden(self.columns.index("Avería"), not self.cfg.fault_descriptions_enabled)
        self._column_widths = self._current_column_widths()
        outer.addWidget(self.table, 1)
        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "table"):
            QTimer.singleShot(0, self._fit_columns_to_viewport)
        if hasattr(self, "settings_scroll"):
            QTimer.singleShot(0, self._update_settings_content_width)

    def showEvent(self, event):
        super().showEvent(event)
        # La tabla conoce aquí su ancho final; restaurar antes hace que Qt
        # recalcule las secciones al mostrar la ventana.
        QTimer.singleShot(0, self._fit_columns_to_viewport)
        if hasattr(self, "settings_scroll"):
            QTimer.singleShot(0, self._update_settings_content_width)

    def _current_column_widths(self):
        header = self.table.horizontalHeader()
        previous = self._column_widths or self.default_column_widths
        return [
            max(60, header.sectionSize(index)) if not self.table.isColumnHidden(index)
            else max(60, int(previous[index]))
            for index in range(len(self.columns))
        ]

    def _visible_table_columns(self):
        return [index for index in range(len(self.columns)) if not self.table.isColumnHidden(index)]

    def _fit_columns_to_viewport(self):
        if not self._column_widths or not self.table.viewport().width():
            return
        available = max(600, self.table.viewport().width())
        widths = [min(limit, max(60, int(width))) for width, limit in zip(self._column_widths, self.max_column_widths)]
        visible = self._visible_table_columns()
        if not visible:
            return
        total = sum(widths[index] for index in visible)
        if total > available:
            scale = available / total
            for index in visible:
                widths[index] = max(60, int(round(widths[index] * scale)))
        # La última columna absorbe siempre el espacio restante para que no
        # quede una franja vacía al final de la tabla.
        last_visible = visible[-1]
        widths[last_visible] = max(60, available - sum(widths[index] for index in visible[:-1]))
        self._restoring_column_widths = True
        try:
            header = self.table.horizontalHeader()
            for index in visible:
                width = widths[index]
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
        last_column = self._visible_table_columns()[-1]
        if _logical_index != last_column:
            delta = header.sectionSize(_logical_index) - _old_size
            target = max(60, header.sectionSize(last_column) - delta)
            self._column_resize_guard = True
            try:
                header.resizeSection(last_column, target)
            finally:
                self._column_resize_guard = False
        else:
            target = max(60, self.table.viewport().width() - sum(
                header.sectionSize(index) for index in self._visible_table_columns() if index != last_column
            ))
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
                values.append(self.default_column_widths[index])
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
        settings_header_host = QWidget()
        settings_header_layout = QHBoxLayout(settings_header_host)
        settings_header_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_header = self._page_header("Configuración", "Acceso, actualización y mantenimiento de Maximo Desktop.")
        self.settings_header.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        settings_header_layout.addStretch(1)
        settings_header_layout.addWidget(self.settings_header)
        settings_header_layout.addStretch(1)
        layout.addWidget(settings_header_host)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll = scroll
        content = QWidget(objectName="settingsContent")
        content_layout = QHBoxLayout(content); content_layout.setContentsMargins(0, 0, 0, 20)
        self.settings_center = QWidget()
        self.settings_center.setMaximumWidth(1280)
        self.settings_center.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        content_layout.addStretch(1)
        content_layout.addWidget(self.settings_center, 0, Qt.AlignTop)
        content_layout.addStretch(1)
        body = QVBoxLayout(self.settings_center); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        self.settings_grid = QGridLayout()
        self.settings_grid.setContentsMargins(0, 0, 0, 0)
        self.settings_grid.setHorizontalSpacing(16)
        self.settings_grid.setVerticalSpacing(16)
        self._settings_wide = None

        self.access_card = QGroupBox("Acceso a Maximo")
        form = QFormLayout(self.access_card)
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

        self.app_updates_card = QGroupBox("Actualizaciones de Maximo Desktop")
        update_form = QFormLayout(self.app_updates_card)
        self.app_version_label = QLabel()
        self.app_latest_label = QLabel()
        self.app_last_check_label = QLabel()
        self.app_update_status_label = QLabel()
        self.app_update_status_label.setObjectName("filterHint")
        self.check_app_updates_button = QPushButton("Buscar actualizaciones")
        self.check_app_updates_button.clicked.connect(lambda: self.check_app_updates(automatic=False))
        self.open_release_button = QPushButton("Abrir release")
        self.open_release_button.clicked.connect(self.open_latest_release)
        update_actions = QHBoxLayout()
        update_actions.addWidget(self.check_app_updates_button)
        update_actions.addWidget(self.open_release_button)
        update_actions.addStretch()
        update_form.addRow("Versión instalada", self.app_version_label)
        update_form.addRow("Última versión detectada", self.app_latest_label)
        update_form.addRow("Última comprobación", self.app_last_check_label)
        update_form.addRow("Estado", self.app_update_status_label)
        update_form.addRow(update_actions)

        self.appearance_card = QGroupBox("Apariencia")
        appearance_form = QFormLayout(self.appearance_card)
        self.theme_combo = DecoratedComboBox()
        self.theme_combo.addItem("Según Windows", "system")
        self.theme_combo.addItem("Claro", "light")
        self.theme_combo.addItem("Oscuro", "dark")
        self.theme_combo.currentIndexChanged.connect(self.preview_theme)
        theme_hint = QLabel("Se aplica al instante; se conserva al guardar los cambios.")
        theme_hint.setObjectName("filterHint")
        appearance_form.addRow("Tema", self.theme_combo)
        appearance_form.addRow("", theme_hint)

        self.maintenance_card = QGroupBox("Mantenimiento")
        mform = QFormLayout(self.maintenance_card)
        self.reconcile_check = QCheckBox("Actualizar estados de OT no activas en segundo plano")
        self.batch_spin = DecoratedSpinBox(); self.batch_spin.setRange(1, 100); self.batch_spin.setSuffix(" OT")
        self.reconcile_pending_label = QLabel(); self.reconcile_pending_label.setObjectName("filterHint")
        priority = QPushButton("Revisar todas las OT pendientes ahora")
        priority.clicked.connect(self.start_priority_reconcile)
        clean = QPushButton("Eliminar registros no activos…", objectName="danger")
        clean.clicked.connect(self.delete_all_inactive)
        maintenance_actions = QHBoxLayout()
        maintenance_actions.addWidget(priority, 1); maintenance_actions.addWidget(clean, 1)
        mform.addRow("", self.reconcile_check); mform.addRow("Tamaño de lote", self.batch_spin)
        mform.addRow("Pendientes", self.reconcile_pending_label); mform.addRow(maintenance_actions)

        self.fault_descriptions_card = QGroupBox("Información ampliada de OT")
        fault_form = QFormLayout(self.fault_descriptions_card)
        self.fault_descriptions_check = QCheckBox("Obtener y mostrar descripción de avería")
        self.fault_descriptions_check.toggled.connect(self._update_fault_description_controls)
        self.fault_batch_spin = DecoratedSpinBox(); self.fault_batch_spin.setRange(1, 100); self.fault_batch_spin.setSuffix(" OT")
        self.fault_pending_label = QLabel(); self.fault_pending_label.setObjectName("filterHint")
        self.fault_run_button = QPushButton("Completar descripciones pendientes ahora")
        self.fault_run_button.clicked.connect(self.start_priority_fault_descriptions)
        fault_form.addRow("", self.fault_descriptions_check)
        fault_form.addRow("Tamaño de lote", self.fault_batch_spin)
        fault_form.addRow("Pendientes", self.fault_pending_label)
        fault_form.addRow(self.fault_run_button)

        self.priorities_card = QGroupBox("Prioridades locales")
        priority_form = QFormLayout(self.priorities_card)
        self.priority_tmb_validity = DecoratedComboBox()
        self.priority_l9_validity = DecoratedComboBox()
        self.priority_renfe_validity = DecoratedComboBox()
        for combo in (self.priority_tmb_validity, self.priority_l9_validity, self.priority_renfe_validity):
            combo.addItem("Diaria", "daily")
            combo.addItem("Semanal · hasta viernes", "weekly")
        self.priority_summary_label = QLabel()
        self.priority_summary_label.setObjectName("filterHint")
        self.import_priorities_button = QPushButton("Importar archivos…")
        self.import_priorities_button.clicked.connect(self.import_priorities)
        self.priority_snapshot_combo = DecoratedComboBox()
        self.priority_snapshot_combo.currentIndexChanged.connect(self._priority_snapshot_selected)
        self.priority_expiry_edit = QDateEdit()
        self.priority_expiry_edit.setCalendarPopup(True)
        self.save_priority_expiry_button = QPushButton("Actualizar vigencia")
        self.save_priority_expiry_button.clicked.connect(self.save_priority_expiration)
        self.clear_priority_button = QPushButton("Retirar prioridad", objectName="danger")
        self.clear_priority_button.clicked.connect(self.clear_priority_snapshot)
        priority_actions = QHBoxLayout()
        priority_actions.addWidget(self.import_priorities_button)
        priority_actions.addStretch()
        manage_actions = QHBoxLayout()
        manage_actions.addWidget(self.save_priority_expiry_button)
        manage_actions.addWidget(self.clear_priority_button)
        manage_actions.addStretch()
        priority_form.addRow("Vigencia TMB", self.priority_tmb_validity)
        priority_form.addRow("Vigencia Línea 9", self.priority_l9_validity)
        priority_form.addRow("Vigencia RENFE", self.priority_renfe_validity)
        priority_form.addRow("Estado", self.priority_summary_label)
        priority_form.addRow(priority_actions)
        priority_form.addRow("Foto cargada", self.priority_snapshot_combo)
        priority_form.addRow("Vigente hasta", self.priority_expiry_edit)
        priority_form.addRow(manage_actions)

        self.paths_card = QGroupBox("Datos y rutas")
        paths_layout = QVBoxLayout(self.paths_card)
        path_actions = QHBoxLayout()
        open_folder = QPushButton("Abrir carpeta de datos")
        open_folder.clicked.connect(self.open_data_folder)
        self.path_details_toggle = QPushButton("Mostrar ubicaciones técnicas")
        self.path_details_toggle.setCheckable(True)
        self.path_details_toggle.toggled.connect(self._toggle_path_details)
        path_actions.addWidget(open_folder)
        path_actions.addWidget(self.path_details_toggle)
        path_actions.addStretch()
        paths_layout.addLayout(path_actions)
        self.path_details = QWidget()
        paths_form = QFormLayout(self.path_details)
        for label, path in (("Carpeta principal", APP_ROOT), ("Base de datos", DB_PATH), ("Logs", LOG_DIR), ("Caché y perfiles Edge", EDGE_PROFILE_DIR), ("Copias de seguridad", BACKUP_DIR)):
            value = QLabel(str(path)); value.setTextInteractionFlags(Qt.TextSelectableByMouse); value.setWordWrap(True)
            paths_form.addRow(label, value)
        self.path_details.setVisible(False)
        paths_layout.addWidget(self.path_details)

        body.addLayout(self.settings_grid)
        body.addStretch()
        save_row = QHBoxLayout()
        save_hint = QLabel("Los cambios de esta página se aplican al guardar.")
        save_hint.setObjectName("filterHint")
        self.save_settings_button = QPushButton("Guardar cambios", objectName="primary")
        self.save_settings_button.clicked.connect(self.save_settings)
        save_row.addWidget(save_hint); save_row.addStretch(); save_row.addWidget(self.save_settings_button)
        scroll.setWidget(content); layout.addWidget(scroll, 1); layout.addLayout(save_row)
        QTimer.singleShot(0, self._update_settings_content_width)
        return page

    def _update_settings_content_width(self):
        """Mantiene un ancho legible en pantalla grande sin estrechar la página."""
        if not hasattr(self, "settings_scroll"):
            return
        # La página apilada conserva el ancho real disponible incluso cuando
        # el QScrollArea todavía no se ha mostrado por primera vez.
        available = self.pages.width() - 60 if hasattr(self, "pages") else self.settings_scroll.viewport().width()
        if available <= 0:
            return
        content_width = min(1280, available)
        self.settings_center.setFixedWidth(content_width)
        if hasattr(self, "settings_header"):
            self.settings_header.setFixedWidth(content_width)
        self._arrange_settings_cards()

    def _arrange_settings_cards(self, force=False):
        """Alterna entre dos columnas legibles y una columna para ventana estrecha."""
        if not hasattr(self, "settings_grid"):
            return
        wide = self.settings_center.width() >= 980
        if not force and wide == self._settings_wide:
            return
        self._settings_wide = wide
        for card in (self.access_card, self.app_updates_card, self.maintenance_card, self.fault_descriptions_card, self.priorities_card, self.appearance_card, self.paths_card):
            self.settings_grid.removeWidget(card)
        if wide:
            self.settings_grid.addWidget(self.access_card, 0, 0, Qt.AlignTop)
            self.settings_grid.addWidget(self.app_updates_card, 0, 1, Qt.AlignTop)
            self.settings_grid.addWidget(self.maintenance_card, 1, 0, Qt.AlignTop)
            self.settings_grid.addWidget(self.fault_descriptions_card, 1, 1, Qt.AlignTop)
            self.settings_grid.addWidget(self.priorities_card, 2, 0, Qt.AlignTop)
            self.settings_grid.addWidget(self.appearance_card, 2, 1, Qt.AlignTop)
            self.settings_grid.addWidget(self.paths_card, 3, 0, 1, 2, Qt.AlignTop)
            self.settings_grid.setColumnStretch(0, 3)
            self.settings_grid.setColumnStretch(1, 2)
        else:
            self.settings_grid.addWidget(self.access_card, 0, 0)
            self.settings_grid.addWidget(self.app_updates_card, 1, 0)
            self.settings_grid.addWidget(self.maintenance_card, 2, 0)
            self.settings_grid.addWidget(self.fault_descriptions_card, 3, 0)
            self.settings_grid.addWidget(self.priorities_card, 4, 0)
            self.settings_grid.addWidget(self.appearance_card, 5, 0)
            self.settings_grid.addWidget(self.paths_card, 6, 0)
            self.settings_grid.setColumnStretch(0, 1)
            self.settings_grid.setColumnStretch(1, 0)

    @staticmethod
    def _set_combo_value(combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def preview_theme(self):
        """Muestra el tema elegido antes de confirmar el resto de ajustes."""
        preference = self.theme_combo.currentData()
        self._effective_theme = apply_application_theme(QApplication.instance(), preference)
        self.client_combo.refresh_theme()
        self.refresh_table()

    def _refresh_priorities(self):
        """Actualiza el resumen y la gestión de fotos locales de prioridad."""
        snapshots = current_priority_snapshots()
        self.priority_snapshot_combo.blockSignals(True)
        previous = self.priority_snapshot_combo.currentData()
        self.priority_snapshot_combo.clear()
        current = [item for item in snapshots if item["is_current"]]
        for item in snapshots:
            state = "vigente" if item["is_current"] else "caducada"
            label = f"{item['project']} · {item['item_count']} OT · {state}"
            self.priority_snapshot_combo.addItem(label, item)
        if previous:
            index = next((i for i in range(self.priority_snapshot_combo.count())
                          if self.priority_snapshot_combo.itemData(i)["project"] == previous.get("project")), -1)
            if index >= 0:
                self.priority_snapshot_combo.setCurrentIndex(index)
        self.priority_snapshot_combo.blockSignals(False)
        self._priority_snapshot_selected(self.priority_snapshot_combo.currentIndex())
        if current:
            text = " · ".join(f"{item['project']}: {item['item_count']} OT hasta {item['expires_on']}" for item in current)
        elif snapshots:
            text = "Las prioridades cargadas han caducado."
        else:
            text = "No hay prioridades locales cargadas."
        self.priority_summary_label.setText(text)

    def _priority_snapshot_selected(self, index):
        item = self.priority_snapshot_combo.itemData(index) if index >= 0 else None
        enabled = bool(item)
        self.priority_expiry_edit.setEnabled(enabled)
        self.save_priority_expiry_button.setEnabled(enabled)
        self.clear_priority_button.setEnabled(enabled)
        if item:
            expiry = date.fromisoformat(item["expires_on"])
            self.priority_expiry_edit.setDate(QDate(expiry.year, expiry.month, expiry.day))

    def import_priorities(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar informes de prioridades", "", "Informes de prioridades (*.xls)"
        )
        if not paths:
            return
        try:
            reports = read_priority_files(paths)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self, "Importar prioridades", str(exc))
            return
        dialog = PriorityImportDialog(reports, self.cfg, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            plans = dialog.import_plans()
            for plan in plans:
                replace_priority_snapshot(**plan)
        except Exception as exc:
            logging.exception("No se pudieron importar las prioridades")
            QMessageBox.critical(self, "Importar prioridades", f"No se pudieron guardar las prioridades: {exc}")
            return
        self._refresh_priorities()
        self.refresh_table()
        detail = "\n".join(f"• {plan['project']}: {len(plan['items'])} OT hasta {plan['expires_on']}" for plan in plans)
        QMessageBox.information(self, "Prioridades importadas", f"Se sustituyó la foto local de los informes seleccionados.\n\n{detail}")
        self.status.showMessage("Prioridades locales importadas.", 5000)

    def save_priority_expiration(self):
        snapshot = self.priority_snapshot_combo.currentData()
        if not snapshot:
            return
        expires_on = self.priority_expiry_edit.date().toPython().isoformat()
        if expires_on < snapshot["effective_date"]:
            QMessageBox.warning(self, "Vigencia", "La fecha final no puede ser anterior al inicio de vigencia.")
            return
        update_priority_expiration(snapshot["project"], expires_on)
        self._refresh_priorities()
        self.refresh_table()
        self.status.showMessage(f"Vigencia de {snapshot['project']} actualizada.", 4000)

    def clear_priority_snapshot(self):
        snapshot = self.priority_snapshot_combo.currentData()
        if not snapshot:
            return
        project = snapshot["project"]
        if QMessageBox.question(self, "Retirar prioridad", f"¿Retirar la foto actual de prioridades de {project}?\n\nEl historial se conservará, pero dejará de marcarse en el listado.") != QMessageBox.Yes:
            return
        clear_current_priority_snapshot(project)
        self._refresh_priorities()
        self.refresh_table()
        self.status.showMessage(f"Prioridades de {project} retiradas.", 4000)

    def _toggle_path_details(self, visible):
        self.path_details.setVisible(visible)
        self.path_details_toggle.setText(
            "Ocultar ubicaciones técnicas" if visible else "Mostrar ubicaciones técnicas"
        )

    def refresh_choices(self):
        choices = filter_choices()
        self.filter_choices_cache = choices
        self.client_combo.set_options(choices["clients"], self.client_combo.selected_values())

    def refresh_profiles(self, selected_name=""):
        try:
            self.profiles = load_profiles(PROFILES_PATH)
            self.profiles_error = None
        except (OSError, ValueError) as exc:
            self.profiles = {}
            self.profiles_error = str(exc)
            logging.warning("No se pudieron cargar los perfiles de búsqueda: %s", exc)
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for name in sorted(self.profiles, key=str.casefold):
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.profile_list.addItem(item)
            if name == selected_name:
                self.profile_list.setCurrentItem(item)
        self.profile_list.blockSignals(False)
        self.delete_profile_button.setEnabled(bool(selected_name and selected_name in self.profiles))

    def current_profile_state(self):
        simple_clients = self.client_combo.selected_values()
        advanced = self.effective_advanced_filters()
        # El formato existente admite un cliente simple; una selección múltiple
        # queda almacenada como filtro avanzado para no perder información.
        client = simple_clients[0] if len(simple_clients) == 1 and not self.advanced_state["clients"] else "Todos"
        return {
            "search": self.search_edit.text().strip(),
            "search_by": self.search_field(),
            "client": client,
            "advanced": advanced,
        }

    def load_selected_profile(self, current, _previous=None):
        name = current.data(Qt.UserRole) if current else ""
        profile = self.profiles.get(name)
        self.delete_profile_button.setEnabled(bool(profile))
        if not profile:
            return
        self.search_edit.setText(profile["search"])
        self.search_by_combo.setCurrentIndex(max(0, self.search_by_combo.findData(profile["search_by"])))
        self.advanced_state = profile["advanced"]
        selected_clients = [] if profile["advanced"]["clients"] else ([profile["client"]] if profile["client"] != "Todos" else [])
        self.client_combo.set_options(self.filter_choices_cache["clients"], selected_clients)
        self.refresh_table()

    def save_current_profile(self):
        if self.profiles_error:
            QMessageBox.critical(self, "Perfiles", "No se puede guardar hasta revisar el archivo de perfiles.\n\n" + self.profiles_error)
            return
        current_item = self.profile_list.currentItem()
        current_name = current_item.data(Qt.UserRole) if current_item else ""
        name, accepted = QInputDialog.getText(self, "Guardar búsqueda", "Nombre de la búsqueda:", text=current_name)
        name = name.strip()
        if not accepted or not name:
            return
        if name in self.profiles and QMessageBox.question(
            self, "Guardar búsqueda", f"La búsqueda «{name}» ya existe. ¿Quieres sustituirla?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            save_profiles(PROFILES_PATH, {**self.profiles, name: self.current_profile_state()})
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Perfiles", str(exc))
            return
        self.refresh_profiles(name)
        self.status.showMessage(f"Búsqueda guardada: {name}.", 4000)

    def delete_selected_profile(self):
        current_item = self.profile_list.currentItem()
        name = current_item.data(Qt.UserRole) if current_item else ""
        if not name or name not in self.profiles:
            return
        if QMessageBox.question(self, "Eliminar búsqueda", f"¿Eliminar la búsqueda «{name}»?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            save_profiles(PROFILES_PATH, {key: value for key, value in self.profiles.items() if key != name})
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Perfiles", str(exc))
            return
        self.refresh_profiles()
        self.status.showMessage(f"Búsqueda eliminada: {name}.", 4000)

    def advanced_filters(self):
        return self.advanced_state

    def open_advanced_filters(self):
        dialog = AdvancedFiltersDialog(self.filter_choices_cache, self.effective_advanced_filters(), self)
        if dialog.exec() == QDialog.Accepted:
            self.advanced_state = dialog.filters()
            self.refresh_table()

    def active_filter_summary(self):
        advanced = self.advanced_filters()
        summary = []
        simple_clients = self.client_combo.selected_values()
        selected_clients = list(dict.fromkeys([*simple_clients, *advanced["clients"]]))
        if selected_clients:
            summary.append(f"Clientes: {', '.join(selected_clients)}")
        if self.search_edit.text().strip():
            summary.append(f"{self.search_field().replace('_', ' ')}: {self.search_edit.text().strip()}")
        if advanced["equipment"]:
            summary.append(f"Equipo: {advanced['equipment']}")
        if advanced["date_from"] or advanced["date_to"]:
            summary.append(f"Fechas: {advanced['date_from'] or '…'} — {advanced['date_to'] or '…'}")
        for key, label in (("types", "Tipo"), ("tracking", "Seguimiento")):
            if advanced[key]:
                summary.append(f"{label}: {', '.join(advanced[key])}")
        return summary

    def effective_advanced_filters(self):
        filters = {key: list(value) if isinstance(value, list) else value for key, value in self.advanced_filters().items()}
        simple_clients = self.client_combo.selected_values()
        if simple_clients:
            filters["clients"] = list(dict.fromkeys([*filters["clients"], *simple_clients]))
        return filters

    def search_field(self):
        return self.search_by_combo.currentData() or "Nº_de_serie"

    def refresh_table(self):
        try:
            rows = fetch_data(self.search_edit.text(), self.search_field(), "Todos", self.effective_advanced_filters(), include_sync=True, include_fault=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Filtros", str(exc)); return
        priority_ots = current_priority_ots()
        self.priority_only_button.setVisible(bool(priority_ots))
        if not priority_ots and self.priority_only_button.isChecked():
            self.priority_only_button.blockSignals(True)
            self.priority_only_button.setChecked(False)
            self.priority_only_button.blockSignals(False)
        if self.priority_only_button.isChecked():
            rows = [raw for raw in rows if raw[0] == 1 and str(raw[2] or "") in priority_ots]
        def ot_sort_key(row):
            value = str(row[2] or "").strip()
            return (0, int(value)) if value.isdigit() else (1, value)
        rows.sort(key=ot_sort_key, reverse=True)
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for raw in rows:
            active, last_seen, *data = raw
            fault_description = data.pop()
            is_priority = active == 1 and str(raw[2] or "") in priority_ots
            status = "▲ Prioridad · ✓ Activo en Maximo" if is_priority else "✓ Activo en Maximo" if active == 1 else "× No activo en Maximo" if active == 0 else "? Estado desconocido"
            try: last_seen = datetime.fromisoformat(last_seen).strftime("%d/%m/%Y %H:%M") if last_seen else ""
            except (TypeError, ValueError): pass
            row = [status, *data, last_seen, fault_description]
            index = self.table.rowCount(); self.table.insertRow(index)
            for column, value in enumerate(row):
                item = QTableWidgetItem(str(value or "")); item.setData(Qt.UserRole, raw[2])
                item.setForeground(QColor(ACTIVE_COLORS["text"] if active == 1 else ACTIVE_COLORS["inactive"]))
                if column == 0:
                    item.setToolTip("Prioridad: marcada en el informe local vigente y todavía activa en Maximo.\n\nActivo en Maximo: aparece en el listado de reparaciones y recibe actualizaciones.\nNo activo en Maximo: ya no aparece en ese listado y no recibe nuevas actualizaciones.")
                    item.setForeground(QColor(ACTIVE_COLORS["priority"] if is_priority else ACTIVE_COLORS["success"] if active == 1 else ACTIVE_COLORS["inactive"]))
                self.table.setItem(index, column, item)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(1, Qt.DescendingOrder)
        self.table.setColumnHidden(self.columns.index("Avería"), not self.cfg.fault_descriptions_enabled)
        summary = self.active_filter_summary()
        if self.priority_only_button.isChecked():
            summary.append("Solo prioritarias")
        self.filter_chips.setVisible(bool(summary))
        self.filter_chips.setText("Filtros activos · " + "   •   ".join(summary))
        advanced_count = sum(bool(value) for value in self.advanced_state.values())
        self.filter_button.setText(f"☷  Filtros ({advanced_count})" if advanced_count else "☷  Filtros")
        self.clear_button.setVisible(bool(summary))
        self.result_label.setText(f"{len(rows):,} resultados · {'Filtros aplicados' if summary else 'Sin filtros'}")

    def clear_filters(self):
        self.search_edit.clear()
        self.client_combo.clear_selection()
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
        update_seguimiento(ot, value); self.refresh_table(); self._refresh_reconciliation_summary(); self.status.showMessage(f"OT {ot}: seguimiento actualizado a {value}.", 5000)

    def delete_inactive(self, ot):
        if QMessageBox.question(self, "Eliminar registro", f"¿Eliminar la OT no activa {ot} de la base local?") == QMessageBox.Yes:
            delete_inactive_record(ot); self.refresh_table(); self._refresh_reconciliation_summary()

    def delete_all_inactive(self):
        count = sum(1 for row in range(self.table.rowCount()) if self.table.item(row, 0).text() == "○ No activo")
        if QMessageBox.question(self, "Eliminar registros", f"¿Eliminar todos los registros no activos?\n\nSe eliminarán de la base local.") == QMessageBox.Yes:
            deleted = delete_all_inactive_records(); self.refresh_table(); self._refresh_reconciliation_summary(); self.status.showMessage(f"{deleted} registros no activos eliminados.", 5000)

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
            self.update_lock.release(); new, changed = result; self.refresh_choices(); self.refresh_table(); self._refresh_reconciliation_summary()
            sync_summary = (
                f"Última sincronización de Maximo ({datetime.now().strftime('%H:%M')}): "
                f"completada · {new} nuevas, {changed} actualizadas"
            )
            self.status.showMessage(sync_summary + " · Conciliación en segundo plano…")
            self.start_background_reconcile(
                sync_summary,
                after=lambda summary: self.start_background_fault_descriptions(summary),
            )
        def failed(error): self.update_lock.release(); QMessageBox.critical(self, "Actualización", f"No se pudo actualizar:\n{error}"); self.status.showMessage("La actualización falló.")
        self._start_task(lambda: run_update(headless=True), done, failed)

    def start_background_reconcile(self, sync_summary=None, after=None):
        if not self.cfg.reconciliation_enabled:
            if after:
                after(sync_summary)
            return
        if not self.reconcile_lock.acquire(False):
            if sync_summary:
                self.status.showMessage(sync_summary + " · Conciliación ya en curso.")
            if after:
                after(sync_summary)
            return
        batch = self.cfg.reconciliation_batch_size
        if not sync_summary:
            self.status.showMessage(f"Revisando hasta {batch} OT históricas en segundo plano…")
        def done(changed):
            self.reconcile_lock.release(); self.refresh_table(); self._refresh_reconciliation_summary()
            reconciliation_summary = (
                "Conciliación: sin cambios" if not changed
                else f"Conciliación: {changed} seguimientos actualizados"
            )
            combined_summary = f"{sync_summary} · {reconciliation_summary}" if sync_summary else reconciliation_summary
            self.status.showMessage(combined_summary)
            if after:
                after(combined_summary)
        def failed(error):
            self.reconcile_lock.release(); logging.warning("Conciliación fallida: %s", error)
            combined_summary = f"{sync_summary} · Conciliación fallida; consulta el log." if sync_summary else "La conciliación falló; consulta el log."
            self.status.showMessage(combined_summary)
            if after:
                after(combined_summary)
        self._start_task(lambda: reconcile_inactive_tracking(limit=batch), done, failed)

    def _refresh_fault_description_summary(self):
        if not hasattr(self, "fault_pending_label"):
            return
        pending = fault_description_candidate_count()
        if self.cfg.fault_descriptions_enabled:
            self.fault_pending_label.setText(f"{pending} OT activas pendientes de completar.")
        else:
            self.fault_pending_label.setText(
                f"Desactivado. Hay {pending} OT activas pendientes de completar."
            )

    def _refresh_reconciliation_summary(self):
        if not hasattr(self, "reconcile_pending_label"):
            return
        pending = inactive_tracking_candidate_count()
        if self.cfg.reconciliation_enabled:
            self.reconcile_pending_label.setText(f"{pending} OT no activas pendientes de revisar.")
        else:
            self.reconcile_pending_label.setText(
                f"Desactivado. Hay {pending} OT no activas pendientes de revisar."
            )

    def _update_fault_description_controls(self):
        enabled = self.fault_descriptions_check.isChecked()
        self.fault_batch_spin.setEnabled(enabled)
        self.fault_run_button.setEnabled(enabled)
        if hasattr(self, "table"):
            self.table.setColumnHidden(self.columns.index("Avería"), not enabled)
            QTimer.singleShot(0, self._fit_columns_to_viewport)

    def start_background_fault_descriptions(self, sync_summary=None):
        """Enriquece en segundo plano solo las OT activas sin avería local."""
        if not self.cfg.fault_descriptions_enabled or not self.update_lock.acquire(False):
            return
        if not self.fault_description_lock.acquire(False):
            self.update_lock.release()
            return
        batch = self.cfg.fault_description_batch_size
        if sync_summary:
            self.status.showMessage(sync_summary + " · Completando averías en segundo plano…")
        else:
            self.status.showMessage(f"Completando hasta {batch} descripciones de avería…")

        def done(completed):
            self.fault_description_lock.release(); self.update_lock.release()
            self.refresh_table(); self._refresh_fault_description_summary()
            detail = "Averías: sin pendientes nuevas" if not completed else f"Averías: {completed} descripciones completadas"
            self.status.showMessage(f"{sync_summary} · {detail}" if sync_summary else detail)

        def failed(error):
            self.fault_description_lock.release(); self.update_lock.release()
            logging.warning("Enriquecimiento de averías falló: %s", error)
            self._refresh_fault_description_summary()
            self.status.showMessage(f"{sync_summary} · Averías: error; consulta el log." if sync_summary else "No se pudieron completar las averías; consulta el log.")

        self._start_task(lambda: enrich_fault_descriptions(limit=batch), done, failed)

    def start_priority_fault_descriptions(self):
        if not self._credentials_ready():
            return
        count = fault_description_candidate_count(minimum_age_hours=None)
        if not count:
            QMessageBox.information(self, "Información ampliada", "No hay descripciones de avería pendientes.")
            return
        if QMessageBox.question(
            self, "Completar averías", f"Se revisarán {count} OT activas. La operación puede tardar varios minutos.\n\n¿Continuar?",
        ) != QMessageBox.Yes:
            return
        if not self.update_lock.acquire(False):
            QMessageBox.information(self, "Información ampliada", "Hay otra tarea de Maximo en curso.")
            return
        if not self.fault_description_lock.acquire(False):
            self.update_lock.release()
            QMessageBox.information(self, "Información ampliada", "Ya hay una lectura de averías en curso.")
            return
        self.status.showMessage(f"Completando {count} descripciones de avería…")

        def done(completed):
            self.fault_description_lock.release(); self.update_lock.release()
            self.refresh_table(); self._refresh_fault_description_summary()
            self.status.showMessage(f"Averías completadas: {completed} OT.", 7000)
            QMessageBox.information(self, "Información ampliada", f"Lectura completada. Descripciones obtenidas: {completed}.")

        def failed(error):
            self.fault_description_lock.release(); self.update_lock.release()
            self._refresh_fault_description_summary()
            self.status.showMessage("La lectura de averías falló; consulta el detalle.", 7000)
            QMessageBox.critical(self, "Información ampliada", error)

        self._start_task(lambda: enrich_fault_descriptions(limit=None, minimum_age_hours=None), done, failed)

    def start_priority_reconcile(self):
        if not self._credentials_ready(): return
        count = inactive_tracking_candidate_count(minimum_age_hours=None)
        if not count: QMessageBox.information(self, "Mantenimiento", "No hay OT no activas pendientes de revisar."); return
        if QMessageBox.question(self, "Revisión prioritaria", f"Se revisarán {count} OT. La operación puede tardar varios minutos.\n\n¿Continuar?") != QMessageBox.Yes: return
        if not self.update_lock.acquire(False): QMessageBox.information(self, "Mantenimiento", "Hay otra tarea de Maximo en curso."); return
        if not self.reconcile_lock.acquire(False):
            self.update_lock.release(); QMessageBox.information(self, "Mantenimiento", "Ya hay una revisión en curso."); return
        self.status.showMessage(f"Revisión prioritaria en curso: {count} OT…")
        def done(changed):
            self.reconcile_lock.release(); self.update_lock.release(); self.refresh_table(); self._refresh_reconciliation_summary()
            self.status.showMessage(f"Revisión prioritaria completada: {changed} seguimientos actualizados.", 7000)
            QMessageBox.information(self, "Mantenimiento", f"Revisión completada. Seguimientos actualizados: {changed}.")
        def failed(error):
            self.reconcile_lock.release(); self.update_lock.release()
            self.status.showMessage("La revisión prioritaria falló; consulta el detalle.", 7000)
            QMessageBox.critical(self, "Mantenimiento", error)
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
        self.fault_descriptions_check.setChecked(self.cfg.fault_descriptions_enabled)
        self.fault_batch_spin.setValue(self.cfg.fault_description_batch_size)
        self._set_combo_value(self.theme_combo, self.cfg.theme)
        self._set_combo_value(self.priority_tmb_validity, self.cfg.priority_tmb_validity)
        self._set_combo_value(self.priority_l9_validity, self.cfg.priority_l9_validity)
        self._set_combo_value(self.priority_renfe_validity, self.cfg.priority_renfe_validity)
        self._refresh_auto_update_summary()
        self._refresh_app_update_block()
        self._refresh_reconciliation_summary()
        self._refresh_fault_description_summary()
        self._update_fault_description_controls()
        self._refresh_priorities()

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
            or self.fault_descriptions_check.isChecked() != self.cfg.fault_descriptions_enabled
            or self.fault_batch_spin.value() != self.cfg.fault_description_batch_size
            or self.priority_tmb_validity.currentData() != self.cfg.priority_tmb_validity
            or self.priority_l9_validity.currentData() != self.cfg.priority_l9_validity
            or self.priority_renfe_validity.currentData() != self.cfg.priority_renfe_validity
            or self.theme_combo.currentData() != self.cfg.theme
        )

    def save_settings(self, show_feedback=True):
        self.cfg.username = self.user_edit.text().strip(); self.cfg.password = self.password_edit.text(); self.cfg.auto_update_enabled = self.auto_check.isChecked(); self.cfg.auto_update_interval_min = self.interval_spin.value(); self.cfg.reconciliation_enabled = self.reconcile_check.isChecked(); self.cfg.reconciliation_batch_size = self.batch_spin.value()
        self.cfg.fault_descriptions_enabled = self.fault_descriptions_check.isChecked()
        self.cfg.fault_description_batch_size = self.fault_batch_spin.value()
        self.cfg.priority_tmb_validity = self.priority_tmb_validity.currentData()
        self.cfg.priority_l9_validity = self.priority_l9_validity.currentData()
        self.cfg.priority_renfe_validity = self.priority_renfe_validity.currentData()
        self.cfg.theme = self.theme_combo.currentData()
        save_config(self.cfg)
        self.schedule_auto_update()
        self._refresh_auto_update_summary()
        self._refresh_reconciliation_summary()
        self._refresh_fault_description_summary()
        self._update_fault_description_controls()
        self._refresh_priorities()
        self.refresh_table()
        logging.info(
            "Configuración UI guardada: auto_update=%s, intervalo=%d, conciliación=%s, lote=%d, averías=%s, lote_averías=%d, prioridad TMB=%s, L9=%s, RENFE=%s, tema=%s.",
            self.cfg.auto_update_enabled, self.cfg.auto_update_interval_min,
            self.cfg.reconciliation_enabled, self.cfg.reconciliation_batch_size,
            self.cfg.fault_descriptions_enabled, self.cfg.fault_description_batch_size,
            self.cfg.priority_tmb_validity, self.cfg.priority_l9_validity, self.cfg.priority_renfe_validity,
            self.cfg.theme,
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

    def _fetch_latest_release_with_retry(self):
        """Consulta GitHub con el mismo margen de reintento que la app estable."""
        last_error = None
        for attempt, delay in enumerate((0.0, 1.0, 2.0), start=1):
            try:
                if delay:
                    time.sleep(delay)
                logging.info("Comprobación de versión UI: intento %d/3.", attempt)
                return fetch_latest_release(timeout_sec=10)
            except Exception as exc:
                last_error = exc
                logging.warning("Comprobación de versión UI falló en intento %d/3: %s", attempt, exc)
        raise RuntimeError(f"No se pudo consultar GitHub: {last_error}")

    def _refresh_app_update_block(self, message=""):
        """Refresca el estado persistido de versiones sin depender de la red."""
        if not hasattr(self, "app_version_label"):
            return
        tag = self.cfg.latest_release_tag or ""
        release_url = self.cfg.latest_release_url or ""
        checked_at = self.cfg.latest_release_checked_at or ""
        self.app_version_label.setText(format_version_tag(version.APP_VERSION))
        self.app_latest_label.setText(format_version_tag(tag) if tag else "—")
        self.app_last_check_label.setText(checked_at or "—")
        self.open_release_button.setEnabled(bool(release_url))
        self.check_app_updates_button.setEnabled(not self._app_update_checking)
        if message:
            state = message
        elif tag and is_newer(tag, version.APP_VERSION):
            state = f"Hay una actualización disponible: {format_version_tag(tag)}."
        elif tag:
            state = "La aplicación está actualizada."
        else:
            state = "Aún no se ha comprobado la disponibilidad de versiones."
        self.app_update_status_label.setText(state)

    def check_app_updates(self, automatic=False):
        """Comprueba releases en segundo plano; no instala nada desde la preview."""
        if self._app_update_checking:
            return
        self._app_update_checking = True
        self._refresh_app_update_block("Comprobando versiones en GitHub…")
        if not automatic:
            self.status.showMessage("Comprobando actualizaciones de Maximo Desktop…")

        def done(latest):
            self._app_update_checking = False
            self._latest_release = latest
            self.cfg.latest_release_tag = latest.tag
            self.cfg.latest_release_url = latest.html_url
            self.cfg.latest_release_checked_at = latest.checked_at
            save_config(self.cfg)
            newer = bool(latest.tag and is_newer(latest.tag, version.APP_VERSION))
            self._refresh_app_update_block()
            logging.info(
                "Comprobación de versión UI completada: local=%s, remota=%s, nueva=%s.",
                version.APP_VERSION, latest.tag, newer,
            )
            if not automatic:
                text = (
                    f"Hay una nueva versión disponible: {format_version_tag(latest.tag)}."
                    if newer else "Ya tienes la versión más reciente disponible."
                )
                QMessageBox.information(self, "Actualizaciones", text)
                self.status.showMessage("Comprobación de actualizaciones completada.", 4000)

        def failed(error):
            self._app_update_checking = False
            detail = "No se pudo comprobar GitHub. Reinténtalo cuando haya conexión."
            self._refresh_app_update_block(detail)
            logging.warning("Comprobación de versión UI no completada: %s", error)
            if not automatic:
                QMessageBox.warning(self, "Actualizaciones", f"{detail}\n\n{error}")
                self.status.showMessage("No se pudo comprobar la versión.", 4000)

        self._start_task(self._fetch_latest_release_with_retry, done, failed)

    def open_latest_release(self):
        url = self.cfg.latest_release_url or ""
        if url:
            webbrowser.open(url)

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
            (self.fault_description_lock, "Esperando a que termine la lectura de averías…"),
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
    apply_application_theme(app, load_config().theme)
    window = MaximoDesktopWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
