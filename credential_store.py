"""Almacén de credenciales ligado al usuario de Windows mediante DPAPI."""
import json
import os
from pathlib import Path

from app_paths import CREDENTIAL_PATH, create_unique_file


class CredentialStoreError(RuntimeError):
    pass


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("El almacén seguro requiere Windows DPAPI.")
    try:
        return _crypt(data, protect=True)
    except Exception as exc:
        raise CredentialStoreError("No se pudieron proteger las credenciales con Windows.") from exc


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("El almacén seguro requiere Windows DPAPI.")
    try:
        return _crypt(data, protect=False)
    except Exception as exc:
        raise CredentialStoreError("No se pudieron leer las credenciales protegidas.") from exc


def _crypt(data: bytes, protect: bool) -> bytes:
    """Llama a DPAPI con ctypes para no depender de pywin32 en el ejecutable."""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = (("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte)))

    source_buffer = ctypes.create_string_buffer(data, max(1, len(data)))
    source = DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = DataBlob()
    if protect:
        success = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), "MaximoDesktop", None, None, None, 1,
            ctypes.byref(destination),
        )
    else:
        success = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1,
            ctypes.byref(destination),
        )
    if not success:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def save_credentials(username: str, password: str, path: Path | None = None) -> None:
    target = Path(path or CREDENTIAL_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    encrypted = _protect(payload)
    temporary = create_unique_file(target.parent, target.name + ".", ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_credentials(path: Path | None = None) -> tuple[str, str]:
    target = Path(path or CREDENTIAL_PATH)
    if not target.exists():
        return "", ""
    try:
        payload = json.loads(_unprotect(target.read_bytes()).decode("utf-8"))
        return str(payload.get("username", "")), str(payload.get("password", ""))
    except CredentialStoreError:
        raise
    except Exception as exc:
        raise CredentialStoreError("El archivo de credenciales no es válido.") from exc
