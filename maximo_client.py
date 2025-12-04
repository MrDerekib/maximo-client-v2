# maximo_client.py
import os
import time
import shutil
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions

from config import load_config, get_credentials


def setup_driver(headless=True):
    cfg = load_config()
    print("Inicializando Edge...")

    options = EdgeOptions()
    if headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # Descarga por defecto
    options.add_argument(f"--download-default-directory={cfg.download_dir}")

    driver = webdriver.Edge(options=options)
    print("Navegador inicializado.")
    return driver


def login(driver):
    cfg = load_config()
    username, password = get_credentials()
    if not username or not password:
        raise RuntimeError("No hay credenciales configuradas.")

    url = cfg.maximo_url

    max_attempts = 3
    for attempt in range(max_attempts):
        print(f"Cargando página de login (intento {attempt+1}/{max_attempts})...")
        driver.get(url)
        time.sleep(6)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "Maximo" in driver.title and len(body_text) > 50:
            break
        if attempt == max_attempts - 1:
            raise RuntimeError("No se pudo cargar la página de login.")

    print("Ingresando credenciales...")
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").send_keys(password + Keys.RETURN)
    time.sleep(10)

    # Podrías añadir aquí la detección del error BMXAA7901E, como en tu script


def open_workorders_app(driver):
    print("Accediendo a la sección de filtros...")
    time.sleep(10)
    driver.find_element(By.ID, "FavoriteApp_WO_TR").click()
    time.sleep(10)
    print("Sección de filtros abierta.")


def apply_filter(driver):
    cfg = load_config()
    filters = cfg.filters
    print("Aplicando filtros...")
    for field_id, value in filters.items():
        print(f"Llenando campo {field_id} con {value}")
        field = driver.find_element(By.ID, field_id)
        field.clear()
        field.send_keys(value)
        time.sleep(1)
    field.send_keys(Keys.RETURN)
    time.sleep(10)
    print("Filtros aplicados.")


def download_file(driver):
    print("Descargando archivo...")
    time.sleep(10)
    download_button = driver.find_element(By.ID, "mx38-lb4")
    driver.execute_script("arguments[0].click();", download_button)
    time.sleep(45)
    print("Archivo descargado.")


def move_latest_file():
    cfg = load_config()
    download_dir = cfg.download_dir
    dest_folder = cfg.dest_folder
    os.makedirs(dest_folder, exist_ok=True)

    print("Moviendo archivo descargado...")
    files = sorted(
        [f for f in os.listdir(download_dir) if f.endswith(".xls")],
        key=lambda x: os.path.getctime(os.path.join(download_dir, x)),
        reverse=True
    )
    if not files:
        print("No se encontró archivo .xls en la carpeta de descargas.")
        return None

    latest_file = os.path.join(download_dir, files[0])
    new_location = os.path.join(dest_folder, files[0])
    shutil.move(latest_file, new_location)
    print(f"Archivo movido a {new_location}")
    return new_location


def process_html_table(file_path):
    print(f"Procesando archivo: {file_path}")
    dfs = pd.read_html(file_path)

    df = dfs[0].iloc[1:, [0, 12, 15, 2, 3, 9, 5, 13]].copy()
    df.columns = ["OT", "Descripción", "Nº de serie", "Fecha", "Cliente",
                  "Tipo de trabajo", "Seguimiento", "Planta"]
    df["Fecha"] = pd.to_datetime(df["Fecha"],
                                 format="%d/%m/%y %H:%M:%S",
                                 errors="coerce").dt.strftime("%Y-%m-%d")
    df["Planta"] = df["Planta"].fillna("").astype(str).str.strip()
    df = df.where(pd.notnull(df), None)

    # Clientes únicos (para el combo de la GUI)
    unique_clients = [c.replace(" ", " ").strip() for c in df["Cliente"].dropna().unique().tolist()]
    with open("clientes_unicos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(unique_clients))

    print("Archivo procesado.")
    return df


def open_ot(ot: str, headless=False):
    """
    Abre Maximo y busca una OT concreta (para doble click en la GUI).
    Equivalente a tu open_maximo actual.
    """
    driver = setup_driver(headless=headless)
    try:
        login(driver)
        print("Login OK, accediendo a búsqueda rápida...")
        time.sleep(6)
        search_box = driver.find_element(By.ID, "quicksearch")
        search_box.send_keys(ot)
        search_box.send_keys(Keys.RETURN)
        print("OT enviada a Maximo.")
        # Aquí ya dejas al usuario en la pantalla de la OT.
    except Exception as e:
        print(f"Error al abrir OT en Maximo: {e}")
        driver.quit()
        raise
