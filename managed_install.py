"""Instalación por usuario para que el actualizador tenga una ruta estable."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from uuid import uuid4

from app_paths import APP_ROOT, MANAGED_APP_DIR, ensure_user_directories


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


def distributed_executable() -> Path | None:
    """Obtiene el exe distribuido sin confundirlo con Python de desarrollo."""
    try:
        # En Nuitka argv[0] es MaximoDesktop.exe; en desarrollo es el .py.
        candidate = Path(sys.argv[0]).resolve()
    except OSError:
        return None
    if candidate.name.lower() == "maximodesktop.exe" and candidate.exists():
        return candidate
    return None


def executable_file_version(executable: Path) -> tuple[int, int, int, int] | None:
    """Devuelve la versión incluida en un exe de Windows por Nuitka.

    Se consulta el recurso de versión del propio ejecutable, sin depender del
    nombre del archivo ni de los datos persistentes de la aplicación.
    """
    if os.name != "nt" or not executable.is_file():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(executable), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(
            str(executable), 0, size, buffer
        ):
            return None
        value = ctypes.c_void_p()
        value_size = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buffer, "\\\\", ctypes.byref(value), ctypes.byref(value_size)
        ):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", wintypes.DWORD),
                ("dwStrucVersion", wintypes.DWORD),
                ("dwFileVersionMS", wintypes.DWORD),
                ("dwFileVersionLS", wintypes.DWORD),
                ("dwProductVersionMS", wintypes.DWORD),
                ("dwProductVersionLS", wintypes.DWORD),
                ("dwFileFlagsMask", wintypes.DWORD),
                ("dwFileFlags", wintypes.DWORD),
                ("dwFileOS", wintypes.DWORD),
                ("dwFileType", wintypes.DWORD),
                ("dwFileSubtype", wintypes.DWORD),
                ("dwFileDateMS", wintypes.DWORD),
                ("dwFileDateLS", wintypes.DWORD),
            ]

        info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        if info.dwSignature != 0xFEEF04BD:
            return None
        return (
            info.dwFileVersionMS >> 16,
            info.dwFileVersionMS & 0xFFFF,
            info.dwFileVersionLS >> 16,
            info.dwFileVersionLS & 0xFFFF,
        )
    except (AttributeError, OSError):
        return None


def _version_is_newer(candidate: tuple[int, ...], installed: tuple[int, ...]) -> bool:
    """Compara versiones numéricas de recursos PE."""
    return candidate > installed


def _format_file_version(value: tuple[int, ...] | None) -> str:
    if value is None:
        return "desconocida"
    visible = list(value)
    while len(visible) > 3 and visible[-1] == 0:
        visible.pop()
    return ".".join(str(part) for part in visible)


def _stage_distribution(source_dir: Path) -> Path:
    """Copia una distribución completa a un directorio no publicado aún."""
    staging = APP_ROOT / f".app-staging-{uuid4().hex}"
    shutil.copytree(source_dir, staging)
    return staging


def _replace_managed_distribution(current: Path, managed: Path, progress: _InstallProgress) -> bool:
    """Publica una distribución más nueva y conserva la anterior para recuperar."""
    staging: Path | None = None
    previous: Path | None = None
    try:
        progress.set("Preparando la nueva versión de Maximo Desktop…")
        staging = _stage_distribution(current.parent)
        staged_executable = staging / current.name
        current_version = executable_file_version(current)
        staged_version = executable_file_version(staged_executable)
        if not staged_executable.exists() or staged_version != current_version:
            raise OSError("La copia temporal no contiene el ejecutable esperado.")

        previous_version = _format_file_version(executable_file_version(managed))
        previous = APP_ROOT / f"app-previous-v{previous_version}"
        if previous.exists():
            previous = APP_ROOT / f"app-previous-v{previous_version}-{uuid4().hex[:8]}"

        progress.set("Instalando la nueva versión de Maximo Desktop…")
        MANAGED_APP_DIR.replace(previous)
        try:
            staging.replace(MANAGED_APP_DIR)
        except OSError:
            previous.replace(MANAGED_APP_DIR)
            raise
        logging.info(
            "Instalación local actualizada: %s -> %s. Copia anterior: %s",
            previous_version, _format_file_version(current_version), previous,
        )
        return True
    except (OSError, shutil.Error) as exc:
        logging.warning("No se pudo sustituir la instalación local: %s", exc)
        return False
    finally:
        if staging is not None and staging.exists():
            try:
                shutil.rmtree(staging)
            except OSError:
                logging.warning("No se pudo eliminar la copia temporal: %s", staging)


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
    current = distributed_executable()
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
        except (OSError, shutil.Error) as exc:
            progress.close()
            logging.warning("No se pudo preparar la instalación gestionada: %s", exc)
            return False
    else:
        current_version = executable_file_version(current)
        managed_version = executable_file_version(managed)
        logging.info(
            "Instalación local: externa v%s, gestionada v%s.",
            _format_file_version(current_version), _format_file_version(managed_version),
        )
        if current_version is None or managed_version is None:
            logging.warning(
                "No se pudo verificar la versión de una instalación; se conserva la copia gestionada."
            )
        elif _version_is_newer(current_version, managed_version):
            if not _replace_managed_distribution(current, managed, progress):
                progress.close()
                return False
        else:
            logging.info("La copia gestionada ya es igual o más reciente; se conserva.")

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
