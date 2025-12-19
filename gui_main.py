# gui_main.py
import threading
import shutil
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

from config import load_config, save_config, set_credentials, AppConfig, credentials_configured, BASE_DIR, DATA_DIR
from db import fetch_data, init_db
from maximo_client import open_ot
from updater import run_update
import logging
import version
from update_checker import fetch_latest_release, is_newer, format_version_tag
from pathlib import Path
import time

# Configuración básica para los logs
logging.basicConfig(
    level=logging.DEBUG,  # Establece el nivel de detalle
    format="%(asctime)s - %(levelname)s - %(message)s",  # Formato del log
    handlers=[
        logging.FileHandler("maximo_client.log"),  # Guarda el log en archivo
        logging.StreamHandler()  # También muestra los logs en consola
    ]
)

logging.info(f"App Version: {version.APP_VERSION} - Iniciando la aplicación")




class MaximoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Cliente Maximo {format_version_tag(version.APP_VERSION)}")
        self.geometry("1600x800")
        icon_path = Path(BASE_DIR) / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                logging.warning("No se pudo aplicar icon.ico a la ventana (no crítico).", exc_info=True)
        else:
            logging.debug("icon.ico no encontrado; se omite iconbitmap.")

        self.cfg: AppConfig = load_config()
        self.auto_update_job = None  # ID del after() del auto-update
        self.ot_sessions = []  # sesiones Edge visibles (OT)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(500, lambda: self.check_updates(notify_popup=True))
        init_db()

        self._build_ui()
        self._load_config_into_ui()
        self.update_table()

        # Si al arrancar no hay credenciales, abrimos directamente la pestaña de config
        if not self.cfg.username or not self.cfg.password:
            self.notebook.select(self.config_frame)

        # Si auto-update está activado, programamos el timer
        if self.cfg.auto_update_enabled:
            self.schedule_auto_update()

    def _ensure_credentials(self) -> bool:
        """
        Devuelve True si hay credenciales configuradas.
        Si no las hay, muestra un aviso y lleva al usuario a la pestaña de Configuración.
        """
        if not credentials_configured():
            #añadimos el mensaje al log
            logging.warning("No hay usuario y/o contraseña configurados.")
            messagebox.showwarning(
                "Credenciales necesarias",
                "No hay usuario y/o contraseña configurados.\n\n"
                "Ve a la pestaña 'Configuración', introduce tus credenciales de Maximo "
                "y guarda la configuración antes de usar esta opción."
            )
            # Cambiar a la pestaña de Configuración
            self.notebook.select(self.config_frame)
            return False
        return True
    def _format_ok_status(self, dt: datetime, new_entries: int, updated_entries: int) -> str:
        """
        Devuelve el texto para la barra de estado en caso de actualización correcta.
        Incluye emoji, fecha dd/mm/aa y hora hh:mm.
        """
        ts_str = dt.strftime("%d/%m/%y %H:%M")
        if (new_entries or 0) > 0 or (updated_entries or 0) > 0:
            # Hubo cambios
            return f"✅ Última actualización {ts_str} – {new_entries} nuevas, {updated_entries} actualizadas."
        else:
            # Sin cambios
            return f"🟢 Última actualización {ts_str} – sin cambios."



    # ---------- UI ----------
    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        # Pestaña LISTADO
        self.list_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.list_frame, text="Listado")
        self._build_list_tab()

        # Pestaña CONFIG
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="Configuración")
        self._build_config_tab()

        # Barra de estado (abajo)
        self.status_var = tk.StringVar(value="Listo.")
        status_bar = ttk.Label(self, textvariable=self.status_var,
                               anchor="w", relief="sunken")
        status_bar.pack(fill="x", side="bottom")

        # Mostrar, si existe, el último estado correcto guardado
        self._load_last_status_into_statusbar()

    def _load_last_status_into_statusbar(self):
        """
        Si hay un último estado correcto guardado en la configuración,
        lo muestra en la barra de estado al arrancar la app.
        """
        last = getattr(self.cfg, "last_status", None)
        if not last:
            self.status_var.set("Listo.")
            return

        try:
            ts = last.get("ts")
            new_entries = int(last.get("new_entries", 0))
            updated_entries = int(last.get("updated_entries", 0))
            dt = datetime.fromisoformat(ts)
        except Exception:
            self.status_var.set("Listo.")
            return

        self.status_var.set(self._format_ok_status(dt, new_entries, updated_entries))

    def _build_list_tab(self):
        top_frame = ttk.Frame(self.list_frame)
        top_frame.pack(fill="x", pady=5)

        # Cliente
        self.client_var = tk.StringVar(value="Todos")
        ttk.Label(top_frame, text="Cliente:").pack(side="left", padx=5)
        self.client_combo = ttk.Combobox(top_frame, textvariable=self.client_var, state="readonly")
        self.client_combo.pack(side="left", padx=5)
        self.client_combo.bind("<<ComboboxSelected>>", lambda e: self.update_table())

        # Búsqueda
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self.update_table())

        self.search_by = tk.StringVar(value="OT")
        rb_frame = ttk.Frame(top_frame)
        rb_frame.pack(side="left", padx=10)
        ttk.Radiobutton(rb_frame, text="OT", variable=self.search_by, value="OT").pack(anchor="w")
        ttk.Radiobutton(rb_frame, text="Nº de serie", variable=self.search_by, value="Nº_de_serie").pack(anchor="w")
        ttk.Radiobutton(rb_frame, text="Descripción", variable=self.search_by, value="Descripción").pack(anchor="w")

        ttk.Button(top_frame, text="Buscar", command=self.update_table).pack(side="left", padx=5)
        ttk.Button(
            top_frame,
            text="Actualizar ahora",
            command=lambda: self.update_now_threaded(show_popup=True)
        ).pack(side="right", padx=5)

        # Tabla
        columns = ("OT", "Descripción", "Nº de serie", "Fecha",
                   "Cliente", "Tipo de trabajo", "Seguimiento", "Planta")
        self.columns = columns
        self.sort_order = {c: False for c in columns}

        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col,
                              command=lambda c=col: self.sort_by_column(c))
            self.tree.column(col, width=100)
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Double-1>", self.on_double_click)

        # Scrollbar vertical
        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Menú contextual copiar
        self._build_context_menu()

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copiar", command=self.copy_cell_to_clipboard)
        self.selected_column_index = 0

        def on_right_click(event):
            region = self.tree.identify_region(event.x, event.y)
            if region == "cell":
                col = self.tree.identify_column(event.x)
                self.selected_column_index = int(col[1:]) - 1
                self.context_menu.tk_popup(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", on_right_click)

    def _build_config_tab(self):
        frame = self.config_frame

        # Subframe 1: formulario (GRID)
        form = ttk.Frame(frame)
        form.pack(fill="x", padx=10, pady=10)

        ttk.Label(form, text="Usuario Maximo:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.user_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.user_var, width=30).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form, text="Contraseña Maximo:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.pass_var, width=30, show="*").grid(row=1, column=1, padx=5, pady=5)

        self.auto_update_var = tk.BooleanVar()
        ttk.Checkbutton(
            form,
            text="Auto-actualizar en segundo plano",
            variable=self.auto_update_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Intervalo (minutos):").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.interval_var = tk.IntVar()
        ttk.Entry(form, textvariable=self.interval_var, width=10).grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(form, text="Guardar configuración", command=self.save_config_from_ui) \
            .grid(row=4, column=0, columnspan=2, pady=15)

        # Subframe 2: actualizaciones (PACK)
        update_frame = ttk.LabelFrame(frame, text="Actualizaciones")
        update_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(update_frame, text=f"Versión instalada: v{version.APP_VERSION}") \
            .pack(anchor="w", padx=10, pady=2)

        self.lbl_latest = ttk.Label(update_frame, text="Última versión detectada: —")
        self.lbl_latest.pack(anchor="w", padx=10, pady=2)

        self.lbl_checked = ttk.Label(update_frame, text="Última comprobación: —")
        self.lbl_checked.pack(anchor="w", padx=10, pady=2)

        btns = ttk.Frame(update_frame)
        btns.pack(fill="x", padx=10, pady=6)

        ttk.Button(btns, text="Buscar actualizaciones", command=lambda: self.check_updates(False)).pack(side="left")
        self.btn_open = ttk.Button(btns, text="Abrir release", command=self._open_latest_release)
        self.btn_open.pack(side="left", padx=8)

        self._refresh_update_block()

        # Añadir el autor después del bloque de actualizaciones
        ttk.Label(frame, text="© Joan Camps (jcamp@indra.es)").pack(anchor="w", padx=10, pady=10)

    # ---------- Lógica GUI ----------
    def _load_config_into_ui(self):
        self.user_var.set(self.cfg.username)
        self.pass_var.set(self.cfg.password)
        self.auto_update_var.set(self.cfg.auto_update_enabled)
        self.interval_var.set(self.cfg.auto_update_interval_min)

        # Cargar lista de clientes para el combo
        try:
            with open("clientes_unicos.txt", "r", encoding="utf-8") as f:
                clients = [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            clients = []
        self.client_combo["values"] = ["Todos"] + clients
        self.client_combo.set("Todos")

    def save_config_from_ui(self):
        self.cfg.username = self.user_var.get().strip()
        self.cfg.password = self.pass_var.get().strip()
        self.cfg.auto_update_enabled = self.auto_update_var.get()
        self.cfg.auto_update_interval_min = max(1, self.interval_var.get() or 5)

        set_credentials(self.cfg.username, self.cfg.password)
        save_config(self.cfg)

        messagebox.showinfo("Configuración", "Configuración guardada correctamente.")
        logging.info("Configuración de usuario guardada correctamente.")

        # Siempre reconfiguramos el auto-update según la nueva config
        self.schedule_auto_update()


    # ---------- Listado ----------
    def update_table(self):
        filter_text = self.search_var.get()
        search_by = self.search_by.get()
        client_filter = self.client_var.get()

        data = fetch_data(filter_text, search_by, client_filter)
        # por defecto, ordenar por OT desc
        data.sort(key=lambda x: x[0], reverse=True)

        for row in self.tree.get_children():
            self.tree.delete(row)

        for row in data:
            self.tree.insert("", "end", values=row)

    def sort_by_column(self, column):
        data = [self.tree.item(i, "values") for i in self.tree.get_children()]
        idx = self.columns.index(column)
        reverse = not self.sort_order[column]
        self.sort_order[column] = reverse
        sorted_data = sorted(data, key=lambda x: x[idx], reverse=reverse)

        for row_id in self.tree.get_children():
            self.tree.delete(row_id)
        for row in sorted_data:
            self.tree.insert("", "end", values=row)

        self.tree.heading(column, text=f"{column} {'↓' if reverse else '↑'}",
                          command=lambda c=column: self.sort_by_column(c))

    def on_double_click(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        ot = self.tree.item(selected[0], "values")[0]
        self.open_ot_threaded(ot)

    def copy_cell_to_clipboard(self):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if not values:
            return
        idx = self.selected_column_index
        if 0 <= idx < len(values):
            value = values[idx]
            self.clipboard_clear()
            self.clipboard_append(value)
            self.update()
            messagebox.showinfo("Copiado", f"Se copió: {value}")

    # ---------- Actualización (manual / auto) ----------
    def update_now_threaded(self, show_popup: bool = True):
        # Comprobar credenciales antes de lanzar el hilo
        if not self._ensure_credentials():
            return

        t = threading.Thread(target=self._update_now_worker,
                             args=(show_popup,), daemon=True)
        t.start()



    def _update_now_worker(self, show_popup: bool):
        try:
            # Mensaje mientras se actualiza
            self.after(0, lambda: self.status_var.set("⏳ Actualizando base de datos..."))

            new_entries, updated_entries = run_update(headless=True)

            def on_done():
                # Momento en que terminamos correctamente
                dt = datetime.now()

                # Texto bonito para la barra
                msg = self._format_ok_status(dt, new_entries, updated_entries)
                self.status_var.set(msg)
                self.update_table()

                # Guardar como último estado correcto (persistente)
                self.cfg.last_status = {
                    "ts": dt.isoformat(timespec="minutes"),
                    "new_entries": int(new_entries),
                    "updated_entries": int(updated_entries),
                }
                save_config(self.cfg)

                if show_popup:
                    # Si algún día quieres popup en actualización manual, lo pones aquí
                    # messagebox.showinfo("Actualización completada", msg)
                    pass

            self.after(0, on_done)


        except Exception as e:
            err_msg = str(e)
            def on_error():
                messagebox.showerror("Error", f"Error en actualización:\n{err_msg}")
                last = getattr(self.cfg, "last_status", None)
                if last:
                    # Construimos mensaje con la última correcta
                    try:
                        ts = last.get("ts")
                        new_entries = int(last.get("new_entries", 0))
                        updated_entries = int(last.get("updated_entries", 0))
                        dt = datetime.fromisoformat(ts)
                        ok_part = self._format_ok_status(dt, new_entries, updated_entries)
                        # ok_part ya empieza con ✅/🟢, lo adaptamos un poco:
                        # quitamos el emoji inicial para reutilizar el texto
                        if ok_part[0] in ("✅", "🟢"):
                            ok_part = ok_part[2:]  # quita "✅ " / "🟢 "
                        self.status_var.set(
                            f"❌ Error en la última actualización. Última correcta: {ok_part}"
                        )
                    except Exception:
                        self.status_var.set("❌ Error en la última actualización.")
                else:
                    self.status_var.set("❌ Error en la última actualización.")

            self.after(0, on_error)



    def schedule_auto_update(self):
        """
        Configura (o detiene) el auto-update según self.cfg.auto_update_enabled
        y self.cfg.auto_update_interval_min. Garantiza que solo haya un timer activo.
        """
        # Si ya había un auto-update programado, lo cancelamos
        if self.auto_update_job is not None:
            try:
                self.after_cancel(self.auto_update_job)
            except Exception:
                pass
            self.auto_update_job = None

        # Si está desactivado en la configuración, no programamos nada
        if not self.cfg.auto_update_enabled:
            # Si quieres, puedes actualizar la barra de estado aquí:
            # self.status_var.set("Auto-actualización desactivada.")
            return

        interval_ms = self.cfg.auto_update_interval_min * 60 * 1000

        def tick():
            # Si mientras tanto se ha desactivado, paramos el bucle
            if not self.cfg.auto_update_enabled:
                self.auto_update_job = None
                return

            # Ejecutamos la actualización silenciosa (sin popups)
            self.update_now_threaded(show_popup=False)

            # Programamos la siguiente ejecución
            self.auto_update_job = self.after(interval_ms, tick)

        # Programamos la primera ejecución
        self.auto_update_job = self.after(interval_ms, tick)
        # Si tienes barra de estado, aquí podrías poner algo tipo:
        # self.status_var.set(f"Auto-actualización cada {self.cfg.auto_update_interval_min} min.")


    # ---------- Abrir OT ----------
    def open_ot_threaded(self, ot):
        # Comprobar credenciales antes de intentar abrir la OT
        if not self._ensure_credentials():
            return

        def worker():
            try:
                session = open_ot(ot, headless=False)  # devuelve (driver, profile_dir)
                if session:
                    self.after(0, lambda s=session: self._register_ot_session(s))
            except Exception as e:
                err_msg = str(e)
                # Y usamos esa variable dentro del callback de Tkinter
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error",
                        f"No se pudo abrir la OT:\n{err_msg}"
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def check_updates(self, notify_popup: bool):
        """
        Comprueba la última release en GitHub.
        - notify_popup=True: si hay versión nueva, muestra popup (solo al arrancar)
        - notify_popup=False: check manual desde Configuración (sin popup)
        """

        def worker():
            import logging

            # Ajustes: al arrancar damos más margen y reintentos
            attempts = 3 if notify_popup else 1
            timeout = 10 if notify_popup else 5
            delays = [0.0, 1.0, 2.0]  # backoff suave

            last_exc = None
            latest = None

            for i in range(attempts):
                try:
                    logging.info(f"Update check: intento {i + 1}/{attempts} (timeout={timeout}s)")
                    if delays[i] > 0:
                        time.sleep(delays[i])

                    latest = fetch_latest_release(timeout_sec=timeout)
                    last_exc = None
                    break

                except Exception as e:
                    last_exc = e
                    logging.info(f"Update check intento {i + 1}/{attempts} falló: {e}")

                logging.warning("Update check falló tras 3 intentos: ...")

            if latest is None:
                # Falló todo: refresca UI pero sin popup
                self.after(0, self._refresh_update_block)
                return

            # Guardamos en config (persistente)
            self.cfg.latest_release_tag = latest.tag
            self.cfg.latest_release_url = latest.html_url
            self.cfg.latest_release_checked_at = latest.checked_at
            save_config(self.cfg)

            def on_ui():
                self._refresh_update_block()

                is_new = is_newer(latest.tag, version.APP_VERSION)
                should_popup = notify_popup and latest.tag and latest.html_url and is_new

                logging.info(
                    f"Update popup check -> "
                    f"notify_popup={notify_popup}, "
                    f"local={version.APP_VERSION}, "
                    f"remote={latest.tag}, "
                    f"is_newer={is_new}, "
                    f"should_popup={should_popup}"
                )

                if should_popup:
                    # Normalizamos el tag SOLO para mostrarlo al usuario
                    raw_tag = latest.tag or ""
                    pretty_tag = format_version_tag(latest.tag)

                    if messagebox.askyesno(
                            "Actualización disponible",
                            f"Hay una nueva versión disponible: {pretty_tag}\n\n"
                            f"¿Quieres abrir la página de la release?",
                            parent=self
                    ):
                        webbrowser.open(latest.html_url)

            self.after(0, on_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _open_latest_release(self):
        url = getattr(self.cfg, "latest_release_url", "") or ""
        if url:
            webbrowser.open(url)

    def _refresh_update_block(self):
        """
        Actualiza labels/botones del bloque de Actualizaciones en Configuración.
        """

        raw_tag = getattr(self.cfg, "latest_release_tag", "") or ""
        checked = getattr(self.cfg, "latest_release_checked_at", "") or ""
        url = getattr(self.cfg, "latest_release_url", "") or ""

        # Versiones bonitas para UI
        installed_ui = format_version_tag(version.APP_VERSION)
        latest_ui = format_version_tag(raw_tag) if raw_tag else "—"

        if hasattr(self, "lbl_installed"):
            self.lbl_installed.config(text=f"Versión instalada: {installed_ui}")

        if hasattr(self, "lbl_latest"):
            self.lbl_latest.config(text=f"Última versión detectada: {latest_ui}")

        if hasattr(self, "lbl_checked"):
            self.lbl_checked.config(text=f"Última comprobación: {checked or '—'}")

        if hasattr(self, "btn_open"):
            self.btn_open.config(state=("normal" if url else "disabled"))



    def _register_ot_session(self, session):
        """Guarda (driver, profile_dir) para mantener viva la ventana y poder limpiarla al cerrar la app."""
        try:
            self.ot_sessions.append(session)
            logging.info(f"OT session registrada. Total sesiones OT: {len(self.ot_sessions)}")
        except Exception:
            logging.exception("No se pudo registrar la sesión OT")

    def on_close(self):
        """Cierre ordenado: cierra navegadores visibles y elimina sus perfiles temporales."""
        sessions = list(getattr(self, "ot_sessions", []) or [])
        for driver, profile_dir in sessions:
            try:
                driver.quit()
            except Exception:
                pass
            try:
                shutil.rmtree(profile_dir, ignore_errors=True)
            except Exception:
                pass
        self.destroy()

if __name__ == "__main__":
    app = MaximoApp()
    app.mainloop()
