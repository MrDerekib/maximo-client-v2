"""Instalación por usuario para que el actualizador tenga una ruta estable."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from app_paths import MANAGED_APP_DIR, ensure_user_directories


class _InstallProgress:
    """Ventana breve y visible durante la primera instalación por usuario."""
    def __init__(self) -> None:
        self.window = tk.Tk()
        self.window.title("Preparando Maximo Desktop")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.message = tk.StringVar(value="Preparando la instalación…")
        tk.Label(self.window, textvariable=self.message, padx=28, pady=20).pack()
        self.window.update_idletasks()
        width, height = 390, 90
        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.update()

    def set(self, text: str) -> None:
        self.message.set(text)
        self.window.update_idletasks()
        self.window.update()

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass


def _distributed_executable() -> Path | None:
    """Obtiene el exe distribuido sin confundirlo con Python de desarrollo."""
    for raw_path in (sys.argv[0], sys.executable):
        try:
            candidate = Path(raw_path).resolve()
        except OSError:
            continue
        if candidate.suffix.lower() == ".exe" and candidate.exists():
            return candidate
    return None


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
    current = _distributed_executable()
    if current is None:
        logging.info("Instalación gestionada omitida: ejecución desde Python de desarrollo.")
        return False

    managed = MANAGED_APP_DIR / current.name
    if managed.exists() and current == managed.resolve():
        logging.info("Instalación gestionada activa: %s", managed)
        create_desktop_shortcut(managed)
        return False

    ensure_user_directories()
    logging.info("Instalación gestionada: origen=%s, destino=%s", current.parent, MANAGED_APP_DIR)
    progress = _InstallProgress()
    if not managed.exists():
        try:
            progress.set("Copiando Maximo Desktop a tu carpeta de usuario…")
            shutil.copytree(current.parent, MANAGED_APP_DIR, dirs_exist_ok=True)
            logging.info("Instalación gestionada copiada correctamente.")
        except OSError as exc:
            progress.close()
            logging.warning("No se pudo preparar la instalación gestionada: %s", exc)
            return False

    if managed.exists():
        try:
            progress.set("Creando acceso directo y reiniciando Maximo Desktop…")
            subprocess.Popen([str(managed)], cwd=str(MANAGED_APP_DIR))
            logging.info("Instalación gestionada iniciada: %s", managed)
            progress.close()
            return True
        except OSError as exc:
            progress.close()
            logging.warning("No se pudo iniciar la instalación gestionada: %s", exc)
    progress.close()
    return False
