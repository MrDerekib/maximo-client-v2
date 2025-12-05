# gui_main.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from config import load_config, save_config, set_credentials, AppConfig, credentials_configured
from db import fetch_data, init_db
from maximo_client import open_ot
from updater import run_update


class MaximoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cliente Maximo (Refactor)")
        self.geometry("1100x650")

        self.cfg: AppConfig = load_config()

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
        ttk.Button(top_frame, text="Actualizar ahora", command=self.update_now_threaded).pack(side="right", padx=5)

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

        # Usuario / contraseña
        ttk.Label(frame, text="Usuario Maximo:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.user_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.user_var, width=30).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Contraseña Maximo:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.pass_var, width=30, show="*").grid(row=1, column=1, padx=5, pady=5)

        # Auto-update
        self.auto_update_var = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Auto-actualizar en segundo plano",
                        variable=self.auto_update_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(frame, text="Intervalo (minutos):").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.interval_var = tk.IntVar()
        ttk.Entry(frame, textvariable=self.interval_var, width=10).grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(frame, text="Guardar configuración", command=self.save_config_from_ui)\
            .grid(row=4, column=0, columnspan=2, pady=15)

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

        if self.cfg.auto_update_enabled:
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
    def update_now_threaded(self):
        # Comprobar credenciales antes de lanzar el hilo
        if not self._ensure_credentials():
            return

        t = threading.Thread(target=self._update_now_worker, daemon=True)
        t.start()


    def _update_now_worker(self):
        try:
            run_update(headless=True)
            self.after(0, self.update_table)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Error en actualización:\n{e}"))

    def schedule_auto_update(self):
        interval_ms = self.cfg.auto_update_interval_min * 60 * 1000

        def tick():
            if self.cfg.auto_update_enabled:
                self.update_now_threaded()
                self.after(interval_ms, tick)

        self.after(interval_ms, tick)

    # ---------- Abrir OT ----------
    def open_ot_threaded(self, ot):
        # Comprobar credenciales antes de intentar abrir la OT
        if not self._ensure_credentials():
            return

        def worker():
            try:
                open_ot(ot, headless=False)  # aquí normal, para que veas la ventana
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"No se pudo abrir la OT:\n{e}"))

        threading.Thread(target=worker, daemon=True).start()



if __name__ == "__main__":
    app = MaximoApp()
    app.mainloop()
