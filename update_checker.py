# update_checker.py
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime

LATEST_URL = "https://api.github.com/repos/MrDerekib/maximo-client-v2/releases/latest"

@dataclass
class LatestRelease:
    tag: str
    html_url: str
    checked_at: str  # ISO string



def _parse_version(v: str) -> tuple[int, int, int]:
    """
    Extrae la primera versión estilo X.Y o X.Y.Z de un tag tipo:
    'v0.8.3', 'v.0.8.3', 'release-0.8.3', '0.8.3', etc.
    """
    v = (v or "").strip()

    # Busca un patrón de versión dentro del string
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", v)
    if not m:
        return (0, 0, 0)

    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


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
    checked_at = datetime.now().isoformat(timespec="minutes")
    return LatestRelease(tag=tag, html_url=html_url, checked_at=checked_at)


def format_version_tag(tag: str) -> str:
    """
    Devuelve una versión bonita para UI: siempre 'vX.Y.Z'
    Acepta '0.8.3', 'v0.8.3', 'v.0.8.3', 'release-0.8.3', etc.
    """
    tag = (tag or "").strip()
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", tag)
    if not m:
        return tag  # fallback: lo devolvemos tal cual
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return f"v{major}.{minor}.{patch}"
