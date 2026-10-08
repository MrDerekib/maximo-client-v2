# maximo_client.py
import os
import json
import time
import shutil
import threading
import pandas as pd
import logging
from pathlib import Path
from uuid import uuid4
from config import load_config, get_credentials
from app_paths import EDGE_PROFILE_DIR, PROGRAM_DIR, create_unique_directory
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import WebDriverException

PAGE_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 180
REPAIR_REPORT_STATUSES = {"ISSUE", "CLOSE", "DAR SALIDA"}


class ExportDownloadTimeout(TimeoutException):
    """Maximo did not deliver a complete XLS in the isolated download folder."""


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


def wait_for(driver, condition, description, timeout=PAGE_TIMEOUT, cancel_event=None):
    """Espera solo hasta que se cumple la condición y registra el tiempo real."""
    started = time.monotonic()

    def checked_condition(browser):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Lectura de información ampliada cancelada.")
        return condition(browser)

    try:
        return WebDriverWait(
            driver, timeout, poll_frequency=0.25,
            ignored_exceptions=(StaleElementReferenceException,),
        ).until(checked_condition)
    except TimeoutException as exc:
        raise TimeoutException(
            f"Tiempo agotado ({timeout}s): {description}"
        ) from exc
    finally:
        logging.info("Espera %s: %.2fs", description, time.monotonic() - started)


def _click_pending_repair_lookup(driver) -> bool:
    """Complete a Maximo YORN lookup with a trusted Selenium click when requested."""
    option_id = driver.execute_script(
        "return document.documentElement?.dataset.maximoNativeLookupClick || '';"
    )
    if not option_id:
        return False
    if not (option_id.startswith("lookup_page") and "_tdrow_" in option_id and
            option_id.endswith("_ttxt-lb[R:0]")):
        driver.execute_script("delete document.documentElement.dataset.maximoNativeLookupClick;")
        logging.warning("Maximo solicitó un click nativo con un identificador no permitido: %s", option_id)
        return False

    options = driver.find_elements(By.ID, option_id)
    if not options or not options[0].is_displayed():
        return False
    options[0].click()
    driver.execute_script(
        "if (document.documentElement.dataset.maximoNativeLookupClick === arguments[0]) "
        "delete document.documentElement.dataset.maximoNativeLookupClick;",
        option_id,
    )
    logging.info("Selección de lookup Maximo confirmada con click WebDriver: %s", option_id)
    return True


def _start_repair_lookup_clicker(driver) -> None:
    """Watch for a lookup request from the extension and click it through WebDriver."""
    if getattr(driver, "_maximo_repair_lookup_clicker", False):
        return
    driver._maximo_repair_lookup_clicker = True

    def watch():
        while True:
            time.sleep(0.5)
            try:
                _click_pending_repair_lookup(driver)
            except WebDriverException:
                # A closed Edge session ends the watcher; a transient stale element
                # is retried on the next pass while the lookup remains open.
                service = getattr(driver, "service", None)
                if not getattr(driver, "session_id", None) or (
                    service is not None and not service.is_connectable()
                ):
                    return
                logging.debug("Click nativo del lookup Maximo pendiente de reintento", exc_info=True)
            except Exception:
                logging.debug("No se pudo atender el lookup Maximo", exc_info=True)

    threading.Thread(target=watch, name="maximo-repair-lookup", daemon=True).start()


def visible_ot_print_preferences():
    """Initial print preview choices for each disposable interactive OT profile."""
    app_state = {
        "version": 2,
        "recentDestinations": [],
        "isColorEnabled": False,
        "isHeaderFooterEnabled": False,
    }
    return {"appState": json.dumps(app_state, separators=(",", ":"))}


def default_printer_name() -> str:
    """Read the Windows default without changing system printer settings."""
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        return QPrinterInfo.defaultPrinterName().strip()
    except Exception:
        logging.warning("No se pudo consultar la impresora predeterminada", exc_info=True)
        return ""


def _should_close_after_direct_print(requested: bool, headless: bool, printer_name: str) -> bool:
    return bool(requested and not headless and printer_name)


