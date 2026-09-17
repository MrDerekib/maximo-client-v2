"""Rutas persistentes de la aplicación, separadas del código actualizable."""
import os
from pathlib import Path
from uuid import uuid4


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
EDGE_PROFILE_DIR = CACHE_DIR / "edge-profiles"
CUSTOM_DIR = APP_ROOT / "custom"

CONFIG_PATH = CONFIG_DIR / "config.json"
CREDENTIAL_PATH = CONFIG_DIR / "credentials.dat"
DB_PATH = DATA_DIR / "maximo_data.db"
PROFILES_PATH = DATA_DIR / "search_profiles.json"
TRACKING_OPTIONS_PATH = CUSTOM_DIR / "seguimiento_options.txt"
DEFAULT_TRACKING_OPTIONS_PATH = PROGRAM_DIR / "seguimiento_options.txt"

USER_DIRECTORIES = (
    CONFIG_DIR, DATA_DIR, BACKUP_DIR, LOG_DIR, DOWNLOAD_DIR,
    EXPORT_DIR, UPDATE_CACHE_DIR, EDGE_PROFILE_DIR, CUSTOM_DIR,
)


def ensure_user_directories() -> None:
    for directory in USER_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def create_unique_directory(parent: Path | str, prefix: str) -> Path:
    """Crea una carpeta única con permisos normales de usuario.

    ``tempfile.mkdtemp`` aplica ACL restrictivas en algunos equipos corporativos
    con Python 3.14, por lo que se evita para las carpetas de trabajo propias.
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = parent / f"{prefix}{uuid4().hex}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"No se pudo crear una carpeta temporal en {parent}")


def create_unique_file(parent: Path | str, prefix: str, suffix: str = "") -> Path:
    """Reserva un fichero temporal con permisos normales de usuario."""
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = parent / f"{prefix}{uuid4().hex}{suffix}"
        try:
            with candidate.open("x"):
                pass
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"No se pudo crear un fichero temporal en {parent}")
