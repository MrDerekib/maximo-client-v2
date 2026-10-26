"""Inicio explícito de OT con el flujo RFN-70, mediante controles de Maximo."""
import logging
import time
import unicodedata
from urllib.parse import urlsplit

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


def normalized(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split()).strip(" *:").casefold()


VISIBLE_DIALOGS_SCRIPT = """
    const visibleDialogs = [...document.querySelectorAll('[role=dialog], #warndiv')].filter(root => {
      // Maximo keeps a zero-width warning shell in the navigation bar even
      // when no warning is open. Its inner table is the visible popup.
      const panel = root.id === 'warndiv' ? root.querySelector('#warndiv_inner') || root : root;
      const rect = panel.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return false;
      for (let node = panel; node; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (node.getAttribute('aria-hidden') === 'true' || style.display === 'none' ||
            ['hidden', 'collapse'].includes(style.visibility) || Number(style.opacity) === 0) return false;
      }
      return true;
    });
"""


class WorkorderStarter:
    route_dialog_timeout = 8

    def __init__(self, driver, ot, progress=None, timeout=30):
        self.driver = driver
        self.ot = str(ot).strip()
        self.progress = progress or (lambda message: None)
        self.timeout = timeout

    def wait(self, condition, description):
        try:
            return WebDriverWait(self.driver, self.timeout, poll_frequency=0.25,
                                 ignored_exceptions=(StaleElementReferenceException,)).until(condition)
        except TimeoutException as exc:
            raise RuntimeError(f"Tiempo agotado: {description}. No se continuará el inicio de la OT.") from exc

    def idle(self):
        self.wait(lambda d: d.execute_script("""
            return document.readyState === 'complete' &&
              ![...document.querySelectorAll('.bx--loading-overlay, #wait')].some(e =>
                e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' &&
                getComputedStyle(e).opacity !== '0');
        """), "respuesta de Maximo")

    def field(self, caption):
        return self.read_field(caption, value_only=False)

    def read_field(self, caption, value_only=True):
        # Read the label and its control in one DOM snapshot. Maximo replaces
        # both during responses, so traversing cached WebElements can go stale.
        return self.driver.execute_script(r"""
            const normalize = text => String(text || '').normalize('NFD')
              .replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ')
              .replace(/^[ *:]+|[ *:]+$/g, '').toLowerCase();
            const visible = e => e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
            const label = [...document.querySelectorAll('label[for]')].find(e =>
              visible(e) && normalize(e.textContent) === arguments[0]);
            const field = label && document.getElementById(label.htmlFor);
            if (!visible(field)) return null;
            return arguments[1] ? String(field.value || '').trim() : field;
        """, normalized(caption), value_only)

    def value(self, caption):
        return self.read_field(caption)

    def check_ot(self):
        current = self.wait(lambda d: self.value("Orden de trabajo"), "ficha de la OT")
        if current != self.ot:
            raise RuntimeError(f"La ficha ya no corresponde a la OT {self.ot}; se detuvo el inicio.")

    def dialogs(self):
        return self.driver.execute_script(VISIBLE_DIALOGS_SCRIPT + "return visibleDialogs;")

    def dialog_snapshot(self):
        return self.driver.execute_script(VISIBLE_DIALOGS_SCRIPT +
                                          "return visibleDialogs.map(e => ({id:e.id, text:e.innerText.slice(0, 900)}));")

    def reject_dialogs(self, allowed=()):
        for dialog in self.dialog_snapshot():
            if dialog['id'] not in allowed:
                raise RuntimeError(f"Maximo requiere revisión: {dialog['text']}")

    def click_fresh(self, find, description, completed=None):
        """Retry only a stale click, reacquiring its target and checking its effect."""
        def click(d):
            self.idle()
            self.check_ot()
            if completed and completed():
                return {"clicked": False}
            element = find()
            if element is None:
                return False
            element.click()
            return {"clicked": True}
        return self.wait(click, description)["clicked"]

    def dialog_is_gone(self, dialog_id):
        return not any(e['id'] == dialog_id for e in self.dialog_snapshot())

    def response_sequence(self):
        """Observe completed UI requests without intercepting Maximo's HTTP APIs."""
        return self.driver.execute_script("""
            if (!window.__maximoDesktopResponses) {
              const state = { sequence: 0 };
              state.observer = new PerformanceObserver(list => {
                for (const entry of list.getEntries()) {
                  const url = new URL(entry.name);
                  if (['xmlhttprequest', 'fetch'].includes(entry.initiatorType) &&
                      url.origin === location.origin && url.pathname.startsWith('/maximo/ui'))
                    state.sequence++;
                }
              });
              state.observer.observe({ entryTypes: ['resource'] });
              window.__maximoDesktopResponses = state;
            }
            return window.__maximoDesktopResponses.sequence;
        """)

    def save(self):
        """Commit pending hierarchy deletions before reusing a child failure code."""
        self.idle()
        self.check_ot()
        self.reject_dialogs()
        action = self.driver.find_element(By.ID, "toolactions_SAVE-tbb_anchor")
        aria_disabled = action.get_attribute("aria-disabled")
        if aria_disabled == "true" or (aria_disabled is None and action.get_attribute("disabled") in {"true", "disabled"}):
            return False
        self.progress(f"OT {self.ot}: guardando los códigos de anomalía…")
        marker = self.response_sequence()
        self.click_fresh(
            lambda: self.driver.find_element(By.ID, "toolactions_SAVE-tbb_anchor"), "botón Guardar",
        )
        for _ in range(4):
            self.wait(lambda d: self.response_sequence() > marker or self.dialogs(), "respuesta al guardar la OT")
            self.idle()
            self.check_ot()
            dialogs = self.dialog_snapshot()
            if dialogs:
                dialog = dialogs[-1]
                if dialog['id'] != "alreadyreported-dialog_inner":
                    self.reject_dialogs()
                marker = self.response_sequence()
                self.progress(f"OT {self.ot}: continuando el aviso de problema ya informado…")
                self.button("alreadyreported-dialog_inner", "Continuar")
                continue
            saved = self.driver.execute_script("""
                return [...document.querySelectorAll('[role=alert]')].some(e =>
                  e.getClientRects().length && /BMXAA4205I/.test(e.textContent));
            """)
            if not saved:
                raise RuntimeError("Maximo respondió, pero no confirmó que la OT se haya guardado.")
            return True
        raise RuntimeError("Maximo repitió el aviso de guardado; se detuvo el inicio de la OT.")

    def start_choice(self, dialog):
        """Match radio captions through labels, ARIA or a single-radio container."""
        choices = []
        labels = dialog.find_elements(By.CSS_SELECTOR, "label")
        for choice in dialog.find_elements(By.CSS_SELECTOR, "input[type=radio]"):
            if not choice.is_displayed():
                continue
            choice_id = choice.get_attribute("id")
            captions = [choice.get_attribute("aria-label")]
            for label in labels:
                if label.get_attribute("for") == choice_id:
                    captions.append(label.text)
            for label_id in (choice.get_attribute("aria-labelledby") or "").split():
                captions.extend(e.text for e in self.driver.find_elements(By.ID, label_id))
            parent = choice
            for _ in range(3):
                parent = parent.find_element(By.XPATH, "..")
                if len(parent.find_elements(By.CSS_SELECTOR, "input[type=radio]")) != 1:
                    break
                captions.append(parent.text)
            if any(normalized(caption) == "iniciar orden" for caption in captions):
                choices.append(choice)
        if len(choices) > 1:
            raise RuntimeError("Maximo no ofrece una única opción «Iniciar orden».")
        return choices[0] if choices else None

    def lookup(self):
        return next((e for e in self.dialogs() if e.get_attribute("id").startswith("lookup_")), None)

    def lookup_filters(self):
        dialog = self.lookup()
        return [e for e in dialog.find_elements(By.CSS_SELECTOR, "input[id*='_tfrow_'][id*='[C:0]']")
                if e.is_displayed()] if dialog else []

    def tab(self, title):
        self.idle()
        self.check_ot()
        self.wait(lambda d: next((e for e in d.find_elements(By.CSS_SELECTOR, "a[role=tab]")
                                 if e.is_displayed() and normalized(e.text) == normalized(title)), None),
                  f"pestaña {title}").click()
        self.idle()
        self.wait(lambda d: self.field("Estado"), f"ficha en {title}")
        self.check_ot()

    def button(self, dialog_id, text):
        def find():
            dialogs = self.driver.find_elements(By.ID, dialog_id)
            if not dialogs:
                return None
            matches = [e for e in dialogs[0].find_elements(By.CSS_SELECTOR, "button")
                       if e.is_displayed() and normalized(e.text) == normalized(text)]
            if len(matches) > 1:
                raise RuntimeError(f"Hay varios botones «{text}» en el diálogo de Maximo.")
            return matches[0] if matches else None
        self.click_fresh(find, f"botón {text}", completed=lambda: self.dialog_is_gone(dialog_id) or
                         self.value("Estado") not in (None, "", "APPR"))

    def option(self, dialog, code):
        if dialog is None:
            return None
        matches = [e for e in dialog.find_elements(By.CSS_SELECTOR, "span[id*='_tdrow_'][mxevent=click]")
                   if e.is_displayed() and (e.text or "").strip() == code]
        if len(matches) > 1:
            raise RuntimeError(f"La lupa contiene varias opciones «{code}»; revisa la selección.")
        return matches[0] if matches else None

    def select(self, caption, code):
        self.idle()
        self.check_ot()
        field = self.wait(lambda d: self.field(caption), f"campo {caption}")
        if (field.get_attribute("value") or "").strip() == code:
            return False
        self.progress(f"OT {self.ot}: seleccionando {caption.lower()} {code}…")
        lookup_id = field.get_attribute("li")
        if not lookup_id:
            raise RuntimeError(f"El campo {caption} no tiene una lupa disponible.")
        self.driver.find_element(By.ID, lookup_id).click()
        dialog = self.wait(lambda d: self.lookup(), f"lupa de {caption}")
        lookup_dialog_id = dialog.get_attribute("id")
        self.idle()
        option = self.option(dialog, code)
        if option is None:
            filters = self.lookup_filters()
            if not filters:
                toggles = [e for e in dialog.find_elements(By.CSS_SELECTOR, "span[mxevent=click]")
                           if e.is_displayed() and normalized(e.text) == "filtro"]
                if len(toggles) != 1:
                    raise RuntimeError(f"No aparece «{code}» ni se puede filtrar su lupa.")
                toggles[0].click()
                filters = self.wait(lambda d: self.lookup_filters(), "filtro de código")
            filters[0].clear()
            filters[0].send_keys("=" + code, Keys.TAB)
            self.idle()
            filters = self.wait(lambda d: self.lookup_filters(), "filtro de código")
            filters[0].send_keys(Keys.ENTER)
            option = self.wait(lambda d: self.option(self.lookup(), code), f"opción {code}")
        self.click_fresh(lambda: self.option(self.lookup(), code), f"selección {code}",
                         completed=lambda: not self.dialogs() and self.value(caption) == code)
        def confirmed(d):
            self.reject_dialogs((lookup_dialog_id,))
            return not self.dialogs() and self.value(caption) == code
        self.wait(confirmed, f"confirmación de {caption} {code}")
        self.idle()
        return True

    def route(self):
        """Solo continúa avisos conocidos; se detiene al confirmar INPRG."""
        deadline = time.monotonic() + 120
        routes = 0
        initiated = False
        handled = 0
        while time.monotonic() < deadline and handled < 10:
            self.idle()
            self.check_ot()
            status = self.wait(lambda d: self.value("Estado"), "estado actual de la OT")
            if status == "INPRG":
                return
            if status != "APPR":
                raise RuntimeError(f"La OT {self.ot} cambió al estado {status}; no se seguirá enrutando.")
            dialogs = self.dialog_snapshot()
            if dialogs:
                dialog = dialogs[-1]
                dialog_id = dialog['id']
                if dialog_id == "alreadyreported-dialog_inner":
                    self.progress(f"OT {self.ot}: continuando el aviso de problema ya informado…")
                    self.button(dialog_id, "Continuar")
                elif dialog_id == "inputwf-dialog_inner" and not initiated:
                    self.click_fresh(
                        lambda: self.start_choice(self.driver.find_element(By.ID, dialog_id)),
                        "opción Iniciar orden", completed=lambda: self.dialog_is_gone(dialog_id) or
                        self.value("Estado") not in (None, "", "APPR"),
                    )
                    self.progress(f"OT {self.ot}: iniciando orden…")
                    self.button(dialog_id, "Aceptar")
                    initiated = True
                    self.wait(lambda d: self.value("Estado") not in (None, "", "APPR") or
                              self.dialog_is_gone("inputwf-dialog_inner"),
                        "respuesta a Iniciar orden")
                else:
                    raise RuntimeError(f"Maximo requiere revisión antes de iniciar la OT: {dialog['text'][:700]}")
                handled += 1
            elif initiated:
                self.wait(lambda d: self.value("Estado") not in (None, "", "APPR") or self.dialog_snapshot(),
                          "estado tras Iniciar orden")
            else:
                if routes >= 3:
                    raise RuntimeError("Maximo no ofreció «Iniciar orden» tras tres intentos de enrutar.")
                self.progress(f"OT {self.ot}: enrutando flujo de trabajo ({routes + 1}/3)…")
                clicked = self.click_fresh(
                    lambda: self.driver.find_element(By.ID, "ROUTEWF_WO-MAIN_-tbb_image"),
                    "botón Enrutar flujo de trabajo", completed=self.route_event,
                )
                if clicked:
                    routes += 1
                try:
                    WebDriverWait(self.driver, self.route_dialog_timeout, poll_frequency=0.25,
                                  ignored_exceptions=(StaleElementReferenceException,)).until(lambda d: self.route_event())
                except TimeoutException:
                    # The first click sometimes only saves or does nothing. The
                    # next loop waits for idle and rechecks state/dialogs before
                    # deciding whether another routing click is still needed.
                    self.progress(f"OT {self.ot}: esperando el diálogo; comprobando antes de reintentar…")
        raise RuntimeError("Maximo no confirmó el inicio de la OT dentro del límite de espera.")

    def route_event(self):
        return self.dialog_snapshot() or self.value("Estado") not in (None, "", "APPR")

    def check_location(self):
        url = urlsplit(self.driver.current_url)
        if url.scheme != "https" or url.hostname != "eam.indraweb.net" or not url.path.startswith("/maximo/ui"):
            raise RuntimeError("El inicio de OT solo está disponible en la ficha de Maximo.")

    def run(self):
        self.check_location()
        self.wait(lambda d: self.value("Orden de trabajo") == self.ot and self.value("Estado"), "carga de la OT")
        self.check_ot()
        status = self.value("Estado")
        if status == "INPRG":
            return {"ot": self.ot, "status": "INPRG", "already_started": True}
        if status != "APPR":
            raise RuntimeError(f"No se puede iniciar la OT {self.ot} en estado {status}. Debe estar en APPR.")
        if self.dialogs():
            raise RuntimeError("Cierra el diálogo abierto en Maximo antes de iniciar la OT.")
        self.save()
        self.tab("Informes de anomalías")
        if self.select("Clase de anomalía", "RFN-70"):
            self.save()
        self.tab("Soluciones")
        for caption, code in (("Síntoma", "OTROS-01"), ("Causa", "OTROS-02"), ("Resolucion", "OTROS-03")):
            if self.select(caption, code):
                self.save()
        self.route()
        # Reload confirms the server persisted the codes and status, not just
        # the visible values of Maximo's asynchronous controls.
        self.driver.refresh()
        self.wait(lambda d: self.value("Orden de trabajo") == self.ot and self.value("Estado") == "INPRG",
                  "confirmación del inicio guardado")
        for caption, code in (("Síntoma", "OTROS-01"), ("Causa", "OTROS-02"), ("Resolucion", "OTROS-03")):
            if self.value(caption) != code:
                raise RuntimeError(f"La OT está iniciada, pero Maximo no conservó {caption} {code}. Revisa la ficha.")
        self.tab("Informes de anomalías")
        if self.value("Clase de anomalía") != "RFN-70":
            raise RuntimeError("La OT está iniciada, pero Maximo no conservó RFN-70. Revisa la ficha.")
        self.tab("Soluciones")
        logging.info("OT %s iniciada y verificada: RFN-70 / OTROS-01 / OTROS-02 / OTROS-03", self.ot)
        return {"ot": self.ot, "status": "INPRG", "already_started": False}


