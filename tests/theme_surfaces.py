"""Offline UI inventory for theme tests and the visual audit. Never starts a job."""
import tests
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication,QCalendarWidget,QFileDialog,QInputDialog,
    QLabel,QMenu,QMessageBox,QProgressDialog,QTextBrowser,QDialog,QVBoxLayout,QRadioButton)
from config import AppConfig
from failure_catalog import default_selection
from priority_importer import PriorityFile
from release_notes import ReleaseNotes
from release_notes_ui import ReleaseNotesDialog
from technician_repair_ui import RepairDialog,RepairProgressDialog,RepairDateTimePopup
from technician_sat_ui import TechnicianSatDialog
from warehouse import WarehouseItem,WarehouseResult
from warehouse_ui import WarehouseBatchDialog
import ui_qt as qt


def create_surfaces(main, folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    item=WarehouseItem('DEMO-1',equipment='Equipo de prueba',serial='SERIE-DEMO',status='EN TALLER',client='TMB')
    surfaces={}
    filters=qt.AdvancedFiltersDialog(main.filter_choices_cache,{},main)
    surfaces['filters']=filters
    report=PriorityFile(folder/'prioridades-demo.xls','TMB',None,None,(('DEMO-1',None),))
    surfaces['priority-import']=qt.PriorityImportDialog([report],AppConfig(),main)
    surfaces['calendar']=QCalendarWidget()
    surfaces['activity']=qt.show_activity_dialog('Esperando la consulta de una OT ficticia…',main)
    for action in ('close','discard'):
        with patch('technician_repair_ui.get_fault_description',return_value='Avería ficticia para validar contraste'):
            repair=RepairDialog(item,default_selection(),main,autoload=False,default_action=action)
        repair.preview_ready({'state':'INPRG','fault':'Avería ficticia','duration':'0,5',
                              'reference':'inc: DEMO','entries':[{'summary':'Test de equipo','details':'Resultado ficticio: correcto.'}]})
        surfaces['repair-'+action]=repair
    owner=surfaces['repair-close']
    surfaces['repair-date-time']=RepairDateTimePopup(owner.time)
    progress=RepairProgressDialog(owner)
    progress.set_stage(4,'Confirmación pendiente')
    progress.set_stage(5,'Reverificación automática sin volver a confirmar')
    progress.failure('Respuesta tardía simulada. No se ha repetido la operación.')
    surfaces['repair-progress']=progress
    for action in ('receive','dispatch','receive_sat_internal','receive_sat_external'):
        surfaces['warehouse-'+action]=WarehouseBatchDialog([item],action,lambda _:None,main,folder,ask_sat_details=True)
    recovery=WarehouseBatchDialog([item],'technician_close',lambda _:None,main,folder,recovery_only=True)
    recovery.results=[WarehouseResult(item,status='uncertain',detail='Ejemplo de resultado pendiente')]
    recovery.table.item(0,4).setText('Pendiente de verificar');recovery._sync_table_palette()
    surfaces['recovery']=recovery
    sat=TechnicianSatDialog([item],lambda _:None,main,selection=default_selection(),report_folder=folder,autoload=False)
    sat.inputs[item.ot]['duration'].setText('0,5');sat.inputs[item.ot]['incident'].setText('inc: DEMO')
    sat.inputs[item.ot]['reason'].setText('Motivo ficticio del envío')
    surfaces['technician-sat']=sat
    notes=ReleaseNotes('vDEMO','## Técnico\n- Mejora de revisión.\n\n## Almacén\n- Mejora de verificación.','https://github.com/example/release')
    surfaces['release-notes']=ReleaseNotesDialog(notes,main)
    for name,icon in (('info',QMessageBox.Information),('warning',QMessageBox.Warning),
                      ('error',QMessageBox.Critical),('confirmation',QMessageBox.Question)):
        box=QMessageBox(icon,'Aviso de prueba','OT DEMO · Revisa los datos antes de continuar.',
                        QMessageBox.Yes|QMessageBox.No,owner)
        box.setInformativeText('Este aviso no ejecuta ninguna operación. Valida texto, fondo y botones.')
        surfaces['message-'+name]=box
    text_input=QInputDialog(main);text_input.setLabelText('Nombre de la búsqueda');text_input.setTextValue('Búsqueda de prueba')
    surfaces['input-dialog']=text_input
    bar=QProgressDialog('Descargando actualización ficticia…','Cancelar',0,100,main)
    bar.setAutoClose(False);bar.setValue(45);surfaces['download-progress']=bar
    file_dialog=QFileDialog(main,'Guardar parte de prueba',str(folder))
    file_dialog.setOption(QFileDialog.DontUseNativeDialog,True)
    file_dialog.setAcceptMode(QFileDialog.AcceptSave);file_dialog.selectFile('parte-demo.pdf')
    surfaces['qt-file-dialog']=file_dialog
    browser=QDialog(main);body=QVBoxLayout(browser);body.addWidget(QLabel('Descripción detallada de prueba'))
    text=QTextBrowser();text.setHtml('<h2>Texto de prueba</h2><p>Descripción en <b>negrita</b> y texto normal.</p>')
    body.addWidget(text);browser.resize(740,450);surfaces['description']=browser
    menu=QMenu(main);menu.addAction('Copiar OT');menu.addAction('Abrir OT en Maximo')
    menu.addAction('Imprimir parte…').setEnabled(False);menu.addSeparator()
    technical=menu.addMenu('Técnico');technical.addAction('Dar salida…');technical.addAction('Declarar irreparable…')
    warehouse=menu.addMenu('Almacén');warehouse.addAction('Confirmar recepción…');warehouse.addAction('Dar salida…')
    surfaces['context-menu']=menu;surfaces['technical-menu']=technical;surfaces['warehouse-menu']=warehouse
    main.client_combo._prepare_menu();surfaces['client-selector']=main.client_combo._menu
    indicators=QDialog(main);body=QVBoxLayout(indicators)
    from PySide6.QtWidgets import QCheckBox
    for label,state in (('Casilla sin marcar',Qt.Unchecked),('Casilla marcada',Qt.Checked),('Selección parcial',Qt.PartiallyChecked)):
        box=QCheckBox(label);box.setCheckState(state);body.addWidget(box)
    for selected in (False,True):
        radio=QRadioButton('Opción seleccionada' if selected else 'Otra opción');radio.setChecked(selected);body.addWidget(radio)
    disabled=QCheckBox('Opción deshabilitada');disabled.setEnabled(False);body.addWidget(disabled)
    surfaces['indicators']=indicators
    return surfaces


def close_surfaces(surfaces,main):
    for widget in reversed(list(surfaces.values())):
        widget.hide()
        if widget is not main.client_combo._menu:widget.deleteLater()
    QApplication.processEvents()
