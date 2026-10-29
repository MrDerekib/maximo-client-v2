"""Inicio explícito de OT mediante los controles nativos de Maximo."""
import json
import logging
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from app_paths import PROGRAM_DIR
from anomaly_diagnostics import record_anomaly_incident
from failure_catalog import catalog_payload, default_selection, resolve_selection

_START_OPTIONS_SOURCE = None
_START_OPTIONS_SOURCE_VERSION = None


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
    active_status = 'APPR'
    operation = 'inicio'

    def __init__(self, driver, ot, progress=None, timeout=30):
        self.driver = driver
        self.ot = str(ot).strip()
        self.progress = progress or (lambda message: None)
        self.timeout = timeout
        self.anomaly_diagnostic_context = None
        self.anomaly_diagnostic_snapshots = []
        self._anomaly_diagnostic_snapshot_keys = set()
        self._anomaly_diagnostic_recorded = False

    @staticmethod
    def _diagnostic_text(value, limit=180):
        return " ".join(str(value or "").split())[:limit]

    def begin_anomaly_diagnostics(self, mode, selection):
        if mode != "configured":
            return
        requested = {}
        if isinstance(selection, dict):
            for key in ("class_key", "class_code", "organization"):
                if selection.get(key) is not None:
                    requested[key] = self._diagnostic_text(selection[key], 180)
            option_keys = selection.get("option_keys")
            if isinstance(option_keys, (list, tuple)):
                requested["option_keys"] = [self._diagnostic_text(key, 180) for key in option_keys[:40]]
            elif option_keys is not None:
                requested["option_keys"] = self._diagnostic_text(option_keys, 180)
        elif selection is not None:
            requested["selection"] = self._diagnostic_text(selection, 300)
        self.anomaly_diagnostic_context = {
            "ot": self.ot,
            "mode": mode,
            "operation": self.operation,
            "stage": "selection_validation",
            "requested": requested,
            "expected": {},
        }

    def set_anomaly_diagnostic_stage(self, stage, expected=None):
        context = self.anomaly_diagnostic_context
        if not context:
            return
        context["stage"] = self._diagnostic_text(stage, 100)
        if expected is not None:
            context["expected"] = {
                key: self._diagnostic_text(expected.get(key), 180)
                for key in ("level", "type", "code") if expected.get(key) is not None
            }

    def record_anomaly_snapshot(self, kind, stage, options, pagination=None, filter_value=None,
                                scope="visible_options", complete=None):
        if not self.anomaly_diagnostic_context:
            return
        bounded_options = []
        for option in (options or [])[:200]:
            if not isinstance(option, dict):
                continue
            bounded_options.append({key: self._diagnostic_text(option.get(key), 180)
                                    for key in ("code", "type", "description", "organization")
                                    if option.get(key) is not None})
        record = {
            "kind": kind,
            "stage": self._diagnostic_text(stage, 100),
            "scope": scope,
            "complete": complete if isinstance(complete, bool) else None,
            "options": bounded_options,
            "truncated": len(options or []) > 200,
        }
        if filter_value is not None:
            record["filter"] = self._diagnostic_text(filter_value, 180)
        if isinstance(pagination, dict):
            record["pagination"] = {key: pagination.get(key) for key in ("first", "last", "total")}
        key = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if key in self._anomaly_diagnostic_snapshot_keys:
            return
        self._anomaly_diagnostic_snapshot_keys.add(key)
        self.anomaly_diagnostic_snapshots.append(record)
        if len(self.anomaly_diagnostic_snapshots) > 12:
            self.anomaly_diagnostic_context["snapshots_truncated"] = True
            removed = self.anomaly_diagnostic_snapshots.pop(0)
            self._anomaly_diagnostic_snapshot_keys.discard(json.dumps(removed, ensure_ascii=False, sort_keys=True))

    def record_anomaly_failure(self, error):
        if not self.anomaly_diagnostic_context or self._anomaly_diagnostic_recorded:
            return None
        self._anomaly_diagnostic_recorded = True
        try:
            return record_anomaly_incident(
                self.anomaly_diagnostic_context,
                self.anomaly_diagnostic_snapshots,
                error,
            )
        except Exception:
            logging.exception("No se pudo registrar la incidencia de anomalías de la OT %s", self.ot)
            return None

    def wait(self, condition, description):
        try:
            return WebDriverWait(self.driver, self.timeout, poll_frequency=0.25,
                                 ignored_exceptions=(StaleElementReferenceException,)).until(condition)
        except TimeoutException as exc:
            raise RuntimeError(f"Tiempo agotado: {description}. No se continuará el {self.operation} de la OT.") from exc

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
            raise RuntimeError(f"La ficha ya no corresponde a la OT {self.ot}; se detuvo el {self.operation}.")

    def check_startable(self):
        self.check_ot()
        status=self.wait(lambda d:self.value("Estado"),"estado de la OT")
        if status != self.active_status:
            raise RuntimeError(f"La OT {self.ot} ya no está en {self.active_status} (estado actual: {status}); "
                               f"se detuvo el {self.operation}.")

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
        """Commit changes through the active toolbar or Maximo's common-actions menu."""
        self.idle()
        self.check_startable()
        self.reject_dialogs()
        def toolbar_enabled():
            actions = self.driver.find_elements(By.ID, "toolactions_SAVE-tbb_anchor")
            if not actions:
                return False
            action = actions[0]
            aria_disabled = action.get_attribute("aria-disabled")
            return not (aria_disabled == "true" or
                        (aria_disabled is None and action.get_attribute("disabled") in {"true", "disabled"}))

        def common_save():
            matches = [e for e in self.driver.find_elements(By.CSS_SELECTOR, "a,button,[role=menuitem],span")
                       if e.is_displayed() and normalized(e.text) == "guardar orden de trabajo"]
            if len(matches) > 1:
                # Prefer the left navigation/action anchor when Maximo exposes
                # both a menu label and a toolbar caption.
                anchors = [e for e in matches if e.tag_name == "a"]
                matches = anchors or matches
            return matches[0] if len(matches) == 1 else None

        if not toolbar_enabled() and common_save() is None:
            return False
        self.progress(f"OT {self.ot}: guardando los cambios…")
        marker = self.response_sequence()
        find_save = (lambda: self.driver.find_element(By.ID, "toolactions_SAVE-tbb_anchor")) \
            if toolbar_enabled() else common_save
        self.click_fresh(
            find_save, "acción Guardar",
        )
        for _ in range(4):
            self.wait(lambda d: self.response_sequence() > marker or self.dialogs(), "respuesta al guardar la OT")
            self.idle()
            self.check_startable()
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
        raise RuntimeError(f"Maximo repitió el aviso de guardado; se detuvo el {self.operation} de la OT.")

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

    def capture_class_options(self):
        """Observe the existing lookup without clicking or requesting more pages."""
        if not self.anomaly_diagnostic_context:
            return
        try:
            state = self.driver.execute_script(VISIBLE_DIALOGS_SCRIPT + r"""
                const dialog=visibleDialogs.find(e=>e.id.startsWith('lookup_'));
                if(!dialog)return null;
                const visible=e=>e.getClientRects().length;
                const options=[...dialog.querySelectorAll("span[id*='_tdrow_'][id*='[C:0]'][mxevent=click]")]
                  .filter(visible).slice(0,201).map(link=>{
                    const row=link.closest('tr');
                    const cell=i=>row?.querySelector(`td[id*='[C:${i}]']`);
                    return {code:link.textContent.trim(),description:cell(1)?.textContent.trim()||'',
                      organization:cell(2)?.textContent.trim()||''};
                  });
                const page=dialog.innerText.match(/(\d+)\s*[-–]\s*(\d+)\s*de\s*(\d+)/i);
                const filter=dialog.querySelector("input[id*='_tfrow_'][id*='[C:0]']")?.value||'';
                return {options,filter,pagination:page?{first:+page[1],last:+page[2],total:+page[3]}:null};
            """)
            if isinstance(state, dict):
                self.record_anomaly_snapshot("class_lookup", self.anomaly_diagnostic_context["stage"],
                                             state["options"], state.get("pagination"), state.get("filter"),
                                             complete=True)
        except Exception:
            logging.debug("No se pudo capturar la lista de clases de anomalía", exc_info=True)

    def observed_class_option(self, code, organization):
        self.capture_class_options()
        return self.option(self.lookup(), code, organization)

    def filter_failure_options(self, code, expected_type):
        self.set_anomaly_diagnostic_stage("code_filter", {"type": expected_type, "code": code})
        dialog_id="wolistfailurecodes-dialog_inner"
        def filter_control():
            dialogs=self.driver.find_elements(By.ID,dialog_id)
            if not dialogs:return None
            candidates=[e for e in dialogs[0].find_elements(By.CSS_SELECTOR,
                "a,button,[role=button],span[mxevent=click],img,[title],[aria-label]") if e.is_displayed()]
            def label(element):
                return " ".join((element.text or "",element.get_attribute("title") or "",
                                 element.get_attribute("alt") or "",element.get_attribute("aria-label") or "")).strip()
            matches=[e for e in candidates if "filtro" in normalized(label(e))]
            # Prefer a clickable toolbar anchor/button over its nested icon.
            for tag in ("a","button"):
                preferred=[e for e in matches if e.tag_name==tag]
                if preferred:matches=preferred;break
            return matches[0] if len(matches)==1 else None
        def filters():
            dialogs=self.driver.find_elements(By.ID,dialog_id)
            return [element for element in dialogs[0].find_elements(By.CSS_SELECTOR,
                "input[id*='_tfrow_'][id*='[C:0]']") if element.is_displayed()] if dialogs else []
        if not filters():
            if filter_control() is None:
                raise RuntimeError(f"No aparece {code} en la lista y Maximo no ofrece un filtro identificable.")
            self.click_fresh(filter_control,"filtro de códigos de anomalía")
        fields=self.wait(lambda d:filters(),"campo de filtro de anomalías")
        fields[0].clear();fields[0].send_keys("="+code)
        tab_marker=self.response_sequence()
        fields[0].send_keys(Keys.TAB)
        self.wait(lambda d:self.response_sequence()>tab_marker,"validación del filtro de anomalías")
        self.idle();self.check_ot();self.reject_dialogs((dialog_id,))
        fields=self.wait(lambda d:filters(),"campo de filtro de anomalías")
        enter_marker=self.response_sequence()
        fields[0].send_keys(Keys.ENTER)
        self.wait(lambda d:self.response_sequence()>enter_marker,"resultados del filtro de anomalías")
        self.idle();self.check_ot();self.reject_dialogs((dialog_id,))
        return self.wait(lambda d: (state:=self.failure_selector_state()) and any(
            row["type"]==expected_type and row["code"]==code for row in state["rows"]),
            f"opción {code} ({expected_type}) tras filtrar")

    def tab(self, title):
        self.idle()
        self.check_ot()
        def find():
            return next((e for e in self.driver.find_elements(By.CSS_SELECTOR, "a[role=tab]")
                         if e.is_displayed() and normalized(e.text) == normalized(title)), None)
        def active():
            tab = find()
            return tab is not None and tab.get_attribute('aria-expanded') == 'true'
        self.click_fresh(find, f"pestaña {title}", completed=active)
        self.wait(lambda d: active(), f"activación de {title}")
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
                         self.value("Estado") not in (None, "", self.active_status))

    def option(self, dialog, code, organization=None):
        if dialog is None:
            return None
        matches = [e for e in dialog.find_elements(By.CSS_SELECTOR, "span[id*='_tdrow_'][mxevent=click]")
                   if e.is_displayed() and (e.text or "").strip() == code]
        if len(matches)>1 and organization:
            scoped=[e for e in matches if organization.casefold() in
                    (e.find_element(By.XPATH,"ancestor::tr[1]").text or "").casefold()]
            if scoped:
                matches=scoped
        if len(matches) > 1:
            raise RuntimeError(f"La lupa contiene varias opciones «{code}»; revisa la selección.")
        return matches[0] if matches else None

    def select_failure_class(self, code, organization=None):
        self.set_anomaly_diagnostic_stage("class_lookup", {"type": "CLASS", "code": code})
        caption = "Clase de anomalía"
        code = str(code or "").strip()
        if not code:
            raise ValueError("La selección no incluye una clase de anomalía válida.")
        self.idle()
        self.check_startable()
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
        self.capture_class_options()
        option = self.option(dialog, code, organization)
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
            filters[0].send_keys("=" + code)
            tab_marker=self.response_sequence()
            filters[0].send_keys(Keys.TAB)
            self.wait(lambda d:self.response_sequence()>tab_marker,"validación del filtro de clase")
            self.idle();self.check_ot();self.reject_dialogs((lookup_dialog_id,))
            filters = self.wait(lambda d: self.lookup_filters(), "filtro de código")
            enter_marker=self.response_sequence()
            filters[0].send_keys(Keys.ENTER)
            self.wait(lambda d:self.response_sequence()>enter_marker,"resultados del filtro de clase")
            self.idle();self.check_ot();self.reject_dialogs((lookup_dialog_id,))
            option = self.wait(lambda d: self.observed_class_option(code, organization), f"opción {code}")
        self.click_fresh(lambda: self.option(self.lookup(), code, organization), f"selección {code}",
                         completed=lambda: not self.dialogs() and self.value(caption) == code)
        def confirmed(d):
            self.reject_dialogs((lookup_dialog_id,))
            return not self.dialogs() and self.value(caption) == code
        self.wait(confirmed, f"confirmación de {caption} {code}")
        self.idle()
        return True

    def failure_selector_state(self):
        state = self.driver.execute_script(VISIBLE_DIALOGS_SCRIPT + r"""
            const dialog = visibleDialogs.find(e => e.id === 'wolistfailurecodes-dialog_inner');
            if (!dialog) return null;
            const rows = [...dialog.querySelectorAll("span[id*='_tdrow_'][id*='[C:0]'][mxevent=click]")]
              .filter(e => e.getClientRects().length).map(link => {
                const cell = link.closest('tr')?.querySelector("td[id*='[C:1]']");
                const type = cell?.querySelector('input')?.value || cell?.textContent || '';
                const description=link.closest('tr')?.querySelector("td[id*='[C:2]']")||link.closest('tr')?.children[2];
                return {id:link.id, code:link.textContent.trim(), type:type.trim().toUpperCase(),
                  description:description?.textContent.trim()||''};
              });
            const page=dialog.innerText.match(/(\d+)\s*[-–]\s*(\d+)\s*de\s*(\d+)/i);
            const filter=dialog.querySelector("input[id*='_tfrow_'][id*='[C:0]']")?.value||'';
            return {rows,filter,pagination:page?{first:+page[1],last:+page[2],total:+page[3]}:null};
        """)
        if isinstance(state, dict):
            try:
                self.record_anomaly_snapshot("failure_selector",
                    (self.anomaly_diagnostic_context or {}).get("stage", "code_lookup"), state["rows"],
                    state.get("pagination"), state.get("filter"), complete=True)
            except Exception:
                logging.debug("No se pudo capturar la lista de códigos de anomalía", exc_info=True)
        return state

    def failure_rows(self):
        """Read selected failure rows and their native suppress/undo controls."""
        return self.driver.execute_script(VISIBLE_DIALOGS_SCRIPT + r"""
            const visible = e => e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
            const normalize = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'')
              .replace(/\s+/g,' ').trim().toLowerCase();
            if (visibleDialogs.length) return null;
            const tables=[...document.querySelectorAll('table')].filter(visible);
            const table=tables.find(candidate => {
              if(normalize(candidate.getAttribute('summary')).includes('codigos de anomalia'))return true;
              for(let node=candidate.parentElement,depth=0;node&&depth<5;node=node.parentElement,depth++){
                const caption=node.querySelector('caption');
                if(caption&&normalize(caption.textContent)==='codigos de anomalia')return true;
                if([...node.children].some(child=>visible(child)&&normalize(child.textContent)==='codigos de anomalia'))return true;
              }
              return false;
            });
            if (!table) return null;
            const rows = [...table.querySelectorAll('tr')].filter(visible).map(row => {
              const cells=[...row.querySelectorAll(':scope > td')];
              const cellFor=index=>[...row.querySelectorAll('td')].find(cell=>
                cell.id.includes(`[C:${index}]`))||cells[index];
              const cellValue=cell=>{const control=cell?.querySelector('input:not([type=checkbox]),textarea,select');
                return String(control?.value||cell?.innerText||'').trim();};
              const type=cellValue(cellFor(0)).toUpperCase();
              const code=cellValue(cellFor(1)).split(/\s+/)[0];
              const text=cells.map(c=>c.innerText.trim());
              const toggle=[...row.querySelectorAll('a,img,button,[ctype="toggleimage"]')].find(e => {
                const label=[e.title,e.getAttribute('alt'),e.getAttribute('aria-label'),e.getAttribute('src')].join(' ');
                return /suprimir|garbage/i.test(label);
              });
              return {type,code,text, toggleTitle:toggle?.title||'', toggleAlt:toggle?.alt||'',
                toggleId:toggle?.id||'', toggleTag:toggle?.tagName||'', rowId:row.id||''};
            }).filter(row => ['PROBLEM','CAUSE','REMEDY'].includes(row.type) && row.code);
            return rows;
        """)

    def suppress_failure_rows(self):
        """Mark the existing failure hierarchy child-first and persist it."""
        self.set_anomaly_diagnostic_stage("clear_previous_hierarchy")
        self.tab("Informes de anomalías")
        snapshot = self.wait(lambda d: (found:=self.failure_rows()) is not None and {"rows":found} or False,
                             "tabla de códigos de anomalía")
        rows=snapshot["rows"]
        active_rows=[row for row in rows if "deshacer suprimir" not in normalized(row.get("toggleTitle"))]
        for row in sorted(active_rows, key=lambda item: {"REMEDY": 0, "CAUSE": 1, "PROBLEM": 2}[item["type"]]):
            if not row.get("toggleId"):
                raise RuntimeError(f"No se encontró el control nativo para suprimir {row['type']} {row['code']}.")

            def find(row_id=row["rowId"], code=row["code"], kind=row["type"], toggle_id=row["toggleId"]):
                current = self.failure_rows()
                if current is None:
                    return None
                matches = [item for item in current if item["type"] == kind and item["code"] == code and
                           (item["rowId"] == row_id or item["toggleId"] == toggle_id)]
                if len(matches) != 1:
                    matches = [item for item in current if item["type"] == kind and item["code"] == code and
                               "deshacer suprimir" not in normalized(item.get("toggleTitle"))]
                return self.driver.find_element(By.ID, matches[0]["toggleId"]) if len(matches) == 1 else None

            marked_before=sum(1 for item in (self.failure_rows() or []) if item["type"]==row["type"] and
                              item["code"]==row["code"] and
                              "deshacer suprimir" in normalized(item.get("toggleTitle")))
            marker=self.response_sequence()
            self.check_startable()
            self.click_fresh(find, f"suprimir {row['type']} {row['code']}")
            self.wait(lambda d: self.response_sequence() > marker, f"respuesta al marcar supresión de {row['code']}")
            self.idle()
            self.check_startable()
            marked=[item for item in (self.failure_rows() or []) if item["type"]==row["type"] and
                    item["code"]==row["code"] and "deshacer suprimir" in normalized(item["toggleTitle"])]
            if len(marked)<=marked_before:
                raise RuntimeError(f"Maximo no confirmó la supresión de {row['type']} {row['code']}.")
        if rows:
            if not self.save():
                raise RuntimeError("Maximo no habilitó Guardar tras marcar la jerarquía anterior para suprimir.")
        self.tab("Informes de anomalías")
        remaining = self.failure_rows()
        if remaining is None or remaining:
            raise RuntimeError("Maximo no confirmó la eliminación de la jerarquía anterior.")

    def select_failure_codes(self, existing=None, path=None):
        """Select a catalog path through Maximo's native hierarchical selector."""
        self.set_anomaly_diagnostic_stage("code_lookup")
        dialog_id = 'wolistfailurecodes-dialog_inner'
        # Keep accepting the old signature for callers outside this module.
        # New code passes the already validated catalog path explicitly.
        if path is None and isinstance(existing, (list, tuple)):
            path = existing
        elif path is None and isinstance(existing, dict):
            path = resolve_selection(default_selection())["path"]
        if not path:
            raise ValueError("La ruta de anomalías está vacía.")
        path = [dict(item) for item in path]
        allowed_types = {"PROBLEM", "CAUSE", "REMEDY"}
        if any(item.get("type") not in allowed_types or not str(item.get("code") or "").strip()
               for item in path):
            raise ValueError("La ruta de anomalías contiene un nivel o código no válido.")
        # A duplicated visible code is ambiguous unless the catalog explicitly
        # says these occurrences are equivalent and validated.
        for item in path:
            item["allow_duplicate"] = item.get("allow_duplicate") is True
        self.idle()
        self.check_startable()
        self.reject_dialogs()
        self.progress(f"OT {self.ot}: abriendo Seleccionar códigos de anomalía…")

        def opener():
            buttons = [e for e in self.driver.find_elements(By.CSS_SELECTOR, 'button')
                       if e.is_displayed() and normalized(e.text) == 'seleccionar codigos de anomalia']
            if len(buttons) > 1:
                raise RuntimeError("Hay varios botones «Seleccionar códigos de anomalía».")
            return buttons[0] if buttons else None

        self.click_fresh(opener, 'Seleccionar códigos de anomalía',
                         completed=lambda: self.failure_selector_state() is not None)

        def loaded(d):
            self.reject_dialogs((dialog_id,))
            state = self.failure_selector_state()
            return state if state and state['rows'] else False

        state = self.wait(loaded, 'primer nivel de códigos de anomalía')
        confirmed = dict(existing or {}) if isinstance(existing, dict) else {}
        for index, item in enumerate(path):
            kind, code = item["type"], str(item["code"]).strip()
            self.set_anomaly_diagnostic_stage("code_selection", {"level": index + 1, "type": kind, "code": code})
            if index and confirmed.get(path[index - 1]["type"]) != path[index - 1]["code"]:
                raise RuntimeError(f"El selector avanzó a {kind} sin confirmar el nivel anterior.")
            if index == 0:
                state = self.wait(loaded, "primer nivel de códigos de anomalía")
            else:
                state = self.wait(loaded, "siguiente nivel de códigos de anomalía")
            types = {row['type'] for row in state['rows']}
            if types != {kind}:
                raise RuntimeError(f"El selector muestra {', '.join(sorted(types)) or 'ningún nivel'}; se esperaba {kind}.")
            matches = [row for row in state['rows'] if row['type'] == kind and row['code'] == code]
            if not matches:
                self.filter_failure_options(code,kind)
                state=self.wait(loaded,f"opción {code} filtrada")
                matches = [row for row in state['rows'] if row['type'] == kind and row['code'] == code]
            if not matches:
                raise RuntimeError(f"No aparece el código {code} de tipo {kind} en el selector nativo.")
            if len(matches) > 1 and not item["allow_duplicate"]:
                raise RuntimeError(f"Hay varias ocurrencias de {code} ({kind}); la ruta no declara equivalencia validada.")
            selected = matches[0]
            before_signature = tuple((row["id"], row["type"], row["code"]) for row in state["rows"])
            before_response = self.response_sequence()
            self.progress(f"OT {self.ot}: seleccionando {code} ({index + 1}/{len(path)})…")

            def find(row_id=selected['id']):
                current = self.failure_selector_state()
                if current is None:
                    return None
                rows = [row for row in current['rows'] if row['id'] == row_id and
                        row['type'] == kind and row['code'] == code]
                return self.driver.find_element(By.ID, rows[0]['id']) if len(rows) == 1 else None

            next_item=path[index+1] if index+1<len(path) else None
            def advanced():
                self.idle()
                self.check_startable()
                self.reject_dialogs((dialog_id,))
                current = self.failure_selector_state()
                if current is None:
                    return self.response_sequence()>before_response
                if next_item is None:
                    return False
                signature = tuple((row["id"], row["type"], row["code"]) for row in current["rows"])
                return (self.response_sequence()>before_response and signature != before_signature and
                        {row["type"] for row in current["rows"]}=={next_item["type"]})

            self.click_fresh(find, f'código {code}', completed=advanced)
            self.wait(lambda d: advanced(), f'avance tras {code}')
            confirmed[kind] = code
            current = self.failure_selector_state()
            if current is None:
                if index != len(path) - 1:
                    raise RuntimeError(f"El selector se cerró antes de seleccionar {path[index + 1]['code']}.")
                return
            if index == len(path) - 1:
                # Some terminal choices close the dialog; if Maximo leaves it
                # open, it is safer to stop than to press a generic footer.
                raise RuntimeError(f"Maximo no cerró el selector tras seleccionar el nivel terminal {code}.")
        raise RuntimeError("El selector de anomalías no completó la ruta elegida.")

    def solution_codes(self):
        self.wait(lambda d: all(self.field(caption) is not None for caption in
                               ("Síntoma", "Causa", "Resolucion")), "campos de Soluciones")
        return {kind: self.value(caption) for kind, caption in
                (("PROBLEM", "Síntoma"), ("CAUSE", "Causa"), ("REMEDY", "Resolucion"))}

    def verify_solution_codes(self, path=None):
        self.set_anomaly_diagnostic_stage("verify_solutions")
        codes = self.solution_codes()
        if self.anomaly_diagnostic_context:
            self.anomaly_diagnostic_context["actual_codes"] = codes
        expected = {item["type"]: item["code"] for item in (path or [])}
        for kind in ("PROBLEM", "CAUSE", "REMEDY"):
            actual = (codes.get(kind) or "").strip()
            wanted = expected.get(kind, "")
            if actual != wanted:
                label = wanted or "vacío"
                raise RuntimeError(f"Maximo no confirmó {label} ({kind}); se detuvo el {self.operation} de la OT.")

    def verify_failure_rows(self, path):
        self.set_anomaly_diagnostic_stage("verify_saved_hierarchy")
        expected=sorted((item["type"],item["code"]) for item in path)
        self.tab("Informes de anomalías")
        snapshot=self.wait(lambda d:(rows:=self.failure_rows()) is not None and {"rows":rows} or False,
                           "tabla de códigos de anomalía")
        rows=snapshot["rows"]
        pending = [row for row in rows if "deshacer suprimir" in normalized(row.get("toggleTitle"))]
        if pending:
            raise RuntimeError(f"Maximo conserva filas marcadas para suprimir tras guardar; se detuvo el {self.operation} de la OT.")
        actual=sorted((row["type"],row["code"]) for row in rows)
        if actual!=expected:
            raise RuntimeError(f"Las filas de anomalía guardadas no coinciden exactamente con la ruta elegida; se detuvo el {self.operation} de la OT.")
        self.tab("Soluciones")

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
            raise RuntimeError("La acción de OT solo está disponible en la ficha de Maximo.")

    def apply_anomalies(self, selection=None):
        """Apply and verify a complete path, without any workflow routing."""
        spec = selection if selection is not None else default_selection()
        self.begin_anomaly_diagnostics("configured", spec)
        resolved = resolve_selection(spec)
        self.anomaly_diagnostic_context["requested"].update(resolved)
        self.set_anomaly_diagnostic_stage("inspect_existing_hierarchy")
        self.anomaly_path = resolved["path"]
        self.tab("Informes de anomalías")
        current_class = (self.value("Clase de anomalía") or "").strip()
        rows_snapshot=self.wait(lambda d:(rows:=self.failure_rows()) is not None and {"rows":rows} or False,
                                "tabla de códigos de anomalía")
        active_rows=[row for row in rows_snapshot["rows"]
                     if "deshacer suprimir" not in normalized(row.get("toggleTitle"))]
        pending_suppressions=[row for row in rows_snapshot["rows"]
                              if "deshacer suprimir" in normalized(row.get("toggleTitle"))]
        self.tab("Soluciones")
        current = self.solution_codes()
        expected = {item["type"]: item["code"] for item in resolved["path"]}
        current_values = {kind: (current.get(kind) or "").strip()
                          for kind in ("PROBLEM", "CAUSE", "REMEDY")}
        rows_match=sorted((row["type"],row["code"]) for row in active_rows)==sorted(
            (item["type"],item["code"]) for item in resolved["path"])
        matches = (current_class == resolved["class_code"] and all(
            current_values[kind] == expected.get(kind, "")
            for kind in ("PROBLEM", "CAUSE", "REMEDY")) and rows_match)
        if not matches:
            prefix_len = 0
            if current_class == resolved["class_code"]:
                for item in resolved["path"]:
                    if current_values[item["type"]] != item["code"]:
                        break
                    prefix_len += 1
                allowed_prefix = {item["type"] for item in resolved["path"][:prefix_len]}
                if any(value and kind not in allowed_prefix for kind, value in current_values.items()):
                    prefix_len = 0
                expected_prefix=sorted((item["type"],item["code"])
                                       for item in resolved["path"][:prefix_len])
                actual_prefix=sorted((row["type"],row["code"]) for row in active_rows)
                if actual_prefix!=expected_prefix:
                    prefix_len=0
            if (any(current_values.values()) or rows_snapshot["rows"]) and prefix_len == 0:
                self.suppress_failure_rows()
            if current_class != resolved["class_code"]:
                self.tab("Informes de anomalías")
                class_changed=self.select_failure_class(resolved["class_code"],resolved["organization"])
                if class_changed:
                    self.set_anomaly_diagnostic_stage("save_class")
                    if not self.save():
                        raise RuntimeError("Maximo no confirmó el guardado de la clase de anomalía.")
            self.tab("Informes de anomalías")
            self.select_failure_codes(path=resolved["path"][prefix_len:])
            self.set_anomaly_diagnostic_stage("save_codes")
            if not self.save():
                raise RuntimeError("Maximo no confirmó el guardado de los códigos de anomalía.")
            self.verify_failure_rows(resolved["path"])
            self.verify_solution_codes(resolved["path"])
        else:
            if pending_suppressions:
                self.set_anomaly_diagnostic_stage("save_pending_suppressions")
                if not self.save():
                    raise RuntimeError("Maximo no confirmó el guardado de las filas marcadas para suprimir.")
                self.verify_failure_rows(resolved["path"])
            self.progress(f"OT {self.ot}: los códigos elegidos ya están aplicados; no se modificarán.")
        return resolved

    def run(self, return_tab=None, anomaly_mode="configured", anomaly_selection=None):
        self.check_location()
        self.wait(lambda d: self.value("Orden de trabajo") == self.ot and self.value("Estado"), "carga de la OT")
        self.check_ot()
        status = self.value("Estado")
        if status == "INPRG":
            if return_tab:
                self.tab(return_tab)
            return {"ot": self.ot, "status": "INPRG", "already_started": True}
        if status != "APPR":
            raise RuntimeError(f"No se puede iniciar la OT {self.ot} en estado {status}. Debe estar en APPR.")
        if self.dialogs():
            raise RuntimeError("Cierra el diálogo abierto en Maximo antes de iniciar la OT.")
        if not isinstance(anomaly_mode, str):
            raise ValueError("El modo de inicio de OT no es válido.")
        mode = anomaly_mode.strip().lower()
        if mode not in {"configured", "only"}:
            raise ValueError("El modo de inicio de OT no es válido.")

        # Validate the complete selection before the first write/navigation.
        resolved = None
        if mode == "configured":
            resolved = self.apply_anomalies(anomaly_selection)
        else:
            # Deliberately do not inspect or edit fault class/solution fields.
            self.progress(f"OT {self.ot}: se iniciará conservando los códigos de anomalía existentes.")
        self.set_anomaly_diagnostic_stage("route_workorder")
        self.route()
        if resolved:
            path_label = " / ".join(item["code"] for item in resolved["path"])
            logging.info("OT %s iniciada y verificada: %s / %s", self.ot,
                         resolved["class_code"], path_label)
        else:
            logging.info("OT %s iniciada conservando sus códigos de anomalía", self.ot)
        if return_tab:
            self.set_anomaly_diagnostic_stage("restore_tab")
            self.tab(return_tab)
        return {"ot": self.ot, "status": "INPRG", "already_started": False}