def start_workorder(driver, ot, progress=None):
    try:
        return WorkorderStarter(driver, ot, progress).run()
    except WebDriverException as exc:
        logging.exception("Falló una acción del navegador al iniciar la OT %s", ot)
        raise RuntimeError(browser_error_message(exc)) from exc


def browser_error_message(error):
    if isinstance(error, StaleElementReferenceException):
        return "Maximo actualizó la pantalla durante la acción. Vuelve a intentar iniciar la OT."
    if isinstance(error, WebDriverException):
        return "No se pudo completar una acción en Maximo. Revisa la ficha y vuelve a intentarlo."
    return " ".join(str(error).split())[:500]


def poll_browser_start(driver):
    """Expose an explicit action in MD's Edge session and consume one click."""
    button_script = """
        if (location.origin !== 'https://eam.indraweb.net' || !location.pathname.startsWith('/maximo/ui')) return '';
    """ + VISIBLE_DIALOGS_SCRIPT + """
        const field = caption => {
          const label = [...document.querySelectorAll('label[for]')].find(e =>
            e.getClientRects().length && e.textContent.trim().replace(/:$/, '') === caption);
          return label && document.getElementById(label.htmlFor)?.value;
        };
        const ot = field('Orden de trabajo'), status = field('Estado');
        let button = document.getElementById('maximo-desktop-start-ot');
        if (!button && ot) {
          button = document.createElement('button');
          button.id = 'maximo-desktop-start-ot'; button.type = 'button';
          button.textContent = 'Iniciar OT';
          Object.assign(button.style, {position:'fixed',right:'20px',bottom:'65px',zIndex:'2147483647',
            padding:'9px 14px',border:'1px solid #1155a0',borderRadius:'6px',background:'#1769c2',
            color:'#fff',font:'600 13px Arial,sans-serif',boxShadow:'0 3px 12px #0004',cursor:'pointer'});
          button.addEventListener('click', () => {
            if (button.disabled) return;
            button.disabled = true; button.dataset.busy = 'true'; button.textContent = 'Iniciando OT…';
            document.documentElement.dataset.maximoStartOt = field('Orden de trabajo');
          });
          document.body.appendChild(button);
        }
        if (button) {
          button.hidden = !/^\\d{1,20}$/.test(ot || '');
          if (button.dataset.busy !== 'true') {
            button.disabled = status !== 'APPR' || visibleDialogs.length > 0;
            button.style.opacity = button.disabled ? '0.6' : '1';
            button.title = 'Establecer RFN-70, OTROS-01/02/03 e iniciar una OT en APPR';
          }
        }
        const request = document.documentElement.dataset.maximoStartOt || '';
        delete document.documentElement.dataset.maximoStartOt;
        return request;
    """
    request = driver.execute_script(button_script)
    if not request:
        return None

    def report(message):
        driver.execute_script("""
            const button = document.getElementById('maximo-desktop-start-ot');
            if (button) { button.textContent = arguments[0]; button.title = arguments[0]; }
        """, message)

    try:
        result = start_workorder(driver, request, report)
        # The verification reload removes injected controls; restore the
        # button before displaying the completion message.
        driver.execute_script(button_script)
        report(f"OT {request} ya iniciada" if result["already_started"] else f"OT {request} iniciada")
        return result
    except Exception as exc:
        logging.exception("No se pudo iniciar la OT %s desde el navegador", request)
        report(f"No se pudo iniciar: {browser_error_message(exc)}")
        return None
    finally:
        driver.execute_script("""
            const button = document.getElementById('maximo-desktop-start-ot');
            if (button) {
              button.dataset.busy = 'false';
              setTimeout(() => { if (button.dataset.busy !== 'true') button.textContent = 'Iniciar OT'; }, 8000);
            }
        """)
