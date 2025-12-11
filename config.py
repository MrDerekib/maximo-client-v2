# config.py
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

#CONFIG_PATH = "config.json"

# Directorio base: donde está el código o el .exe (si está compilado con Nuitka)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Carpeta de datos propia de la app
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Config junto al ejecutable / script
CONFIG_PATH = str(BASE_DIR / "config.json")

@dataclass
class AppConfig:
    maximo_url: str = "https://eam.indraweb.net/maximo/"
    username: str = ""
    password: str = ""

    # Descargas: por defecto, carpeta de Descargas del usuario
    download_dir: str = str(Path.home() / "Downloads")

    # Carpeta de trabajo de la app: ./data/exports (junto a la app)
    dest_folder: str = str(DATA_DIR / "exports")

    # Base de datos: ./data/maximo_data.db
    db_path: str = str(DATA_DIR / "maximo_data.db")

    auto_update_enabled: bool = False
    auto_update_interval_min: int = 10

    # Filtros por defecto (se usan en apply_filter)
    filters: dict | None = None

    # Para la barra de estado persistente
    last_status: dict | None = None


    def __post_init__(self):
        if self.filters is None:
            self.filters = {
                "mx38_tfrow_[C:26]_txt-tb": "=LAB-BAD"  # valor filtro planta = LAB-BDN
            }


def load_config() -> AppConfig:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge con defaults por si faltan claves
        base = AppConfig()
        base_dict = asdict(base)
        base_dict.update(data)
        return AppConfig(**base_dict)
    else:
        cfg = AppConfig()
        save_config(cfg)
        return cfg


def save_config(cfg: AppConfig):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True) if os.path.dirname(CONFIG_PATH) else None
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)


def get_credentials():
    cfg = load_config()
    return cfg.username, cfg.password

def credentials_configured() -> bool:
    """
    Devuelve True si hay usuario y contraseña configurados,
    False en caso contrario.
    """
    username, password = get_credentials()
    return bool(username and password)


def set_credentials(username: str, password: str):
    cfg = load_config()
    cfg.username = username
    cfg.password = password
    save_config(cfg)
