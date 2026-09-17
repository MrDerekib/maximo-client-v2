"""Configuración persistente y migración desde versiones anteriores."""
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, asdict, fields
from contextlib import closing
from pathlib import Path

from app_paths import (
    BACKUP_DIR, BASE_DIR, CONFIG_PATH, DB_PATH, DOWNLOAD_DIR,
    EXPORT_DIR, LOG_DIR, PROFILES_PATH, TRACKING_OPTIONS_PATH,
    ensure_user_directories,
)
from credential_store import load_credentials, save_credentials

LEGACY_CONFIG_PATH = BASE_DIR / "config.json"
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
    filters: dict | None = None
    last_status: dict | None = None
    latest_release_tag: str = ""
    latest_release_url: str = ""
    latest_release_checked_at: str = ""

    def __post_init__(self):
        self.download_dir = str(DOWNLOAD_DIR)
        self.dest_folder = str(EXPORT_DIR)
        self.db_path = str(DB_PATH)
        if self.filters is None:
            self.filters = {"mx38_tfrow_[C:26]_txt-tb": "=LAB-BAD"}


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
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
    _copy_if_missing(BASE_DIR / "seguimiento_options.txt", TRACKING_OPTIONS_PATH)
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
