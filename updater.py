# updater.py
from maximo_client import (
    setup_driver,
    create_edge_profile,
    cleanup_edge_profile,
    login,
    open_workorders_app,
    read_workorder_status,
    apply_filter,
    download_file,
    move_downloaded_file,
    process_html_table,
)
from db import apply_reconciled_status, inactive_tracking_candidates, update_database_from_df
from config import load_config
from maintenance import cleanup_exports
from pathlib import Path
from app_paths import create_unique_directory
import logging
import shutil
import time

INACTIVE_RECONCILIATION_LIMIT = 5
INACTIVE_RECONCILIATION_HOURS = 24


def _timed(label, operation, *args, **kwargs):
    started = time.monotonic()
    try:
        return operation(*args, **kwargs)
    finally:
        logging.info("Etapa %s: %.2fs", label, time.monotonic() - started)


def run_update(headless=True):
    started = time.monotonic()
    profile_dir = create_edge_profile("maximo-update-")
    logging.info(f"Updater: usando perfil temporal {profile_dir}")
    driver = None
    download_dir = None
    try:
        # Carpeta vacía y exclusiva: nunca importar un XLS de otra ejecución.
        download_root = Path(load_config().download_dir).resolve()
        download_root.mkdir(parents=True, exist_ok=True)
        download_dir = str(create_unique_directory(download_root, "maximo-download-"))
        driver = _timed("abrir Edge", setup_driver, headless=headless,
                        profile_dir=profile_dir, download_dir=download_dir)
        _timed("login", login, driver, headless=headless)
        _timed("abrir listado", open_workorders_app, driver, headless=headless)
        ##apply_filter(driver)
        downloaded = _timed("descargar XLS", download_file, driver, download_dir)
        file_path = move_downloaded_file(downloaded)
        df = _timed("procesar XLS", process_html_table, file_path)
        new_entries, updated_entries = _timed("sincronizar BD", update_database_from_df, df)
        logging.info("Actualización de base de datos completada.")
        cleanup_exports(Path(file_path).parent)
        return new_entries, updated_entries
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            cleanup_edge_profile(profile_dir)
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)
            logging.info(f"Updater: navegador cerrado y perfil {profile_dir} eliminado")
            logging.info("Actualización total: %.2fs", time.monotonic() - started)

        logging.info("Navegador cerrado.")


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
