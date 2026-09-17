# maximo_client.py
import os
import time
import shutil
import pandas as pd
import logging
from pathlib import Path
from uuid import uuid4
from config import load_config, get_credentials
from app_paths import EDGE_PROFILE_DIR, create_unique_directory
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException

PAGE_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 180


def create_edge_profile(prefix: str) -> str:
    """Crea un perfil de Edge en la caché controlada por la aplicación."""
    EDGE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return str(create_unique_directory(EDGE_PROFILE_DIR, prefix))


def cleanup_edge_profile(profile_dir: str | Path) -> bool:
    """Elimina un perfil tras dar a Edge tiempo breve para terminar procesos hijos."""
    profile = Path(profile_dir)
    last_error = None
    for delay in (0.0, 0.5, 1.0):
        if delay:
            time.sleep(delay)
        try:
            shutil.rmtree(profile)
            logging.info("Perfil temporal de Edge eliminado: %s", profile)
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:
            last_error = exc
    logging.warning(
        "No se pudo eliminar el perfil temporal de Edge %s tras varios intentos: %s",
        profile,
        last_error,
    )
    return False


def wait_for(driver, condition, description, timeout=PAGE_TIMEOUT):
    """Espera solo hasta que se cumple la condición y registra el tiempo real."""
    started = time.monotonic()
    try:
        return WebDriverWait(
            driver, timeout, poll_frequency=0.25,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(condition)
    except TimeoutException as exc:
        raise TimeoutException(
            f"Tiempo agotado ({timeout}s): {description}"
        ) from exc
    finally:
        logging.info("Espera %s: %.2fs", description, time.monotonic() - started)


def setup_driver(headless=True, profile_dir=None, download_dir=None):
    cfg = load_config()
    logging.info("Inicializando Edge...")

    options = EdgeOptions()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-position=-32000,-32000")
    options.add_argument("--no-sandbox")

    # PERFIL AISLADO (clave para que quit() no mate otras ventanas)
    if profile_dir is None:
        profile_dir = create_edge_profile("maximo-edge-")
        logging.warning(
            f"setup_driver llamado sin profile_dir explícito. "
            f"Usando perfil temporal por defecto: {profile_dir}"
        )
    options.add_argument(f"--user-data-dir={profile_dir}")

    # Descarga por defecto
    target_dir = Path(download_dir or cfg.download_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    options.add_experimental_option("prefs", {
        "download.default_directory": str(target_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    })

    driver = webdriver.Edge(options=options)
    try:
        driver.set_page_load_timeout(PAGE_TIMEOUT)
    except Exception:
        driver.quit()
        raise
    logging.info("Navegador inicializado.")
    return driver


def login(driver, headless=True, username=None, password=None):
    cfg = load_config()
    if username is None or password is None:
        username, password = get_credentials()
    if not username or not password:
        logging.warning("No hay credenciales configuradas.")
        raise RuntimeError("No hay credenciales configuradas.")

    url = cfg.maximo_url

    max_attempts = 3
    for attempt in range(max_attempts):
        logging.info(f"Cargando página de login (intento {attempt+1}/{max_attempts})...")
        try:
            driver.get(url)
            wait_for(driver, EC.element_to_be_clickable((By.ID, "username")),
                     "formulario de login")
            wait_for(driver, EC.element_to_be_clickable((By.ID, "password")),
                     "campo de contraseña")
            break
        except TimeoutException:
            if attempt == max_attempts - 1:
                raise RuntimeError("No se pudo cargar la página de login.")


    logging.info("Ingresando credenciales...")
    driver.find_element(By.ID, "username").clear()
    driver.find_element(By.ID, "username").send_keys(username)
    driver.find_element(By.ID, "password").clear()
    driver.find_element(By.ID, "password").send_keys(password + Keys.RETURN)

    def logged_in(browser):
        for error_div in browser.find_elements(By.CLASS_NAME, "errorText"):
            if not error_div.is_displayed() or not error_div.text.strip():
                continue
            raise RuntimeError(
                "Login rechazado por Maximo, compruebe que sus credenciales son correctas y Máximo funciona correctamente."
            )
        return (
            EC.invisibility_of_element_located((By.ID, "username"))(browser)
            and browser.execute_script("return typeof sendEvent === 'function';")
        )

    wait_for(driver, logged_in, "inicio de sesión")
    logging.info("Login exitoso. Continuando...")


def verify_credentials(username: str, password: str) -> None:
    """Comprueba un login sin guardar credenciales ni modificar datos locales."""
    if not username.strip() or not password:
        raise ValueError("Introduce usuario y contraseña antes de comprobarlos.")

    profile_dir = create_edge_profile("maximo-edge-")
    driver = None
    try:
        logging.info("Comprobando credenciales de Maximo...")
        driver = setup_driver(headless=True, profile_dir=profile_dir)
        login(driver, headless=True, username=username.strip(), password=password)
        logging.info("Credenciales de Maximo verificadas correctamente.")
    finally:
        try:
            if driver is not None:
                driver.quit()
        finally:
            cleanup_edge_profile(profile_dir)


def open_workorders_app(driver, headless=True):
    logging.info("Accediendo a la sección de filtros...")
    driver.execute_script("sendEvent('changeapp','startcntr','WO_TR',3);")
    wait_for(driver, EC.element_to_be_clickable((By.ID, "mx38-lb4")),
             "listado de órdenes de trabajo")
    wait_for(driver, EC.element_to_be_clickable((By.ID, "quicksearch")),
             "búsqueda de órdenes de trabajo")
    if headless:
        driver.set_window_position(-32000, -32000)
    logging.info("Sección de filtros abierta.")


def read_workorder_status(driver, ot: str) -> str:
    """Busca una OT y devuelve el valor actual del campo de estado mx73-tb."""
    search_box = wait_for(
        driver, EC.element_to_be_clickable((By.ID, "quicksearch")),
        "búsqueda rápida de OT para conciliación",
    )
    search_box.clear()
    search_box.send_keys(ot)
    search_box.send_keys(Keys.RETURN)
    # El campo de estado de la ficha anterior puede permanecer visible durante
    # la navegación. Esperar solo a que mx73-tb sea visible permitiría leer
    # ese valor antiguo (especialmente en búsquedas consecutivas rápidas).
    target_ot = str(ot).strip()

    def current_workorder_is_loaded(browser):
        return browser.execute_script(
            """
            const target = arguments[0];
            return Array.from(document.querySelectorAll('input[id], textarea[id]'))
              .some(element => element.id !== 'quicksearch'
                && String(element.value || '').trim() === target);
            """,
            target_ot,
        )

    wait_for(
        driver,
        current_workorder_is_loaded,
        f"carga de la OT {target_ot} para conciliación",
    )
    status_field = wait_for(
        driver, EC.visibility_of_element_located((By.ID, "mx73-tb")),
        f"estado real de la OT {ot}",
    )
    value = status_field.get_attribute("value") or status_field.text
    return " ".join((value or "").split())


def apply_filter(driver):
    cfg = load_config()
    filters = cfg.filters
    logging.info("Aplicando filtros...")
    for field_id, value in filters.items():
        logging.info(f"Llenando campo {field_id} con {value}")
        field = driver.find_element(By.ID, field_id)
        field.clear()
        field.send_keys(value)
        time.sleep(2)
    field.send_keys(Keys.RETURN)
    time.sleep(10)
    logging.info("Filtros aplicados.")


def download_file(driver, download_dir, timeout=DOWNLOAD_TIMEOUT):
    logging.info("Descargando archivo...")
    folder = Path(download_dir)
    previous_files = set(folder.iterdir())
    download_button = wait_for(
        driver, EC.element_to_be_clickable((By.ID, "mx38-lb4")),
        "botón de descarga",
    )
    driver.execute_script("arguments[0].click();", download_button)
    observations = {}

    def completed(_):
        files = set(folder.iterdir()) - previous_files
        # Edge mantiene .crdownload hasta finalizar la descarga.
        if any(p.suffix.lower() in (".crdownload", ".tmp", ".part") for p in files):
            observations.clear()
            return False
        for path in sorted(files):
            if path.suffix.lower() != ".xls" or not path.is_file():
                continue
            try:
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                stable = observations.get(path) == signature
                observations[path] = signature
                if stat.st_size and stable:
                    with path.open("rb") as stream:
                        stream.read(1)
                    return str(path)
            except OSError:
                observations.pop(path, None)
        return False

    file_path = wait_for(driver, completed, "finalización de la descarga XLS", timeout)
    logging.info("Archivo descargado: %s", file_path)
    return file_path


def move_downloaded_file(file_path):
    """Archiva exclusivamente el archivo devuelto por download_file."""
    cfg = load_config()
    dest_folder = cfg.dest_folder
    os.makedirs(dest_folder, exist_ok=True)

    logging.info("Moviendo archivo descargado...")
    source = Path(file_path)
    new_location = Path(dest_folder) / f"maximo-export-{uuid4().hex}.xls"
    shutil.move(str(source), str(new_location))
    logging.info(f"Archivo movido a {new_location}")
    return str(new_location)


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

    logging.info("Archivo procesado.")
    return df


def open_ot(ot: str, headless: bool = False):
    """
    Abre Maximo, entra en la aplicación de OT favorita y busca una OT concreta.

    Para evitar que en la versión .exe (Nuitka) se cierre la ventana de Edge:
    - Si headless=False (visible), devolvemos (driver, profile_dir) y NO cerramos aquí.
      La GUI debe conservar la referencia y decidir cuándo cerrar/limpiar.
    - Si headless=True, cerramos y eliminamos el perfil temporal.
    """
    profile_dir = create_edge_profile("maximo-ot-")
    logging.info(f"OT {ot}: usando perfil temporal {profile_dir}")

    driver = None
    try:
        driver = setup_driver(headless=headless, profile_dir=profile_dir)
        login(driver, headless=headless)
        logging.info("Login OK, abriendo aplicación de órdenes de trabajo favoritas...")

        open_workorders_app(driver, headless=headless)

        try:
            search_box = wait_for(
                driver, EC.element_to_be_clickable((By.ID, "quicksearch")),
                "búsqueda rápida de OT",
            )
        except TimeoutException:
            logging.warning("No se encontró el cuadro de búsqueda rápida (id 'quicksearch')")
            raise RuntimeError(
                "No se encontró el cuadro de búsqueda rápida (id 'quicksearch') "
                "después de abrir la app de OT. Comprueba que la página se ha "
                "cargado correctamente o si ha cambiado el identificador."
            )

        search_box.clear()
        search_box.send_keys(ot)
        search_box.send_keys(Keys.RETURN)
        logging.info(f"OT {ot} enviada a Maximo.")

        if headless:
            if driver is not None:
                driver.quit()
            cleanup_edge_profile(profile_dir)
            logging.info(f"OT {ot}: navegador cerrado y perfil {profile_dir} eliminado (headless)")
            return None

        # Visible: devolvemos para que la GUI mantenga viva la sesión.
        return driver, profile_dir

    except Exception:
        logging.exception(f"Error al abrir OT en Maximo (OT={ot})")
        try:
            driver.quit()
        except Exception:
            pass
        cleanup_edge_profile(profile_dir)
        raise
