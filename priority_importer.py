"""Lectura segura de prioridades marcadas en amarillo en informes .xls."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import xlrd
except ImportError:  # El mensaje se muestra solo al intentar importar.
    xlrd = None


YELLOW_MINIMUM = (180, 160, 170)
_DATE_RE = re.compile(r"Informe emitido el\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class PriorityFile:
    path: Path
    project: str
    section: str | None
    source_report_date: str | None
    items: tuple[tuple[str, str | None], ...]


def _text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_heading(value) -> str:
    return _text(value).lower().replace("º", "o").replace("°", "o")


def _colour(book, index):
    value = book.colour_map.get(index)
    return value if isinstance(value, tuple) else None


def _is_yellow(value) -> bool:
    return bool(value and value[0] >= YELLOW_MINIMUM[0] and value[1] >= YELLOW_MINIMUM[1] and value[2] <= YELLOW_MINIMUM[2])


def _project_from_sheet(sheet) -> tuple[str, str | None]:
    probe = " ".join(_text(sheet.cell_value(row, col)) for row in range(min(5, sheet.nrows)) for col in range(sheet.ncols)).upper()
    if "RENFE" in probe:
        return "RENFE", None
    if "TMB" in probe:
        return "TMB", None
    match = re.search(r"L9\s+TRAMO\s+(I|II|IV)\b", probe)
    if match:
        return "Línea 9", f"Tramo {match.group(1)}"
    raise ValueError(f"No se reconoce el proyecto en la hoja «{sheet.name}».")


def _report_date(sheet) -> str | None:
    text = " ".join(_text(sheet.cell_value(row, col)) for row in range(min(5, sheet.nrows)) for col in range(sheet.ncols))
    match = _DATE_RE.search(text)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%d/%m/%Y").date().isoformat()


def read_priority_file(path: str | Path) -> PriorityFile:
    """Devuelve OT cuya propia celda está resaltada en amarillo."""
    if xlrd is None:
        raise RuntimeError("Falta el lector de archivos Excel .xls. Reinstala Maximo Desktop.")
    path = Path(path)
    if path.suffix.lower() != ".xls":
        raise ValueError(f"{path.name} no es un archivo .xls.")
    try:
        book = xlrd.open_workbook(path, formatting_info=True)
    except Exception as exc:
        raise ValueError(f"No se pudo abrir {path.name}: {exc}") from exc
    if book.nsheets != 1:
        raise ValueError(f"{path.name} debe contener una sola hoja de prioridades.")
    sheet = book.sheet_by_index(0)
    project, section = _project_from_sheet(sheet)
    header_row = next(
        (row for row in range(sheet.nrows) if any(_normalize_heading(sheet.cell_value(row, col)) in {"no ot", "n o ot"} for col in range(sheet.ncols))),
        None,
    )
    if header_row is None:
        raise ValueError(f"No se encontró la columna «Nº OT» en {path.name}.")
    ot_column = next(
        col for col in range(sheet.ncols)
        if _normalize_heading(sheet.cell_value(header_row, col)) in {"no ot", "n o ot"}
    )
    items = []
    for row in range(header_row + 1, sheet.nrows):
        cell = sheet.cell(row, ot_column)
        background = book.xf_list[cell.xf_index].background
        colours = (_colour(book, background.pattern_colour_index), _colour(book, background.background_colour_index))
        ot = _text(cell.value)
        if ot and any(_is_yellow(colour) for colour in colours):
            items.append((ot, section))
    if not items:
        raise ValueError(f"No se encontraron OT prioritarias en amarillo en {path.name}.")
    return PriorityFile(path, project, section, _report_date(sheet), tuple(dict.fromkeys(items)))


def read_priority_files(paths: list[str | Path]) -> list[PriorityFile]:
    reports = [read_priority_file(path) for path in paths]
    seen = set()
    for report in reports:
        key = (report.project, report.section)
        if key in seen:
            label = f"{report.project} {report.section or ''}".strip()
            raise ValueError(f"Hay más de un archivo para {label}.")
        seen.add(key)
    return reports
