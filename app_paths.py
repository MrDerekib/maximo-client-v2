"""Rutas persistentes de la aplicación, separadas del código actualizable."""
import os
from pathlib import Path


def _program_dir() -> Path:
    compiled = globals().get("__compiled__")
    containing_dir = getattr(compiled, "containing_dir", None)
    if containing_dir:
        return Path(containing_dir).resolve()
    return Path(__file__).resolve().parent


PROGRAM_DIR = _program_dir()
BASE_DIR = PROGRAM_DIR

if os.name == "nt":
    _local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    APP_ROOT = _local_app_data / "MaximoDesktop"
else:
    APP_ROOT = Path.home() / ".local" / "share" / "MaximoDesktop"

CONFIG_DIR = APP_ROOT / "config"
DATA_DIR = APP_ROOT / "data"
BACKUP_DIR = APP_ROOT / "backups"
LOG_DIR = APP_ROOT / "logs"
CACHE_DIR = APP_ROOT / "cache"
DOWNLOAD_DIR = CACHE_DIR / "downloads"
EXPORT_DIR = CACHE_DIR / "exports"
UPDATE_CACHE_DIR = CACHE_DIR / "updates"
CUSTOM_DIR = APP_ROOT / "custom"

CONFIG_PATH = CONFIG_DIR / "config.json"
CREDENTIAL_PATH = CONFIG_DIR / "credentials.dat"
DB_PATH = DATA_DIR / "maximo_data.db"
PROFILES_PATH = DATA_DIR / "search_profiles.json"
TRACKING_OPTIONS_PATH = CUSTOM_DIR / "seguimiento_options.txt"

USER_DIRECTORIES = (
    CONFIG_DIR, DATA_DIR, BACKUP_DIR, LOG_DIR, DOWNLOAD_DIR,
    EXPORT_DIR, UPDATE_CACHE_DIR, CUSTOM_DIR,
)


def ensure_user_directories() -> None:
    for directory in USER_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)
