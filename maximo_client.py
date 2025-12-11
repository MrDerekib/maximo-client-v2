# maximo_client.py
import os
import time
import shutil
import pandas as pd
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException


from config import load_config, get_credentials


def setup_driver(headless=True):
    cfg = load_config()
    logging.info("Inicializando Edge...")

    options = EdgeOptions()
    if headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # Descarga por defecto
    options.add_argument(f"--download-default-directory={cfg.download_dir}")

    driver = webdriver.Edge(options=options)
    logging.info("Navegador inicializado.")
    return driver


def login(driver):
    cfg = load_config()
    username, password = get_credentials()
    if not username or not password:
        logging.warning("No hay credenciales configuradas.")
        raise RuntimeError("No hay credenciales configuradas.")

    url = cfg.maximo_url

    max_attempts = 3
    for attempt in range(max_attempts):
        logging.info(f"Cargando página de login (intento {attempt+1}/{max_attempts})...")
        driver.get(url)
        time.sleep(6)
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if "Maximo" in driver.title and len(body_text) > 50:
            break
        if attempt == max_attempts - 1:
            logging.warning("No se pudo cargar la página de login")
            raise RuntimeError("No se pudo cargar la página de login.")


    logging.info("Ingresando credenciales...")
    driver.find_element(By.ID, "username").clear()
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").clear()
    driver.find_element(By.ID, "password").send_keys(password + Keys.RETURN)

    # Damos unos segundos para que Maximo muestre el posible mensaje de error
    time.sleep(5)

    # Comprobar el mensaje de error BMXAA7901E en <div class="errorText">
    try:
        error_div = driver.find_element(By.CLASS_NAME, "errorText")
        error_message = error_div.text.strip() if error_div else ""
        if "BMXAA7901E" in error_message:
            # Este es exactamente el mensaje de tu captura:
            # "BMXAA7901E - No se puede iniciar sesión en este momento..."
            raise RuntimeError(
                "Login rechazado por Maximo, compruebe que sus credenciales son correctas y Máximo funciona correctamente."
            )
    except NoSuchElementException:
        # No hay div de error -> asumimos que el login ha ido bien
        logging.info("Login exitoso. Continuando...")


def open_workorders_app(driver):
    logging.info("Accediendo a la sección de filtros...")
    time.sleep(10)
    driver.find_element(By.ID, "FavoriteApp_WO_TR").click()
    time.sleep(10)
    logging.info("Sección de filtros abierta.")


def apply_filter(driver):
    cfg = load_config()
    filters = cfg.filters
    logging.info("Aplicando filtros...")
    for field_id, value in filters.items():
        logging.info(f"Llenando campo {field_id} con {value}")
        field = driver.find_element(By.ID, field_id)
        field.clear()
        field.send_keys(value)
        time.sleep(1)
    field.send_keys(Keys.RETURN)
    time.sleep(10)
    logging.info("Filtros aplicados.")


def download_file(driver):
    logging.info("Descargando archivo...")
    time.sleep(10)
    download_button = driver.find_element(By.ID, "mx38-lb4")
    driver.execute_script("arguments[0].click();", download_button)
    time.sleep(45)
    logging.info("Archivo descargado.")


def move_latest_file():
    cfg = load_config()
    download_dir = cfg.download_dir
    dest_folder = cfg.dest_folder
    os.makedirs(dest_folder, exist_ok=True)

    logging.info("Moviendo archivo descargado...")
    files = sorted(
        [f for f in os.listdir(download_dir) if f.endswith(".xls")],
        key=lambda x: os.path.getctime(os.path.join(download_dir, x)),
        reverse=True
    )
    if not files:
        logging.warning("No se encontró archivo .xls en la carpeta de descargas.")
        return None

    latest_file = os.path.join(download_dir, files[0])
    new_location = os.path.join(dest_folder, files[0])
    shutil.move(latest_file, new_location)
    logging.info(f"Archivo movido a {new_location}")
    return new_location


def process_html_table(file_path):
    logging.info(f"Procesando archivo: {file_path}")
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

    logging.info("Archivo procesado.")
    return df


def open_ot(ot: str, headless=False):
    """
    Abre Maximo, entra en la aplicación de OT favorita y busca una OT concreta.
    """
    driver = setup_driver(headless=headless)
    try:
        # Login
        login(driver)
        logging.info("Login OK, abriendo aplicación de órdenes de trabajo favoritas...")

        # Ir a la app de OT, igual que en el flujo de actualización de BD
        open_workorders_app(driver)

        # Ahora sí, estamos en la pantalla donde existe quicksearch
        wait = WebDriverWait(driver, 30)
        try:
            search_box = wait.until(
                EC.presence_of_element_located((By.ID, "quicksearch"))
            )
        except TimeoutException:
            logging.warning("No se encontró el cuadro de búsqueda rápida (id 'quicksearch')")
            raise RuntimeError(
                "No se encontró el cuadro de búsqueda rápida (id 'quicksearch') "
                "después de abrir la app de OT. Comprueba que la página se ha "
                "cargado correctamente o si ha cambiado el identificador."
            )

        # Por si viniera con texto pre-rellenado
        search_box.clear()
        search_box.send_keys(ot)
        search_box.send_keys(Keys.RETURN)
        logging.info(f"OT {ot} enviada a Maximo.")

        # IMPORTANTE:
        # - Si headless=True -> no tiene sentido dejar la ventana abierta
        # - Si headless=False -> dejamos la ventana para que el usuario trabaje
        if headless:
            driver.quit()

    except Exception as e:
        print(f"Error al abrir OT en Maximo: {e}")
        logging.warning("Error al abrir OT en Maximo.")
        try:
            driver.quit()
        except Exception:
            pass
        # Propagamos para que la GUI muestre el messagebox
        raise

