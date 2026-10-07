"""Instalación por usuario de Maximo Desktop con Qt."""
from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

from app_paths import APP_ROOT, DEVELOPMENT_MODE, MANAGED_APP_DIR, ensure_user_directories
from update_installer import distributed_executable


class ManagedInstallError(RuntimeError):
    """No se pudo preparar o iniciar la instalación por usuario."""


def executable_file_version(executable: Path) -> tuple[int, int, int, int] | None:
    """Lee la versión PE incluida en el ejecutable distribuido."""
    if os.name != "nt" or not executable.is_file():
        return None
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(executable), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(executable), 0, size, buffer):
            return None
        value = ctypes.c_void_p()
        value_size = wintypes.UINT()
        if not ctypes.windll.version.VerQueryValueW(
            buffer, "\\", ctypes.byref(value), ctypes.byref(value_size)
        ):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [(name, wintypes.DWORD) for name in (
                "dwSignature", "dwStrucVersion", "dwFileVersionMS", "dwFileVersionLS",
                "dwProductVersionMS", "dwProductVersionLS", "dwFileFlagsMask",
                "dwFileFlags", "dwFileOS", "dwFileType", "dwFileSubtype",
                "dwFileDateMS", "dwFileDateLS",
            )]

        info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        if info.dwSignature != 0xFEEF04BD:
            return None
        return (
            info.dwFileVersionMS >> 16, info.dwFileVersionMS & 0xFFFF,
            info.dwFileVersionLS >> 16, info.dwFileVersionLS & 0xFFFF,
        )
    except (AttributeError, OSError, ValueError):
        return None


def _version_text(value: tuple[int, ...]) -> str:
    parts = list(value)
    while len(parts) > 3 and parts[-1] == 0:
        parts.pop()
    return ".".join(map(str, parts))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_distribution(current: Path) -> Path:
    stage = APP_ROOT / f".app-staging-{uuid4().hex}"
    try:
        shutil.copytree(current.parent, stage)
        staged_executable = stage / current.name
        if not staged_executable.is_file() or _sha256(staged_executable) != _sha256(current):
            raise ManagedInstallError("La copia temporal del ejecutable no coincide con el paquete original.")
        return stage
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def _replace_managed_distribution(stage: Path, installed_version: tuple[int, ...], progress) -> None:
    previous = APP_ROOT / f"app-previous-v{_version_text(installed_version)}"
    if previous.exists():
        previous = APP_ROOT / f"{previous.name}-{uuid4().hex[:8]}"
    progress("Esperando a que Windows libere la instalación anterior…")
    for attempt, delay in enumerate((0, 1, 2), start=1):
        try:
            MANAGED_APP_DIR.replace(previous)
            break
        except PermissionError as exc:
            if getattr(exc, "winerror", None) != 32 or attempt == 3:
                raise
            time.sleep(delay or 1)
    try:
        stage.replace(MANAGED_APP_DIR)
    except OSError:
        previous.replace(MANAGED_APP_DIR)
        raise
    logging.info("Instalación Qt actualizada; copia anterior: %s", previous)


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_desktop_shortcut(executable: Path) -> None:
    """Actualiza el acceso directo estable; un fallo no impide abrir la app."""
    if os.name != "nt":
        return
    desktop_path = ctypes.create_unicode_buffer(32768)
    found_desktop = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, desktop_path) == 0
    shortcut_name = "Maximo Desktop.lnk"
    if found_desktop and (Path(desktop_path.value) / shortcut_name).exists():
        return
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
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.warning("No se pudo crear el acceso directo del Escritorio: %s", exc)


def redirect_to_managed_install(progress=None) -> bool:
    """Instala la distribución fuera del ZIP y abre la copia gestionada.

    Devuelve True si ha iniciado esa copia y el proceso actual debe terminar.
    """
    current = distributed_executable()
    if current is None or DEVELOPMENT_MODE or os.name != "nt":
        return False
    managed = (MANAGED_APP_DIR / current.name).resolve()
    if current == managed:
        create_desktop_shortcut(managed)
        return False

    progress = progress or (lambda message: None)
    ensure_user_directories()
    stage = None
    try:
        if managed.is_file():
            candidate_version = executable_file_version(current)
            installed_version = executable_file_version(managed)
            if candidate_version is None or installed_version is None:
                raise ManagedInstallError("No se pudo verificar la versión de la instalación existente.")
            if candidate_version < installed_version:
                raise ManagedInstallError(
                    f"La versión instalada ({_version_text(installed_version)}) es más reciente "
                    f"que este paquete ({_version_text(candidate_version)})."
                )
            if candidate_version > installed_version:
                progress("Preparando la nueva versión de Maximo Desktop…")
                stage = _stage_distribution(current)
                progress("Instalando la nueva versión de Maximo Desktop…")
                _replace_managed_distribution(stage, installed_version, progress)
                stage = None
        else:
            if MANAGED_APP_DIR.exists():
                raise ManagedInstallError("La carpeta de instalación existe, pero falta MaximoDesktop.exe.")
            progress("Instalando Maximo Desktop en tu carpeta de usuario…")
            stage = _stage_distribution(current)
            stage.replace(MANAGED_APP_DIR)
            stage = None
        create_desktop_shortcut(managed)
        progress("Abriendo Maximo Desktop…")
        subprocess.Popen([str(managed), *sys.argv[1:]], cwd=str(MANAGED_APP_DIR))
        logging.info("Copia Qt instalada e iniciada: %s", managed)
        return True
    except (OSError, shutil.Error, ManagedInstallError) as exc:
        logging.exception("No se pudo preparar la instalación Qt por usuario")
        raise ManagedInstallError(str(exc)) from exc
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
