# config.py
import json
import os
from dataclasses import dataclass, asdict

CONFIG_PATH = "config.json"


@dataclass
class AppConfig:
    maximo_url: str = "https://eam.indraweb.net/maximo/"
    username: str = ""
    password: str = ""
    download_dir: str = os.path.expanduser("~/Downloads")
    dest_folder: str = os.path.expanduser("~/Documents/Maximo")
    db_path: str = "maximo_data.db"
    auto_update_enabled: bool = False
    auto_update_interval_min: int = 5
    # Filtros por defecto (ajusta a tu caso)
    filters: dict = None
    last_status: dict | None = None

    def __post_init__(self):
        if self.filters is None:
            self.filters = {
                "mx38_tfrow_[C:26]_txt-tb": "=LAB-BAD"  # mismo que en tus scripts
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
