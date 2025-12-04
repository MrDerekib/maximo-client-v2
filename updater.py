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


def run_update(headless=True):
    """
    Lanza una actualización completa de la BD:
    - Abre navegador
    - Login
    - Accede a WO
    - Aplica filtros
    - Descarga XLS
    - Procesa tabla
    - Actualiza SQLite
    """
    driver = setup_driver(headless=headless)
    try:
        login(driver)
        open_workorders_app(driver)
        apply_filter(driver)
        download_file(driver)
        file_path = move_latest_file()
        if not file_path:
            print("No se pudo mover el archivo descargado. Abortando actualización.")
            return
        df = process_html_table(file_path)
        update_database_from_df(df)
        print("Actualización de base de datos completada.")
    finally:
        driver.quit()
        print("Navegador cerrado.")
