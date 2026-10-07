# updater.py
from maximo_client import (
    setup_driver,
    create_edge_profile,
    cleanup_edge_profile,
    login,
    open_workorders_app,
    read_workorder_status,
    read_workorder_fault_description,
    read_workorder_detailed_description,
    apply_filter,
    download_file,
    ExportDownloadTimeout,
    move_downloaded_file,
    process_html_table,
)
from db import (
    apply_fault_description, apply_reconciled_status, fault_description_candidates,
    mark_fault_description_attempt, inactive_tracking_candidates, update_database_from_df,
    detailed_description_candidates, apply_detailed_description, mark_detailed_description_attempt,
)
from config import load_config
from maintenance import cleanup_exports
from pathlib import Path
from app_paths import create_unique_directory
import logging
from itertools import zip_longest
import shutil
import time

INACTIVE_RECONCILIATION_LIMIT = 5
INACTIVE_RECONCILIATION_HOURS = 24
FAULT_DESCRIPTION_LIMIT = 5
FAULT_DESCRIPTION_HOURS = 24


def _timed(label, operation, *args, **kwargs):
    started = time.monotonic()
    try:
        return operation(*args, **kwargs)
    finally:
        logging.info("Etapa %s: %.2fs", label, time.monotonic() - started)


def _download_export_once(headless, download_root, attempt):
    """Use a fresh Edge profile for each read-only export attempt."""
    profile_dir = create_edge_profile("maximo-update-")
    driver = None
    download_dir = None
    try:
        download_dir = str(create_unique_directory(download_root, "maximo-download-"))
        logging.info("Descarga XLS: intento %d/2; perfil %s", attempt, profile_dir)
        driver = _timed("abrir Edge", setup_driver, headless=headless,
                        profile_dir=profile_dir, download_dir=download_dir)
        _timed("login", login, driver, headless=headless)
        _timed("abrir listado", open_workorders_app, driver, headless=headless)
        downloaded = _timed("descargar XLS", download_file, driver, download_dir)
        return move_downloaded_file(downloaded)
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            cleanup_edge_profile(profile_dir)
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)
            logging.info("Descarga XLS: intento %d/2 cerrado y limpiado.", attempt)


def run_update(headless=True):
    started = time.monotonic()
    try:
        download_root = Path(load_config().download_dir).resolve()
        download_root.mkdir(parents=True, exist_ok=True)
        for attempt in (1, 2):
            try:
                file_path = _download_export_once(headless, download_root, attempt)
                break
            except ExportDownloadTimeout:
                if attempt == 2:
                    raise
                logging.warning("La descarga XLS falló; se reintentará con una sesión nueva de Edge.")
        df = _timed("procesar XLS", process_html_table, file_path)
        new_entries, updated_entries = _timed("sincronizar BD", update_database_from_df, df)
        logging.info("Actualización de base de datos completada.")
        cleanup_exports(Path(file_path).parent)
        return new_entries, updated_entries
    finally:
        logging.info("Actualización total: %.2fs", time.monotonic() - started)


def reconcile_inactive_tracking(limit=INACTIVE_RECONCILIATION_LIMIT,
                                minimum_age_hours=INACTIVE_RECONCILIATION_HOURS):
    """Contrasta en Maximo OT históricas con seguimiento que requiere revisión."""
    candidates = inactive_tracking_candidates(limit, minimum_age_hours)
    if not candidates:
        logging.info("Conciliación de OT inactivas: no hay candidatas pendientes.")
        return 0

    profile_dir = create_edge_profile("maximo-reconcile-")
    driver = None
    changed = 0
    try:
        logging.info("Conciliación de OT inactivas: revisando hasta %d OT.", len(candidates))
        driver = setup_driver(headless=True, profile_dir=profile_dir)
        login(driver, headless=True)
        open_workorders_app(driver, headless=True)
        for ot, previous_status in candidates:
            try:
                status = read_workorder_status(driver, ot)
                if apply_reconciled_status(ot, status):
                    if status and status != previous_status:
                        changed += 1
                        logging.info(
                            "OT inactiva %s: seguimiento %s -> %s",
                            ot, previous_status, status,
                        )
                    elif status:
                        logging.info(
                            "OT inactiva %s: estado confirmado sin cambios (%s)",
                            ot, status,
                        )
                    else:
                        logging.warning(
                            "OT inactiva %s: Maximo no devolvió un estado; se reintentará en 24 h.",
                            ot,
                        )
            except Exception as exc:
                logging.warning("No se pudo conciliar la OT inactiva %s: %s", ot, exc)
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            cleanup_edge_profile(profile_dir)
    logging.info("Conciliación de OT inactivas completada: %d seguimientos actualizados.", changed)
    return changed