class WorkorderAnomalyChanger(WorkorderStarter):
    """Save anomaly changes on an already started OT, without routing it."""
    active_status = "INPRG"
    operation = "cambio de anomalías"

    def run_change(self, selection, return_tab=None):
        self.check_location()
        self.wait(lambda d: self.value("Orden de trabajo") == self.ot and self.value("Estado"), "carga de la OT")
        self.check_startable()
        self.reject_dialogs()
        if selection is None:
            raise ValueError("Elige una combinación de anomalías completa.")
        resolved = self.apply_anomalies(selection)
        self.check_startable()
        if return_tab:
            self.set_anomaly_diagnostic_stage("restore_tab")
            self.tab(return_tab)
        self.check_startable()
        logging.info("OT %s: anomalías guardadas y verificadas sin enrutar: %s / %s", self.ot,
                     resolved["class_code"], " / ".join(item["code"] for item in resolved["path"]))
        return {"ot": self.ot, "status": "INPRG", "action": "change_anomalies"}


def change_workorder_anomalies(driver, ot, selection, progress=None, return_tab=None):
    changer = WorkorderAnomalyChanger(driver, ot, progress)
    try:
        return changer.run_change(selection, return_tab=return_tab)
    except Exception as exc:
        changer.record_anomaly_failure(exc)
        if return_tab:
            try:
                changer.tab(return_tab)
            except Exception:
                logging.info("No se pudo restaurar la pestaña tras el cambio de anomalías de la OT %s", ot)
        if isinstance(exc, WebDriverException):
            logging.exception("Falló el navegador al cambiar las anomalías de la OT %s", ot)
            raise RuntimeError(browser_error_message(exc)) from exc
        raise


