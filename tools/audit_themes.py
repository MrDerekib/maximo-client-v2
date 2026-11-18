"""Generate an offline theme/profile gallery; tests isolate all persistent data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tests
import argparse,json,html,logging
from unittest.mock import patch
from PySide6.QtGui import QFont,QFontDatabase,QPixmap
from PySide6.QtWidgets import QMenu
from tests.test_filters import FilterTests
from tests.theme_surfaces import create_surfaces,close_surfaces
import ui_qt as qt


def capture(widget,path):
    widget.ensurePolished()
    if isinstance(widget,QMenu):
        widget.resize(widget.sizeHint())
        if widget.actions():widget.setActiveAction(widget.actions()[0])
        pixmap=QPixmap(widget.size());widget.render(pixmap);pixmap.save(str(path))
    else:
        widget.show();qt.QApplication.processEvents()
        widget.grab().save(str(path));widget.hide()


def run(output, themes=None):
    output.mkdir(parents=True,exist_ok=True)
    fixture=FilterTests('runTest');fixture.setUp();images=[]
    try:
        with fixture.qt_window() as (window,qt):
            fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
            for name in ('segoeui.ttf','seguisb.ttf'):
                if (fonts/name).exists():QFontDatabase.addApplicationFont(str(fonts/name))
            app=qt.QApplication.instance();app.setFont(QFont('Segoe UI',9))
            window.resize(1500,940)
            # A second guard: no preview or operational worker can start from this tool.
            with patch('PySide6.QtCore.QThread.start',side_effect=AssertionError('The theme audit must not start jobs')):
                for theme in (themes or qt.THEME_PALETTES):
                    for profile in ('normal','comfortable','contrast'):
                        with qt.QSignalBlocker(window.theme_combo),qt.QSignalBlocker(window.legibility_combo):
                            window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
                            window.legibility_combo.setCurrentIndex(window.legibility_combo.findData(profile))
                        window.preview_theme()
                        folder=output/(theme+'-'+profile);folder.mkdir(exist_ok=True)
                        window.show();window.pages.setCurrentIndex(0);app.processEvents()
                        path=folder/'main-list.png';window.grab().save(str(path));images.append(str(path.relative_to(output)))
                        window.pages.setCurrentIndex(1)
                        for index in range(4):
                            window.settings_tabs.setCurrentIndex(index);app.processEvents()
                            window._update_settings_content_width();app.processEvents()
                            path=folder/f'settings-{index}.png';window.grab().save(str(path));images.append(str(path.relative_to(output)))
                        window.hide()
                        surfaces=create_surfaces(window,tests.TEST_DATA_ROOT/'audit-reports')
                        for name,widget in surfaces.items():
                            path=folder/(name+'.png');capture(widget,path);images.append(str(path.relative_to(output)))
                        close_surfaces(surfaces,window)
                        print(theme,profile,len(surfaces)+5,'surfaces rendered',flush=True)
            (output/'manifest.json').write_text(json.dumps(images,indent=2),encoding='utf-8')
            cards=''.join('<figure><figcaption>'+html.escape(path)+'</figcaption><a href="'+html.escape(path)+'"><img loading="lazy" src="'+html.escape(path)+'"></a></figure>' for path in images)
            (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Auditoría visual de temas MD</title><style>body{font:14px system-ui;background:#eef2f6;color:#172033;margin:24px}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}figure{margin:0;background:white;border:1px solid #cad5e1;padding:10px}img{max-width:100%;height:260px;object-fit:contain}figcaption{margin-bottom:8px}</style><h1>Auditoría visual de temas · Datos ficticios</h1><p>Haz clic para ampliar. No se ha conectado a Maximo ni se han ejecutado operaciones.</p><main>'+cards+'</main>',encoding='utf-8')
    finally:fixture.doCleanups()
    return len(images)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--themes',nargs='+',choices=list(qt.THEME_PALETTES),help='Opcional: auditar solo estos temas registrados')
    args=parser.parse_args();logging.disable(logging.CRITICAL)
    print('Total:',run(args.output,args.themes))
