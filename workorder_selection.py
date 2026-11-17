"""Persistent OT marks, independent of the active row, with a full-cell gutter."""
from shiboken6 import isValid
from appearance import readable_color
from PySide6.QtCore import QEvent,QItemSelection,QItemSelectionModel,QModelIndex,QObject,QPointF,QPersistentModelIndex,QRectF,QTimer,Qt
from PySide6.QtGui import QColor,QPainter,QPalette,QPen,QPolygonF
from PySide6.QtWidgets import QApplication,QAbstractButton,QSplitterHandle,QCheckBox,QHeaderView,QHBoxLayout,QLabel,QPushButton,QStyledItemDelegate,QStyle,QStyleFactory,QStyleOptionViewItem,QWidget


def _paint_check(painter,rect,palette,state):
    painter.save();painter.setRenderHint(QPainter.Antialiasing)
    side=20;box=QRectF(rect.center().x()-side/2,rect.center().y()-side/2,side,side)
    accent=palette.color(QPalette.Link)
    painter.setPen(QPen(palette.color(QPalette.Mid),1.3))
    painter.setBrush(palette.color(QPalette.Base))
    if state!=Qt.Unchecked:
        painter.setPen(QPen(accent,1));painter.setBrush(accent)
    painter.drawRoundedRect(box,4,4)
    if state!=Qt.Unchecked:
        painter.setPen(QPen(QColor(readable_color('#ffffff',[accent.name()],4.5)),2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        point=lambda x,y:QPointF(box.left()+side*x,box.top()+side*y)
        if state==Qt.PartiallyChecked:painter.drawLine(point(.25,.5),point(.75,.5))
        else:painter.drawPolyline(QPolygonF([point(.23,.51),point(.43,.71),point(.77,.30)]))
    painter.restore()


class VisibleRowsCheckBox(QCheckBox):
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),self.palette().color(QPalette.Button))
        painter.setPen(self.palette().color(QPalette.Mid))
        painter.drawLine(self.rect().topRight(),self.rect().bottomRight())
        painter.drawLine(self.rect().bottomLeft(),self.rect().bottomRight())
        _paint_check(painter,QRectF(self.rect()),self.palette(),self.checkState())
        painter.end()

    def hitButton(self,point):return self.rect().contains(point)

    def nextCheckState(self):
        self.setCheckState(Qt.Unchecked if self.checkState()==Qt.Checked else Qt.Checked)


class SelectionGutter(QHeaderView):
    """A dedicated visual column; data/export column indexes remain unchanged."""
    def __init__(self,selector):
        super().__init__(Qt.Vertical,selector.table)
        self.selector=selector;self.hover_row=-1
        self.setFixedWidth(44);self.setMouseTracking(True)
        self.setAccessibleName('Marcar órdenes de trabajo')
        self.setToolTip('Pulsa en cualquier punto de esta columna para marcar la OT. Mayús selecciona un rango.')

    def paintSection(self,painter,rect,logical):
        if not self.selector.enabled:return super().paintSection(painter,rect,logical)
        painter.save()
        painter.fillRect(rect,self.palette().color(QPalette.Button))
        if logical==self.hover_row:painter.fillRect(rect,self.palette().color(QPalette.Highlight))
        painter.setPen(self.palette().color(QPalette.Mid))
        painter.drawLine(rect.bottomLeft(),rect.bottomRight())
        painter.drawLine(rect.topRight(),rect.bottomRight())
        _paint_check(painter,QRectF(rect),self.palette(),Qt.Checked if self.selector.is_marked(logical) else Qt.Unchecked)
        painter.restore()


