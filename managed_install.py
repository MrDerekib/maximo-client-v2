"""Instalación por usuario para que el actualizador tenga una ruta estable."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app_paths import MANAGED_APP_DIR, ensure_user_directories


def _is_distributed_executable() -> bool:
    """Evita mover la ejecución desde Python durante desarrollo."""
    return sys.executable.lower().endswith("maximodesktop.exe")


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_desktop_shortcut(executable: Path) -> None:
    """Crea un acceso directo por usuario; un fallo no impide abrir la app."""
    if os.name != "nt":
        return
    shortcut_name = "Maximo Desktop.lnk"
    icon = executable.parent / "icon.ico"
    command = (
        "$desktop=[Environment]::GetFolderPath('Desktop');"
        "$shell=New-Object -ComObject WScript.Shell;"
        f"$link=$shell.CreateShortcut((Join-Path $desktop {_powershell_literal(shortcut_name)}));"
        f"$link.TargetPath={_powershell_literal(str(executable))};"
        f"$link.WorkingDirectory={_powershell_literal(str(executable.parent))};"
        f"$link.IconLocation={_powershell_literal(str(icon))};"
        "$link.Save()"
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("No se pudo crear el acceso directo del Escritorio: %s", exc)


def start_managed_install_if_needed() -> bool:
    """Instala la distribución en LocalAppData y arranca desde allí.

    Devuelve ``True`` cuando ya se lanzó la copia gestionada, para que el
    proceso actual termine antes de construir la interfaz.
    """
    if not _is_distributed_executable():
        return False

    current = Path(sys.executable).resolve()
    managed = MANAGED_APP_DIR / current.name
    if managed.exists() and current == managed.resolve():
        create_desktop_shortcut(managed)
        return False

    ensure_user_directories()
    if not managed.exists():
        try:
            shutil.copytree(current.parent, MANAGED_APP_DIR, dirs_exist_ok=True)
        except OSError as exc:
            logging.warning("No se pudo preparar la instalación gestionada: %s", exc)
            return False

    if managed.exists():
        try:
            subprocess.Popen([str(managed)], cwd=str(MANAGED_APP_DIR))
            return True
        except OSError as exc:
            logging.warning("No se pudo iniciar la instalación gestionada: %s", exc)
    return False
