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

def run_update(headless=True):
    """
    Lanza una actualización completa de la BD y devuelve (new_entries, updated_entries).
    """
    driver = setup_driver(headless=headless)
    try:
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
        driver.quit()
        logging.info("Navegador cerrado.")