class SelectionIndicatorDelegate(QStyledItemDelegate):
    def __init__(self,selector):
        super().__init__(selector.table);self.selector=selector
        self.item_style=QStyleFactory.create('Fusion');self.item_style.setParent(self)

    def paint(self,painter,option,index):
        view=QStyleOptionViewItem(option);self.initStyleOption(view,index)
        view.showDecorationSelected=True;view.palette.setCurrentColorGroup(QPalette.Active)
        view.state &= ~QStyle.State_Selected
        if self.selector.is_marked(index.row()):view.state |= QStyle.State_Selected
        self.item_style.drawControl(QStyle.CE_ItemViewItem,view,painter,view.widget)
        # Focus is a fine outline; it never replaces the marked batch.
        if self.selector.table.hasFocus() and index.row()==self.selector.table.currentRow():
            painter.save();painter.setPen(QPen(view.palette.color(QPalette.Link),1,Qt.DotLine))
            painter.drawLine(view.rect.topLeft(),view.rect.topRight())
            painter.drawLine(view.rect.bottomLeft(),view.rect.bottomRight());painter.restore()


def prepare_row_context_selection(table,index):
    selector=getattr(table,'_ot_selector',None)
    if selector is not None and selector.enabled:
        selector.prepare_context(index);return
    if table.selectionModel().isRowSelected(index.row()):
        table.selectionModel().setCurrentIndex(index,QItemSelectionModel.NoUpdate)
    else:
        table.selectionModel().select(index,QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)
        table.selectionModel().setCurrentIndex(index,QItemSelectionModel.NoUpdate)


def action_rows(table):
    selector=getattr(table,'_ot_selector',None)
    if selector is not None and selector.enabled:return selector.action_rows()
    return sorted({index.row() for index in table.selectionModel().selectedRows()})


