"""Validación y persistencia de perfiles de búsqueda locales (sin credenciales)."""
from datetime import date
import json
import os
from pathlib import Path
from app_paths import create_unique_file


def normalize_filter_value(value):
    """Unifica espacios HTML, repetidos y exteriores sin modificar la BD."""
    return " ".join((value or "").split())


def validate_filters(value):
    result = {}
    for key in ("clients", "types", "tracking"):
        items = value.get(key, [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise ValueError("Selección de filtros no válida")
        result[key] = list(dict.fromkeys(normalize_filter_value(item) for item in items))
    for key in ("equipment", "date_from", "date_to"):
        item = value.get(key, "")
        if not isinstance(item, str):
            raise ValueError("Texto de filtro no válido")
        result[key] = item.strip()
    for key in ("date_from", "date_to"):
        if result[key]:
            try:
                parsed = date.fromisoformat(result[key])
                if parsed.isoformat() != result[key]:
                    raise ValueError()
            except ValueError:
                raise ValueError("Introduce las fechas como AAAA-MM-DD.") from None
    if result["date_from"] and result["date_to"] and result["date_from"] > result["date_to"]:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    return result


def validate_profile(value):
    if not isinstance(value, dict):
        raise ValueError("Perfil no válido")
    field = value.get("search_by", "OT")
    if field not in ("OT", "Nº_de_serie", "Descripción"):
        raise ValueError("Campo de búsqueda no válido")
    if not isinstance(value.get("advanced", {}), dict):
        raise ValueError("Filtros no válidos")
    result = {"search_by": field, "advanced": validate_filters(value.get("advanced", {}))}
    for key, default in (("search", ""), ("client", "Todos")):
        result[key] = value.get(key, default)
        if not isinstance(result[key], str):
            raise ValueError("Perfil no válido")
    result["client"] = normalize_filter_value(result["client"])
    return result


def load_profiles(path):
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Archivo de perfiles no válido")
    return {name: validate_profile(value) for name, value in data.items()}


def save_profiles(path, profiles):
    data = {name: validate_profile(value) for name, value in profiles.items()}
    path = Path(path)
    temporary = create_unique_file(path.parent, "profiles-", ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
