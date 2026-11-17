"""Interfaz de escritorio Qt de Maximo Desktop."""
from __future__ import annotations

from runtime_limits import configure_numerical_threads
configure_numerical_threads()

import logging
import os
import sys
import threading
import time
import webbrowser
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QDate, QEvent, QObject, QPointF, QRunnable, QSize, Qt, QThread, QThreadPool, QTimer, Signal, QSignalBlocker
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap, QTextCharFormat
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QButtonGroup, QCalendarWidget, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QCompleter, QDateEdit, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QProgressBar, QProgressDialog, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QStatusBar, QTableWidget, QTableWidgetItem,
    QTextBrowser, QStyle, QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from column_widths import ColumnWidthHeader
from rounded_table import RoundedTableFrame
from ui_activity_icon import RefreshIcon, set_list_update_busy
from native_titlebar import NativeTitleBarStyler
from typography import FONT_OPTIONS, normalize_font, apply_font
from app_paths import APP_ROOT, BACKUP_DIR, CONFIG_PATH, DB_PATH, DEVELOPMENT_MODE, DOWNLOAD_DIR, PROGRAM_DIR, EDGE_PROFILE_DIR, EXPORT_DIR, LOG_DIR, PROFILES_PATH, UPDATE_CACHE_DIR, WAREHOUSE_DEVELOPMENT_MODE
from config import AppConfig, credentials_configured, load_config, save_config
from appearance import (readable_color, profile_for, custom_legibility, normalize_custom_legibility, THEME_PALETTES, THEME_LABELS, _LIGHT_HEX_ROLES, PROFILES, effective_palette,
                        legibility_css, application_legibility_css, appearance_overrides, tracking_style, presence_style, component_css)
from failure_catalog import resolve_selection
from failure_picker import FailurePathPicker
from warehouse_ui import WarehouseWindowMixin
from task_priorities import coordinator, JobCounter, AUTOMATIC, MANUAL, HIGH
from priority_notices import PriorityNotices
from update_status import UpdateStatusBar
from workorder_selection import WorkorderSelection, prepare_row_context_selection
from db import (
    apply_started_workorder, apply_closed_repair, apply_warehouse_status,
    clear_current_priority_snapshot, current_priority_ots, current_priority_snapshots,
    delete_all_inactive_records, delete_inactive_record, fetch_data, filter_choices,
    fault_description_candidate_count, detailed_description_candidate_count,
    enrichment_candidate_count, get_detailed_description, inactive_tracking_candidate_count, init_db,
    replace_priority_snapshot, update_priority_expiration,
)
from maximo_client import REPAIR_REPORT_STATUSES, cleanup_edge_profile, open_ot, verify_credentials
from updater import enrich_fault_descriptions, reconcile_inactive_tracking, run_update
from search_filters import load_profiles, save_profiles
from update_checker import UpdateDownloadCancelled, download_release_asset, fetch_latest_release, format_version_tag, is_newer
from update_installer import distributed_executable, start_update
from managed_install_qt import ManagedInstallError, redirect_to_managed_install
from priority_importer import read_priority_files
from deep_links import parse_ot_uri, register_protocol_handler
from excel_export import write_workorders_xlsx
from release_notes import STATE_FILENAME, cache_release_notes, installed_release_notes, mark_notes_seen, same_version, should_show_notes
from release_notes_ui import ReleaseNotesDialog
import version

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=(
        RotatingFileHandler(
            LOG_DIR / "maximo_desktop.log", maxBytes=5 * 1024 * 1024,
            backupCount=3, encoding="utf-8", delay=True,
        ),
        logging.StreamHandler(),
    ),
    force=True,
)
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.info("Maximo Desktop v%s iniciada. Datos: %s", version.APP_VERSION, APP_ROOT)


STYLESHEET = """
QMainWindow { background: #f5f7fb; color: #172033; }
QDialog { background: #f5f7fb; color: #172033; }
QDialog QLabel, QDialog QCheckBox { color: #172033; }
QLabel { color: #172033; }
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
QLabel#settingsSectionTitle { color: #486581; font-size: 12px; font-weight: 700; padding: 0 2px; }
QLabel#resultLabel { padding: 5px 2px; }
QGroupBox { margin-top: 12px; padding: 12px; font-size: 16px; font-weight: 700; color: #334e68; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #102a43; }
QGroupBox QLabel, QGroupBox QCheckBox { font-size: 12px; font-weight: 400; color: #172033; }
QGroupBox QLineEdit, QGroupBox QSpinBox { font-size: 12px; font-weight: 400; color: #172033; }
QGroupBox QPushButton { font-size: 12px; font-weight: 600; }
QLineEdit, QComboBox, QListWidget, QSpinBox, QDateEdit { border: 1px solid #bcccdc; border-radius: 7px; padding: 7px 10px; background: #ffffff; color: #172033; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus { border: 2px solid #2f80ed; }
QComboBox { padding-right: 36px; }
QDateEdit { padding-right: 36px; }
QComboBox:hover, QSpinBox:hover, QDateEdit:hover { border-color: #829ab1; }
QComboBox::drop-down, QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 30px; border-left: 1px solid #d9e2ec; background: #f8fafc; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QComboBox::drop-down:hover, QDateEdit::drop-down:hover { background: #e8eef5; }
QDateEdit::down-arrow { image: none; }
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
QTabWidget#settingsTabs::pane { border: 0; background: #f5f7fb; }
QTabBar::tab { background: #e8eef5; color: #486581; padding: 10px 16px; margin-right: 5px; border-bottom: 3px solid transparent; border-top-left-radius: 6px; border-top-right-radius: 6px; font-size: 12px; font-weight: 600; }
QTabBar::tab:selected { background: #ffffff; color: #102a43; border-bottom-color: #1976d2; }
QTabBar::tab:hover { background: #dbeafe; }
QToolButton#sidebarToggle, QToolButton#navigationMenu { background: transparent; color: #172033; border: none; border-radius: 6px; padding: 5px; }
QFrame#navigationBar { border-bottom: 1px solid #bcccdc; }
QToolButton#sidebarToggle:hover, QToolButton#navigationMenu:hover { background: #dbeafe; }
"""

# Los perfiles transforman los roles del tema; los widgets no conocen nombres de temas.
ACTIVE_THEME = "light"
ACTIVE_PROFILE = "normal"
ACTIVE_CUSTOM_LEGIBILITY = normalize_custom_legibility(None)
ACTIVE_LEGIBILITY = profile_for("normal")
ACTIVE_FONT_PREFERENCE = "theme"
ACTIVE_FONT_FAMILY = ""
ACTIVE_COLORS = effective_palette(THEME_PALETTES[ACTIVE_THEME])


def _style_tracking_item(item, enabled, default_color, cache=None):
    """Apply/reset only the tracking cell; selection still uses the table palette."""
    cache = cache if cache is not None else {}
    value = item.text()
    if enabled and value not in cache:
        foreground, emphasized = tracking_style(value, ACTIVE_COLORS)
        font = QFont()
        if emphasized:font.setWeight(QFont.DemiBold)
        cache[value] = (QColor(foreground), emphasized, font)
    if enabled and cache[value][1]:
        foreground, _, font = cache[value]
        item.setForeground(foreground);item.setBackground(QBrush());item.setFont(font)
    else:
        item.setForeground(default_color);item.setBackground(QBrush());item.setFont(QFont())


def _style_presence_item(item, active, priority, enabled, cache=None):
    cache = cache if cache is not None else {}
    key = ('presence', active, bool(priority))
    if enabled:
        if key not in cache:
            foreground, _ = presence_style(active, priority, ACTIVE_COLORS)
            font=QFont();font.setWeight(QFont.DemiBold)
            cache[key]=(QColor(foreground),font)
        foreground,font=cache[key]
        item.setForeground(foreground);item.setFont(font)
    else:
        role='priority' if active==1 and priority else 'success' if active==1 else 'inactive'
        item.setForeground(QColor(ACTIVE_COLORS[role]));item.setFont(QFont())
    item.setBackground(QBrush())


def _resolve_theme(preference: str) -> str:
    if preference in THEME_PALETTES:
        return preference
    try:
        scheme = QApplication.styleHints().colorScheme()
        return "dark" if "dark" in str(scheme).lower() else "light"
    except Exception:
        return "light"


def _theme_css(css: str, colors=None) -> str:
    colors = colors or ACTIVE_COLORS
    # La primera pasada usa marcadores. Si sustituyéramos directamente, un
    # color oscuro podría coincidir con un color claro aún pendiente y acabar
    # reemplazado una segunda vez.
    for source, role in _LIGHT_HEX_ROLES.items():
        css = css.replace(source, f"__MAXIMO_{role.upper()}__")
    # El azul oscuro se usaba tanto para el encabezado como para la barra
    # lateral; en oscuro son superficies distintas.
    css = css.replace(
        "QFrame#sidebar { background: __MAXIMO_HEADING__; }",
        "QFrame#sidebar { background: __MAXIMO_SIDEBAR__; }",
    )
    for role, value in colors.items():
        css = css.replace(f"__MAXIMO_{role.upper()}__", value)
    return legibility_css(css, ACTIVE_LEGIBILITY)


def apply_application_theme(app, preference: str, profile="normal", font_preference="theme", custom_options=None) -> str:
    global ACTIVE_THEME, ACTIVE_COLORS, ACTIVE_PROFILE, ACTIVE_FONT_PREFERENCE, ACTIVE_FONT_FAMILY, ACTIVE_CUSTOM_LEGIBILITY, ACTIVE_LEGIBILITY
    ACTIVE_THEME = _resolve_theme(preference)
    ACTIVE_PROFILE = profile if profile in PROFILES else "normal"
    ACTIVE_CUSTOM_LEGIBILITY = normalize_custom_legibility(custom_options)
    ACTIVE_LEGIBILITY = custom_legibility(ACTIVE_CUSTOM_LEGIBILITY) if ACTIVE_PROFILE == "custom" else profile_for(ACTIVE_PROFILE)
    ACTIVE_COLORS = effective_palette(THEME_PALETTES[ACTIVE_THEME], ACTIVE_LEGIBILITY)
    ACTIVE_FONT_PREFERENCE = normalize_font(font_preference)
    ACTIVE_FONT_FAMILY = apply_font(app, PROGRAM_DIR / "ui_assets", ACTIVE_FONT_PREFERENCE, ACTIVE_THEME)
    palette = QPalette(app.palette())
    for role, key in ((QPalette.Window, "canvas"), (QPalette.WindowText, "text"),
                      (QPalette.Base, "surface"), (QPalette.AlternateBase, "subtle"),
                      (QPalette.Text, "text"), (QPalette.Button, "control"),
                      (QPalette.ButtonText, "button_text"), (QPalette.Highlight, "accent_light"),
                      (QPalette.HighlightedText, "text"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.Link, "accent"),
                      (QPalette.PlaceholderText, "muted"), (QPalette.LinkVisited, "accent_hover"),
                      (QPalette.Mid, "border_strong"), (QPalette.Dark, "border_strong"),
                      (QPalette.Light, "soft_border")):
        palette.setColor(role, QColor(ACTIVE_COLORS[key]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(ACTIVE_COLORS["inactive"]))
    app.setPalette(palette)
    app.setStyleSheet(f'QWidget {{ font-family: "{ACTIVE_FONT_FAMILY}"; }}\n'
                     + application_legibility_css(ACTIVE_LEGIBILITY)
                     + _theme_css(STYLESHEET, ACTIVE_COLORS)
                     + legibility_css(component_css(ACTIVE_COLORS, PROGRAM_DIR / "ui_assets"), ACTIVE_LEGIBILITY)
                     + appearance_overrides(ACTIVE_COLORS))
    if not getattr(app,'_md_titlebar_styler',None):
        app._md_titlebar_styler=NativeTitleBarStyler(app,lambda:ACTIVE_COLORS)
        app.installEventFilter(app._md_titlebar_styler)
    app._md_titlebar_styler.refresh()
    if not getattr(app,'_md_theme_polisher',None):
        app._md_theme_polisher = ThemeControlPolisher(app)
        app.installEventFilter(app._md_theme_polisher)
    for calendar in app.allWidgets():
        if isinstance(calendar, QCalendarWidget):
            _style_calendar(calendar)
    return ACTIVE_THEME


class ThemeControlPolisher(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Polish and isinstance(watched,QCalendarWidget):
            _style_calendar(watched)
        return False


def _style_calendar(calendar):
    for day in (Qt.Monday, Qt.Tuesday, Qt.Wednesday, Qt.Thursday, Qt.Friday, Qt.Saturday, Qt.Sunday):
        fmt = QTextCharFormat()
        role = 'danger' if day in (Qt.Saturday,Qt.Sunday) else 'text'
        fmt.setForeground(QColor(ACTIVE_COLORS[role]));calendar.setWeekdayTextFormat(day,fmt)
    header=QTextCharFormat();header.setForeground(QColor(ACTIVE_COLORS['header_text']))
    calendar.setHeaderTextFormat(header)


def show_activity_dialog(message: str, parent=None, theme_preference=None, profile_preference=None):
    """Muestra un diálogo compacto de actividad con los colores del tema activo."""
    dialog = QDialog(parent)
    dialog.setObjectName("activityDialog")
    dialog.setWindowFlags(
        Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
    )
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dialog.setFixedWidth(390)

    card = QFrame(dialog)
    card.setObjectName("activityCard")
    card_layout = QHBoxLayout(card)
    card_layout.setContentsMargins(18, 16, 18, 14)
    card_layout.setSpacing(12)

    icon_label = QLabel()
    icon_path = Path(__file__).resolve().parent / "icon.ico"
    if icon_path.exists():
        icon_label.setPixmap(QIcon(str(icon_path)).pixmap(QSize(32, 32)))
    else:
        icon_label.setText("✿")
    icon_label.setFixedSize(32, 32)
    card_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

    content = QVBoxLayout()
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(5)
    title = QLabel("Maximo Desktop")
    title.setObjectName("activityTitle")
    status = QLabel(message)
    status.setObjectName("activityMessage")
    status.setWordWrap(True)
    content.addWidget(title)
    content.addWidget(status)

    progress = QProgressBar(objectName="activityProgress")
    progress.setRange(0, 0)
    progress.setTextVisible(False)
    progress.setFixedHeight(5)
    content.addSpacing(3)
    content.addWidget(progress)
    card_layout.addLayout(content, 1)

    dialog_layout = QVBoxLayout(dialog)
    dialog_layout.setContentsMargins(1, 1, 1, 1)
    dialog_layout.addWidget(card)
    dialog.adjustSize()
    if parent is not None:
        center = parent.mapToGlobal(parent.rect().center())
    else:
        screen = QApplication.primaryScreen()
        center = screen.availableGeometry().center() if screen else QPointF(0, 0).toPoint()
    dialog.move(center - dialog.rect().center())
    dialog.show()
    QApplication.processEvents()
    return dialog


class TaskSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)


class BackgroundTask(QRunnable):
    def __init__(self, function, with_progress=False):
        super().__init__()
        self.function = function
        self.with_progress = with_progress
        self.signals = TaskSignals()

    def run(self):
        try:
            result = (self.function(self.signals.progress.emit) if self.with_progress
                      else self.function())
            self.signals.completed.emit(result)
        except Exception as exc:  # El detalle completo queda en el log.
            logging.exception("Tarea de interfaz fallida")
            self.signals.failed.emit(str(exc))


class CoordinatedTaskThread(QThread):
    def __init__(self, task, parent):
        super().__init__(parent)
        self.task = task

    def run(self):
        self.task.run()


class LocalOpenBridge(QObject):
    """Forwarda enlaces de Excel a la ventana ya abierta del mismo entorno."""
    uri_received = Signal(str)
    activate_requested = Signal()

    def __init__(self, development=False, initial_uri=""):
        super().__init__()
        suffix = "-dev" if development else ""
        if development and WAREHOUSE_DEVELOPMENT_MODE:
            suffix += "-almacen"
        self.server_name = f"MaximoDesktop{suffix}"
        self.server = None
        self.is_primary = False
        self._buffers = {}

        client = QLocalSocket()
        client.connectToServer(self.server_name)
        if client.waitForConnected(500):
            payload = initial_uri or "__MAXIMODESK_ACTIVATE__"
            client.write((payload + "\n").encode("utf-8"))
            client.waitForBytesWritten(500)
            client.disconnectFromServer()
            return

        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept_connections)
        if not self.server.listen(self.server_name):
            # Si no hay una instancia que responda, puede quedar un nombre de
            # socket obsoleto tras un cierre forzado. Limpiarlo y reintentar.
            QLocalServer.removeServer(self.server_name)
            if not self.server.listen(self.server_name):
                raise RuntimeError(f"No se pudo iniciar el puente local: {self.server.errorString()}")
        self.is_primary = True
        if initial_uri:
            QTimer.singleShot(0, lambda value=initial_uri: self.uri_received.emit(value))

    def _accept_connections(self):
        while self.server and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda client=socket: self._read_request(client))
            socket.disconnected.connect(lambda client=socket: self._forget_client(client))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._read_request(socket)

    def _read_request(self, socket):
        buffer = self._buffers.setdefault(socket, bytearray())
        buffer.extend(bytes(socket.readAll()))
        if b"\n" not in buffer:
            return
        raw_payload, _, remaining = buffer.partition(b"\n")
        self._buffers[socket] = bytearray(remaining)
        payload = raw_payload.decode("utf-8", errors="replace").strip()
        if payload == "__MAXIMODESK_ACTIVATE__":
            self.activate_requested.emit()
            return
        if parse_ot_uri(payload):
            self.uri_received.emit(payload)

    def _forget_client(self, socket):
        self._buffers.pop(socket, None)


