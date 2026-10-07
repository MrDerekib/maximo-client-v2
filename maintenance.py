"""Retención de exportaciones XLS procesadas por la sincronización."""
import logging
from pathlib import Path
import re
import stat
import time

EXPORT_NAME = re.compile(r"(?:\d{8}(?:-[0-9a-f]{32})?|maximo-export-[0-9a-f]{32})\.xls", re.I)
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
