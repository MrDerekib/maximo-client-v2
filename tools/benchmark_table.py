"""Synthetic Qt table benchmark: isolated data, no credentials and no network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]


def child(folder, count):
    root = folder / ('runtime-' + uuid4().hex)
    root.mkdir()
    os.environ.update(LOCALAPPDATA=str(root), MAXIMO_DESKTOP_DEV='1',
                      MAXIMO_DESKTOP_WAREHOUSE_DEV='1', QT_QPA_PLATFORM='offscreen')
    sys.path.insert(0, str(PROJECT))
    from contextlib import ExitStack
    from unittest.mock import patch
    import ui_qt, db
    from config import AppConfig
    from PySide6.QtTest import QTest
    from benchmark_openblas import resources
    cfg = AppConfig(theme='light', fault_descriptions_enabled=True, detailed_descriptions_enabled=True)
    target = root / 'synthetic.db'
    assert not target.exists() and target.parent == root
    cfg.db_path = str(target)
    app = ui_qt.QApplication.instance() or ui_qt.QApplication([])
    ui_qt.apply_application_theme(app, 'light')
    with ExitStack() as stack:
        for module in (ui_qt, db):
            stack.enter_context(patch.object(module, 'load_config', return_value=cfg))
        stack.enter_context(patch.object(ui_qt, 'save_config'))
        stack.enter_context(patch.object(ui_qt.QTimer, 'singleShot'))
        stack.enter_context(patch.object(ui_qt.MaximoDesktopWindow, 'schedule_auto_update'))
        db.init_db()
        with sqlite3.connect(target) as conn:
            conn.executemany('INSERT INTO maximo (OT,Descripción,Nº_de_serie,Fecha,Cliente,Tipo_de_trabajo,Seguimiento,Planta,Activo,Ultima_vez_visto,Descripcion_averia,Descripcion_detallada_texto) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                [(str(5000000+i), f'Equipo sintético {i%25}', f'SN-{i:06}', '2026-11-01',
                  'TMB' if i%2 else 'LINEA-9', 'REPARACION', 'EN TALLER', 'LAB-BAD',
                  int(i%7!=0), '2026-11-10T08:00:00', f'Avería sintética {i%8}',
                  'Detalle sintético' if i%3==0 else '') for i in range(count)])
        started = time.perf_counter(); window = ui_qt.MaximoDesktopWindow()
        report = {'initial_seconds': time.perf_counter()-started, 'rows': count, 'cases': {}}
        window.show(); app.processEvents()
        report['resources'] = resources()
        inserts = []; removes = []
        window.table.model().rowsInserted.connect(lambda parent, first, last: inserts.append(last-first+1))
        window.table.model().rowsRemoved.connect(lambda parent, first, last: removes.append(last-first+1))
        pulse = {'last': time.perf_counter(), 'gaps': []}
        def tick():
            now=time.perf_counter();pulse['gaps'].append(now-pulse['last']);pulse['last']=now
        timer=ui_qt.QTimer();timer.timeout.connect(tick);timer.start(10)
        def measure(name, action):
            QTest.qWait(25);pulse['gaps'].clear();pulse['last']=time.perf_counter()
            before_inserts=sum(inserts);before_removes=sum(removes)
            first=window.table.item(0,1) if window.table.rowCount() else None
            started=time.perf_counter();action();app.processEvents();seconds=time.perf_counter()-started
            QTest.qWait(25)
            report['cases'][name]={'seconds':seconds,'longest_tick_gap_ms':max(pulse['gaps'],default=0)*1000,
                'inserted_rows':sum(inserts)-before_inserts,'removed_rows':sum(removes)-before_removes,
                'same_first_cell':first is not None and window.table.rowCount()>0 and first is window.table.item(0,1)}
        measure('unchanged_refresh',window.refresh_table)
        measure('three_unchanged_refreshes',lambda:[window.refresh_table() for _ in range(3)])
        def theme():
            with ui_qt.QSignalBlocker(window.theme_combo):
                window.theme_combo.setCurrentIndex(window.theme_combo.findData('dark'))
            window.preview_theme()
        # Qt's blocker is imported here to keep this tool usable before the optimization.
        from PySide6.QtCore import QSignalBlocker
        ui_qt.QSignalBlocker = QSignalBlocker
        measure('theme',theme)
        def narrow():
            window.search_edit.setText('SN-0000');window.refresh_table()
        measure('narrow_filter',narrow)
        measure('clear_filter',window.clear_filters)
        def changed():
            with sqlite3.connect(target) as conn:
                conn.execute('UPDATE maximo SET Descripción=? WHERE OT=?',('Equipo modificado',str(5000000+count-1)))
            window.refresh_table()
        measure('changed_record',changed)
        def metadata():
            with sqlite3.connect(target) as conn:
                conn.execute("UPDATE maximo SET Ultima_vez_visto='2026-11-10T09:00:00'")
            window.refresh_table()
        measure('changed_last_seen',metadata)
        digest=hashlib.sha256()
        for row in range(window.table.rowCount()):
            for column in range(window.table.columnCount()):
                item=window.table.item(row,column)
                digest.update((item.text()+'\0').encode('utf-8'))
            digest.update(str(window.table.isRowHidden(row)).encode())
        report['display_sha256']=digest.hexdigest();report['final_resources']=resources()
        timer.stop();window._column_width_save_timer.stop();window._close_finalized=True
        window.close();window.deleteLater();app.processEvents()
    print(json.dumps(report))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--rows',type=int,default=5000)
    parser.add_argument('--repeat',type=int,default=3)
    parser.add_argument('--phase',choices=('before','after'))
    parser.add_argument('--child',action='store_true')
    args=parser.parse_args();folder=args.folder.resolve();marker=folder/'synthetic-owned.json'
    if folder.parent!=Path(tempfile.gettempdir()).resolve() or not folder.name.startswith('maximo-table-'):
        raise RuntimeError('Use a new maximo-table-* folder directly under TEMP')
    if args.child:
        if not marker.is_file():raise RuntimeError('Not a benchmark directory')
        child(folder,args.rows);return
    if args.phase=='before':
        folder.mkdir(exist_ok=False);marker.write_text(json.dumps({'rows':args.rows}),encoding='utf-8')
    elif not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))['rows']!=args.rows:
        raise RuntimeError('Use the same rows and directory as before')
    samples=[]
    for index in range(args.repeat):
        process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child','--folder',str(folder),'--rows',str(args.rows)],cwd=PROJECT,capture_output=True,text=True,check=True)
        samples.append(json.loads(process.stdout.splitlines()[-1]));print(f'{args.phase}: {index+1}/{args.repeat}',flush=True)
    median={name:{key:statistics.median(sample['cases'][name][key] for sample in samples) for key in ('seconds','longest_tick_gap_ms','inserted_rows','removed_rows')} for name in samples[0]['cases']}
    output={'samples':samples,'median':median}
    (folder/(args.phase+'.json')).write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps({'median':median,'display_sha256':samples[0]['display_sha256']}))


if __name__=='__main__':main()
