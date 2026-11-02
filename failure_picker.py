"""Selección de una ruta completa del catálogo de anomalías en Qt."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from failure_catalog import catalog_payload, choices, resolve_selection


class FailurePathPicker(QWidget):
    selection_changed = Signal()

    def __init__(self, parent=None, combo_factory=QComboBox):
        super().__init__(parent)
        self._combo_factory = combo_factory
        self._levels = []
        self._loading = False
        self._unresolved = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        outer.addLayout(self.form)
        self.class_combo = self._make_combo()
        self.class_combo.addItem("Elegir clase de anomalía…", None)
        for entry in catalog_payload()["classes"]:
            label = f"{entry['code']} — {entry.get('description') or 'Sin descripción'}"
            self.class_combo.addItem(label, entry["key"])
            self.class_combo.setItemData(self.class_combo.count() - 1, label, Qt.ToolTipRole)
        self.form.addRow("Clase de anomalía", self.class_combo)
        self.hint = QLabel()
        self.hint.setObjectName("filterHint")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)
        self.class_combo.currentIndexChanged.connect(self._class_changed)
        self._update_hint()

    def _make_combo(self):
        combo = self._combo_factory()
        # Long catalogue descriptions must not widen the two-column settings.
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.currentTextChanged.connect(combo.setToolTip)
        return combo

    def _clear_levels(self, start=0):
        while len(self._levels) > start:
            _, combo = self._levels.pop()
            row = self.form.takeRow(combo)
            for item in (row.labelItem, row.fieldItem):
                if item is not None and item.widget() is not None:
                    item.widget().hide()
                    item.widget().deleteLater()

    def _path(self):
        keys = []
        for _, combo in self._levels:
            key = combo.currentData()
            if key is None:
                break
            keys.append(key)
        return keys

    def selection(self):
        if self._unresolved is not None:
            return deepcopy(self._unresolved)
        return {"class_key": self.class_combo.currentData(), "option_keys": self._path()}

    def _append_level(self):
        class_key = self.class_combo.currentData()
        if not class_key:
            return
        try:
            options = choices(class_key, self._path())
        except ValueError:
            return
        if not options:
            return
        kinds = {option["type"] for option in options}
        labels = {"PROBLEM": "Síntoma", "CAUSE": "Causa", "REMEDY": "Resolución"}
        caption = labels.get(next(iter(kinds)), "Código") if len(kinds) == 1 else "Código"
        combo = self._make_combo()
        combo.addItem(f"Elegir {caption.lower()}…", None)
        for option in options:
            description = option.get("description") or "Sin descripción"
            label = f"{option['code']} — {description}"
            if len(kinds) != 1:
                label = f"{labels.get(option['type'], option['type'])}: {label}"
            combo.addItem(label, option["key"])
            combo.setItemData(combo.count() - 1, label, Qt.ToolTipRole)
        index = len(self._levels)
        self._levels.append((caption, combo))
        self.form.addRow(caption, combo)
        combo.currentIndexChanged.connect(lambda _value, level=index: self._level_changed(level))

    def _class_changed(self, _index):
        if self._loading:
            return
        self._unresolved = None
        self._clear_levels()
        self._append_level()
        self._update_hint()
        self.selection_changed.emit()

    def _level_changed(self, level):
        if self._loading:
            return
        self._unresolved = None
        self._clear_levels(level + 1)
        if self._levels[level][1].currentData() is not None:
            self._append_level()
        self._update_hint()
        self.selection_changed.emit()

    def _update_hint(self):
        try:
            resolved = resolve_selection(self.selection())
        except (TypeError, ValueError):
            self.hint.setText(
                "La combinación guardada necesita revisión. Elige una ruta completa."
                if self._unresolved is not None else
                "Elige una ruta completa. Al cambiar un nivel se limpian sus opciones dependientes."
            )
            return
        self.hint.setText("Predeterminada: " + resolved["class_code"] + " → " +
                          " → ".join(node["code"] for node in resolved["path"]))

    def set_selection(self, selection):
        self._loading = True
        self._unresolved = None
        self._clear_levels()
        try:
            spec = selection if isinstance(selection, dict) else {}
            self.class_combo.setCurrentIndex(max(0, self.class_combo.findData(spec.get("class_key"))))
            self._append_level()
            keys = spec.get("option_keys", [])
            for key in keys if isinstance(keys, list) else []:
                if not isinstance(key, str):
                    break
                if not self._levels:
                    break
                combo = self._levels[-1][1]
                index = combo.findData(key)
                if index < 1:
                    break
                combo.setCurrentIndex(index)
                self._append_level()
            if self.selection() != selection:
                self._unresolved = deepcopy(selection)
        finally:
            self._loading = False
        self._update_hint()
