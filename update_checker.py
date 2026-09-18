# update_checker.py
from __future__ import annotations

import json
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LATEST_URL = "https://api.github.com/repos/MrDerekib/maximo-client-v2/releases/latest"

@dataclass
class LatestRelease:
    tag: str
    html_url: str
    checked_at: str  # ISO string
    asset_url: str = ""



def _parse_version(v: str) -> tuple[int, int, int, int]:
    """
    Extrae la primera versión estilo X.Y, X.Y.Z o X.Y.Z.R de un tag tipo:
    'v0.8.3', 'v.0.8.3', 'release-0.8.3', '0.8.3', etc.
    """
    v = (v or "").strip()

    # Busca un patrón de versión dentro del string
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?", v)
    if not m:
        return (0, 0, 0, 0)

    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    revision = int(m.group(4) or 0)
    return (major, minor, patch, revision)


def is_newer(remote_tag: str, local_version: str) -> bool:
    return _parse_version(remote_tag) > _parse_version(local_version)

def fetch_latest_release(timeout_sec: int = 5) -> LatestRelease:
    req = urllib.request.Request(
        LATEST_URL,
        headers={"User-Agent": "maximo-client-v2"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag = (data.get("tag_name") or "").strip()
    html_url = (data.get("html_url") or "").strip()
    assets = data.get("assets") or []
    zip_asset = next((asset for asset in assets if str(asset.get("name", "")).lower().endswith(".zip")), {})
    checked_at = datetime.now().isoformat(timespec="minutes")
    return LatestRelease(tag=tag, html_url=html_url, checked_at=checked_at,
                         asset_url=str(zip_asset.get("browser_download_url") or ""))


def download_release_asset(release: LatestRelease, destination: Path, timeout_sec: int = 30) -> Path:
    """Descarga y extrae el ZIP de una release dentro de la caché local."""
    if not release.asset_url:
        raise RuntimeError("La release no incluye un paquete ZIP para Windows.")
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    archive = destination / "update.zip"
    request = urllib.request.Request(release.asset_url, headers={"User-Agent": "MaximoDesktop"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    extracted = destination / "files"
    extracted.mkdir()
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError("El paquete de actualización contiene una ruta no válida.")
        package.extractall(extracted)
    executables = list(extracted.rglob("MaximoDesktop.exe"))
    if len(executables) != 1:
        raise RuntimeError("El paquete no contiene una instalación válida de Maximo Desktop.")
    return executables[0].parent


def format_version_tag(tag: str) -> str:
    """
    Devuelve 'vX.Y.Z', conservando '.R' cuando el tag incluye una revisión.
    Acepta '0.8.3', 'v0.8.3', 'v.0.8.3', 'release-0.8.3', etc.
    """
    tag = (tag or "").strip()
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?", tag)
    if not m:
        return tag  # fallback: lo devolvemos tal cual
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    revision = f".{int(m.group(4))}" if m.group(4) is not None else ""
    return f"v{major}.{minor}.{patch}{revision}"