def enrich_fault_descriptions(limit=FAULT_DESCRIPTION_LIMIT,
                              minimum_age_hours=FAULT_DESCRIPTION_HOURS,
                              include_fault=True, include_detail=False, cancel_event=None):
    """Read optional fault and full details in the same Maximo session/OT visit."""
    faults = (fault_description_candidates(limit=None, minimum_age_hours=minimum_age_hours)
              if include_fault else [])
    details = (detailed_description_candidates(limit=None, minimum_age_hours=minimum_age_hours)
               if include_detail else [])
    candidates = list(dict.fromkeys(
        ot for pair in zip_longest(faults, details) for ot in pair if ot is not None
    ))
    if limit is not None:
        candidates = candidates[:limit]
    if not candidates:
        logging.info("Información ampliada: no hay OT activas pendientes.")
        return 0

    fault_set, detail_set = set(faults), set(details)
    profile_dir = create_edge_profile("maximo-fault-")
    driver = None
    completed = 0
    try:
        logging.info("Información ampliada: revisando hasta %d OT activas.", len(candidates))
        driver = setup_driver(headless=True, profile_dir=profile_dir)
        login(driver, headless=True)
        open_workorders_app(driver, headless=True)
        # A stuck refresh must not block cancellation or app shutdown indefinitely.
        driver.set_page_load_timeout(20)
        reset_view = False
        detail_failures = 0
        for ot in candidates:
            if cancel_event is not None and cancel_event.is_set():
                break
            if reset_view:
                # Maximo leaves the Dojo long-description widget in a stale
                # state after closing it. Refresh before the next OT so the
                # editor and Cancel button belong to the new record.
                driver.refresh()
                open_workorders_app(driver, headless=True)
                reset_view = False
            loaded = False
            if ot in fault_set:
                try:
                    description = read_workorder_fault_description(driver, ot, cancel_event=cancel_event)
                    loaded = True
                    if apply_fault_description(ot, description):
                        completed += 1
                except Exception as exc:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    mark_fault_description_attempt(ot)
                    logging.warning("No se pudo leer la avería de la OT %s: %s", ot, exc)
            if cancel_event is not None and cancel_event.is_set():
                break
            if ot in detail_set:
                try:
                    text, safe_html = read_workorder_detailed_description(
                        driver, ot, already_loaded=loaded, cancel_event=cancel_event,
                    )
                    # A complete read is committed before honoring a late cancel.
                    if apply_detailed_description(ot, text, safe_html):
                        completed += 1
                    detail_failures = 0
                    if cancel_event is not None and cancel_event.is_set():
                        break
                except Exception as exc:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    mark_detailed_description_attempt(ot)
                    detail_failures += 1
                    logging.warning("No se pudo leer la descripción detallada de la OT %s: %s", ot, exc)
                    if detail_failures >= 3:
                        raise RuntimeError(
                            "La lectura detallada se detuvo tras 3 fallos consecutivos. "
                            "Las OT restantes siguen pendientes para otro intento."
                        ) from exc
                finally:
                    reset_view = True
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            cleanup_edge_profile(profile_dir)
    logging.info("Información ampliada completada: %d campos leídos.", completed)
    return completed
