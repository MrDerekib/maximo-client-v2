"""Checkboxes mirror Qt's row selection without changing the table's data columns."""
from PySide6.QtCore import QEvent, QItemSelection, QItemSelectionModel, QModelIndex, QObject, QPointF, QPersistentModelIndex, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QStyledItemDelegate, QStyle, QStyleFactory, QStyleOptionButton, QStyleOptionViewItem, QWidget


class VisibleRowsCheckBox(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.indicator_style = QStyleFactory.create('Fusion')
        self.indicator_style.setParent(self)

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QPainter(self)
        if self.isEnabled() and self.checkState() != Qt.Unchecked:
            painter.setRenderHint(QPainter.Antialiasing)
            side = min(16, self.width() - 2, self.height() - 2)
            box = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#1976d2'))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QPen(QColor('white'), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            point = lambda x, y: QPointF(box.left() + side*x, box.top() + side*y)
            if self.checkState() == Qt.PartiallyChecked:
                painter.drawLine(point(0.26, 0.5), point(0.74, 0.5))
            else:
                painter.drawPolyline(QPolygonF([point(0.23, 0.51), point(0.43, 0.71), point(0.77, 0.30)]))
            if self.hasFocus():
                painter.setPen(QPen(QColor('#93c5fd'), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(box.adjusted(-1, -1, 1, 1), 4, 4)
        else:
            self.indicator_style.drawControl(QStyle.CE_CheckBox, option, painter, self)
        painter.end()

    def nextCheckState(self):
        # Partial is a display state, not an extra step for the user.
        self.setCheckState(Qt.Unchecked if self.checkState() == Qt.Checked else Qt.Checked)


class SelectionIndicatorDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.item_style = QStyleFactory.create('Fusion')
        self.item_style.setParent(self)

    def paint(self, painter, option, index):
        # Windows 11's native item drawing can override the stylesheet's
        # selection colors and lose the check mark. Paint only this table's
        # cells consistently, keeping the app's fonts, colors and item roles.
        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        view_option.showDecorationSelected = True
        view_option.palette.setCurrentColorGroup(QPalette.Active)
        self.item_style.drawControl(QStyle.CE_ItemViewItem, view_option, painter, view_option.widget)

    def indicator_rect(self, table, index):
        option = QStyleOptionViewItem()
        option.initFrom(table.viewport())
        self.initStyleOption(option, index)
        option.rect = table.visualRect(index)
        return self.item_style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, table.viewport())


def prepare_row_context_selection(table, index):
    """Keep an existing row selection when opening its context menu."""
    if table.selectionModel().isRowSelected(index.row()):
        table.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)
    else:
        table.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        table.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)


