"""Configuración persistente y migración desde versiones anteriores."""
import json
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, asdict, field, fields
from contextlib import closing
from pathlib import Path

from app_paths import (
    BACKUP_DIR, BASE_DIR, CONFIG_PATH, DB_PATH, DOWNLOAD_DIR,
    EXPORT_DIR, LOG_DIR, PROFILES_PATH,
    create_unique_file, ensure_user_directories,
)
from credential_store import load_credentials, save_credentials
from appearance import PROFILES, THEME_PALETTES, default_custom_legibility, normalize_custom_legibility
from typography import normalize_font
from failure_catalog import default_selection
from release_notes import STATE_FILENAME, initialize_history
import version

LEGACY_CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_REPAIR_ORIGIN_PROJECTS = ("ATM", "Línea 9")
_legacy_cleanup_attempted = False


@dataclass
class AppConfig:
    maximo_url: str = "https://eam.indraweb.net/maximo/"
    username: str = ""
    password: str = ""
    download_dir: str = str(DOWNLOAD_DIR)
    dest_folder: str = str(EXPORT_DIR)
    db_path: str = str(DB_PATH)
    auto_update_enabled: bool = False
    auto_update_interval_min: int = 10
    reconciliation_enabled: bool = True
    reconciliation_batch_size: int = 5
    fault_descriptions_enabled: bool = False
    detailed_descriptions_enabled: bool = False
    fault_description_batch_size: int = 5
    priority_tmb_validity: str = "daily"
    priority_l9_validity: str = "daily"
    priority_renfe_validity: str = "weekly"
    theme: str = "system"
    legibility_profile: str = "normal"
    legibility_custom: dict = field(default_factory=default_custom_legibility)
    font_family: str = "theme"
    tracking_colors: bool = False
    repair_extension_enabled: bool = False
    workorder_start_enabled: bool = False
    workorder_start_mode: str = "configured"
    workorder_start_selection: dict = field(default_factory=default_selection)
    workorder_close_enabled: bool = False
    technician_sat_enabled: bool = False
    warehouse_enabled: bool = False
    warehouse_ask_sat_details: bool = False
    repair_print_mode: str = "dialog"
    repair_close_tabs_after_direct_print: bool = False
    repair_irreparable_stamp_enabled: bool = True
    repair_origin_mode: str = "selected"
    repair_origin_projects: list[str] = field(default_factory=lambda: list(DEFAULT_REPAIR_ORIGIN_PROJECTS))
    filters: dict | None = None
    last_status: dict | None = None
    latest_release_tag: str = ""
    latest_release_url: str = ""
    latest_release_checked_at: str = ""
    table_column_widths: dict | None = None
    table_hidden_columns: list[str] = field(default_factory=list)
    table_layout_initialized: bool = False
    window_size: list | None = None
    window_maximized: bool = False
    sidebar_collapsed: bool = False
    sidebar_width: int = 226

    def __post_init__(self):
        self.download_dir = str(DOWNLOAD_DIR)
        self.dest_folder = str(EXPORT_DIR)
        self.db_path = str(DB_PATH)
        try:
            self.reconciliation_batch_size = min(100, max(1, int(self.reconciliation_batch_size)))
        except (TypeError, ValueError):
            self.reconciliation_batch_size = 5
        try:
            self.fault_description_batch_size = min(100, max(1, int(self.fault_description_batch_size)))
        except (TypeError, ValueError):
            self.fault_description_batch_size = 5
        for attribute, default in (
            ("priority_tmb_validity", "daily"),
            ("priority_l9_validity", "daily"),
            ("priority_renfe_validity", "weekly"),
        ):
            if getattr(self, attribute) not in {"daily", "weekly"}:
                setattr(self, attribute, default)
        if self.theme != "system" and self.theme not in THEME_PALETTES:
            self.theme = "system"
        if not isinstance(self.legibility_profile, str) or self.legibility_profile not in PROFILES:
            self.legibility_profile = "normal"
        try:
            self.sidebar_width = min(420, max(210, int(self.sidebar_width)))
        except (TypeError, ValueError, OverflowError):
            self.sidebar_width = 226
        self.legibility_custom = normalize_custom_legibility(self.legibility_custom)
        self.font_family = normalize_font(self.font_family)
        if not isinstance(self.sidebar_collapsed, bool):
            self.sidebar_collapsed = False
        if not isinstance(self.tracking_colors, bool):
            self.tracking_colors = False
        if self.repair_print_mode not in {"dialog", "direct"}:
            self.repair_print_mode = "dialog"
        if not isinstance(self.workorder_start_enabled, bool):
            self.workorder_start_enabled = False
        if self.workorder_start_mode not in ("configured", "only"):
            self.workorder_start_mode = "invalid"
        if not isinstance(self.workorder_start_selection, dict):
            self.workorder_start_selection = {}
        if not isinstance(self.workorder_close_enabled, bool):
            self.workorder_close_enabled = False
        if not isinstance(self.technician_sat_enabled, bool):
            self.technician_sat_enabled = False
        if not isinstance(self.warehouse_enabled, bool):
            self.warehouse_enabled = False
        if not isinstance(self.warehouse_ask_sat_details, bool):
            self.warehouse_ask_sat_details = False
        if self.repair_origin_mode not in ("disabled", "all", "selected"):
            self.repair_origin_mode = "selected"
        if not isinstance(self.repair_origin_projects, list):
            self.repair_origin_projects = list(DEFAULT_REPAIR_ORIGIN_PROJECTS)
        self.repair_origin_projects = sorted({
            value.strip() for value in self.repair_origin_projects
            if isinstance(value, str) and value.strip()
        }, key=str.casefold)
        if not isinstance(self.repair_irreparable_stamp_enabled, bool):
            self.repair_irreparable_stamp_enabled = True
        if not isinstance(self.repair_close_tabs_after_direct_print, bool):
            self.repair_close_tabs_after_direct_print = False
        if self.filters is None:
            self.filters = {"mx38_tfrow_[C:26]_txt-tb": "=LAB-BAD"}
        if not isinstance(self.table_column_widths, dict):
            self.table_column_widths = {}
        if not isinstance(self.table_hidden_columns, list):
            self.table_hidden_columns = []
        else:
            self.table_hidden_columns = [
                name for name in self.table_hidden_columns if isinstance(name, str) and name != "OT"
            ]
        if not isinstance(self.window_size, list) or len(self.window_size) != 2:
            self.window_size = None


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = create_unique_file(path.parent, path.name + ".", ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _config_data(cfg: AppConfig) -> dict:
    data = asdict(cfg)
    data.pop("username", None)
    data.pop("password", None)
    return data


def _copy_database(source: Path, destination: Path) -> None:
    if not source.exists() or destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".migrating")
    temporary.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src, \
             closing(sqlite3.connect(temporary)) as dst:
            with dst:
                src.backup(dst)
                source_count = src.execute("SELECT COUNT(*) FROM maximo").fetchone()[0]
                copied_count = dst.execute("SELECT COUNT(*) FROM maximo").fetchone()[0]
                integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if source_count != copied_count or integrity != "ok":
            raise RuntimeError("La copia de la base de datos no superó la verificación.")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_if_missing(source: Path, destination: Path) -> None:
    if source.exists() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _redact_file(path: Path, secrets: tuple[str, ...]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTADO]")
    if redacted != text:
        path.write_text(redacted, encoding="utf-8")


