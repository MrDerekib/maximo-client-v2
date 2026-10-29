"""Bounded, best-effort evidence of configured anomaly workflow failures."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app_paths import LOG_DIR

MAX_BYTES = 1024 * 1024
BACKUPS = 3
MAX_OPTIONS = 200
MAX_SNAPSHOTS = 12
_LOCK = Lock()


def _text(value, limit=300):
    text = " ".join(str(value if value is not None else "").split())
    text = text.split("Stacktrace:", 1)[0]
    text = re.sub(r"<[^>]*>", "[HTML omitido]", text)
    text = re.sub(r"https?://\S+", "[URL omitida]", text, flags=re.I)
    text = re.sub(r"(?i)\b(password|passwd|cookie|authorization|csrftoken|uisessionid|sessionid|token)\s*[=:]\s*[^\s,;]+",
                  r"\1=[omitido]", text)
    return text[:limit]


def _fields(value, names):
    if not isinstance(value, dict):
        return {}
    return {name: _text(value[name]) for name in names if value.get(name) is not None}


def _pagination(value):
    value = value if isinstance(value, dict) else {}
    return {key: number if type(number := value.get(key)) is int and number >= 0 else None
            for key in ("first", "last", "total")}


def record_anomaly_incident(context, snapshots, error):
    """Write one allowlisted JSONL event; failures must not affect the workflow."""
    try:
        if not isinstance(context, dict) or context.get("mode") != "configured":
            return None
        identifier = uuid4().hex
        event = {"schema_version": 1, "id": identifier,
                 "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                 **_fields(context, ("ot", "mode", "stage", "operation")),
                 "error": {"type": type(error).__name__, "message": _text(error, 700)}}
        requested = context.get("requested", {})
        event["requested"] = _fields(requested, ("class_key", "class_code", "organization"))
        if isinstance(requested, dict):
            if isinstance(requested.get("path"), (list, tuple)):
                event["requested"]["path"] = [_fields(row, ("key", "type", "code")) for row in requested["path"][:40]]
            if isinstance(requested.get("option_keys"), (list, tuple)):
                event["requested"]["option_keys"] = [_text(key, 180) for key in requested["option_keys"][:40]]
        event["expected"] = _fields(context.get("expected"), ("level", "type", "code"))
        if isinstance(context.get("actual_codes"), dict):
            event["actual_codes"] = _fields(context["actual_codes"], ("PROBLEM", "CAUSE", "REMEDY"))
        event["snapshots"] = []
        remaining = MAX_OPTIONS
        snapshots = snapshots if isinstance(snapshots, (list, tuple)) else []
        event["snapshots_truncated"] = len(snapshots) > MAX_SNAPSHOTS or context.get("snapshots_truncated") is True
        for source in snapshots[-MAX_SNAPSHOTS:]:
            if not isinstance(source, dict):
                continue
            options = source.get("options", [])
            options = options if isinstance(options, (list, tuple)) else []
            taken = options[:remaining]
            remaining -= len(taken)
            pagination = _pagination(source.get("pagination"))
            truncated = len(taken) < len(options) or source.get("truncated") is True
            all_pages = (pagination["total"] is not None and pagination["first"] is not None and
                         pagination["last"] is not None and
                         ((pagination["first"] == 1 and pagination["last"] == pagination["total"]) or
                          (pagination["total"] == pagination["first"] == pagination["last"] == 0)))
            event["snapshots"].append({
                **_fields(source, ("kind", "stage", "filter")),
                "scope": "visible_options", "pagination": pagination,
                "complete": bool(source.get("complete") is True and all_pages and not truncated and
                                 len(options) == pagination["total"]),
                "truncated": truncated,
                "options": [_fields(option, ("code", "type", "description", "organization")) for option in taken]})
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        path = Path(LOG_DIR) / "anomalias_incidencias.jsonl"
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size + len(line.encode("utf-8")) > MAX_BYTES:
                oldest = path.with_name(path.name + f".{BACKUPS}")
                oldest.unlink(missing_ok=True)
                for index in range(BACKUPS - 1, 0, -1):
                    source = path.with_name(path.name + f".{index}")
                    if source.exists():
                        source.replace(path.with_name(path.name + f".{index + 1}"))
                path.replace(path.with_name(path.name + ".1"))
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
        return {"id": identifier, "path": str(path)}
    except Exception:
        return None
