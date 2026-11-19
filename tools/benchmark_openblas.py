"""Offline before/after benchmark. Copies inputs; never opens a Maximo session."""
import argparse
import ctypes
from ctypes import wintypes
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


def resources():
    class Memory(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('peak_ws', 'ws', 'peak_paged', 'paged',
                'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    class Thread(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in ('size', 'usage', 'tid', 'pid')] + [
            ('base', wintypes.LONG), ('delta', wintypes.LONG), ('flags', wintypes.DWORD)]
    memory = Memory(); memory.cb = ctypes.sizeof(memory)
    ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1), ctypes.byref(memory), memory.cb)
    snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot
    snapshot.restype = wintypes.HANDLE
    handle = snapshot(4, 0); thread = Thread(); thread.size = ctypes.sizeof(thread); count = 0
    try:
        ok = ctypes.windll.kernel32.Thread32First(wintypes.HANDLE(handle), ctypes.byref(thread))
        while ok:
            count += thread.pid == os.getpid()
            ok = ctypes.windll.kernel32.Thread32Next(wintypes.HANDLE(handle), ctypes.byref(thread))
    finally:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(handle))
    return {'working_mib': round(memory.ws / 1048576, 2),
            'private_mib': round(memory.private / 1048576, 2), 'threads': count}


def backup(source, target):
    if target.exists():
        raise RuntimeError('Benchmark destination already exists')
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)


def child(folder):
    # These paths are exclusively owned by this one child, before any app import.
    root = folder / ('runtime-' + uuid4().hex)
    root.mkdir()
    os.environ.update(LOCALAPPDATA=str(root), MAXIMO_DESKTOP_DEV='1',
                      MAXIMO_DESKTOP_WAREHOUSE_DEV='1', QT_QPA_PLATFORM='offscreen')
    sys.path.insert(0, str(PROJECT))
    measured = {'seconds': {}}
    def timed(name, operation):
        started = time.perf_counter(); result = operation()
        measured['seconds'][name] = time.perf_counter() - started
        return result
    started = time.perf_counter()
    import ui_qt
    import db
    import maximo_client
    from config import AppConfig
    from unittest.mock import patch
    from contextlib import ExitStack
    measured['seconds']['imports'] = time.perf_counter() - started
    measured['after_imports'] = resources()
    target = root / 'snapshot.db'
    backup(folder / 'input.db', target)
    cfg = AppConfig(theme='light', fault_descriptions_enabled=True, detailed_descriptions_enabled=True)
    cfg.db_path = str(target)
    app = ui_qt.QApplication.instance() or ui_qt.QApplication([])
    ui_qt.apply_application_theme(app, 'light')
    with ExitStack() as stack:
        for module in (ui_qt, db):
            stack.enter_context(patch.object(module, 'load_config', return_value=cfg))
        stack.enter_context(patch.object(ui_qt, 'save_config'))
        stack.enter_context(patch.object(ui_qt.QTimer, 'singleShot'))
        stack.enter_context(patch.object(ui_qt.MaximoDesktopWindow, 'schedule_auto_update'))
        window = timed('window', ui_qt.MaximoDesktopWindow)
        measured['table_rows'] = window.table.rowCount()
        measured['after_window'] = resources()
        timed('refresh', window.refresh_table)
        window.search_edit.setText('maximo-benchmark-no-match-xyz')
        timed('empty_filter', window.refresh_table)
        window.search_edit.clear()
        timed('clear_filter', window.refresh_table)
        def theme():
            ui_qt.apply_application_theme(app, 'dark')
            window.refresh_table()
        timed('theme', theme)
        frame = timed('parse_export', lambda: maximo_client.process_html_table(folder / 'input.xls'))
        measured['export_rows'] = len(frame)
        measured['frame_sha256'] = hashlib.sha256(frame.to_json(orient='split', date_format='iso').encode()).hexdigest()
        measured['import_result'] = timed('import_database', lambda: db.update_database_from_df(frame))
        with sqlite3.connect(target) as conn:
            values = conn.execute('SELECT OT,Descripción,Nº_de_serie,Fecha,Cliente,Tipo_de_trabajo,Seguimiento,Planta,Activo,Descripcion_averia,Descripcion_detallada_texto,Descripcion_detallada_html FROM maximo ORDER BY OT').fetchall()
        measured['database_sha256'] = hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
        measured['final_resources'] = resources()
        measured['blas_env'] = os.environ.get('OPENBLAS_NUM_THREADS')
        window._column_width_save_timer.stop(); window._close_finalized = True
        window.close(); window.deleteLater(); app.processEvents()
    print(json.dumps(measured))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--phase', choices=('before', 'after'))
    parser.add_argument('--database', type=Path)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    folder = args.folder.resolve()
    if folder.parent != Path(tempfile.gettempdir()).resolve() or not folder.name.startswith('maximo-perf-'):
        raise RuntimeError('Use a new maximo-perf-* folder directly under TEMP')
    marker = folder / 'benchmark-owned.json'
    if args.child:
        if not marker.is_file(): raise RuntimeError('Not a benchmark-owned directory')
        child(folder); return
    if args.phase == 'before':
        folder.mkdir(exist_ok=False)
        backup(args.database, folder / 'input.db')
        with (folder / 'input.xls').open('xb') as dst:
            dst.write(args.export.read_bytes())
        marker.write_text(json.dumps({'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT, text=True).strip()}), encoding='utf-8')
    elif not marker.is_file():
        raise RuntimeError('Run before first to freeze the inputs')
    values = []
    for index in range(args.repeat):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', '--folder', str(folder)],
                                cwd=PROJECT, capture_output=True, text=True, check=True)
        values.append(json.loads(result.stdout.splitlines()[-1]))
        print(f'{args.phase}: {index + 1}/{args.repeat}', flush=True)
    report = {'phase': args.phase, 'samples': values,
              'median_seconds': {key: round(statistics.median(v['seconds'][key] for v in values), 4) for key in values[0]['seconds']}}
    (folder / (args.phase + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
