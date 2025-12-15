# updater.py
from maximo_client import (
    setup_driver,
    login,
    open_workorders_app,
    apply_filter,
    download_file,
    move_latest_file,
    process_html_table,
)
from db import update_database_from_df
import logging
import tempfile
import shutil


def run_update(headless=True):
    profile_dir = tempfile.mkdtemp(prefix="maximo-update-")
    logging.info(f"Updater: usando perfil temporal {profile_dir}")
    driver = None
    try:
        driver = setup_driver(headless=headless, profile_dir=profile_dir)
        login(driver)
        open_workorders_app(driver)
        apply_filter(driver)
        download_file(driver)
        file_path = move_latest_file()
        if not file_path:
            logging.warning("No se pudo mover el archivo descargado. Abortando actualización.")
            return 0, 0
        df = process_html_table(file_path)
        new_entries, updated_entries = update_database_from_df(df)
        logging.info("Actualización de base de datos completada.")
        return new_entries, updated_entries
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
            logging.info(f"Updater: navegador cerrado y perfil {profile_dir} eliminado")

        logging.info("Navegador cerrado.")