def _draw_chevron(painter: QPainter, center_x: float, center_y: float, up: bool) -> None:
    """Dibuja una flecha nítida sin depender de temas ni rutas de recursos."""
    # En coordenadas Qt el eje Y crece hacia abajo: para la punta superior
    # el vértice central debe tener una Y menor que los extremos.
    offset = 2.5 if up else -2.5
    painter.drawLine(QPointF(center_x - 4, center_y + offset), QPointF(center_x, center_y - offset))
    painter.drawLine(QPointF(center_x, center_y - offset), QPointF(center_x + 4, center_y + offset))


class DecoratedComboBox(QComboBox):
    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(ACTIVE_COLORS["header_text"]), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        _draw_chevron(painter, self.width() - 15, self.height() / 2, up=False)


class DecoratedDateEdit(QDateEdit):
    def wheelEvent(self, event):
        if self.calendarWidget().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()

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
        self._menu.setObjectName('clientSelectionMenu')
        self._menu.update()

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
        self.setObjectName('priorityImport')
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
            title.setObjectName("sectionTitle")
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


class MaximoDesktopWindow(WarehouseWindowMixin, QMainWindow):
    columns = ("Estado en Maximo", "OT", "Descripción", "Nº de serie", "Fecha", "Cliente", "Tipo de trabajo", "Seguimiento", "Planta", "Última vez visto", "Avería")
    default_column_widths = (180, 110, 340, 145, 135, 140, 180, 130, 105, 140, 340)
    max_column_widths = (180, 140, 600, 240, 160, 220, 220, 240, 160, 1200, 700)
    close_progress = Signal(str)
    close_finished = Signal()
    app_download_progress = Signal(int, int)
    app_download_status = Signal(str)
    workorder_started = Signal(object)
    workorder_closed = Signal(object)

    def __init__(self):
        super().__init__()
        self.cfg: AppConfig = load_config()
        if (ACTIVE_THEME, ACTIVE_PROFILE, ACTIVE_FONT_PREFERENCE, ACTIVE_CUSTOM_LEGIBILITY) != (_resolve_theme(self.cfg.theme), self.cfg.legibility_profile, self.cfg.font_family, self.cfg.legibility_custom):
            apply_application_theme(QApplication.instance(), self.cfg.theme, self.cfg.legibility_profile, self.cfg.font_family, self.cfg.legibility_custom)
        self.update_lock = JobCounter()
        self.reconcile_lock = JobCounter()
        self.fault_description_lock = JobCounter()
        self.enrichment_cancel_event = threading.Event()
        self.pool = QThreadPool.globalInstance()
        self._running_tasks = set()
        self._coordinated_threads = set()
        self._list_update_pending = False
        self._tasks_idle = threading.Event()
        self._tasks_idle.set()
        self._latest_release = None
        self._app_update_checking = False
        self._app_update_downloading = False
        self._app_update_cancel = threading.Event()
        self._pending_update = None
        self._ready_update = None
        self._prompted_release_tags = set()
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
        self._column_widths_dirty = False
        self._column_width_save_timer = QTimer(self)
        self._column_width_save_timer.setSingleShot(True)
        self._column_width_save_timer.timeout.connect(self._save_column_widths)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(lambda: self.update_now(automatic=True))
        self.close_progress.connect(self._set_close_progress)
        self.close_finished.connect(self._finish_close)
        self.app_download_progress.connect(self._set_app_download_progress)
        self.app_download_status.connect(self._set_app_download_status)
        self.workorder_started.connect(self._workorder_started)
        self.workorder_closed.connect(self._workorder_closed)
        self._priority_coordinator = coordinator
        self._priority_notices = PriorityNotices(lambda message: show_activity_dialog(message, self),
                                                 lambda message: self.status.showMessage(message,7000), self)
        self.destroyed.connect(coordinator.subscribe(self._priority_notices.event_received.emit))
        self.setWindowTitle(f"Maximo Desktop · v{version.APP_VERSION}")
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
        QTimer.singleShot(1800, self.offer_warehouse_recovery)
        # La consulta no bloquea el inicio; si hay una versión nueva, ofrece
        # instalarla una sola vez por sesión.
        if not WAREHOUSE_DEVELOPMENT_MODE:
            QTimer.singleShot(1200, self._startup_release_updates)

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = self._build_sidebar()
        self.sidebar_splitter = QSplitter(Qt.Horizontal, root)
        self.sidebar_splitter.setObjectName("sidebarSplitter")
        self.sidebar_splitter.setChildrenCollapsible(False)
        self.sidebar_splitter.setOpaqueResize(False)
        self.sidebar_splitter.setHandleWidth(5)
        self.sidebar_splitter.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_list_page())
        self.pages.addWidget(self._build_settings_page())
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_navigation_bar())
        content_layout.addWidget(self.pages, 1)
        content.setMinimumWidth(0)
        self.sidebar_splitter.addWidget(content)
        self.sidebar_splitter.setStretchFactor(0, 0)
        self.sidebar_splitter.setStretchFactor(1, 1)
        self.sidebar_splitter.handle(1).setToolTip("Arrastra para ajustar el ancho de la barra lateral")
        self.sidebar_splitter.handle(1).setAccessibleName("Ajustar ancho de la barra lateral")
        self.sidebar_splitter.splitterMoved.connect(self._sidebar_resized)
        layout.addWidget(self.sidebar_splitter, 1)
        self.setCentralWidget(root)
        self._set_sidebar_visible(not self.cfg.sidebar_collapsed)
        self.status = UpdateStatusBar()
        self._priority_notices.event_received.connect(self.status.handle_job_event)
        self.status.showMessage("Listo para consultar la base local.")
        self.setStatusBar(self.status)

    def _build_sidebar(self):
        sidebar = QFrame(objectName="sidebar")
        sidebar.setMinimumWidth(210)
        sidebar.setMaximumWidth(420)
        box = QVBoxLayout(sidebar)
        box.setContentsMargins(16, 24, 16, 18)
        brand_row = QHBoxLayout();brand_row.setContentsMargins(0,0,0,0);brand_row.setSpacing(12)
        self.brand_icon = QLabel(objectName="brandIcon")
        self.brand_icon.setFixedSize(40,40)
        self.brand_icon.setToolTip("Maximo Desktop")
        brand = QLabel("Maximo\nDesktop", objectName="brand")
        brand_row.addWidget(self.brand_icon,0,Qt.AlignVCenter)
        brand_row.addWidget(brand,1)
        box.addLayout(brand_row)
        subtitle = QLabel("SEGUIMIENTO DE REPARACIONES", objectName="subtitle")
        subtitle.setWordWrap(True)
        box.addWidget(subtitle)
        box.addSpacing(24)
        self.load_excel_button=QPushButton("Cargar Excel",objectName="sidebarAction")
        self.load_excel_button.setToolTip("Importar informes Excel de prioridades (.xls)")
        self.load_excel_button.setIcon(QIcon(str(PROGRAM_DIR/'ui_assets'/'excel.svg')))
        self.load_excel_button.setIconSize(QSize(20,20))
        self.load_excel_button.clicked.connect(self.import_priorities)
        box.addWidget(self.load_excel_button)
        self.export_button = QPushButton("Exportar a Excel", objectName="sidebarAction")
        self.export_button.clicked.connect(self.export_current_list)
        box.addWidget(self.export_button)
        box.addSpacing(10)
        separator = QFrame(objectName="sidebarExportSeparator")
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Plain)
        box.addWidget(separator)
        box.addSpacing(10)
        saved_searches_label = QLabel("BÚSQUEDAS GUARDADAS", objectName="sidebarSection")
        saved_searches_label.setWordWrap(True)
        box.addWidget(saved_searches_label)
        self.profile_list = QListWidget(objectName="profileList")
        self.profile_list.setMinimumHeight(140)
        self.profile_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.profile_list.currentItemChanged.connect(self.load_selected_profile)
        self.profile_list.itemClicked.connect(self.load_selected_profile)
        # La lista ocupa todo el alto libre del lateral. Solo necesitará
        # desplazamiento cuando la ventana no pueda mostrar más entradas.
        box.addWidget(self.profile_list, 1)
        save_profile = QPushButton("Guardar búsqueda", objectName="sidebarAction")
        self.save_profile_button=save_profile
        save_profile.clicked.connect(self.save_current_profile)
        box.addWidget(save_profile)
        self.delete_profile_button = QPushButton("Eliminar búsqueda", objectName="sidebarAction")
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.delete_profile_button.setEnabled(False)
        self.delete_profile_button.setToolTip("Selecciona una búsqueda guardada para eliminarla")
        box.addWidget(self.delete_profile_button)
        for button, asset in ((self.export_button,'excel.svg'),
                              (save_profile,'save-search.svg'),
                              (self.delete_profile_button,'delete-search.svg')):
            button.setIcon(QIcon(str(PROGRAM_DIR / 'ui_assets' / asset)))
            button.setIconSize(QSize(20,20))
        if DEVELOPMENT_MODE:
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

    def _build_navigation_bar(self):
        bar = QFrame(objectName='navigationBar')
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 5, 16, 5)
        row.setSpacing(12)
        self.sidebar_toggle = QToolButton(objectName='sidebarToggle')
        self.sidebar_toggle.setFixedSize(32, 30)
        self.sidebar_toggle.setIconSize(QSize(20, 20))
        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        row.addWidget(self.sidebar_toggle)
        self.navigation_menu_button = QToolButton(objectName='navigationMenu')
        self.navigation_menu_button.setText('Maximo Desktop Menú')
        self.navigation_menu_button.setPopupMode(QToolButton.InstantPopup)
        self.navigation_menu_button.setAccessibleName('Maximo Desktop Menú')
        menu = QMenu(self.navigation_menu_button)
        self.navigation_actions = []
        for page, caption in enumerate(('Listado', 'Configuración')):
            action = menu.addAction(caption)
            action.triggered.connect(lambda _checked=False, page=page:self.navigate_to(page))
            self.navigation_actions.append(action)
        menu.addSeparator()
        load_excel_action=menu.addAction('Cargar Excel de prioridades')
        load_excel_action.setIcon(QIcon(str(PROGRAM_DIR / 'ui_assets' / 'excel.svg')))
        load_excel_action.triggered.connect(self.import_priorities)
        self.export_action = menu.addAction('Exportar a Excel')
        self.export_action.setIcon(QIcon(str(PROGRAM_DIR / 'ui_assets' / 'excel.svg')))
        self.export_action.triggered.connect(self.export_current_list)
        self.navigation_menu_button.setMenu(menu)
        row.addWidget(self.navigation_menu_button)
        row.addSpacing(24)
        self.navigation_location = QLabel('Listado', objectName='pageSubtitle')
        row.addWidget(self.navigation_location)
        row.addStretch()
        self._refresh_navigation_icon()
        return bar

    def _refresh_navigation_icon(self):
        if not hasattr(self, "sidebar_toggle"):return
        # Draw at double resolution: the sidebar symbol stays crisp at small sizes.
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(ACTIVE_COLORS['text']), 2.5))
        painter.drawRoundedRect(5, 7, 30, 26, 4, 4)
        painter.drawLine(15, 8, 15, 32)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        self.sidebar_toggle.setIcon(QIcon(pixmap))
        if hasattr(self,"update_icon"):self.update_icon.set_color(ACTIVE_COLORS["on_accent"])
        if hasattr(self,"brand_icon"):
            size = self.brand_icon.width()
            logo = QIcon(str(PROGRAM_DIR / "ui_assets" / "md-brand.svg")).pixmap(size*2,size*2)
            painter = QPainter(logo)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            color = readable_color(ACTIVE_COLORS["accent"],[ACTIVE_COLORS["sidebar"]],4.5)
            painter.fillRect(logo.rect(),QColor(color));painter.end()
            logo.setDevicePixelRatio(2)
            self.brand_icon.setPixmap(logo)
        # Vector icons follow their surface text color, including light sidebars.
        for attribute,asset,role,size in (
                ('save_profile_button','save-search.svg','sidebar_text',20),
                ('delete_profile_button','delete-search.svg','sidebar_text',20),
                ('priority_only_button','priority-flag.svg','button_text',18)):
            if not hasattr(self,attribute):continue
            icon=QIcon(str(PROGRAM_DIR / 'ui_assets' / asset)).pixmap(size*2,size*2)
            painter=QPainter(icon)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(icon.rect(),QColor(ACTIVE_COLORS[role]))
            painter.end();icon.setDevicePixelRatio(2)
            themed_icon = QIcon(icon)
            themed_icon.addPixmap(icon, QIcon.Disabled)
            if attribute == 'priority_only_button':
                active_icon = icon.copy()
                painter = QPainter(active_icon)
                painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                painter.fillRect(active_icon.rect(), QColor(ACTIVE_COLORS['on_accent']))
                painter.end()
                for mode in (QIcon.Normal, QIcon.Active):
                    themed_icon.addPixmap(active_icon, mode, QIcon.On)
            getattr(self,attribute).setIcon(themed_icon)
        # Keep large personal text readable without cutting sidebar actions.
        required = max((button.minimumSizeHint().width() + 32 for button in
            (self.load_excel_button, self.export_button, self.save_profile_button, self.delete_profile_button)), default=210)
        self.sidebar.setMinimumWidth(min(420, max(210, required)))

    def _set_sidebar_visible(self, visible):
        self.sidebar.setVisible(visible)
        if visible:
            total = max(self.sidebar_splitter.width(), self.cfg.sidebar_width + 1)
            with QSignalBlocker(self.sidebar_splitter):
                self.sidebar_splitter.setSizes([self.cfg.sidebar_width, total - self.cfg.sidebar_width])
        caption = 'Ocultar barra lateral' if visible else 'Mostrar barra lateral'
        self.sidebar_toggle.setToolTip(caption)
        self.sidebar_toggle.setAccessibleName(caption)

    def _sidebar_resized(self, _position, _index):
        if self.sidebar.isHidden():
            return
        self.cfg.sidebar_width = self.sidebar.width()
        save_config(self.cfg)
        self._fit_columns_to_viewport()
        self._update_settings_content_width()

    def toggle_sidebar(self):
        visible = self.sidebar.isHidden()
        self._set_sidebar_visible(visible)
        self.cfg.sidebar_collapsed = not visible
        save_config(self.cfg)
        # The window size stays the same; its content viewport has changed.
        QTimer.singleShot(0, self._fit_columns_to_viewport)
        QTimer.singleShot(0, self._update_settings_content_width)

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
                if self.save_settings(show_feedback=False) is False:
                    return False
            elif dialog.clickedButton() is discard:
                self._load_config()
            else:
                return False
        self.pages.setCurrentIndex(page)
        self.navigation_location.setText(("Listado", "Configuración")[page])
        if page == 1:
            # Esta página puede haber estado oculta al calcularse por primera
            # vez; ahora sí conocemos el ancho final del panel principal.
            QTimer.singleShot(0, self._update_settings_content_width)
        return True

    def _build_list_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(30, 0, 30, 18)
        update = QPushButton("Actualizar Maximo", objectName="primary");self.update_button=update
        update_icon = Path(__file__).resolve().parent / "ui_assets" / "refresh-white.svg"
        self.update_icon=RefreshIcon(update,update_icon,ACTIVE_COLORS["on_accent"])
        update.setIconSize(QSize(22, 22))
        update.clicked.connect(self.update_now)
        outer.addWidget(self._page_header("Órdenes de trabajo", "Consulta, filtra y gestiona el seguimiento local.", update))

        search_card = QFrame(objectName="filtersCard");self.search_card=search_card
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
        self.search_edit.setPlaceholderText("OT, nº de serie o descripción · separa varios valores con comas…")
        self.search_edit.setToolTip("Comas: busca cualquiera de los valores. Espacios: todas las partes dentro del mismo valor.")
        self.search_edit.returnPressed.connect(self.refresh_table)
        toolbar.addWidget(self.search_edit, 1, 1)
        toolbar.addWidget(QLabel("Buscar por"), 0, 2)
        self.search_by_combo = DecoratedComboBox()
        self.search_by_combo.addItem("Nº de serie", "Nº_de_serie")
        self.search_by_combo.addItem("OT", "OT")
        self.search_by_combo.addItem("Descripción", "Descripción")
        self.search_by_combo.currentIndexChanged.connect(self.refresh_table)
        toolbar.addWidget(self.search_by_combo, 1, 2)
        self.filter_button = QPushButton("☷  Filtros", objectName="advancedFilter")
        self.filter_button.setProperty("filtersActive", False)
        self.filter_button.clicked.connect(self.open_advanced_filters)
        toolbar.addWidget(self.filter_button, 1, 3)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.clicked.connect(self.clear_filters)
        self.clear_button.setVisible(False)
        toolbar.addWidget(self.clear_button, 1, 4)
        self.priority_only_button = QPushButton("Prioridades", objectName="priorityFilter")
        self.priority_only_button.setIcon(QIcon(str(PROGRAM_DIR / "ui_assets" / "priority-flag.svg")))
        self.priority_only_button.setIconSize(QSize(18, 18))
        self.priority_only_button.setCheckable(True)
        self.priority_only_button.setVisible(False)
        self.priority_only_button.toggled.connect(self._toggle_priority_filter)
        toolbar.addWidget(self.priority_only_button, 1, 5)
        toolbar.setColumnStretch(1, 1)
        search_layout.addLayout(toolbar)
        self.filter_chips = QLabel("Sin filtros", objectName="filterChips")
        self.filter_chips.setVisible(False)
        filter_footer = QHBoxLayout()
        filter_footer.setSpacing(16)
        filter_footer.addWidget(self.filter_chips, 1)
        search_layout.addLayout(filter_footer)

        outer.addWidget(search_card)

        results_row = QHBoxLayout()
        self.result_label = QLabel(objectName="resultLabel")
        results_row.addWidget(self.result_label)
        results_row.addStretch()
        outer.addLayout(results_row)
        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeader(ColumnWidthHeader(self.table))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self.open_table_cell)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setMinimumSectionSize(60)
        header.setCursor(Qt.SplitHCursor)
        header.manualSectionResized.connect(self._column_resized)
        header.resizeStarted.connect(self._column_width_save_timer.stop)
        header.resizeFinished.connect(self._schedule_column_width_save)
        for column, width in enumerate(self.default_column_widths):
            header.resizeSection(column, width)
        self.table.setColumnHidden(self.columns.index("Avería"), not self.cfg.fault_descriptions_enabled)
        self._column_widths = self._current_column_widths()
        self._workorder_selector = WorkorderSelection(self.table, self, compact=True)
        self._workorder_selector.set_enabled(True)
        self._workorder_selector.bar.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
        filter_footer.addStretch()
        filter_footer.addWidget(self._workorder_selector.bar)
        self.table_frame=RoundedTableFrame(self.table,page)
        outer.addWidget(self.table_frame,1)
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
        self._column_widths_dirty = True

    def _schedule_column_width_save(self):
        if self._column_widths_dirty:
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

    def _store_column_width_preferences(self):
        """Persist the user's preferred widths, never the adaptive viewport fit."""
        if not getattr(self, "_column_widths_dirty", False):
            return False
        widths = {str(index): int(width) for index, width in enumerate(self._column_widths)}
        self._column_widths_dirty = False
        if widths == self.cfg.table_column_widths and self.cfg.table_layout_initialized:
            return False
        self.cfg.table_column_widths = widths
        self.cfg.table_layout_initialized = True
        return True

    def _save_column_widths(self):
        if not self._store_column_width_preferences():
            return
        save_config(self.cfg)
        logging.info("Anchos de columnas elegidos por el usuario guardados.")

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 0, 30, 18)
        settings_header_host = QWidget()
        settings_header_layout = QHBoxLayout(settings_header_host)
        settings_header_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_header = self._page_header("Configuración", "Ajustes de la aplicación y de las órdenes de trabajo.")
        self.settings_header.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        settings_header_layout.addWidget(self.settings_header)
        layout.addWidget(settings_header_host)
        self.settings_tabs = QTabWidget(objectName='settingsTabs')
        self.settings_tabs.setDocumentMode(True)
        self._settings_tab_layouts = []

        self.access_card = QGroupBox("Acceso a Maximo")
        form = QFormLayout(self.access_card)
        self.user_edit = QLineEdit(); self.password_edit = QLineEdit(); self.password_edit.setEchoMode(QLineEdit.Password)
        self.auto_check = QCheckBox("Actualizar el listado automáticamente")
        self.interval_spin = DecoratedSpinBox(); self.interval_spin.setRange(1, 1440); self.interval_spin.setSuffix(" min")
        form.addRow("Usuario", self.user_edit); form.addRow("Contraseña", self.password_edit)
        self.auto_update_summary = QLabel()
        self.auto_update_summary.setObjectName("filterHint")
        access_actions = QHBoxLayout()
        self.test_button = QPushButton("Probar y guardar credenciales")
        self.test_button.clicked.connect(self.test_credentials)
        access_actions.addWidget(self.test_button); access_actions.addStretch(); form.addRow(access_actions)

        self.sync_card = QGroupBox('Actualización de Maximo')
        sync_form = QFormLayout(self.sync_card)
        sync_form.addRow('', self.auto_check)
        sync_form.addRow('Intervalo', self.interval_spin)
        sync_form.addRow('Estado', self.auto_update_summary)

        self.app_updates_card = QGroupBox("Actualizaciones de Maximo Desktop")
        update_form = QFormLayout(self.app_updates_card)
        self.app_version_label = QLabel()
        self.app_latest_label = QLabel()
        self.app_last_check_label = QLabel()
        self.app_update_status_label = QLabel()
        self.app_update_status_label.setObjectName("filterHint")
        self.app_update_status_label.setWordWrap(True)
        self.check_app_updates_button = QPushButton("Buscar actualizaciones")
        self.check_app_updates_button.clicked.connect(lambda: self.check_app_updates(automatic=False))
        self.open_release_button = QPushButton("Abrir release")
        self.open_release_button.clicked.connect(self.open_latest_release)
        self.install_update_button = QPushButton("Actualizar ahora")
        self.install_update_button.setObjectName("primary")
        self.install_update_button.clicked.connect(self.install_latest_release)
        update_actions = QHBoxLayout()
        update_actions.addWidget(self.check_app_updates_button)
        update_actions.addWidget(self.install_update_button)
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
        for key in THEME_PALETTES:
            self.theme_combo.addItem(THEME_LABELS.get(key, key), key)
        theme_hint = QLabel("Se aplica al instante; se conserva al guardar los cambios.")
        theme_hint.setObjectName("filterHint")
        theme_hint.setWordWrap(True)
        appearance_form.addRow("Tema", self.theme_combo)
        self.font_combo = DecoratedComboBox()
        for key, option in FONT_OPTIONS.items():
            self.font_combo.addItem(option.label, key)
        appearance_form.addRow("Tipografía", self.font_combo)
        self.font_sample = QLabel("Reparación · OT 4433029 · Áéñ 0O 1Il")
        self.font_sample.setWordWrap(True)
        appearance_form.addRow("Vista previa", self.font_sample)
        self.font_hint = QLabel()
        self.font_hint.setObjectName("filterHint")
        self.font_hint.setWordWrap(True)
        appearance_form.addRow("", self.font_hint)
        self.legibility_combo = DecoratedComboBox()
        for key, profile in PROFILES.items():
            self.legibility_combo.addItem(profile.label, key)
        appearance_form.addRow("Legibilidad", self.legibility_combo)
        self.custom_legibility_controls = QWidget()
        custom_form = QFormLayout(self.custom_legibility_controls)
        custom_form.setContentsMargins(0, 0, 0, 0)
        self.custom_text_size = DecoratedSpinBox()
        self.custom_text_size.setRange(12, 20);self.custom_text_size.setSuffix(" px")
        self.custom_text_size.setKeyboardTracking(False)
        self.custom_text_weight = DecoratedComboBox()
        for caption, weight in (("Regular",400),("Seminegrita",600),("Negrita",700)):
            self.custom_text_weight.addItem(caption,weight)
        self.custom_text_contrast = QCheckBox("Reforzar contraste del texto")
        self.custom_borders = QCheckBox("Resaltar bordes")
        custom_form.addRow("Tamaño base", self.custom_text_size)
        custom_form.addRow("Grosor", self.custom_text_weight)
        custom_form.addRow("", self.custom_text_contrast)
        custom_form.addRow("", self.custom_borders)
        appearance_form.addRow(self.custom_legibility_controls)
        self.custom_legibility_controls.hide()
        self.tracking_colors_check = QCheckBox("Distinguir estados con colores")
        self.tracking_colors_check.setToolTip("Resalta Estado en Maximo y Seguimiento con colores y seminegrita, sin fondo. Mantiene los textos y los indicadores.")
        appearance_form.addRow("", self.tracking_colors_check)
        profile_hint = QLabel("Mayor visibilidad: texto más grande y seminegrita. Alto contraste: además refuerza textos y bordes.")
        profile_hint.setWordWrap(True)
        profile_hint.setObjectName("filterHint")
        appearance_form.addRow("", profile_hint)
        self.theme_combo.currentIndexChanged.connect(self.preview_theme)
        self.legibility_combo.currentIndexChanged.connect(self.preview_theme)
        self.font_combo.currentIndexChanged.connect(self.preview_theme)
        self.custom_text_size.valueChanged.connect(self.preview_theme)
        self.custom_text_weight.currentIndexChanged.connect(self.preview_theme)
        self.custom_text_contrast.toggled.connect(self.preview_theme)
        self.custom_borders.toggled.connect(self.preview_theme)
        self.tracking_colors_check.toggled.connect(self._refresh_table_colors)
        appearance_form.addRow("", theme_hint)

        self.edge_extension_card = QGroupBox("Extensión de Edge")
        edge_extension_layout = QVBoxLayout(self.edge_extension_card)
        edge_extension_intro = QLabel(
            "Opciones de la extensión para las ventanas de Maximo abiertas desde Maximo Desktop."
        )
        edge_extension_intro.setObjectName("filterHint")
        edge_extension_intro.setWordWrap(True)
        edge_extension_layout.addWidget(edge_extension_intro)
        edge_extension_layout.addWidget(QLabel("Órdenes de trabajo", objectName="settingsSectionTitle"))

        start_form = QFormLayout()
        self.workorder_start_check = QCheckBox("Mostrar «Iniciar OT» y «Cambiar anomalías» en Edge")
        self.workorder_start_mode_combo = DecoratedComboBox()
        self.workorder_start_mode_combo.addItem("Elegir comportamiento…", None)
        self.workorder_start_mode_combo.addItem("Iniciar y establecer anomalías", "configured")
        self.workorder_start_mode_combo.addItem("Solo iniciar: conservar anomalías actuales", "only")
        self.workorder_failure_picker = FailurePathPicker(combo_factory=DecoratedComboBox)
        self.workorder_close_check = QCheckBox("Cerrar OT en Edge y finalizar reparaciones desde MD")
        start_hint = QLabel(
            "Añade un botón «Iniciar OT» en las nuevas ventanas de Maximo abiertas desde MD. "
            "Elige si inicia conservando los datos actuales o establece la combinación predeterminada. "
            "En Edge también puedes elegir otra combinación para una OT concreta. "
            "En estado INPRG permite cambiar las anomalías sin iniciar ni cerrar la OT. "
            "Se aplica a las nuevas ventanas de OT."
        )
        start_hint.setObjectName("filterHint")
        start_hint.setWordWrap(True)
        start_form.addRow("", self.workorder_start_check)
        start_form.addRow("Al pulsar Iniciar OT", self.workorder_start_mode_combo)
        start_form.addRow("", self.workorder_failure_picker)
        start_form.addRow("", start_hint)
        self.workorder_start_check.toggled.connect(self._update_workorder_start_controls)
        self.workorder_start_mode_combo.currentIndexChanged.connect(self._update_workorder_start_controls)
        start_form.addRow("", self.workorder_close_check)
        close_hint = QLabel(
            "Añade «Cerrar OT» en las nuevas ventanas de Maximo abiertas desde MD. "
            "Pide el inicio real y revisa la duración en tramos de 15 minutos. Calcula la finalización, "
            "sin superar la hora actual, y pide confirmar antes de ejecutar el flujo hacia ISSUE. "
            "También habilita la finalización de reparaciones desde el menú Técnico del listado de MD."
        )
        close_hint.setObjectName('filterHint')
        close_hint.setWordWrap(True)
        start_form.addRow('', close_hint)

        edge_extension_layout.addLayout(start_form)
        self.printing_card = QGroupBox('Partes de reparación')
        printing_layout = QVBoxLayout(self.printing_card)

        repair_form = QFormLayout()
        self.repair_extension_check = QCheckBox("Mostrar «Imprimir parte» en Edge")
        self.repair_mode_combo = DecoratedComboBox()
        self.repair_mode_combo.addItem("Mostrar diálogo de impresión", "dialog")
        self.repair_mode_combo.addItem("Imprimir directamente", "direct")
        self.repair_stamp_check = QCheckBox("Sello «IRREPARABLE» en el parte")
        self.repair_stamp_check.setToolTip("Solo con desecho verificado. Impresión HTML: color desde MD; blanco y negro desde Edge. No modifica el PDF nativo de BIRT.")
        self.repair_close_tabs_check = QCheckBox("Cerrar las ventanas del parte tras impresión directa")
        self.repair_hint = QLabel(
            "El modo directo usa la impresora predeterminada de Windows. "
            "Se aplica a todas las impresiones de esa ventana de Edge. "
            "Las ventanas del parte solo se cierran en modo directo si activas esta opción. "
            "Con el diálogo de impresión permanecen abiertas para que puedas revisarlas o cancelar. "
            "Los cambios afectan a las nuevas ventanas de OT."
        )
        self.repair_hint.setObjectName("filterHint")
        self.repair_hint.setWordWrap(True)
        repair_form.addRow("", self.repair_extension_check)
        repair_form.addRow("Al pulsar Imprimir parte", self.repair_mode_combo)
        repair_form.addRow("", self.repair_close_tabs_check)
        repair_form.addRow("", self.repair_stamp_check)
        repair_form.addRow("", self.repair_hint)
        printing_layout.addLayout(repair_form)
        self.repair_extension_check.toggled.connect(self.repair_mode_combo.setEnabled)


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
        self.detailed_descriptions_check = QCheckBox("Obtener descripciones detalladas de OT")
        self.detailed_descriptions_check.toggled.connect(self._update_fault_description_controls)
        self.fault_batch_spin = DecoratedSpinBox(); self.fault_batch_spin.setRange(1, 100); self.fault_batch_spin.setSuffix(" OT")
        self.fault_pending_label = QLabel(); self.fault_pending_label.setObjectName("filterHint")
        self.fault_run_button = QPushButton("Completar información pendiente ahora")
        self.fault_run_button.clicked.connect(self.start_priority_fault_descriptions)
        self.fault_cancel_button = QPushButton("Cancelar lectura")
        self.fault_cancel_button.setEnabled(False)
        self.fault_cancel_button.clicked.connect(self.cancel_fault_descriptions)
        fault_form.addRow("", self.fault_descriptions_check)
        fault_form.addRow("", self.detailed_descriptions_check)
        fault_form.addRow("Tamaño de lote", self.fault_batch_spin)
        fault_form.addRow("Pendientes de avería", self.fault_pending_label)
        self.detail_pending_label = QLabel(objectName="filterHint")
        fault_form.addRow("Pendientes de detalle", self.detail_pending_label)
        fault_actions = QHBoxLayout()
        fault_actions.addWidget(self.fault_run_button, 1)
        fault_actions.addWidget(self.fault_cancel_button)
        fault_form.addRow(fault_actions)

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
        self.priority_expiry_edit = DecoratedDateEdit()
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

        self.technician_sat_card = QGroupBox("Envío a SAT · Técnico")
        technical_layout = QVBoxLayout(self.technician_sat_card)
        self.technician_sat_check = QCheckBox("Mostrar envío técnico a SAT externo en MD")
        technical_layout.addWidget(self.technician_sat_check)
        technical_hint = QLabel("Permite revisar y enviar una o varias OTs en APPR desde el menú contextual. "
            "Pide horas, incidencia o referencia y motivo; propone la avería de MD y la consulta en Maximo solo si falta. "
            "La combinación de anomalías se revisa antes de ejecutar. No activa opciones de almacén ni de Edge.")
        technical_hint.setWordWrap(True); technical_hint.setObjectName("filterHint")
        technical_layout.addWidget(technical_hint)
        technical_recovery = QPushButton("Revisar operaciones pendientes…")
        technical_recovery.clicked.connect(self.open_warehouse_recovery)
        technical_layout.addWidget(technical_recovery)

        self.warehouse_card = QGroupBox("Funciones de almacén · En pruebas")
        warehouse_layout = QVBoxLayout(self.warehouse_card)
        self.warehouse_check = QCheckBox("Mostrar acciones de almacén")
        warehouse_layout.addWidget(self.warehouse_check)
        self.warehouse_details_check = QCheckBox("Pedir detalles antes de enviar a SAT")
        self.warehouse_details_check.setToolTip(
            "Muestra un campo opcional por OT en la revisión del lote. "
            "Desactivado: se deja Detalles vacío; no se inventa una justificación.")
        warehouse_layout.addWidget(self.warehouse_details_check)
        self.warehouse_recovery_button = QPushButton("Revisar operaciones pendientes…")
        self.warehouse_recovery_button.clicked.connect(self.open_warehouse_recovery)
        self.warehouse_recovery_button.setEnabled(self.cfg.warehouse_enabled)
        self.warehouse_check.toggled.connect(self.warehouse_recovery_button.setEnabled)
        warehouse_layout.addWidget(self.warehouse_recovery_button)
        warehouse_hint = QLabel("Muestra las acciones de recepción y salida en el menú contextual. "
                               "Ejecuta las acciones validadas en segundo plano tras revisar y confirmar las OTs. "
                               "Las opciones pendientes de validación permanecen deshabilitadas.")
        warehouse_hint.setWordWrap(True)
        warehouse_hint.setObjectName("filterHint")
        warehouse_layout.addWidget(warehouse_hint)

        self._add_settings_tab('General',
            (self.access_card, self.app_updates_card), (self.appearance_card,))
        self._add_settings_tab('Datos y sincronización',
            (self.sync_card, self.maintenance_card, self.paths_card),
            (self.fault_descriptions_card, self.priorities_card))
        self._add_settings_tab('Técnico y extensión',
            (self.edge_extension_card,), (self.printing_card, self.technician_sat_card))
        self._add_settings_tab('Almacén', (self.warehouse_card,), ())
        self.settings_tabs.currentChanged.connect(self._settings_tab_changed)
        self._settings_tab_changed(0)
        save_row = QHBoxLayout()
        self.settings_save_hint = QLabel('Los cambios se conservan al guardar.')
        self.settings_save_hint.setObjectName('filterHint')
        self.settings_save_hint.setWordWrap(True)
        self.save_settings_button = QPushButton('Guardar cambios', objectName='primary')
        self.save_settings_button.clicked.connect(self.save_settings)
        save_row.addWidget(self.settings_save_hint,1);save_row.addWidget(self.save_settings_button)
        layout.addWidget(self.settings_tabs, 1);layout.addLayout(save_row)
        for widget_type, signal in ((QLineEdit,'textChanged'),(QComboBox,'currentIndexChanged'),
                                    (QCheckBox,'toggled'),(QSpinBox,'valueChanged'),(QDateEdit,'dateChanged')):
            for widget in self.settings_tabs.findChildren(widget_type):
                getattr(widget,signal).connect(self._update_settings_dirty_hint)
        QTimer.singleShot(0, self._update_settings_content_width)
        return page

    def _add_settings_tab(self, title, left_cards, right_cards):
        scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(objectName='settingsContent')
        outer = QHBoxLayout(content);outer.setContentsMargins(0,10,0,20)
        center = QWidget();center.setMaximumWidth(1280)
        center.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        outer.addWidget(center,1,Qt.AlignTop)
        columns = QBoxLayout(QBoxLayout.LeftToRight)
        columns.setContentsMargins(0,0,0,0);columns.setSpacing(16)
        body = QVBoxLayout(center);body.setContentsMargins(0,0,0,0);body.addLayout(columns);body.addStretch()
        for cards in (left_cards,right_cards):
            column=QWidget();column.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
            box=QVBoxLayout(column);box.setContentsMargins(0,0,0,0);box.setSpacing(16)
            for card in cards:box.addWidget(card)
            columns.addWidget(column,1,Qt.AlignTop)
        scroll.setWidget(content)
        self._settings_tab_layouts.append({'scroll':scroll,'center':center,'columns':columns})
        self.settings_tabs.addTab(scroll,title)

    def _settings_tab_changed(self, index):
        if index<0:return
        current=self._settings_tab_layouts[index]
        # Aliases describe the active page, including in the isolated settings harness.
        self.settings_scroll=current['scroll'];self.settings_center=current['center'];self.settings_columns=current['columns']
        self._update_settings_content_width()
        QTimer.singleShot(0,self._update_settings_content_width)

    def _update_settings_dirty_hint(self,*_args):
        if not hasattr(self,'settings_save_hint'):return
        self.settings_save_hint.setText('Hay cambios sin guardar.' if self.settings_dirty() else
                                       'Los cambios se conservan al guardar.')

    def _update_settings_content_width(self):
        if not hasattr(self,'settings_scroll'):return
        available=self.settings_scroll.viewport().width()
        if available<=0:return
        width=min(1280,available)
        self.settings_center.setMaximumWidth(width)
        self.settings_center.resize(width,self.settings_center.height())
        self._arrange_settings_cards()

    def _arrange_settings_cards(self):
        if not hasattr(self,'settings_columns'):return
        direction=QBoxLayout.LeftToRight if self.settings_center.width()>=980 else QBoxLayout.TopToBottom
        self.settings_columns.setDirection(direction)

    @staticmethod
    def _set_combo_value(combo, value):
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def preview_theme(self):
        """Muestra el tema elegido antes de confirmar el resto de ajustes."""
        preference = self.theme_combo.currentData()
        self.custom_legibility_controls.setVisible(self.legibility_combo.currentData() == "custom")
        activity = show_activity_dialog(
            "Aplicando la apariencia…",
            self,
            theme_preference=preference,
            profile_preference=self.legibility_combo.currentData(),
        )
        try:
            self._effective_theme = apply_application_theme(QApplication.instance(), preference, self.legibility_combo.currentData(), self.font_combo.currentData(), self._custom_legibility_options())
            self._refresh_font_hint()
            self._refresh_navigation_icon()
            self.client_combo.refresh_theme()
            self._refresh_table_colors()
        finally:
            activity.close()

    def _custom_legibility_options(self):
        return {"text_size":self.custom_text_size.value(), "weight":self.custom_text_weight.currentData(),
                "contrast":self.custom_text_contrast.isChecked(), "borders":self.custom_borders.isChecked()}

    def _refresh_font_hint(self):
        source = "Predeterminada del tema" if self.font_combo.currentData() == "theme" else "Elección personal"
        self.font_hint.setText(f"{source}: {ACTIVE_FONT_FAMILY}. La elección personal se mantiene al cambiar de tema.")

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
        self._refresh_priority_indicators()
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
        self._refresh_priority_indicators()
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
        self._refresh_priority_indicators()
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
        with QSignalBlocker(self.search_by_combo):
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
            filters = self.effective_advanced_filters()
            rows = fetch_data(self.search_edit.text(), self.search_field(), "Todos", filters,
                              include_sync=True, include_fault=True, include_detail=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Filtros", str(exc)); return
        priority_ots = current_priority_ots()
        self._refresh_priority_button_label()
        self.priority_only_button.setVisible(bool(priority_ots))
        if not priority_ots and self.priority_only_button.isChecked():
            with QSignalBlocker(self.priority_only_button):
                self.priority_only_button.setChecked(False)
        self._priority_ots = priority_ots
        def ot_sort_key(row):
            value = str(row[2] or "").strip()
            return (0, int(value)) if value.isdigit() else (1, value)
        rows.sort(key=ot_sort_key, reverse=True)
        snapshot = (tuple(rows), frozenset(priority_ots),
                    self.cfg.fault_descriptions_enabled, self.cfg.detailed_descriptions_enabled)
        filter_key = (self.search_edit.text(), self.search_field(), repr(filters))
        if getattr(self, '_table_snapshot', None) == snapshot and self.table.rowCount() == len(rows):
            self._refresh_table_colors()
            if getattr(self, '_table_filter_key', None) != filter_key:
                self._workorder_selector.clear_selection()
            self._table_filter_key = filter_key
            self._update_list_summary()
            return False

        detail_column = self.columns.index("Avería" if self.cfg.fault_descriptions_enabled else "Descripción")
        tracking_colors = {}
        colors = {key: QColor(value) for key, value in ACTIVE_COLORS.items()}
        detail_icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
        updates_enabled = self.table.updatesEnabled()
        self._table_snapshot = None
        self.table.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self.table):
                self.table.setSortingEnabled(False)
                self.table.setRowCount(0)
                self.table.setRowCount(len(rows))
                for index, raw in enumerate(rows):
                    active, last_seen, *data = raw
                    has_detail = bool(data.pop())
                    fault_description = data.pop()
                    is_priority = active == 1 and str(raw[2] or "") in priority_ots
                    status = "▲ Prioridad · ✓ Activo en Maximo" if is_priority else "✓ Activo en Maximo" if active == 1 else "× No activo en Maximo" if active == 0 else "? Estado desconocido"
                    try: last_seen = datetime.fromisoformat(last_seen).strftime("%d/%m/%Y %H:%M") if last_seen else ""
                    except (TypeError, ValueError): pass
                    values = [status, *data, last_seen, fault_description]
                    for column, value in enumerate(values):
                        item = QTableWidgetItem(str(value or "")); item.setData(Qt.UserRole, raw[2])
                        item.setForeground(colors["text" if active == 1 else "inactive"])
                        if column == detail_column and has_detail and self.cfg.detailed_descriptions_enabled:
                            item.setIcon(detail_icon)
                            item.setToolTip("Descripción detallada disponible. Doble clic para verla.")
                        if column == self.columns.index("Seguimiento"):
                            _style_tracking_item(item, self.tracking_colors_check.isChecked(),
                                colors["text" if active == 1 else "inactive"], tracking_colors)
                        if column == 0:
                            item.setToolTip("Prioridad: marcada en el informe local vigente y todavía activa en Maximo.\n\nActivo en Maximo: aparece en el listado de reparaciones y recibe actualizaciones.\nNo activo en Maximo: ya no aparece en ese listado y no recibe nuevas actualizaciones.")
                            _style_presence_item(item,active,is_priority,self.tracking_colors_check.isChecked(),tracking_colors)
                            item.setData(Qt.UserRole + 1, is_priority)
                            item.setData(Qt.UserRole + 2, active)
                        self.table.setItem(index, column, item)
                self.table.setSortingEnabled(True)
                self.table.horizontalHeader().setSortIndicator(1, Qt.DescendingOrder)
                self.table.setColumnHidden(self.columns.index("Avería"), not self.cfg.fault_descriptions_enabled)
        finally:
            self.table.setUpdatesEnabled(updates_enabled)
        self._table_snapshot = snapshot
        self._table_filter_key = filter_key
        self._table_palette = (dict(ACTIVE_COLORS), ACTIVE_LEGIBILITY, self.tracking_colors_check.isChecked())
        self.table.verticalHeader().setDefaultSectionSize(ACTIVE_LEGIBILITY.row_height)
        self._apply_priority_filter()
        self._update_list_summary()
        return True

    def _refresh_table_colors(self):
        """Apply the theme to existing items without querying or rebuilding data."""
        signature = (dict(ACTIVE_COLORS), ACTIVE_LEGIBILITY, self.tracking_colors_check.isChecked())
        if not hasattr(self, 'table') or getattr(self, '_table_palette', None) == signature:
            return
        colors = {key: QColor(value) for key, value in ACTIVE_COLORS.items()}
        tracking_colors = {}
        detail_icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
        detail_column = self.columns.index("Avería" if self.cfg.fault_descriptions_enabled else "Descripción")
        updates_enabled = self.table.updatesEnabled()
        self.table.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self.table):
                for row in range(self.table.rowCount()):
                    status = self.table.item(row, 0)
                    if status is None:
                        continue
                    active = status.data(Qt.UserRole + 2)
                    priority = bool(status.data(Qt.UserRole + 1))
                    for column in range(1, self.table.columnCount()):
                        item = self.table.item(row, column)
                        if item is not None:
                            item.setForeground(colors["text" if active == 1 else "inactive"])
                            if column == detail_column and not item.icon().isNull():
                                item.setIcon(detail_icon)
                    _style_presence_item(status,active,priority,self.tracking_colors_check.isChecked(),tracking_colors)
                    tracking = self.table.item(row, self.columns.index("Seguimiento"))
                    if tracking is not None:
                        _style_tracking_item(tracking, self.tracking_colors_check.isChecked(),
                            colors["text" if active == 1 else "inactive"], tracking_colors)
        finally:
            self.table.setUpdatesEnabled(updates_enabled)
        self._table_palette = signature
        self.table.verticalHeader().setDefaultSectionSize(ACTIVE_LEGIBILITY.row_height)

    def warehouse_row_updated(self, ot, tracking):
        """Refresh a verified operation without rebuilding thousands of unchanged rows."""
        self._table_snapshot = None
        try:
            allowed = {str(row[0]): str(row[6] or '') for row in fetch_data(
                self.search_edit.text(), self.search_field(), "Todos", self.effective_advanced_filters())}
            choices = self.filter_choices_cache['tracking']
            if tracking not in choices:
                choices.append(tracking)
                choices.sort()
            row = next((r for r in range(self.table.rowCount())
                        if self.table.item(r, 1) and self.table.item(r, 1).text() == ot), None)
            if row is None:
                if ot in allowed:
                    self.refresh_table()
                return
            sorting = self.table.isSortingEnabled()
            self.table.setSortingEnabled(False)
            try:
                if ot not in allowed:
                    self.table.removeRow(row)
                else:
                    self.table.item(row, 7).setText(allowed[ot])
                    active=self.table.item(row,0).data(Qt.UserRole+2)
                    _style_tracking_item(self.table.item(row,7),self.tracking_colors_check.isChecked(),
                                         QColor(ACTIVE_COLORS['text' if active==1 else 'inactive']))
            finally:
                self.table.setSortingEnabled(sorting)
            self._update_list_summary()
            if getattr(self, '_workorder_selector', None) is not None:
                self._workorder_selector.refresh()
        except Exception:
            logging.exception('Estado local guardado; no se pudo refrescar la fila de almacén %s', ot)
            self.status.showMessage('Estado guardado. Actualiza el listado para refrescar la tabla.', 7000)

    def _refresh_priority_button_label(self):
        projects = {item["project"] for item in current_priority_snapshots()
                    if item["is_current"] and item["item_count"] > 0}
        aliases = {"TMB": "TMB", "Línea 9": "L9", "RENFE": "RENFE"}
        ordered = [aliases[project] for project in aliases if project in projects]
        ordered.extend(sorted(projects - aliases.keys()))
        suffix = "/".join(ordered)
        self.priority_only_button.setText("Prioridades" + (" " + suffix if suffix else ""))

    def _toggle_priority_filter(self, _checked):
        """Shows or hides existing table rows without querying SQLite or rebuilding cells."""
        if getattr(self, '_workorder_selector', None) is not None:
            self._workorder_selector.clear_selection()
        self._apply_priority_filter()
        self._update_list_summary()

    def _apply_priority_filter(self):
        checked = self.priority_only_button.isChecked()
        self.table.setUpdatesEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                self.table.setRowHidden(row, checked and not bool(item and item.data(Qt.UserRole + 1)))
        finally:
            self.table.setUpdatesEnabled(True)
        self.table.viewport().update()
        if getattr(self, '_workorder_selector', None) is not None:
            self._workorder_selector.refresh()

    def _refresh_priority_indicators(self):
        """Refreshes priority markers and visibility after local priority changes."""
        self._table_snapshot = None
        priority_ots = current_priority_ots()
        self._priority_ots = priority_ots
        self._refresh_priority_button_label()
        self.priority_only_button.setVisible(bool(priority_ots))
        if not priority_ots and self.priority_only_button.isChecked():
            self.priority_only_button.blockSignals(True)
            self.priority_only_button.setChecked(False)
            self.priority_only_button.blockSignals(False)
        sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        presence_colors = {}
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                active = item.data(Qt.UserRole + 2)
                ot = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
                is_priority = active == 1 and ot in priority_ots
                item.setData(Qt.UserRole + 1, is_priority)
                item.setText("▲ Prioridad · ✓ Activo en Maximo" if is_priority else
                             "✓ Activo en Maximo" if active == 1 else
                             "× No activo en Maximo" if active == 0 else "? Estado desconocido")
                _style_presence_item(item,active,is_priority,self.tracking_colors_check.isChecked(),presence_colors)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(sorting_enabled)
        self._apply_priority_filter()
        self._update_list_summary()

    def _update_list_summary(self):
        summary = self.active_filter_summary()
        if self.priority_only_button.isChecked():
            summary.append("Solo prioritarias")
        self.filter_chips.setVisible(bool(summary))
        self.filter_chips.setText("Filtros activos · " + "   •   ".join(summary))
        advanced_count = sum(bool(value) for value in self.advanced_state.values())
        active = advanced_count > 0
        if self.filter_button.property("filtersActive") != active:
            self.filter_button.setProperty("filtersActive", active)
            self.filter_button.style().unpolish(self.filter_button)
            self.filter_button.style().polish(self.filter_button)
            self.filter_button.update()
        self.filter_button.setText(f"☷  Filtros ({advanced_count})" if advanced_count else "☷  Filtros")
        self.clear_button.setVisible(bool(summary))
        visible_count = sum(not self.table.isRowHidden(row) for row in range(self.table.rowCount()))
        self.result_label.setText(f"{visible_count:,} resultados · {'Filtros aplicados' if summary else 'Sin filtros'}")
        self.export_button.setEnabled(visible_count > 0)
        if hasattr(self,"export_action"):self.export_action.setEnabled(visible_count > 0)

    def clear_filters(self):
        self.search_edit.clear()
        with QSignalBlocker(self.client_combo):
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
        prepare_row_context_selection(self.table, self.table.indexAt(position))
        ot = self.selected_ot(row)
        menu = QMenu(self); menu.addAction("Copiar valor", lambda: QApplication.clipboard().setText(self.table.currentItem().text()))
        menu.addAction("Copiar OT", lambda: QApplication.clipboard().setText(ot))
        menu.addAction("Copiar número de serie", lambda: QApplication.clipboard().setText(self.table.item(row, 3).text()))
        menu.addSeparator()
        if self.cfg.detailed_descriptions_enabled and get_detailed_description(ot)[0]:
            menu.addAction("Ver descripción detallada", lambda: self.show_detailed_description(ot))
        menu.addAction("Abrir OT en Maximo", lambda: self.open_ot_for_row(row))
        tracking = self.table.item(row, 7).text().strip().upper()
        report_enabled = tracking in REPAIR_REPORT_STATUSES
        print_action = menu.addAction("Imprimir parte…", lambda: self.open_repair_report(ot, "print"))
        pdf_action = menu.addAction("Guardar parte en PDF…", lambda: self.open_repair_report(ot, "pdf"))
        print_action.setEnabled(report_enabled)
        pdf_action.setEnabled(report_enabled)
        if not report_enabled:
            reason = f"No disponible en el estado «{tracking or 'desconocido'}». Actualiza Maximo cuando la OT pase a ISSUE/DAR SALIDA o CLOSE."
            print_action.setToolTip(reason)
            pdf_action.setToolTip(reason)
        if self.table.item(row, 0).text() == "○ No activo":
            menu.addAction("Eliminar registro local…", lambda: self.delete_inactive(ot))
        self.add_role_action_menus(menu)
        try:menu.exec(self.table.viewport().mapToGlobal(position))
        finally:self._workorder_selector.clear_context()

    def delete_inactive(self, ot):
        if QMessageBox.question(self, "Eliminar registro", f"¿Eliminar la OT no activa {ot} de la base local?") == QMessageBox.Yes:
            delete_inactive_record(ot); self.refresh_table(); self._refresh_reconciliation_summary()

    def delete_all_inactive(self):
        count = sum(1 for row in range(self.table.rowCount()) if self.table.item(row, 0).text() == "○ No activo")
        if QMessageBox.question(self, "Eliminar registros", f"¿Eliminar todos los registros no activos?\n\nSe eliminarán de la base local.") == QMessageBox.Yes:
            deleted = delete_all_inactive_records(); self.refresh_table(); self._refresh_reconciliation_summary(); self.status.showMessage(f"{deleted} registros no activos eliminados.", 5000)

    def _start_task(self, function, completed, failed=None, progress=None, coordinated=False):
        """Mantiene viva la señal de Qt hasta que la tarea responde.

        QThreadPool conserva el QRunnable nativo, pero no necesariamente el
        QObject de señales de Python. Retenerlo aquí evita perder la llamada de
        fin y dejar bloqueados los candados de Maximo.
        """
        task = BackgroundTask(function, with_progress=progress is not None)
        if progress is not None:
            task.signals.progress.connect(progress)
        self._running_tasks.add(task)
        self._tasks_idle.clear()

        def on_completed(result):
            try:
                completed(result)
            finally:
                self._running_tasks.discard(task)
                if not self._running_tasks:
                    self._tasks_idle.set()

        def on_failed(error):
            try:
                if failed:
                    failed(error)
                elif not self._closing:
                    QMessageBox.critical(self, "Error", error)
            finally:
                self._running_tasks.discard(task)
                if not self._running_tasks:
                    self._tasks_idle.set()

        task.signals.completed.connect(on_completed)
        task.signals.failed.connect(on_failed)
        if coordinated:
            thread = CoordinatedTaskThread(task, self)
            self._coordinated_threads.add(thread)
            thread.finished.connect(lambda: self._coordinated_threads.discard(thread))
            thread.finished.connect(thread.deleteLater)
            thread.start()
        else:
            self.pool.start(task)

    def _credentials_ready(self):
        if credentials_configured(): return True
        QMessageBox.information(self, "Credenciales necesarias", "Configura y guarda las credenciales de Maximo antes de continuar.")
        self.navigate_to(1)
        return False

    def update_now(self, automatic=False):
        if getattr(self, '_list_update_pending', False):
            if not automatic and not self._closing:
                QMessageBox.information(self, "Actualización", "Ya hay una actualización del listado en curso o pendiente de comenzar.")
            return
        if self._closing or not self._credentials_ready() or not self.update_lock.acquire(False): return
        set_list_update_busy(self,True)
        self.status.begin_progress()
        def done(result):
            set_list_update_busy(self,False)
            self.status.finish_progress()
            self.update_lock.release(); new, changed = result; self.refresh_choices(); self.refresh_table(); self._refresh_reconciliation_summary()
            sync_summary = (
                f"Última sincronización de Maximo ({datetime.now().strftime('%H:%M')}): "
                f"completada · {new} nuevas, {changed} actualizadas"
            )
            if self._closing:
                self.status.showMessage(sync_summary)
                return
            self.status.showMessage(sync_summary + " · Conciliación en segundo plano…")
            self.start_background_reconcile(
                sync_summary,
                after=lambda summary: self.start_background_fault_descriptions(summary),
            )
        def failed(error):
            set_list_update_busy(self,False)
            self.status.finish_progress()
            self.update_lock.release()
            if not self._closing:
                QMessageBox.critical(self, "Actualización", f"No se pudo actualizar:\n{error}")
            self.status.showMessage("La actualización falló.")
        try:
            self._start_task(lambda progress: run_update(headless=True,
                job_priority=AUTOMATIC if automatic else MANUAL, progress_callback=progress), done, failed,
                progress=lambda _completed, _total, phase: self.status.update_progress(phase), coordinated=True)
        except Exception as exc:
            if self._list_update_pending:failed(str(exc))
            else:raise

    def start_background_reconcile(self, sync_summary=None, after=None):
        if self._closing:
            return
        if not self.cfg.reconciliation_enabled:
            if after:
                after(sync_summary)
            return
        if self.reconcile_lock.locked() or not self.reconcile_lock.acquire(False):
            if sync_summary:
                self.status.showMessage(sync_summary + " · Conciliación ya en curso.")
            if after:
                after(sync_summary)
            return
        batch = self.cfg.reconciliation_batch_size
        if not sync_summary:
            self.status.showMessage(f"Revisando hasta {batch} OT históricas en segundo plano…")
        def done(changed):
            self.reconcile_lock.release()
            if changed:
                self.refresh_table()
            self._refresh_reconciliation_summary()
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
        self._start_task(lambda: reconcile_inactive_tracking(limit=batch), done, failed, coordinated=True)

    def _refresh_fault_description_summary(self):
        if not hasattr(self, "fault_pending_label"):
            return
        pending = fault_description_candidate_count()
        detail_pending = detailed_description_candidate_count()
        self.detail_pending_label.setText(
            f"{detail_pending} OT activas pendientes de comprobar."
            if self.cfg.detailed_descriptions_enabled else
            f"Desactivado. {detail_pending} OT activas pendientes."
        )
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
        enabled = self.fault_descriptions_check.isChecked() or self.detailed_descriptions_check.isChecked()
        self.fault_batch_spin.setEnabled(enabled)
        self.fault_run_button.setEnabled(enabled)
        if hasattr(self, "table"):
            self.table.setColumnHidden(self.columns.index("Avería"), not self.fault_descriptions_check.isChecked())
            QTimer.singleShot(0, self._fit_columns_to_viewport)

    def cancel_fault_descriptions(self):
        if self.fault_description_lock.locked():
            self.enrichment_cancel_event.set()
            self.fault_cancel_button.setEnabled(False)
            self.status.showMessage("Cancelando lectura de OT…")

    def start_background_fault_descriptions(self, sync_summary=None):
        """Enriquece en segundo plano solo las OT activas sin avería local."""
        if self._closing:
            return
        if self.fault_description_lock.locked():
            return
        if not (self.cfg.fault_descriptions_enabled or self.cfg.detailed_descriptions_enabled) or not self.update_lock.acquire(False):
            return
        if not self.fault_description_lock.acquire(False):
            self.update_lock.release()
            return
        cancel_event = threading.Event()
        self.enrichment_cancel_event = cancel_event
        self.fault_cancel_button.setEnabled(True)
        batch = self.cfg.fault_description_batch_size
        if sync_summary:
            self.status.showMessage(sync_summary + " · Completando información de OT en segundo plano…")
        else:
            self.status.showMessage(f"Completando información de hasta {batch} OT…")

        def done(completed):
            cancelled = cancel_event.is_set()
            self.fault_description_lock.release(); self.update_lock.release()
            self.fault_cancel_button.setEnabled(self.fault_description_lock.locked())
            if completed:
                self.refresh_table()
            self._refresh_fault_description_summary()
            detail = (f"Lectura cancelada: {completed} campos guardados" if cancelled else
                      "Información ampliada: sin pendientes nuevas" if not completed else
                      f"Información ampliada: {completed} campos completados")
            self.status.showMessage(f"{sync_summary} · {detail}" if sync_summary else detail)

        def failed(error):
            self.fault_description_lock.release(); self.update_lock.release()
            self.fault_cancel_button.setEnabled(self.fault_description_lock.locked())
            logging.warning("Enriquecimiento de averías falló: %s", error)
            self._refresh_fault_description_summary()
            self.status.showMessage(f"{sync_summary} · Información ampliada: error; consulta el log." if sync_summary else "No se pudo completar la información de OT; consulta el log.")

        self._start_task(lambda: enrich_fault_descriptions(
            limit=batch, include_fault=self.cfg.fault_descriptions_enabled,
            include_detail=self.cfg.detailed_descriptions_enabled,
            cancel_event=cancel_event), done, failed, coordinated=True)

    def start_priority_fault_descriptions(self):
        if not self._credentials_ready():
            return
        count = enrichment_candidate_count(
            self.cfg.fault_descriptions_enabled, self.cfg.detailed_descriptions_enabled,
            minimum_age_hours=None)
        if not count:
            QMessageBox.information(self, "Información ampliada", "No hay información ampliada pendiente.")
            return
        if QMessageBox.question(
            self, "Completar información", f"Se revisarán {count} OT activas. La operación puede tardar varios minutos.\n\n¿Continuar?",
        ) != QMessageBox.Yes:
            return
        if not self.update_lock.acquire(False):
            QMessageBox.information(self, "Información ampliada", "Hay otra tarea de Maximo en curso.")
            return
        if not self.fault_description_lock.acquire(False):
            self.update_lock.release()
            QMessageBox.information(self, "Información ampliada", "Ya hay una lectura de información ampliada en curso.")
            return
        cancel_event = threading.Event()
        self.enrichment_cancel_event = cancel_event
        self.fault_cancel_button.setEnabled(True)
        self.status.showMessage(f"Completando información de {count} OT…")

        def done(completed):
            cancelled = cancel_event.is_set()
            self.fault_description_lock.release(); self.update_lock.release()
            self.fault_cancel_button.setEnabled(self.fault_description_lock.locked())
            if completed:
                self.refresh_table()
            self._refresh_fault_description_summary()
            if cancelled:
                self.status.showMessage(f"Lectura cancelada: {completed} campos guardados.", 7000)
            else:
                self.status.showMessage(f"Información ampliada: {completed} campos leídos.", 7000)
                QMessageBox.information(self, "Información ampliada", f"Lectura completada. Campos obtenidos: {completed}.")

        def failed(error):
            self.fault_description_lock.release(); self.update_lock.release()
            self.fault_cancel_button.setEnabled(self.fault_description_lock.locked())
            self._refresh_fault_description_summary()
            self.status.showMessage("La lectura de información ampliada falló; consulta el detalle.", 7000)
            if not self._closing:
                QMessageBox.critical(self, "Información ampliada", error)

        self._start_task(lambda: enrich_fault_descriptions(
            limit=None, minimum_age_hours=None, include_fault=self.cfg.fault_descriptions_enabled,
            include_detail=self.cfg.detailed_descriptions_enabled,
            cancel_event=cancel_event, job_priority=MANUAL), done, failed, coordinated=True)

    def _show_priority_reconcile_progress(self, completed, total, ot):
        self.status.showMessage(f"Revisión prioritaria: {completed}/{total} OT · {ot}")

    def start_priority_reconcile(self):
        if not self._credentials_ready(): return
        count = inactive_tracking_candidate_count(minimum_age_hours=None)
        if not count: QMessageBox.information(self, "Mantenimiento", "No hay OT no activas pendientes de revisar."); return
        if QMessageBox.question(self, "Revisión prioritaria", f"Se revisarán {count} OT. La operación puede tardar varios minutos.\n\n¿Continuar?") != QMessageBox.Yes: return
        if not self.update_lock.acquire(False): QMessageBox.information(self, "Mantenimiento", "Hay otra tarea de Maximo en curso."); return
        if not self.reconcile_lock.acquire(False):
            self.update_lock.release(); QMessageBox.information(self, "Mantenimiento", "Ya hay una revisión en curso."); return
        self.status.showMessage(f"Revisión prioritaria: iniciando sesión… 0/{count} OT")
        def done(changed):
            self.reconcile_lock.release(); self.update_lock.release()
            if changed:
                self.refresh_table()
            self._refresh_reconciliation_summary()
            self.status.showMessage(f"Revisión prioritaria completada: {changed} seguimientos actualizados.", 7000)
            if not self._closing:
                QMessageBox.information(self, "Mantenimiento", f"Revisión completada. Seguimientos actualizados: {changed}.")
        def failed(error):
            self.reconcile_lock.release(); self.update_lock.release()
            self.status.showMessage("La revisión prioritaria falló; consulta el detalle.", 7000)
            if not self._closing:
                QMessageBox.critical(self, "Mantenimiento", error)
        self._start_task(
            lambda report: reconcile_inactive_tracking(
                limit=None, minimum_age_hours=None, progress_callback=report, job_priority=MANUAL,
            ),
            done, failed, progress=self._show_priority_reconcile_progress, coordinated=True,
        )

    def open_table_cell(self, row, column):
        detail_column = self.columns.index("Avería" if self.cfg.fault_descriptions_enabled else "Descripción")
        if column == detail_column and self.cfg.detailed_descriptions_enabled:
            ot = self.selected_ot(row)
            if get_detailed_description(ot)[0]:
                self.show_detailed_description(ot)
                return
        self.open_ot_for_row(row)

    def show_detailed_description(self, ot):
        text, safe_html = get_detailed_description(ot)
        if not text:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"OT {ot} · Descripción detallada")
        available = self.screen().availableGeometry()
        dialog.resize(min(1480, available.width() - 80), min(560, available.height() - 80))
        layout = QVBoxLayout(dialog)
        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(False)
        viewer.setHtml(safe_html) if safe_html else viewer.setPlainText(text)
        layout.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def open_ot_for_row(self, row):
        ot = self.selected_ot(row)
        self.open_ot_number(ot)

    def open_ot_number(self, ot):
        if self._closing or not ot or not self._credentials_ready(): return
        self.status.showMessage(f"Abriendo OT {ot} en Maximo…")
        close_after_direct_print = (
            self.cfg.repair_print_mode == "direct"
            and self.cfg.repair_close_tabs_after_direct_print
        )
        def done(session):
            if session: self.ot_sessions.append(session)
            self.status.showMessage(f"OT {ot} abierta en Microsoft Edge.")
        self._start_task(lambda: open_ot(
            ot, headless=False, close_after_direct_print=close_after_direct_print,
            on_workorder_started=self.workorder_started.emit,
            on_workorder_closed=self.workorder_closed.emit,
        ), done, coordinated=True)

    def _workorder_started(self, result):
        if self._closing:
            return
        ot = result["ot"]
        try:
            apply_started_workorder(ot)
            self.refresh_choices()
            self.refresh_table()
        except Exception:
            logging.exception("OT %s iniciada, pero no se pudo refrescar su seguimiento local", ot)
        suffix = "ya estaba iniciada" if result["already_started"] else "iniciada correctamente"
        self.status.showMessage(f"OT {ot}: {suffix} (INPRG).", 10000)

    def _workorder_closed(self, result):
        if self._closing:
            return
        ot = result['ot']
        final=result.get('status','ISSUE')
        try:
            if final=='CLOSE':apply_warehouse_status(ot,'CLOSE')
            else:apply_closed_repair(ot)
            self.refresh_choices()
            self.refresh_table()
        except Exception:
            logging.exception('OT %s en ISSUE, pero no se pudo refrescar su seguimiento local', ot)
        message='equipo declarado irreparable (CLOSE)' if final=='CLOSE' else 'pendiente dar salida del almacén (ISSUE)'
        self.status.showMessage(f'OT {ot}: {message}.', 10000)

    def open_repair_report(self, ot, action):
        if self._closing or not ot or not self._credentials_ready(): return
        label = "impresión" if action == "print" else "PDF"
        self.status.showMessage(f"Abriendo OT {ot} y preparando parte para {label}…")
        close_after_direct_print = (
            action == "print"
            and self.cfg.repair_print_mode == "direct"
            and self.cfg.repair_close_tabs_after_direct_print
        )
        def done(session):
            if session: self.ot_sessions.append(session)
            self.status.showMessage(f"OT {ot}: parte en preparación en Microsoft Edge.")
        def prepare_report():
            with coordinator.job(f"Preparar parte de OT {ot}", HIGH):
                return open_ot(
                    ot, headless=False, report_action=action,
                    close_after_direct_print=close_after_direct_print,
                    on_workorder_started=self.workorder_started.emit,
                    on_workorder_closed=self.workorder_closed.emit,
                )
        self._start_task(prepare_report, done, coordinated=True)

    def export_current_list(self):
        if not any(not self.table.isRowHidden(row) for row in range(self.table.rowCount())):
            QMessageBox.information(self, "Exportar a Excel", "No hay órdenes que exportar.")
            return
        suggested = EXPORT_DIR / f"ordenes_trabajo_{date.today():%Y%m%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar listado a Excel", str(suggested), "Libro de Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        header = self.table.horizontalHeader()
        visible_columns = sorted(
            (column for column in range(self.table.columnCount()) if not self.table.isColumnHidden(column)),
            key=header.visualIndex,
        )
        headers = [self.table.horizontalHeaderItem(column).text() for column in visible_columns]
        try:
            ot_column = headers.index("OT")
        except ValueError:
            QMessageBox.critical(self, "Exportar a Excel", "No se encuentra la columna OT en el listado.")
            return
        rows = [
            [self.table.item(row, column).text() if self.table.item(row, column) else "" for column in visible_columns]
            for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)
        ]
        scheme_is_development = DEVELOPMENT_MODE
        try:
            count = write_workorders_xlsx(
                path, headers, rows, ot_column,
                uri_scheme="maximodesk-dev" if scheme_is_development else "maximodesk",
            )
        except PermissionError:
            QMessageBox.warning(self, "Exportar a Excel", "No se pudo guardar el archivo. Comprueba que no esté abierto en Excel y vuelve a intentarlo.")
            return
        except ImportError:
            QMessageBox.critical(self, "Exportar a Excel", "Falta el componente de Excel. Instala las dependencias de Maximo Desktop y vuelve a abrir la aplicación.")
            return
        except Exception as exc:
            logging.exception("No se pudo exportar el listado a Excel")
            QMessageBox.critical(self, "Exportar a Excel", f"No se pudo crear el archivo:\n{exc}")
            return
        self.status.showMessage(f"Exportadas {count:,} OT a Excel.", 6000)
        QMessageBox.information(
            self, "Exportar a Excel",
            f"Se exportaron {count:,} órdenes a:\n{path}\n\nLa columna OT incluye un enlace para abrirla con Maximo Desktop.",
        )

    def handle_deep_link(self, uri):
        ot = parse_ot_uri(uri)
        if not ot:
            return
        self.pages.setCurrentIndex(0)
        self.navigation_location.setText("Listado")
        self.open_ot_number(ot)

    def activate_window(self):
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _load_config(self):
        self.user_edit.setText(self.cfg.username); self.password_edit.setText(self.cfg.password)
        self.auto_check.setChecked(self.cfg.auto_update_enabled); self.interval_spin.setValue(self.cfg.auto_update_interval_min)
        self.reconcile_check.setChecked(self.cfg.reconciliation_enabled); self.batch_spin.setValue(self.cfg.reconciliation_batch_size)
        self.fault_descriptions_check.setChecked(self.cfg.fault_descriptions_enabled)
        self.detailed_descriptions_check.setChecked(self.cfg.detailed_descriptions_enabled)
        self.repair_extension_check.setChecked(self.cfg.repair_extension_enabled)
        self.workorder_start_check.setChecked(self.cfg.workorder_start_enabled)
        self._set_combo_value(self.workorder_start_mode_combo, self.cfg.workorder_start_mode)
        self.workorder_failure_picker.set_selection(self.cfg.workorder_start_selection)
        self._update_workorder_start_controls()
        self.workorder_close_check.setChecked(self.cfg.workorder_close_enabled)
        self.technician_sat_check.setChecked(self.cfg.technician_sat_enabled)
        self.warehouse_check.setChecked(self.cfg.warehouse_enabled)
        self.warehouse_details_check.setChecked(self.cfg.warehouse_ask_sat_details)
        self._set_combo_value(self.repair_mode_combo, self.cfg.repair_print_mode)
        self.repair_close_tabs_check.setChecked(self.cfg.repair_close_tabs_after_direct_print)
        self.repair_stamp_check.setChecked(self.cfg.repair_irreparable_stamp_enabled)
        self.repair_mode_combo.setEnabled(self.cfg.repair_extension_enabled)
        self.fault_batch_spin.setValue(self.cfg.fault_description_batch_size)
        theme_signals_blocked = self.theme_combo.blockSignals(True)
        self._set_combo_value(self.theme_combo, self.cfg.theme)
        self.theme_combo.blockSignals(theme_signals_blocked)
        with QSignalBlocker(self.font_combo):
            self._set_combo_value(self.font_combo, self.cfg.font_family)
        with QSignalBlocker(self.custom_text_size), QSignalBlocker(self.custom_text_weight), QSignalBlocker(self.custom_text_contrast), QSignalBlocker(self.custom_borders):
            self.custom_text_size.setValue(self.cfg.legibility_custom["text_size"])
            self._set_combo_value(self.custom_text_weight, self.cfg.legibility_custom["weight"])
            self.custom_text_contrast.setChecked(self.cfg.legibility_custom["contrast"])
            self.custom_borders.setChecked(self.cfg.legibility_custom["borders"])
        self.custom_legibility_controls.setVisible(self.cfg.legibility_profile == "custom")
        if (ACTIVE_THEME, ACTIVE_PROFILE, ACTIVE_FONT_PREFERENCE, ACTIVE_CUSTOM_LEGIBILITY) != (_resolve_theme(self.cfg.theme), self.cfg.legibility_profile, self.cfg.font_family, self.cfg.legibility_custom):
            apply_application_theme(QApplication.instance(), self.cfg.theme, self.cfg.legibility_profile, self.cfg.font_family, self.cfg.legibility_custom)
        self._refresh_font_hint()
        with QSignalBlocker(self.legibility_combo), QSignalBlocker(self.tracking_colors_check):
            self._set_combo_value(self.legibility_combo, self.cfg.legibility_profile)
            self.tracking_colors_check.setChecked(self.cfg.tracking_colors)
        self._set_combo_value(self.priority_tmb_validity, self.cfg.priority_tmb_validity)
        self._set_combo_value(self.priority_l9_validity, self.cfg.priority_l9_validity)
        self._set_combo_value(self.priority_renfe_validity, self.cfg.priority_renfe_validity)
        self._refresh_auto_update_summary()
        self._refresh_app_update_block()
        self._refresh_reconciliation_summary()
        self._refresh_fault_description_summary()
        self._update_fault_description_controls()
        self._refresh_priorities()
        self._refresh_navigation_icon()
        if hasattr(self, "client_combo"):
            self.client_combo.refresh_theme()
        self._refresh_table_colors()
        self._update_settings_dirty_hint()

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
        self._store_column_width_preferences()
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.cfg.window_size = [geometry.width(), geometry.height()]
        self.cfg.window_maximized = self.isMaximized()
        save_config(self.cfg)
        logging.info("Estado de ventana y preferencias de columnas guardados.")

    def settings_dirty(self):
        return (
            self.user_edit.text().strip() != self.cfg.username
            or self.password_edit.text() != self.cfg.password
            or self.auto_check.isChecked() != self.cfg.auto_update_enabled
            or self.interval_spin.value() != self.cfg.auto_update_interval_min
            or self.reconcile_check.isChecked() != self.cfg.reconciliation_enabled
            or self.batch_spin.value() != self.cfg.reconciliation_batch_size
            or self.fault_descriptions_check.isChecked() != self.cfg.fault_descriptions_enabled
            or self.detailed_descriptions_check.isChecked() != self.cfg.detailed_descriptions_enabled
            or self.repair_extension_check.isChecked() != self.cfg.repair_extension_enabled
            or self.workorder_start_check.isChecked() != self.cfg.workorder_start_enabled
            or (self.workorder_start_mode_combo.currentData() or "invalid") != self.cfg.workorder_start_mode
            or self.workorder_failure_picker.selection() != self.cfg.workorder_start_selection
            or self.workorder_close_check.isChecked() != self.cfg.workorder_close_enabled
            or self.technician_sat_check.isChecked() != self.cfg.technician_sat_enabled
            or self.warehouse_check.isChecked() != self.cfg.warehouse_enabled
            or self.warehouse_details_check.isChecked() != self.cfg.warehouse_ask_sat_details
            or self.repair_mode_combo.currentData() != self.cfg.repair_print_mode
            or self.repair_close_tabs_check.isChecked() != self.cfg.repair_close_tabs_after_direct_print
            or self.repair_stamp_check.isChecked() != self.cfg.repair_irreparable_stamp_enabled
            or self.fault_batch_spin.value() != self.cfg.fault_description_batch_size
            or self.priority_tmb_validity.currentData() != self.cfg.priority_tmb_validity
            or self.priority_l9_validity.currentData() != self.cfg.priority_l9_validity
            or self.priority_renfe_validity.currentData() != self.cfg.priority_renfe_validity
            or self.theme_combo.currentData() != self.cfg.theme
            or self.font_combo.currentData() != self.cfg.font_family
            or self._custom_legibility_options() != self.cfg.legibility_custom
            or self.legibility_combo.currentData() != self.cfg.legibility_profile
            or self.tracking_colors_check.isChecked() != self.cfg.tracking_colors
        )

    def save_settings(self, show_feedback=True):
        start_mode = self.workorder_start_mode_combo.currentData()
        start_selection = self.workorder_failure_picker.selection()
        if self.workorder_start_check.isChecked():
            try:
                if start_mode not in ("configured", "only"):
                    raise ValueError("Elige cómo quieres iniciar las OT.")
                if start_mode == "configured":
                    resolve_selection(start_selection)
            except (TypeError, ValueError) as exc:
                QMessageBox.warning(self, "Anomalías al iniciar OT", str(exc))
                return False
        self.cfg.username = self.user_edit.text().strip(); self.cfg.password = self.password_edit.text(); self.cfg.auto_update_enabled = self.auto_check.isChecked(); self.cfg.auto_update_interval_min = self.interval_spin.value(); self.cfg.reconciliation_enabled = self.reconcile_check.isChecked(); self.cfg.reconciliation_batch_size = self.batch_spin.value()
        self.cfg.fault_descriptions_enabled = self.fault_descriptions_check.isChecked()
        self.cfg.detailed_descriptions_enabled = self.detailed_descriptions_check.isChecked()
        self.cfg.repair_extension_enabled = self.repair_extension_check.isChecked()
        self.cfg.workorder_start_enabled = self.workorder_start_check.isChecked()
        self.cfg.workorder_start_mode = start_mode or "invalid"
        self.cfg.workorder_start_selection = start_selection
        self.cfg.workorder_close_enabled = self.workorder_close_check.isChecked()
        self.cfg.technician_sat_enabled = self.technician_sat_check.isChecked()
        self.cfg.warehouse_enabled = self.warehouse_check.isChecked()
        self.cfg.warehouse_ask_sat_details = self.warehouse_details_check.isChecked()
        self.cfg.repair_print_mode = self.repair_mode_combo.currentData()
        self.cfg.repair_close_tabs_after_direct_print = self.repair_close_tabs_check.isChecked()
        self.cfg.repair_irreparable_stamp_enabled = self.repair_stamp_check.isChecked()
        self.cfg.fault_description_batch_size = self.fault_batch_spin.value()
        self.cfg.priority_tmb_validity = self.priority_tmb_validity.currentData()
        self.cfg.priority_l9_validity = self.priority_l9_validity.currentData()
        self.cfg.priority_renfe_validity = self.priority_renfe_validity.currentData()
        self.cfg.theme = self.theme_combo.currentData()
        self.cfg.legibility_profile = self.legibility_combo.currentData()
        self.cfg.legibility_custom = self._custom_legibility_options()
        self.cfg.font_family = self.font_combo.currentData()
        self.cfg.tracking_colors = self.tracking_colors_check.isChecked()
        save_config(self.cfg)
        logging.info("Inicio de OT habilitado: %s; modo: %s", self.cfg.workorder_start_enabled, self.cfg.workorder_start_mode)
        logging.info("Cierre de OT en Edge habilitado: %s", self.cfg.workorder_close_enabled)
        self.schedule_auto_update()
        self._refresh_auto_update_summary()
        self._refresh_reconciliation_summary()
        self._refresh_fault_description_summary()
        self._update_fault_description_controls()
        self._refresh_priorities()
        self.refresh_table()
        logging.info(
            "Configuración UI guardada: auto_update=%s, intervalo=%d, conciliación=%s, lote=%d, averías=%s, lote_averías=%d, prioridad TMB=%s, L9=%s, RENFE=%s, tema=%s, legibilidad=%s, tipografía=%s, colores_seguimiento=%s.",
            self.cfg.auto_update_enabled, self.cfg.auto_update_interval_min,
            self.cfg.reconciliation_enabled, self.cfg.reconciliation_batch_size,
            self.cfg.fault_descriptions_enabled, self.cfg.fault_description_batch_size,
            self.cfg.priority_tmb_validity, self.cfg.priority_l9_validity, self.cfg.priority_renfe_validity,
            self.cfg.theme, self.cfg.legibility_profile, self.cfg.font_family, self.cfg.tracking_colors,
        )
        if show_feedback:
            QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
        self._update_settings_dirty_hint()
        self.status.showMessage("Configuración guardada y aplicada.", 4000)
        return True

    def _update_workorder_start_controls(self, *_args):
        enabled = self.workorder_start_check.isChecked()
        configured = self.workorder_start_mode_combo.currentData() == "configured"
        self.workorder_start_mode_combo.setEnabled(enabled)
        self.workorder_failure_picker.setVisible(configured)
        self.workorder_failure_picker.setEnabled(enabled and configured)

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

    def _startup_release_updates(self):
        """Show installed-version notes before offering another update."""
        if self._closing:
            return
        try:
            self._show_installed_release_notes()
        except Exception:
            logging.exception('No se pudieron mostrar las novedades de la versión instalada.')
        if not self._closing:
            self.check_app_updates(automatic=True)

    def _show_installed_release_notes(self):
        if self._closing or DEVELOPMENT_MODE or not distributed_executable():
            return
        path = CONFIG_PATH.parent / STATE_FILENAME
        if not should_show_notes(path, version.APP_VERSION):
            return
        url = self.cfg.latest_release_url if same_version(self.cfg.latest_release_tag, version.APP_VERSION) else ''
        notes = installed_release_notes(path, version.APP_VERSION, fallback_url=url)
        if notes.markdown:
            logging.info('Mostrando novedades de %s (fuente: %s).', notes.version, notes.source)
            dialog = ReleaseNotesDialog(notes, self, ACTIVE_COLORS)
            dialog.exec()
        else:
            logging.warning('No hay notas locales de %s; se omite el aviso vacío.', version.APP_VERSION)
        try:
            mark_notes_seen(path, version.APP_VERSION)
        except OSError:
            logging.warning('No se pudo guardar el historial de novedades.', exc_info=True)

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
        self.check_app_updates_button.setEnabled(not self._app_update_checking and not self._app_update_downloading)
        newer = bool(tag and is_newer(tag, version.APP_VERSION))
        installable = bool(
            newer and self._latest_release and self._latest_release.tag == tag
            and self._latest_release.asset_url and self._latest_release.asset_digest
            and not DEVELOPMENT_MODE and distributed_executable()
        )
        self.install_update_button.setEnabled(
            installable and not self._app_update_checking and not self._app_update_downloading and not self._closing
        )
        if message:
            state = message
        elif newer and DEVELOPMENT_MODE:
            state = f"Hay una versión publicada: {format_version_tag(tag)}. La edición de desarrollo no se actualiza automáticamente."
        elif newer and not distributed_executable():
            state = f"Hay una versión publicada: {format_version_tag(tag)}. La instalación requiere la app distribuida."
        elif newer and not installable:
            state = f"Hay una versión publicada: {format_version_tag(tag)}. El paquete verificable aún no está disponible."
        elif newer:
            state = f"Hay una actualización disponible: {format_version_tag(tag)}."
        elif tag:
            state = "La aplicación está actualizada."
        else:
            state = "Aún no se ha comprobado la disponibilidad de versiones."
        self.app_update_status_label.setText(state)

    def check_app_updates(self, automatic=False):
        """Busca una release y ofrece instalarla en la edición distribuida."""
        if self._closing or self._app_update_checking or self._app_update_downloading:
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
            if latest.notes and not DEVELOPMENT_MODE and distributed_executable():
                try:
                    cache_release_notes(CONFIG_PATH.parent / STATE_FILENAME, latest.tag, latest.notes, latest.html_url)
                except OSError:
                    logging.warning('No se pudieron conservar las notas de la release.', exc_info=True)
            save_config(self.cfg)
            newer = bool(latest.tag and is_newer(latest.tag, version.APP_VERSION))
            self._refresh_app_update_block()
            logging.info(
                "Comprobación de versión UI completada: local=%s, remota=%s, nueva=%s.",
                version.APP_VERSION, latest.tag, newer,
            )
            installable = self.install_update_button.isEnabled()
            should_prompt = (
                installable and not self._closing
                and (not automatic or latest.tag not in self._prompted_release_tags)
            )
            if should_prompt:
                self._prompted_release_tags.add(latest.tag)
                answer = QMessageBox.question(
                    self, "Actualización disponible",
                    f"Está disponible Maximo Desktop {format_version_tag(latest.tag)}.\n\n"
                    "¿Descargarla, instalarla y reiniciar la aplicación ahora?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    self.install_latest_release()
                    return
            elif not automatic and not self._closing:
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
            if not automatic and not self._closing:
                QMessageBox.warning(self, "Actualizaciones", f"{detail}\n\n{error}")
                self.status.showMessage("No se pudo comprobar la versión.", 4000)

        self._start_task(self._fetch_latest_release_with_retry, done, failed)

    def _set_app_download_progress(self, downloaded, total):
        if not hasattr(self, "app_download_dialog") or not self.app_download_dialog:
            return
        if total:
            self.app_download_dialog.setRange(0, 100)
            self.app_download_dialog.setValue(min(100, int(downloaded * 100 / total)))
        else:
            self.app_download_dialog.setRange(0, 0)
        self.app_download_dialog.setLabelText(f"Descargando actualización… {downloaded / 1048576:.1f} MB")

    def _set_app_download_status(self, message):
        if hasattr(self, "app_download_dialog") and self.app_download_dialog:
            self.app_download_dialog.setRange(0, 0)
            self.app_download_dialog.setLabelText(message)

    def _close_app_download_dialog(self):
        if hasattr(self, "app_download_dialog") and self.app_download_dialog:
            # Cerrar el diálogo al completar la descarga no es una cancelación.
            self.app_download_dialog.blockSignals(True)
            self.app_download_dialog.close()
            self.app_download_dialog.deleteLater()
            self.app_download_dialog = None

    def install_latest_release(self):
        """Descarga y valida el paquete antes de iniciar el cierre de la UI."""
        latest = self._latest_release
        if self._closing or self._app_update_downloading or DEVELOPMENT_MODE or not distributed_executable():
            return
        if not latest or not is_newer(latest.tag, version.APP_VERSION) or not latest.asset_url or not latest.asset_digest:
            QMessageBox.warning(self, "Actualizaciones", "No hay un paquete de actualización verificable disponible.")
            return
        if self._ready_update and self._ready_update[0] == latest.tag and self._ready_update[1].is_dir():
            self._begin_update_close(self._ready_update[1])
            return
        self._app_update_downloading = True
        self._app_update_cancel.clear()
        self._refresh_app_update_block("Descargando y verificando la actualización…")
        dialog = QProgressDialog("Preparando descarga…", "Cancelar descarga", 0, 0, self)
        dialog.setWindowTitle("Actualizando Maximo Desktop")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.canceled.connect(self._app_update_cancel.set)
        self.app_download_dialog = dialog
        dialog.show()
        destination = UPDATE_CACHE_DIR / "qt-release"

        def download():
            last_error = None
            for attempt in range(3):
                if self._app_update_cancel.is_set():
                    raise UpdateDownloadCancelled("Descarga cancelada.")
                try:
                    return download_release_asset(
                        latest, destination, progress=self.app_download_progress.emit,
                        status=self.app_download_status.emit, cancel_event=self._app_update_cancel,
                    )
                except UpdateDownloadCancelled:
                    raise
                except Exception as exc:
                    last_error = exc
                    logging.warning("Descarga de actualización: intento %d/3 falló: %s", attempt + 1, exc)
                    if attempt < 2 and self._app_update_cancel.wait(attempt + 1):
                        raise UpdateDownloadCancelled("Descarga cancelada.")
            raise RuntimeError(f"No se pudo descargar la actualización: {last_error}")

        def done(source):
            self._app_update_downloading = False
            self._close_app_download_dialog()
            self._ready_update = (latest.tag, source)
            self._refresh_app_update_block("Actualización descargada y verificada; lista para instalar.")
            if self._app_update_cancel.is_set():
                if not self._closing:
                    self.status.showMessage("Actualización preparada. La instalación se ha cancelado.", 5000)
            elif not self._closing:
                self._begin_update_close(source)

        def failed(error):
            self._app_update_downloading = False
            self._close_app_download_dialog()
            self._refresh_app_update_block()
            if self._closing:
                return
            if self._app_update_cancel.is_set():
                self.status.showMessage("Descarga de actualización cancelada.", 5000)
            else:
                QMessageBox.warning(self, "Actualizaciones", error)

        self._start_task(download, done, failed)

    def _begin_update_close(self, source):
        executable = distributed_executable()
        if not executable:
            QMessageBox.warning(self, "Actualizaciones", "No se encontró el ejecutable instalado.")
            return
        self._pending_update = (executable, source)
        self.close()
        if not self._closing:
            # El usuario decidió seguir trabajando o conservar cambios.
            self._pending_update = None
            self._refresh_app_update_block("Actualización preparada. Pulsa «Actualizar ahora» cuando quieras reiniciar.")

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
            if self._closing:
                return
            QMessageBox.information(
                self, "Credenciales válidas",
                "El acceso a Maximo se ha comprobado y las credenciales se han guardado.\n\n"
                "Los demás cambios de la página siguen pendientes hasta pulsar «Guardar cambios»."
            )
        def failed(error):
            self.test_button.setEnabled(True)
            if not self._closing:
                QMessageBox.critical(self, "No se pudo comprobar el acceso", error)
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
        if WarehouseWindowMixin.warehouse_is_running(self):
            for dialog in self._warehouse_dialogs:
                if dialog.is_running():
                    dialog.request_stop()
                    target=getattr(dialog,'progress_dialog',None) or dialog
                    target.show(); target.raise_()
            return
        if self._closing:
            return
        if self.settings_dirty():
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Cambios sin guardar")
            prompt.setText("Hay cambios de configuración pendientes de guardar.")
            save = prompt.addButton("Guardar y salir", QMessageBox.AcceptRole)
            discard = prompt.addButton("Salir sin guardar", QMessageBox.DestructiveRole)
            keep_open = prompt.addButton("Seguir trabajando", QMessageBox.RejectRole)
            prompt.setDefaultButton(keep_open)
            prompt.exec()
            if prompt.clickedButton() is save:
                if self.save_settings(show_feedback=False) is False:
                    return
            elif prompt.clickedButton() is not discard:
                return
        if self.ot_sessions:
            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Warning)
            prompt.setWindowTitle("Sesiones de Maximo abiertas")
            prompt.setText("Maximo Desktop cerrará las ventanas de OT que abrió en Edge.")
            prompt.setInformativeText(
                "Si hay cambios sin guardar en alguna OT, vuelve a esa ventana y guárdalos "
                "antes de salir."
            )
            keep_open = prompt.addButton("Seguir trabajando", QMessageBox.RejectRole)
            close_sessions = prompt.addButton("Cerrar sesiones y salir", QMessageBox.AcceptRole)
            prompt.setDefaultButton(keep_open)
            prompt.exec()
            if prompt.clickedButton() is not close_sessions:
                return
        self._closing = True
        scheduler = getattr(self, '_priority_coordinator', None)
        if scheduler is not None:
            scheduler.shutdown()
        notices = getattr(self, '_priority_notices', None)
        if notices is not None:
            notices.close()
        self.enrichment_cancel_event.set()
        self._app_update_cancel.set()
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
            (self.fault_description_lock, "Cancelando la lectura de información ampliada…"),
        )
        while True:
            pending = [label for lock, label in labels if lock.locked()]
            if pending:
                self.close_progress.emit(pending[0])
            elif not self._tasks_idle.is_set() or any(t.isRunning() for t in list(getattr(self, "_coordinated_threads", ()))):
                self.close_progress.emit("Esperando a que terminen las tareas en segundo plano…")
            else:
                break
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
        if self._pending_update:
            executable, source = self._pending_update
            try:
                start_update(executable, source)
            except Exception as exc:
                logging.exception("No se pudo iniciar el instalador de la actualización")
                self._pending_update = None
                self._closing = False
                self.ot_sessions = []
                self.enrichment_cancel_event.clear()
                self.schedule_auto_update()
                self._refresh_app_update_block("La actualización está descargada, pero no se pudo iniciar la instalación.")
                QMessageBox.critical(self, "Actualizaciones", f"No se pudo iniciar la instalación:\n\n{exc}")
                return
        self._close_finalized = True
        self.close()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Maximo Desktop")
    startup_config = load_config()
    startup_theme = startup_config.theme
    apply_application_theme(app, startup_theme, startup_config.legibility_profile, startup_config.font_family, startup_config.legibility_custom)
    activity_dialog = show_activity_dialog(
        "Iniciando Maximo Desktop…\nCargando datos locales",
        theme_preference=startup_theme,
    )
    activity_message = activity_dialog.findChild(QLabel, "activityMessage")

    def installation_progress(message):
        if activity_message is not None:
            activity_message.setText(message)
            QApplication.processEvents()

    try:
        if redirect_to_managed_install(installation_progress):
            activity_dialog.close()
            return 0
    except ManagedInstallError as exc:
        activity_dialog.close()
        QMessageBox.critical(None, "Instalación de Maximo Desktop", str(exc))
        return 1
    initial_uri = next((argument for argument in sys.argv[1:] if parse_ot_uri(argument)), "")
    try:
        bridge = LocalOpenBridge(DEVELOPMENT_MODE, initial_uri)
    except RuntimeError as exc:
        activity_dialog.close()
        QMessageBox.critical(None, "Maximo Desktop", str(exc))
        return 1
    if not bridge.is_primary:
        activity_dialog.close()
        return 0
    window = MaximoDesktopWindow()
    bridge.uri_received.connect(window.handle_deep_link)
    bridge.activate_requested.connect(window.activate_window)
    try:
        registered = False if WAREHOUSE_DEVELOPMENT_MODE else register_protocol_handler(DEVELOPMENT_MODE)
        if registered:
            logging.info("Protocolo local de OT registrado para el usuario actual.")
    except OSError:
        logging.warning("No se pudo registrar el protocolo local de OT.", exc_info=True)
    window.show()
    logging.info("Ventana Qt abierta. Ejecutable: %s", distributed_executable() or sys.argv[0])
    activity_dialog.close()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