def start_workorder(driver, ot, progress=None, return_tab=None, anomaly_mode="configured", anomaly_selection=None):
    starter = WorkorderStarter(driver, ot, progress)
    try:
        return starter.run(return_tab=return_tab, anomaly_mode=anomaly_mode,
                           anomaly_selection=anomaly_selection)
    except WebDriverException as exc:
        starter.record_anomaly_failure(exc)
        logging.exception("Falló una acción del navegador al iniciar la OT %s", ot)
        if return_tab:
            try:
                starter.tab(return_tab)
            except Exception:
                logging.info("No se pudo restaurar la pestaña de origen tras el fallo al iniciar la OT %s", ot)
        raise RuntimeError(browser_error_message(exc)) from exc
    except Exception as exc:
        starter.record_anomaly_failure(exc)
        if return_tab:
            try:
                starter.tab(return_tab)
            except Exception:
                logging.info("No se pudo restaurar la pestaña de origen tras el fallo al iniciar la OT %s", ot)
        raise


def browser_error_message(error):
    if isinstance(error, StaleElementReferenceException):
        return "Maximo actualizó la pantalla durante la acción. Vuelve a intentar la acción de OT."
    if isinstance(error, WebDriverException):
        return "No se pudo completar una acción en Maximo. Revisa la ficha y vuelve a intentarlo."
    return " ".join(str(error).split())[:500]