class WorkorderSelection(QObject):
    def __init__(self,table,parent=None,*,compact=False):
        super().__init__(parent or table)
        self.table=table;table._ot_selector=self;self.compact=compact;self.enabled=False
        self._syncing=False;self._refresh_pending=False;self._preserve_marks=False;self._explicit_selection=False
        self._marks={};self._marked_rows=set();self._anchor=QPersistentModelIndex()
        self._pressed=QPersistentModelIndex();self._context=QPersistentModelIndex()
        self.original_delegate=table.itemDelegate()
        self.delegate=SelectionIndicatorDelegate(self)
        self.gutter=SelectionGutter(self);table.setVerticalHeader(self.gutter)
        self.bar=QWidget();layout=QHBoxLayout(self.bar);layout.setContentsMargins(0,0,0,0)
        self.counter=QLabel('0 OTs seleccionadas')
        self.hint=QLabel('Marca en la columna izquierda o usa Ctrl/Mayús. Las marcas se mantienen al consultar otras filas.')
        self.hint.setObjectName('filterHint');self.hint.setWordWrap(True)
        self.clear_button=QPushButton('Limpiar selección');self.clear_button.clicked.connect(self.clear_selection)
        layout.addWidget(self.counter)
        if compact:
            self.hint.hide();self.counter.setToolTip(self.hint.text())
            policy=self.clear_button.sizePolicy();policy.setRetainSizeWhenHidden(True);self.clear_button.setSizePolicy(policy)
        else:layout.addWidget(self.hint,1)
        layout.addWidget(self.clear_button)
        self.all_checkbox=VisibleRowsCheckBox(table);self.all_checkbox.setTristate(True)
        self.all_checkbox.setAccessibleName('Seleccionar todas las OTs visibles')
        self.all_checkbox.setToolTip('Seleccionar o desmarcar todas las filas visibles')
        self.all_checkbox.clicked.connect(self._toggle_all)
        QApplication.instance().installEventFilter(self)
        table.selectionModel().selectionChanged.connect(self._selection_changed)
        model=table.model()
        for signal in (model.modelReset,model.rowsInserted,model.rowsRemoved,model.layoutChanged):signal.connect(self._queue_refresh)
        self.bar.hide();self.all_checkbox.hide()

    def set_enabled(self,enabled):
        enabled=bool(enabled)
        if self.enabled==enabled:return
        self.enabled=enabled;self.table.setItemDelegate(self.delegate if enabled else self.original_delegate)
        self.bar.setVisible(enabled);self.table.setCornerButtonEnabled(not enabled)
        if not enabled:self.clear_selection()
        self.refresh()

    def _visible_rows(self):return [r for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)]

    def _key(self,row):
        item=self.table.item(row,1)
        return item.text() if item else str(row)

    def selected_rows(self):
        if not isValid(self.table):return []
        self._marks={key:index for key,index in self._marks.items() if index.isValid() and not self.table.isRowHidden(index.row())}
        self._marked_rows={index.row() for index in self._marks.values()}
        return sorted(self._marked_rows)

    def is_marked(self,row):return row in self._marked_rows

    def _set_rows(self,rows,*,sync=True):
        self._marks={self._key(row):QPersistentModelIndex(self.table.model().index(row,0))
                     for row in rows if 0<=row<self.table.rowCount() and not self.table.isRowHidden(row)}
        self.selected_rows();self.clear_context()
        if sync:self._sync_qt_selection()
        self._update_summary();self.table.viewport().update();self.gutter.viewport().update()

    def _sync_qt_selection(self):
        selection=QItemSelection()
        rows=self.selected_rows()
        if rows:
            first=previous=rows[0]
            for row in [*rows[1:],None]:
                if row is None or row!=previous+1:
                    selection.select(self.table.model().index(first,0),self.table.model().index(previous,self.table.columnCount()-1));first=row
                previous=row
        self._syncing=True
        try:self.table.selectionModel().select(selection,QItemSelectionModel.ClearAndSelect)
        finally:self._syncing=False

    def clear_selection(self):
        self._set_rows([]);self._anchor=QPersistentModelIndex()

    def clear_context(self):self._context=QPersistentModelIndex()

    def prepare_context(self,index):
        self._context=QPersistentModelIndex(index)
        self.table.selectionModel().setCurrentIndex(index,QItemSelectionModel.NoUpdate)

    def action_rows(self):
        rows=self.selected_rows()
        if self._context.isValid():
            row=self._context.row()
            return rows if row in rows else [row]
        return rows or sorted({i.row() for i in self.table.selectionModel().selectedRows() if not self.table.isRowHidden(i.row())})

    def _queue_refresh(self,*args):
        if not isValid(self.table):return
        if not self._refresh_pending:
            self._refresh_pending=True;QTimer.singleShot(0,self,self.refresh)

    def refresh(self):
        if not isValid(self.table) or not isValid(self.gutter):return
        self._refresh_pending=False
        self.counter.ensurePolished()
        palette=self.table.palette();palette.setColor(QPalette.Text,self.counter.palette().color(QPalette.WindowText));self.table.setPalette(palette)
        self.selected_rows();self._update_summary();self.gutter.viewport().update();self.table.viewport().update()

    def _selection_changed(self,*args):
        if self._syncing or not self.enabled or not isValid(self.table):return
        self.clear_context()
        if not self._preserve_marks and (self._explicit_selection or not self._marks):
            self._set_rows({i.row() for i in self.table.selectionModel().selectedRows()},sync=False)
        self.table.viewport().update()

    def _update_summary(self):
        count=len(self.selected_rows());visible=self._visible_rows()
        self.counter.setText(f'{count} OT seleccionada' if count==1 else f'{count} OTs seleccionadas')
        self.clear_button.setEnabled(bool(count))
        if self.compact:self.clear_button.setVisible(bool(count))
        state=Qt.Unchecked if not count else Qt.Checked if count==len(visible) else Qt.PartiallyChecked
        blocked=self.all_checkbox.blockSignals(True);self.all_checkbox.setCheckState(state);self.all_checkbox.blockSignals(blocked)
        self.all_checkbox.setEnabled(bool(visible));self._position_header_checkbox()

    def _position_header_checkbox(self):
        if not isValid(self.table) or not isValid(self.gutter) or not isValid(self.all_checkbox):return
        vertical,horizontal=self.gutter,self.table.horizontalHeader()
        self.all_checkbox.setGeometry(vertical.x(),horizontal.y(),vertical.width(),horizontal.height())
        self.all_checkbox.setVisible(self.enabled and not vertical.isHidden() and not horizontal.isHidden());self.all_checkbox.raise_()

    def _toggle_all(self,*args):
        if self.enabled:self._set_rows(self._visible_rows() if self.all_checkbox.checkState()==Qt.Checked else [])

    def _toggle_row(self,index,modifiers):
        row=index.row();rows=set(self.selected_rows())
        if modifiers & Qt.ShiftModifier and self._anchor.isValid():
            start,end=sorted((self._anchor.row(),row));rows.update(r for r in range(start,end+1) if not self.table.isRowHidden(r))
        else:
            if row in rows:rows.remove(row)
            else:rows.add(row)
            self._anchor=QPersistentModelIndex(index)
        self._set_rows(rows);self.table.selectionModel().setCurrentIndex(index,QItemSelectionModel.NoUpdate)

    def _same_window(self,widget):
        return isinstance(widget,QWidget) and isValid(widget) and widget.window() is self.table.window()

    def _outside_click_clears(self,widget,event):
        if not self._same_window(widget) or not self.table.isVisible():return False
        point=self.table.mapFromGlobal(event.globalPosition().toPoint())
        if self.table.rect().contains(point):return False
        # Buttons may open an operation or a menu using this batch. Never clear
        # it before their clicked signal runs. Separate dialogs/menus are scoped out.
        current=widget
        while current is not None:
            if isinstance(current,(QAbstractButton,QSplitterHandle)):return False
            current=current.parentWidget()
        return True

    def eventFilter(self,watched,event):
        if not isValid(self.table) or not isValid(self.gutter):return False
        if self.enabled and self._marks:
            if event.type()==QEvent.KeyPress and event.key()==Qt.Key_Escape and self._same_window(watched):
                self.clear_selection();return True
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton and self._outside_click_clears(watched,event):
                self.clear_selection()
        if self.enabled and watched is self.gutter.viewport():
            if event.type()==QEvent.MouseMove:
                self.gutter.hover_row=self.gutter.logicalIndexAt(event.position().toPoint());self.gutter.viewport().update()
            elif event.type()==QEvent.Leave:
                self.gutter.hover_row=-1;self.gutter.viewport().update()
            elif event.type()==QEvent.MouseButtonDblClick:return True
            elif event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                row=self.gutter.logicalIndexAt(event.position().toPoint())
                self._pressed=QPersistentModelIndex(self.table.model().index(row,0));self.table.setFocus(Qt.MouseFocusReason);return True
            elif event.type()==QEvent.MouseButtonRelease and event.button()==Qt.LeftButton:
                index=QModelIndex(self._pressed);self._pressed=QPersistentModelIndex()
                if index.isValid() and self.gutter.viewport().rect().contains(event.position().toPoint()) and index.row()==self.gutter.logicalIndexAt(event.position().toPoint()):self._toggle_row(index,event.modifiers())
                return True
        if self.enabled and watched is self.table.viewport():
            if event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonDblClick):
                self.clear_context()
                if event.button()==Qt.LeftButton and not self.table.indexAt(event.position().toPoint()).isValid() and not event.modifiers():
                    self.clear_selection()
                self._explicit_selection=bool(event.modifiers() & (Qt.ControlModifier|Qt.ShiftModifier))
                self._preserve_marks=not self._explicit_selection
                if self._explicit_selection and self._marks:self._sync_qt_selection()
            elif event.type()==QEvent.MouseButtonRelease:
                self._preserve_marks=False;self._explicit_selection=False
        if self.enabled and watched is self.table:
            if event.type()==QEvent.KeyPress:
                self.clear_context()
                if event.key()==Qt.Key_Space and self.table.currentIndex().isValid():
                    self._toggle_row(self.table.currentIndex(),event.modifiers());return True
                self._explicit_selection=bool(event.modifiers() & (Qt.ControlModifier|Qt.ShiftModifier))
                self._preserve_marks=not self._explicit_selection
                if self._explicit_selection and self._marks:self._sync_qt_selection()
            elif event.type()==QEvent.KeyRelease:
                self._preserve_marks=False;self._explicit_selection=False
        if event.type() in (QEvent.Resize,QEvent.Show,QEvent.StyleChange):self._position_header_checkbox()
        return super().eventFilter(watched,event)