def _sanitize_legacy_artifacts() -> None:
    """Elimina secretos heredados incluso si una migración anterior quedó a medias."""
    global _legacy_cleanup_attempted
    if _legacy_cleanup_attempted:
        return
    _legacy_cleanup_attempted = True
    if not LEGACY_CONFIG_PATH.exists():
        return
    try:
        legacy = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    username = str(legacy.get("username", ""))
    password = str(legacy.get("password", ""))
    if not username and not password:
        try:
            username, password = load_credentials()
        except Exception:
            username, password = "", ""
    for legacy_log in BASE_DIR.glob("maximo_client.log*"):
        try:
            _redact_file(legacy_log, (username, password))
            _copy_if_missing(legacy_log, LOG_DIR / legacy_log.name)
        except OSError as exc:
            logging.warning("No se pudo sanear el log anterior %s: %s", legacy_log, exc)
    if legacy.get("username") or legacy.get("password"):
        legacy["username"] = ""
        legacy["password"] = ""
        try:
            _atomic_json(LEGACY_CONFIG_PATH, legacy)
        except OSError as exc:
            logging.warning("No se pudo sanear la configuración anterior: %s", exc)


def _migrate_legacy_storage() -> None:
    if CONFIG_PATH.exists() or not LEGACY_CONFIG_PATH.exists():
        return
    legacy = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
    username = str(legacy.get("username", ""))
    password = str(legacy.get("password", ""))
    old_db = Path(legacy.get("db_path") or BASE_DIR / "data" / "maximo_data.db")
    fallback_db = BASE_DIR / "data" / "maximo_data.db"
    if not old_db.exists() and fallback_db.exists():
        old_db = fallback_db
    if not old_db.exists():
        raise FileNotFoundError(f"No se encuentra la base de datos anterior: {old_db}")
    old_data = old_db.parent

    ensure_user_directories()
    _copy_database(old_db, DB_PATH)
    _copy_if_missing(old_data / "search_profiles.json", PROFILES_PATH)
    _copy_if_missing(BASE_DIR / "data" / "search_profiles.json", PROFILES_PATH)
    old_backups = old_data / "backups"
    if old_backups.exists():
        for item in old_backups.glob("*.db"):
            _copy_if_missing(item, BACKUP_DIR / item.name)

    save_credentials(username, password)
    if load_credentials() != (username, password):
        raise RuntimeError("No se pudieron verificar las credenciales migradas.")
    allowed = {field.name for field in fields(AppConfig)}
    cfg = AppConfig(**{key: value for key, value in legacy.items() if key in allowed})
    save_config(cfg)

def load_config() -> AppConfig:
    ensure_user_directories()
    _migrate_legacy_storage()
    _sanitize_legacy_artifacts()
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(AppConfig)} - {"username", "password"}
        cfg = AppConfig(**{key: value for key, value in data.items() if key in allowed})
    else:
        cfg = AppConfig()
        try:
            initialize_history(CONFIG_PATH.parent / STATE_FILENAME, version.APP_VERSION)
        except OSError:
            logging.warning('No se pudo inicializar el historial de novedades.', exc_info=True)
        save_config(cfg)
    cfg.username, cfg.password = load_credentials()
    return cfg


def save_config(cfg: AppConfig) -> None:
    ensure_user_directories()
    save_credentials(cfg.username, cfg.password)
    _atomic_json(CONFIG_PATH, _config_data(cfg))


def get_credentials() -> tuple[str, str]:
    return load_credentials()


def credentials_configured() -> bool:
    username, password = get_credentials()
    return bool(username and password)


def set_credentials(username: str, password: str) -> None:
    save_credentials(username, password)
