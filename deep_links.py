"""Enlaces locales que abren una OT en la aplicación de escritorio."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qsl


OT_URI_PATTERN = re.compile(r"^\d{1,20}$")


def scheme_for_environment(development: bool = False) -> str:
    return "maximodesk-dev" if development else "maximodesk"


OT_LINK_ACTIONS = {"open", "open_filter", "filter"}


def make_ot_uri(ot: str, development: bool = False, action: str = "open") -> str:
    value = str(ot).strip()
    if not OT_URI_PATTERN.fullmatch(value):
        raise ValueError("El número de OT del enlace debe contener solo dígitos.")
    if action not in OT_LINK_ACTIONS:
        raise ValueError("Acción de enlace OT no válida.")
    suffix = "" if action == "open" else f"?action={action}"
    return f"{scheme_for_environment(development)}://ot/{value}{suffix}"


def parse_ot_uri(uri: str) -> str | None:
    try:
        parsed = urlparse(uri)
    except ValueError:
        return None
    if parsed.scheme not in {"maximodesk", "maximodesk-dev"} or parsed.netloc.lower() != "ot":
        return None
    ot = parsed.path.strip("/")
    return ot if OT_URI_PATTERN.fullmatch(ot) and parse_ot_action(uri) is not None else None


def parse_ot_action(uri: str) -> str | None:
    try:
        parsed = urlparse(uri)
        if parsed.fragment:
            return None
        params = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    if not params:
        return "open"
    if len(params) != 1 or params[0][0] != "action" or params[0][1] not in OT_LINK_ACTIONS:
        return None
    return params[0][1]


def register_protocol_handler(development: bool = False, script_path: Path | None = None) -> bool:
    """Registra el protocolo solo para el usuario actual; sin elevación."""
    if os.name != "nt":
        return False
    try:
        import winreg
    except ImportError:
        return False

    scheme = scheme_for_environment(development)
    if development:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        script_path = (script_path or Path(__file__).resolve().with_name("dev_link_launcher.pyw")).resolve()
        if not pythonw.is_file() or not script_path.is_file():
            return False
        command = f'"{pythonw}" "{script_path}" "%1"'
    else:
        executable = Path(sys.argv[0]).resolve()
        if executable.suffix.lower() != ".exe":
            return False
        command = f'"{executable}" "%1"'

    base = rf"Software\Classes\{scheme}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f"URL:Maximo Desktop ({'desarrollo' if development else 'OT'})")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)
    return True
