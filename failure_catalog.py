"""Portable failure catalogue and validation of complete, parent-bound paths.

The checked-in resource is prepared offline. Runtime never reads the audit docs.
Option keys identify occurrences in shared groups; ancestors identify their route.
"""
from collections.abc import Mapping
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from app_paths import PROGRAM_DIR


def _resource_path():
    relative = Path("resources") / "failure_catalog.json"
    for base in (PROGRAM_DIR, Path(__file__).resolve().parent):
        candidate = Path(base) / relative
        if candidate.is_file():
            return candidate
    raise RuntimeError("No se encuentra el catálogo de anomalías instalado.")


@lru_cache(maxsize=1)
def _catalog():
    with _resource_path().open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("version") != 1:
        raise RuntimeError("La versión del catálogo de anomalías no es compatible.")
    return payload


def catalog_payload():
    """Return a JSON-serializable copy, safe for UI or caller modifications."""
    return deepcopy(_catalog())


def _walk(class_key, option_keys):
    payload = _catalog()
    if not isinstance(class_key, str):
        raise ValueError("La clase de anomalía guardada no es válida. Vuelve a elegirla.")
    failure_class = next((item for item in payload["classes"] if item["key"] == class_key), None)
    if failure_class is None:
        raise ValueError("La clase de anomalía ya no existe en el catálogo.")
    if not isinstance(option_keys, (list, tuple)) or any(not isinstance(key, str) for key in option_keys):
        raise ValueError("La ruta de anomalía guardada no es válida. Vuelve a elegirla.")
    options = payload["option_sets"].get(failure_class["options_ref"], [])
    path = []
    for index, key in enumerate(option_keys):
        item = next((item for item in options if item["key"] == key), None)
        if item is None:
            raise ValueError(f"La opción del nivel {index + 1} ya no existe o no pertenece a su padre.")
        # Distinct occurrence keys cannot disambiguate a native UI that exposes
        # identical codes with different successors. Never silently choose one.
        siblings = [other for other in options
                    if (other["type"], other["code"]) == (item["type"], item["code"])]
        if len(siblings) > 1 and not all(other.get("allow_duplicate", False) for other in siblings):
            raise ValueError(f"La opción {item['code']} tiene ocurrencias no equivalentes; requiere revisión.")
        path.append(item)
        options = payload["option_sets"].get(item.get("children_ref"), [])
    return payload, failure_class, path, options


def _described(payload, organization, item):
    return {**item, "description": payload["descriptions"].get(organization, {}).get(item["code"], ""),
            "allow_duplicate": bool(item.get("allow_duplicate", False))}


def choices(class_key, option_keys=()):
    """Return the next options for a valid prefix; a real leaf returns []."""
    payload, failure_class, _, options = _walk(class_key, option_keys)
    return [_described(payload, failure_class["organization"], item) for item in options]


def resolve_selection(selection):
    """Validate a complete route and resolve trusted codes for automation."""
    if not isinstance(selection, Mapping):
        raise ValueError("La combinación de anomalías guardada no es válida.")
    if "class_key" not in selection or "option_keys" not in selection:
        raise ValueError("Elige una clase y una ruta de anomalía completas.")
    payload, failure_class, path, options = _walk(selection["class_key"], selection["option_keys"])
    if not path or options:
        raise ValueError("La ruta de anomalía está incompleta; selecciona hasta su última opción.")
    return {"class_key": failure_class["key"], "class_code": failure_class["code"],
            "organization": failure_class["organization"],
            "path": [{key: value for key, value in _described(payload, failure_class["organization"], item).items()
                      if key in ("key", "type", "code", "description", "allow_duplicate")}
                     for item in path]}


def default_selection():
    """Return the established RFN-70 / OTROS-01 / OTROS-02 / OTROS-03 route."""
    selection = {"class_key": "TRANSPORTES|RFN-70", "option_keys": []}
    for code in ("OTROS-01", "OTROS-02", "OTROS-03"):
        matches = [item for item in choices(**selection) if item["code"] == code]
        if len(matches) != 1:
            raise RuntimeError("El catálogo no contiene una ruta predeterminada única.")
        selection["option_keys"].append(matches[0]["key"])
    resolve_selection(selection)
    return selection