def _start_options_source():
    global _START_OPTIONS_SOURCE, _START_OPTIONS_SOURCE_VERSION
    path = Path(PROGRAM_DIR) / "browser_extension" / "start_options.js"
    if not path.is_file():
        path = Path(__file__).resolve().parent / "browser_extension" / "start_options.js"
    stat = path.stat()
    version = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if _START_OPTIONS_SOURCE is None or _START_OPTIONS_SOURCE_VERSION != version:
        _START_OPTIONS_SOURCE = path.read_text(encoding="utf-8")
        _START_OPTIONS_SOURCE_VERSION = version
    return _START_OPTIONS_SOURCE


def poll_browser_start(driver):
    """Expose start/default and per-OT override actions in the Edge session."""
    if not driver.execute_script("return location.origin === 'https://eam.indraweb.net' && location.pathname.startsWith('/maximo/ui')"):
        return None

    source = _start_options_source()
    driver.execute_script(source)
    if not driver.execute_script("return Boolean(globalThis.MaximoDesktopStartOptions?.installed)"):
        payload = catalog_payload()
        default = getattr(driver, "_maximo_workorder_start_selection", None)
        if default is None:
            default = default_selection()
        mode = getattr(driver, "_maximo_workorder_start_mode", "configured")
        driver.execute_script("return globalThis.MaximoDesktopStartOptions.install(arguments[0],arguments[1],arguments[2])",
                              payload, default, mode)
    request_data = driver.execute_script("return globalThis.MaximoDesktopStartOptions?.poll() || ''")
    if not request_data:
        return None
    try:
        request = json.loads(request_data)
        ot = str(request.get("ot") or "").strip()
        return_tab = str(request.get("returnTab") or "").strip()
        anomaly_mode = request.get("mode")
        anomaly_selection = request.get("selection")
        has_selection = "selection" in request
        action = request.get("action", "start")
    except (TypeError, ValueError, AttributeError):
        logging.warning("Se descartó una solicitud mal formada para iniciar una OT")
        driver.execute_script("globalThis.MaximoDesktopStartOptions?.complete('No se pudo leer la solicitud de inicio.');")
        return None
    normalized_mode = anomaly_mode.strip().lower() if isinstance(anomaly_mode, str) else None
    if (not ot or action not in ("start", "change_anomalies") or not isinstance(anomaly_mode, str) or
            normalized_mode not in {"configured", "only"} or
            (action == "change_anomalies" and normalized_mode != "configured") or
            (normalized_mode == "configured" and (not has_selection or anomaly_selection is None))):
        driver.execute_script("globalThis.MaximoDesktopStartOptions?.complete('Solicitud de inicio no válida.');")
        return None
    anomaly_mode = normalized_mode

    def report(message):
        driver.execute_script("""
            globalThis.MaximoDesktopStartOptions?.message(arguments[0]);
        """, message)

    try:
        if action == "change_anomalies":
            change_workorder_anomalies(driver, ot, anomaly_selection, report, return_tab=return_tab)
            driver.execute_script("globalThis.MaximoDesktopStartOptions?.complete(arguments[0]);",
                                  f"OT {ot}: anomalías guardadas")
            # The watcher callback applies a started status locally; a change
            # of anomaly codes must never be reported as a new start action.
            return None
        result = start_workorder(driver, ot, report, return_tab=return_tab,
                                 anomaly_mode=anomaly_mode, anomaly_selection=anomaly_selection)
        driver.execute_script("globalThis.MaximoDesktopStartOptions?.complete(arguments[0]);",
                              f"OT {ot} ya iniciada" if result["already_started"] else f"OT {ot} iniciada")
        return result
    except Exception as exc:
        failure_label = "cambiar anomalías" if action == "change_anomalies" else "iniciar"
        logging.exception("No se pudo %s la OT %s desde el navegador", failure_label, ot)
        driver.execute_script("globalThis.MaximoDesktopStartOptions?.complete(arguments[0]);",
                              f"No se pudo {failure_label}: {browser_error_message(exc)}")
        return None
