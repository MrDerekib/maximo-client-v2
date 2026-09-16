"""Limpieza limitada a exportaciones y temporales identificables del cliente."""
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

EXPORT_NAME = re.compile(r"(?:\d{8}(?:-[0-9a-f]{32})?|maximo-export-[0-9a-f]{32})\.xls", re.I)
TEMP_NAME = re.compile(r"maximo-(?:ot|update|edge|download)-[a-z0-9_]{8}")
DAY = 24 * 60 * 60


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _direct_child(path, root):
    """Nunca seguir enlaces ni aceptar una ruta fuera de la carpeta prevista."""
    return not _is_link(path) and path.resolve().parent == root.resolve()


def cleanup_exports(folder, keep=5, now=None):
    """Conserva los cinco más recientes y todos los del último día."""
    now = time.time() if now is None else now
    root = Path(folder)
    removed = 0
    freed = 0
    try:
        if not root.exists() or _is_link(root):
            return 0, 0
        candidates = []
        for path in root.iterdir():
            if EXPORT_NAME.fullmatch(path.name) and _direct_child(path, root) and path.is_file():
                candidates.append((path.stat().st_mtime, path))
        candidates.sort(reverse=True)
        for modified, path in candidates[max(1, keep):]:
            if now - modified < DAY:
                continue
            try:
                if not _direct_child(path, root):
                    continue
                size = path.stat().st_size
                path.unlink()
                removed += 1
                freed += size
            except OSError:
                logging.warning("No se pudo limpiar la exportación %s", path, exc_info=True)
    except OSError:
        logging.warning("No se pudieron revisar las exportaciones", exc_info=True)
    logging.info("Limpieza de exportaciones: %d archivos, %.2f MiB", removed, freed / 1024**2)
    return removed, freed


def _edge_commands():
    """Si Windows no permite verificar TODOS los Edge, no se borra ningún perfil."""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "$ErrorActionPreference = 'Stop'; "
             "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
             "@(Get-CimInstance Win32_Process -Filter \"Name = 'msedge.exe'\" | "
             "Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8-sig", timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW, check=True,
        )
        processes = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(processes, dict):
            processes = [processes]
        if not isinstance(processes, list):
            return None
        commands = []
        for process in processes:
            command = process.get("CommandLine")
            if not isinstance(command, str) or not command.strip():
                return None
            commands.append(command.replace("/", "\\").casefold())
        return commands
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        logging.warning("No se puede verificar Edge; se conservan los temporales.")
        return None


def _tree_size_without_links(path):
    """Rechaza también enlaces o junctions dentro del perfil antes de borrarlo."""
    size = 0
    for root, dirs, files in os.walk(path, followlinks=False, onerror=_raise_walk_error):
        for name in dirs + files:
            child = Path(root) / name
            if _is_link(child):
                raise OSError(f"La carpeta contiene un enlace: {child}")
            if name in files:
                size += child.stat().st_size
    return size


def _raise_walk_error(error):
    raise error


def cleanup_stale_temps(download_root, now=None):
    now = time.time() if now is None else now
    removed = 0
    freed = 0
    roots = {Path(tempfile.gettempdir()).resolve(), Path(download_root).resolve()}
    commands = _edge_commands()
    if commands is None:
        return 0, 0
    for root in roots:
        try:
            if not root.is_dir() or _is_link(root):
                continue
            for path in root.iterdir():
                if not TEMP_NAME.fullmatch(path.name):
                    continue
                try:
                    if not _direct_child(path, root) or not path.is_dir():
                        continue
                    if now - path.stat().st_mtime < 7 * DAY:
                        continue
                    resolved = path.resolve()
                    needle = str(resolved).replace("/", "\\").casefold()
                    if any(needle in command for command in commands):
                        continue
                    # Un perfil abierto usa --user-data-dir; una descarga activa
                    # está protegida por su antigüedad y su nombre único por ejecución.
                    size = _tree_size_without_links(resolved)
                    if not _direct_child(path, root):
                        continue
                    shutil.rmtree(resolved)
                    removed += 1
                    freed += size
                except OSError:
                    logging.warning("Se conserva temporal inaccesible: %s", path)
        except OSError:
            logging.warning("No se pudieron revisar temporales en %s", root)
    logging.info("Limpieza de temporales: %d carpetas, %.2f MiB", removed, freed / 1024**2)
    return removed, freed


def run_maintenance(cfg):
    cleanup_exports(cfg.dest_folder)
    cleanup_stale_temps(cfg.download_dir)
