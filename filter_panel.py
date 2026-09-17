import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import calendar
from datetime import date

from app_paths import PROFILES_PATH
from db import filter_choices
from search_filters import validate_filters, load_profiles, save_profiles

MONTH_NAMES = ("", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def bind_edit_menu(widget):
    """Añade acciones de portapapeles para usar el ratón en campos editables."""
    menu = tk.Menu(widget, tearoff=0)
    for label, event in (("Cortar", "<<Cut>>"), ("Copiar", "<<Copy>>"),
                         ("Pegar", "<<Paste>>"), ("Seleccionar todo", "<<SelectAll>>")):
        menu.add_command(label=label, command=lambda value=event: widget.event_generate(value))

    def show_menu(event):
        widget.focus_set()
        menu.tk_popup(event.x_root, event.y_root)

    widget.bind("<Button-3>", show_menu, add=True)


class CalendarPicker:
    """Calendario ligero que escribe una fecha ISO en el campo indicado."""
    def __init__(self, parent, variable):
        self.variable = variable
        try:
            selected = date.fromisoformat(variable.get())
        except ValueError:
            selected = date.today()
        self.year, self.month = selected.year, selected.month
        self.window = tk.Toplevel(parent)
        self.window.title("Seleccionar fecha")
        self.window.resizable(False, False)
        self.window.transient(parent.winfo_toplevel())
        self.header = ttk.Frame(self.window)
        self.header.pack(fill="x", padx=8, pady=8)
        ttk.Button(self.header, text="‹", width=3, command=lambda: self.change_month(-1)).pack(side="left")
        self.title = ttk.Label(self.header, anchor="center", font=("", 10, "bold"))
        self.title.pack(side="left", fill="x", expand=True)
        ttk.Button(self.header, text="›", width=3, command=lambda: self.change_month(1)).pack(side="right")
        self.days = ttk.Frame(self.window)
        self.days.pack(padx=8, pady=(0, 8))
        self.render()

    def change_month(self, offset):
        self.month += offset
        if self.month == 13:
            self.year, self.month = self.year + 1, 1
        elif self.month == 0:
            self.year, self.month = self.year - 1, 12
        self.render()

    def render(self):
        for child in self.days.winfo_children():
            child.destroy()
        self.title.configure(text=f"{MONTH_NAMES[self.month]} {self.year}")
        for column, name in enumerate(("Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do")):
            ttk.Label(self.days, text=name, width=3, anchor="center").grid(row=0, column=column, pady=(0, 3))
        for row, week in enumerate(calendar.monthcalendar(self.year, self.month), start=1):
            for column, day in enumerate(week):
                if day:
                    ttk.Button(self.days, text=str(day), width=3,
                               command=lambda value=day: self.select(value)).grid(row=row, column=column)

    def select(self, day):
        self.variable.set(date(self.year, self.month, day).isoformat())
        self.window.destroy()


class FilterPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.path = PROFILES_PATH
        self.profiles = {}
        self.profiles_error = None
        try:
            self.profiles = load_profiles(self.path)
        except (OSError, ValueError) as exc:
            self.profiles_error = str(exc)
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.toggle = ttk.Button(bar, text="Mostrar filtros avanzados", command=self.toggle_panel)
        self.toggle.pack(side="left", padx=5)
        ttk.Label(bar, text="Perfil:").pack(side="left")
        self.profile = tk.StringVar()
        self.combo = ttk.Combobox(bar, textvariable=self.profile, state="readonly", width=28)
        self.combo.pack(side="left", padx=5)
        self.combo.bind("<<ComboboxSelected>>", self.load_selected)
        ttk.Button(bar, text="Guardar perfil…", command=self.save_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Eliminar perfil", command=self.delete_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Limpiar filtros", command=self.clear).pack(side="left", padx=10)
        self.details = ttk.LabelFrame(self, text="Combinar filtros")
        self.visible = False
        self.variables = {key: tk.StringVar() for key in ("equipment", "date_from", "date_to")}
        self.equipment_values = []
        text_row = ttk.Frame(self.details)
        text_row.pack(fill="x", padx=8, pady=5)
        ttk.Label(text_row, text="Equipo (descripción):").pack(side="left", padx=4)
        self.equipment_combo = ttk.Combobox(text_row, textvariable=self.variables["equipment"], width=30)
        self.equipment_combo.pack(side="left")
        self.equipment_combo.bind("<KeyRelease>", self.suggest_equipment)
        self.equipment_combo.bind("<<ComboboxSelected>>", lambda event: self.app.update_table())
        self.equipment_combo.bind("<Return>", lambda event: self.app.update_table())
        bind_edit_menu(self.equipment_combo)
        for key, title in (("date_from", "Desde (AAAA-MM-DD):"), ("date_to", "Hasta:")):
            ttk.Label(text_row, text=title).pack(side="left", padx=4)
            entry = ttk.Entry(text_row, textvariable=self.variables[key], width=12)
            entry.pack(side="left")
            entry.bind("<Return>", lambda event: self.app.update_table())
            bind_edit_menu(entry)
            ttk.Button(text_row, text="📅", width=3,
                       command=lambda value=key: CalendarPicker(self, self.variables[value])).pack(side="left", padx=(2, 4))
        choices_row = ttk.Frame(self.details)
        choices_row.pack(fill="x", padx=8)
        self.boxes = {}
        self.values = {}
        for key, title in (("clients", "Clientes"), ("types", "Estado / tipo de trabajo"), ("tracking", "Seguimiento")):
            frame = ttk.LabelFrame(choices_row, text=title)
            frame.pack(side="left", fill="both", expand=True, padx=4)
            box = tk.Listbox(frame, selectmode="multiple", exportselection=False, height=5)
            scroll = ttk.Scrollbar(frame, command=box.yview)
            box.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            box.pack(fill="both", expand=True)
            self.boxes[key] = box
            self.values[key] = []
        ttk.Label(self.details, text="Pulsa para marcar/desmarcar varias opciones. Sin selección = todos. "
                  "Los clientes avanzados sustituyen al cliente del buscador sencillo.").pack(anchor="w", padx=12, pady=4)
        ttk.Button(self.details, text="Aplicar filtros", command=app.update_table).pack(anchor="e", padx=12, pady=5)
        self.summary = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.summary, wraplength=1400).pack(fill="x", padx=8, pady=5)
        self.refresh_profiles()
        self.refresh_choices()
        if self.profiles_error:
            self.after_idle(lambda: messagebox.showwarning("Perfiles", "No se pudieron cargar los perfiles. "
                "El archivo se conservará sin sobrescribir.\n" + self.profiles_error, parent=app))

    def toggle_panel(self):
        self.visible = not self.visible
        if self.visible:
            self.details.pack(fill="x", before=self.winfo_children()[-1], padx=5, pady=5)
        else:
            self.details.pack_forget()
        self.toggle.configure(text="Ocultar filtros avanzados" if self.visible else "Mostrar filtros avanzados")

    def filters(self):
        data = {key: var.get() for key, var in self.variables.items()}
        data.update({key: [self.values[key][i] for i in box.curselection()] for key, box in self.boxes.items()})
        return validate_filters(data)

    def refresh_choices(self, selected=None):
        if selected is None:
            selected = {key: [self.values[key][i] for i in box.curselection()] for key, box in self.boxes.items()}
        choices = filter_choices()
        self.equipment_values = choices.get("equipment", [])
        self.equipment_combo["values"] = self.equipment_values
        for key, box in self.boxes.items():
            self.values[key] = sorted(set(choices[key]) | set(selected.get(key, [])))
            box.delete(0, "end")
            for i, value in enumerate(self.values[key]):
                box.insert("end", value or "(Sin valor)")
                if value in selected.get(key, []):
                    box.selection_set(i)
        current = self.app.client_var.get()
        self.app.client_combo["values"] = ["Todos"] + sorted(set(v for v in choices["clients"] if v) | ({current} if current != "Todos" else set()))

    def suggest_equipment(self, event=None):
        typed = self.variables["equipment"].get().casefold().strip()
        matches = [value for value in self.equipment_values if typed in value.casefold()] if typed else self.equipment_values
        self.equipment_combo["values"] = matches

    def state(self):
        return {"search": self.app.search_var.get(), "search_by": self.app.search_by.get(),
                "client": self.app.client_var.get(), "advanced": self.filters()}

    def clear(self):
        self.app.search_var.set("")
        self.app.search_by.set("Nº_de_serie")
        self.app.client_var.set("Todos")
        self.profile.set("")
        for var in self.variables.values():
            var.set("")
        for box in self.boxes.values():
            box.selection_clear(0, "end")
        self.app.update_table()

    def refresh_profiles(self):
        self.combo["values"] = sorted(self.profiles, key=str.casefold)

    def load_selected(self, event=None):
        value = self.profiles.get(self.profile.get())
        if value is None:
            return
        self.app.search_var.set(value["search"])
        self.app.search_by.set(value["search_by"])
        self.app.client_var.set(value["client"])
        for key, var in self.variables.items():
            var.set(value["advanced"].get(key, ""))
        self.refresh_choices(value["advanced"])
        self.app.update_table()

    def persist(self, profiles):
        if self.profiles_error:
            messagebox.showerror("Perfiles", "Revisa el archivo de perfiles antes de modificarlo.\n" + self.profiles_error, parent=self.app)
            return False
        try:
            save_profiles(self.path, profiles)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Perfiles", str(exc), parent=self.app)
            return False
        self.profiles = profiles
        self.refresh_profiles()
        return True

    def save_selected(self):
        try:
            value = self.state()
        except ValueError as exc:
            messagebox.showerror("Filtros", str(exc), parent=self.app)
            return
        name = simpledialog.askstring("Guardar perfil", "Nombre (por ejemplo: TMB pendientes):",
                                      initialvalue=self.profile.get(), parent=self.app)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.profiles and not messagebox.askyesno("Guardar perfil", f"¿Sustituir el perfil «{name}»?", parent=self.app):
            return
        if self.persist({**self.profiles, name: value}):
            self.profile.set(name)
            self.app.update_table()

    def delete_selected(self):
        name = self.profile.get()
        if name not in self.profiles:
            return
        if messagebox.askyesno("Eliminar perfil", f"¿Eliminar el perfil «{name}»?", parent=self.app):
            if self.persist({key: value for key, value in self.profiles.items() if key != name}):
                self.profile.set("")
                self.app.update_table()

    def show_result(self, count, advanced):
        parts = []
        for key, label in (("clients", "Clientes"), ("types", "Tipo de trabajo"), ("tracking", "Seguimiento")):
            if advanced[key]:
                parts.append(f"{label}: " + ", ".join(value or "(Sin valor)" for value in advanced[key]))
        for key, label in (("equipment", "Equipo"), ("date_from", "Desde"), ("date_to", "Hasta")):
            if advanced[key]:
                parts.append(f"{label}: {advanced[key]}")
        if not advanced["clients"] and self.app.client_var.get() != "Todos":
            parts.append("Cliente: " + self.app.client_var.get())
        if self.app.search_var.get():
            parts.append(self.app.search_by.get() + ": " + self.app.search_var.get())
        name = self.profile.get()
        prefix = ""
        if name in self.profiles:
            changed = self.state() != self.profiles[name]
            prefix = f"Perfil: {name}" + (" (modificado)" if changed else "") + " · "
        self.summary.set(prefix + f"{count} resultados" + (" · " + " | ".join(parts) if parts else " · Sin filtros"))
