"""Local warehouse demo with fictitious OTs, no credentials, browser or database."""
import os
from pathlib import Path
import sys

os.environ['MAXIMO_DESKTOP_DEV'] = '1'
os.environ['MAXIMO_DESKTOP_WAREHOUSE_DEV'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QLabel, QMainWindow,
                              QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from config import AppConfig
from ui_qt import apply_application_theme
from warehouse_ui import WarehouseWindowMixin
from warehouse_selection import WarehouseSelection
from warehouse import warehouse_status_code


class WarehouseDemo(WarehouseWindowMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig()
        self._closing = False
        self.setWindowTitle('Maximo Desktop · Almacén · Demostración aislada')
        self.resize(1100, 680)
        root = QWidget(); layout = QVBoxLayout(root)
        title = QLabel('Funciones de almacén · Datos ficticios')
        title.setStyleSheet('font-size: 24px; font-weight: 600')
        layout.addWidget(title)
        hint = QLabel('Activa las funciones, marca casillas o selecciona filas con Ctrl/Mayús '
                      'y usa el botón secundario. Ninguna acción de esta demostración accede a Maximo.')
        hint.setWordWrap(True); layout.addWidget(hint)
        self.warehouse_check = QCheckBox('Mostrar acciones de almacén')
        self.warehouse_check.toggled.connect(self._warehouse_enabled)
        layout.addWidget(self.warehouse_check)
        self.table = QTableWidget(6, 8)
        self.table.setHorizontalHeaderLabels(('Presencia', 'OT', 'Equipo', 'Nº de serie', 'Fecha',
                                             'Cliente', 'Tipo', 'Estado del listado'))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        for row in range(6):
            values = ('Ficticia', f'DEMO-{row+1:03}', f'Equipo de prueba {row+1}', f'SN-DEMO-{row+1}',
                      '', 'Cliente de prueba', 'REPARACION', 'PDTE CONFIRMAR' if row < 4 else 'DAR SALIDA')
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self._warehouse_selector = WarehouseSelection(self.table, self)
        self._warehouse_selector.counter.ensurePolished()
        self.warehouse_check.setPalette(self._warehouse_selector.counter.palette())
        self.table.horizontalHeader().setStretchLastSection(True)
        self.state_filter = QComboBox()
        self.state_filter.addItem('Todos los estados', '')
        self.state_filter.addItem('Pendientes de recepción · PDTE CONFIRMAR', 'WAPPR')
        self.state_filter.addItem('Pendientes de salida · DAR SALIDA', 'ISSUE')
        self.state_filter.currentIndexChanged.connect(self._filter_rows)
        layout.addWidget(self.state_filter)
        layout.addWidget(self._warehouse_selector.bar)
        layout.addWidget(self.table, 1)
        layout.addWidget(QLabel('Recepción: DEMO-001 a DEMO-004 · Salida: DEMO-005 y DEMO-006'))
        self.setCentralWidget(root)

    def _warehouse_enabled(self, enabled):
        self.cfg.warehouse_enabled = enabled
        self._warehouse_selector.set_enabled(enabled)

    def _filter_rows(self):
        self._warehouse_selector.clear_selection()
        status = self.state_filter.currentData()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, bool(status) and warehouse_status_code(self.table.item(row, 7).text()) != status)
        self._warehouse_selector.refresh()

    def show_context_menu(self, point):
        index = self.table.indexAt(point)
        if not index.isValid():
            return
        self.prepare_warehouse_context_selection(index)
        menu = QMenu(self)
        if self.cfg.warehouse_enabled:
            self.add_warehouse_actions(menu)
        else:
            menu.addAction('Activa «Mostrar acciones de almacén» para probarlas').setEnabled(False)
        menu.exec(self.table.viewport().mapToGlobal(point))

    def open_ot_number(self, ot):
        QMessageBox.information(self, 'OT ficticia', f'{ot} es un dato de demostración. '
                                'En MD, este enlace abrirá la ficha real en Edge para revisión manual.')

    def closeEvent(self, event):
        if self.warehouse_is_running():
            for dialog in self._warehouse_dialogs:
                if dialog.is_running():
                    dialog.request_stop(); dialog.show(); dialog.raise_()
            event.ignore()
            return
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    apply_application_theme(app, 'light')
    window = WarehouseDemo()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