def setup_driver(headless=True, profile_dir=None, download_dir=None, force_repair_extension=False):
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
    if not headless and (force_repair_extension or getattr(cfg, "repair_extension_enabled", False)):
        extension = PROGRAM_DIR / "browser_extension"
        if not (extension / "manifest.json").is_file():
            raise FileNotFoundError(f"No se encuentra la extensión del parte: {extension}")
        options.add_argument(f"--load-extension={extension}")
        if getattr(cfg, "repair_print_mode", "dialog") == "direct":
            printer = default_printer_name()
            if printer:
                options.add_argument("--kiosk-printing")
                logging.info("Impresión directa del parte: impresora predeterminada %s", printer)
            else:
                logging.warning("No hay impresora predeterminada; se mostrará el diálogo de impresión")

    # Descarga por defecto
    target_dir = Path(download_dir or cfg.download_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    prefs = {
        "download.default_directory": str(target_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    if not headless:
        prefs["printing.print_preview_sticky_settings"] = visible_ot_print_preferences()
    options.add_experimental_option("prefs", prefs)

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
    # El estado de la ficha anterior puede permanecer visible durante la
    # navegación. Primero se verifica el campo de OT de la ficha (mx45-tb)
    # para no leer mx73-tb hasta que Maximo haya cargado la OT solicitada.
    target_ot = str(ot).strip()

    def current_workorder_is_loaded(browser):
        current_ot = browser.find_element(By.ID, "mx45-tb").get_attribute("value")
        return str(current_ot or "").strip() == target_ot

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


def read_workorder_fault_description(driver, ot: str, cancel_event=None) -> str:
    """Busca una OT y devuelve la descripción de avería del campo mx46-tb."""
    search_box = wait_for(
        driver, EC.element_to_be_clickable((By.ID, "quicksearch")),
        "búsqueda rápida de OT para descripción de avería", timeout=20, cancel_event=cancel_event,
    )
    search_box.clear()
    search_box.send_keys(ot)
    search_box.send_keys(Keys.RETURN)
    target_ot = str(ot).strip()

    def current_workorder_is_loaded(browser):
        current_ot = browser.find_element(By.ID, "mx45-tb").get_attribute("value")
        return str(current_ot or "").strip() == target_ot

    wait_for(
        driver,
        current_workorder_is_loaded,
        f"carga de la OT {target_ot} para descripción de avería", timeout=20, cancel_event=cancel_event,
    )
    fault_field = wait_for(
        driver, EC.visibility_of_element_located((By.ID, "mx46-tb")),
        f"descripción de avería de la OT {ot}", timeout=15, cancel_event=cancel_event,
    )
    value = fault_field.get_attribute("value") or fault_field.text
    return " ".join((value or "").split())


def read_workorder_detailed_description(driver, ot: str, already_loaded: bool = False, cancel_event=None) -> tuple[str, str]:
    """Read the long-description editor without accepting or changing the OT."""
    if not already_loaded:
        search_box = wait_for(driver, EC.element_to_be_clickable((By.ID, "quicksearch")),
                              "búsqueda rápida de OT para descripción detallada", timeout=20,
                              cancel_event=cancel_event)
        search_box.clear()
        search_box.send_keys(str(ot).strip())
        search_box.send_keys(Keys.RETURN)
        wait_for(driver, lambda browser: (
            browser.find_element(By.ID, "mx45-tb").get_attribute("value") or ""
        ).strip() == str(ot).strip(), f"carga de la OT {ot} para descripción detallada",
                 timeout=20, cancel_event=cancel_event)

    icons = driver.find_elements(By.ID, "mx45-img2")
    if not icons or "img_longdescription_on" not in (icons[0].get_attribute("source") or ""):
        return "", ""

    icons[0].click()
    try:
        wait_for(driver, EC.visibility_of_element_located((By.ID, "longdesc_dialog-dialog_inner")),
                 f"diálogo de descripción detallada de la OT {ot}", timeout=12,
                 cancel_event=cancel_event)
        def editor_content(browser):
            return browser.execute_script("""
                const frame = document.getElementById('mx253-rte_iframe');
                const body = frame?.contentDocument?.getElementById('dijitEditorBody');
                return body ? {text: body.innerText || '', html: body.innerHTML || ''} : false;
            """)
        content = wait_for(driver, editor_content, f"contenido detallado de la OT {ot}",
                           timeout=12, cancel_event=cancel_event)
        from detailed_description import sanitize_detail_html
        text = (content["text"] or "").strip()
        return text, sanitize_detail_html(content["html"]) if text else ""
    finally:
        # Cancel closes the read-only editor without sending its contents to Maximo.
        cancel = driver.find_elements(By.ID, "mx260-pb")
        if not cancel:
            raise RuntimeError(
                f"El diálogo detallado de la OT {ot} quedó incompleto; "
                "se reiniciará la vista antes de la siguiente OT."
            )
        cancel[0].click()
        wait_for(driver, EC.invisibility_of_element_located((By.ID, "longdesc_dialog-dialog_inner")),
                 "cierre del diálogo de descripción detallada", timeout=10,
                 cancel_event=cancel_event)


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
    clicked_at = time.monotonic()

    def completed(_):
        files = set(folder.iterdir()) - previous_files
        # A completed XLS can coexist with a stale partial file. Check it first.
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
        if not files and time.monotonic() - clicked_at >= min(60, timeout):
            raise ExportDownloadTimeout("Maximo no inició la descarga XLS en 60 segundos.")
        return False

    try:
        file_path = wait_for(driver, completed, "finalización de la descarga XLS", timeout)
    except TimeoutException as exc:
        state = []
        for path in sorted(set(folder.iterdir()) - previous_files):
            try:
                state.append(f"{path.name} ({path.stat().st_size} bytes)")
            except OSError:
                state.append(f"{path.name} (no accesible)")
        logging.warning("Descarga XLS incompleta; carpeta temporal: %s", ", ".join(state) or "sin archivos")
        raise ExportDownloadTimeout(str(exc)) from exc
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


def open_ot(
    ot: str, headless: bool = False, report_action: str | None = None,
    close_after_direct_print: bool = False,
):
    """
    Abre Maximo, entra en la aplicación de OT favorita y busca una OT concreta.

    Para evitar que en la versión .exe (Nuitka) se cierre la ventana de Edge:
    - Si headless=False (visible), devolvemos (driver, profile_dir) y NO cerramos aquí.
      La GUI debe conservar la referencia y decidir cuándo cerrar/limpiar.
    - Si headless=True, cerramos y eliminamos el perfil temporal.
    """
    if report_action not in (None, "print", "pdf") or (report_action and headless):
        raise ValueError("La acción del parte requiere una ventana visible y un formato válido.")
    cfg = load_config()
    repair_extension_loaded = not headless and (
        report_action is not None or getattr(cfg, "repair_extension_enabled", False)
    )
    profile_dir = create_edge_profile("maximo-ot-")
    logging.info(f"OT {ot}: usando perfil temporal {profile_dir}")

    driver = None
    try:
        options = {"force_repair_extension": True} if report_action else {}
        driver = setup_driver(headless=headless, profile_dir=profile_dir, **options)
        close_after_direct_print = _should_close_after_direct_print(
            close_after_direct_print, headless,
            default_printer_name() if close_after_direct_print and not headless else "",
        )
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

        if repair_extension_loaded:
            wait_for(
                driver,
                lambda browser: (
                    element if str((element := browser.find_element(By.ID, "mx45-tb")).get_attribute("value") or "").strip()
                    == str(ot).strip() else False
                ),
                f"carga de la OT {ot} para activar la selección nativa del lookup",
                timeout=45,
            )
        if report_action:
            start_repair_report(
                driver, ot, report_action,
                close_after_direct_print=close_after_direct_print,
            )
        elif close_after_direct_print:
            wait_for(
                driver,
                lambda browser: (
                    element if str((element := browser.find_element(By.ID, "mx45-tb")).get_attribute("value") or "").strip()
                    == str(ot).strip() else False
                ),
                f"carga de la OT {ot} para aplicar las preferencias de impresión",
                timeout=45,
            )
            driver.execute_script(
                "document.documentElement.dataset.maximoCloseReportTabs = 'true';"
            )

        if repair_extension_loaded:
            _start_repair_lookup_clicker(driver)

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


def start_repair_report(
    driver, ot: str, action: str, close_after_direct_print: bool = False,
):
    """Inicia el flujo de la extensión solo cuando la ficha solicitada está lista."""
    if action not in ("print", "pdf"):
        raise ValueError("Acción de parte desconocida.")

    wait_for(
        driver,
        lambda browser: (
            element if str((element := browser.find_element(By.ID, "mx45-tb")).get_attribute("value") or "").strip()
            == str(ot).strip() else False
        ),
        f"carga de la OT {ot} para el parte", timeout=45,
    )
    status = str(driver.find_element(By.ID, "mx73-tb").get_attribute("value") or "").strip().upper()
    if status not in REPAIR_REPORT_STATUSES:
        raise RuntimeError(f"La OT {ot} no admite parte en su estado actual ({status or 'desconocido'}).")

    def ready(browser):
        try:
            button = browser.find_element(By.ID, "maximo-desktop-print-part")
            return button if button.is_displayed() and button.is_enabled() else False
        except Exception:
            return False

    button = wait_for(driver, ready, f"botón de parte para la OT {ot}", timeout=20)
    driver.execute_script(
        "arguments[0].dataset.maximoReportAction = arguments[1]; "
        "arguments[0].dataset.maximoCloseReportTabs = arguments[2] ? 'true' : 'false'; "
        "arguments[0].click();",
        button, action, bool(close_after_direct_print and action == "print"),
    )
