"""Utilidades de prueba independientes de las restricciones de %TEMP%."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4


@contextmanager
def temporary_directory():
    """Crea un temporal escribible sin los ACL restrictivos de TemporaryDirectory."""
    path = Path(tempfile.gettempdir()) / f"maximo-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)
