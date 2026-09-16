# updater.py
from maximo_client import (
    setup_driver,
    login,
    open_workorders_app,
    apply_filter,
    download_file,
    move_downloaded_file,
    process_html_table,
)
from db import update_database_from_df
from config import load_config
from pathlib import Path
import logging
import tempfile
import shutil
import time


def _timed(label, operation, *args, **kwargs):
    started = time.monotonic()
    try:
        return operation(*args, **kwargs)
    finally:
        logging.info("Etapa %s: %.2fs", label, time.monotonic() - started)


def run_update(headless=True):
    started = time.monotonic()
    profile_dir = tempfile.mkdtemp(prefix="maximo-update-")
    logging.info(f"Updater: usando perfil temporal {profile_dir}")
    driver = None
    download_dir = None
    try:
        # Carpeta vacía y exclusiva: nunca importar un XLS de otra ejecución.
        download_root = Path(load_config().download_dir).resolve()
        download_root.mkdir(parents=True, exist_ok=True)
        download_dir = tempfile.mkdtemp(prefix="maximo-download-", dir=download_root)
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
        return new_entries, updated_entries
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
            if download_dir is not None:
                shutil.rmtree(download_dir, ignore_errors=True)
            logging.info(f"Updater: navegador cerrado y perfil {profile_dir} eliminado")
            logging.info("Actualización total: %.2fs", time.monotonic() - started)

        logging.info("Navegador cerrado.")