class WorkorderSelection(QObject):
    def __init__(self, table, parent=None):
        super().__init__(parent or table)
        self.table = table
        self.enabled = False
        self._syncing = False
        self._refresh_pending = False
        self._pressed = QPersistentModelIndex()
        self._pressed_active = False
        self._anchor = QPersistentModelIndex()
        self._selected_rows = set()
        self.delegate = SelectionIndicatorDelegate(table)
        self.original_delegate = table.itemDelegate()
        self.bar = QWidget()
        layout = QHBoxLayout(self.bar)
        layout.setContentsMargins(0, 2, 0, 2)
        self.counter = QLabel('0 OTs seleccionadas')
        self.hint = QLabel('Marca casillas o usa Ctrl/Mayús. La casilla superior selecciona las filas visibles.')
        self.hint.setObjectName('filterHint')
        self.hint.setWordWrap(True)
        self.clear_button = QPushButton('Limpiar selección')
        self.clear_button.clicked.connect(self.clear_selection)
        layout.addWidget(self.counter)
        layout.addWidget(self.hint, 1)
        layout.addWidget(self.clear_button)
        self.all_checkbox = VisibleRowsCheckBox(table)
        self.all_checkbox.setTristate(True)
        self.all_checkbox.setAccessibleName('Seleccionar todas las OTs visibles')
        self.all_checkbox.setToolTip('Seleccionar o desmarcar todas las filas visibles')
        self.all_checkbox.clicked.connect(self._toggle_all)
        table.viewport().installEventFilter(self)
        table.installEventFilter(self)
        table.horizontalHeader().installEventFilter(self)
        table.verticalHeader().installEventFilter(self)
        table.selectionModel().selectionChanged.connect(self._selection_changed)
        table.itemChanged.connect(self._item_changed)
        model = table.model()
        for signal in (model.modelReset, model.rowsInserted, model.rowsRemoved, model.layoutChanged):
            signal.connect(self._queue_refresh)
        self.bar.hide()
        self.all_checkbox.hide()

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if self.enabled == enabled:
            return
        self.enabled = enabled
        self.table.setItemDelegate(self.delegate if enabled else self.original_delegate)
        self.bar.setVisible(enabled)
        self.table.setCornerButtonEnabled(not enabled)
        self.all_checkbox.setVisible(enabled)
        if not enabled:
            self.clear_selection()
        self.refresh()

    def _visible_rows(self):
        return [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def clear_selection(self):
        self.table.clearSelection()
        self._anchor = QPersistentModelIndex()
        self._selection_changed()

    def _queue_refresh(self, *_args):
        if not self._refresh_pending:
            self._refresh_pending = True
            QTimer.singleShot(0, self, self.refresh)

    def refresh(self):
        self._refresh_pending = False
        self.counter.ensurePolished()
        palette = self.table.palette()
        palette.setColor(QPalette.Text, self.counter.palette().color(QPalette.WindowText))
        self.table.setPalette(palette)
        self._syncing = True
        try:
            # Visibility filters do not necessarily rebuild the model.
            for index in self.table.selectionModel().selectedRows():
                if self.enabled and self.table.isRowHidden(index.row()):
                    self.table.selectionModel().select(index, QItemSelectionModel.Deselect | QItemSelectionModel.Rows)
            selected = {index.row() for index in self.table.selectionModel().selectedRows()}
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                if self.enabled:
                    flags = item.flags() | Qt.ItemIsUserCheckable
                    if item.flags() != flags:
                        item.setFlags(flags)
                    state = Qt.Checked if row in selected else Qt.Unchecked
                    if item.data(Qt.CheckStateRole) is None or item.checkState() != state:
                        item.setCheckState(state)
                else:
                    flags = item.flags() & ~Qt.ItemIsUserCheckable
                    if item.flags() != flags:
                        item.setFlags(flags)
                    if item.data(Qt.CheckStateRole) is not None:
                        item.setData(Qt.CheckStateRole, None)
            self._selected_rows = selected
        finally:
            self._syncing = False
        self._update_summary()

    def _selection_changed(self, *_args):
        if self._syncing:
            return
        selected = {index.row() for index in self.table.selectionModel().selectedRows()}
        self._syncing = True
        try:
            if self.enabled:
                for row in selected ^ self._selected_rows:
                    item = self.table.item(row, 0)
                    if item is not None:
                        item.setCheckState(Qt.Checked if row in selected else Qt.Unchecked)
            self._selected_rows = selected
        finally:
            self._syncing = False
        self._update_summary()

    def _item_changed(self, item):
        if self._syncing or not self.enabled or item.column() != 0:
            return
        if not item.flags() & Qt.ItemIsUserCheckable:
            return
        checked = item.checkState() == Qt.Checked
        selected = self.table.selectionModel().isRowSelected(item.row())
        if checked != selected:
            flag = QItemSelectionModel.Select if checked else QItemSelectionModel.Deselect
            self.table.selectionModel().select(self.table.indexFromItem(item), flag | QItemSelectionModel.Rows)

    def _update_summary(self):
        visible = set(self._visible_rows())
        count = len(self._selected_rows & visible)
        self.counter.setText(f'{count} OT seleccionada' if count == 1 else f'{count} OTs seleccionadas')
        self.clear_button.setEnabled(bool(self._selected_rows))
        state = Qt.Unchecked if not count else Qt.Checked if count == len(visible) else Qt.PartiallyChecked
        blocked = self.all_checkbox.blockSignals(True)
        self.all_checkbox.setCheckState(state)
        self.all_checkbox.blockSignals(blocked)
        self.all_checkbox.setEnabled(bool(visible))
        self._position_header_checkbox()

    def _position_header_checkbox(self):
        vertical, horizontal = self.table.verticalHeader(), self.table.horizontalHeader()
        size = self.all_checkbox.sizeHint()
        self.all_checkbox.setGeometry(vertical.x() + max(0, (vertical.width() - size.width()) // 2),
                                      horizontal.y() + max(0, (horizontal.height() - size.height()) // 2),
                                      size.width(), size.height())
        self.all_checkbox.setVisible(self.enabled and vertical.width() >= size.width()
                                     and not vertical.isHidden() and not horizontal.isHidden())
        self.all_checkbox.raise_()

    def _toggle_all(self, _checked):
        if not self.enabled:
            return
        if self.all_checkbox.checkState() != Qt.Checked:
            self.clear_selection()
            return
        rows = self._visible_rows()
        selection = QItemSelection()
        if rows:
            first = previous = rows[0]
            for row in [*rows[1:], None]:
                if row is None or row != previous + 1:
                    selection.select(self.table.model().index(first, 0),
                                     self.table.model().index(previous, self.table.columnCount() - 1))
                    first = row
                previous = row
        self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)

    def _toggle_row(self, index, modifiers):
        row = index.row()
        selected = self.table.selectionModel().isRowSelected(row)
        if modifiers & Qt.ShiftModifier and self._anchor.isValid():
            start, end = sorted((self._anchor.row(), row))
            selection = QItemSelection()
            for current in range(start, end + 1):
                if not self.table.isRowHidden(current):
                    selection.select(self.table.model().index(current, 0),
                                     self.table.model().index(current, self.table.columnCount() - 1))
            self.table.selectionModel().select(selection, QItemSelectionModel.Select)
        else:
            flag = QItemSelectionModel.Deselect if selected else QItemSelectionModel.Select
            self.table.selectionModel().select(index, flag | QItemSelectionModel.Rows)
            self._anchor = QPersistentModelIndex(index)
        self.table.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)

    def eventFilter(self, watched, event):
        if self.enabled and watched is self.table.viewport():
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                index = self.table.indexAt(event.position().toPoint())
                if index.isValid() and index.column() == 0 and self.delegate.indicator_rect(
                        self.table, index).contains(event.position().toPoint()):
                    self._pressed = QPersistentModelIndex(index)
                    self._pressed_active = True
                    self.table.setFocus(Qt.MouseFocusReason)
                    return True
            if event.type() == QEvent.MouseButtonRelease and self._pressed_active:
                self._pressed_active = False
                index = QModelIndex(self._pressed)
                self._pressed = QPersistentModelIndex()
                if index.isValid() and self.delegate.indicator_rect(self.table, index).contains(event.position().toPoint()):
                    self._toggle_row(index, event.modifiers())
                return True
            if event.type() == QEvent.MouseButtonDblClick:
                index = self.table.indexAt(event.position().toPoint())
                if index.isValid() and index.column() == 0 and self.delegate.indicator_rect(
                        self.table, index).contains(event.position().toPoint()):
                    return True
        if event.type() in (QEvent.Resize, QEvent.Show, QEvent.StyleChange):
            self._position_header_checkbox()
        return super().eventFilter(watched, event)
