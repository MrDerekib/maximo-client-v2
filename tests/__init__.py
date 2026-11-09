"""Tests always use disposable application data, never installed/dev profiles."""
import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

if 'app_paths' in sys.modules:
    raise RuntimeError('Import tests before app modules to isolate persistent data.')

TEST_DATA_ROOT = Path(tempfile.gettempdir()) / ('maximo-suite-' + uuid4().hex)
TEST_DATA_ROOT.mkdir()
os.environ['LOCALAPPDATA'] = str(TEST_DATA_ROOT)
os.environ['MAXIMO_DESKTOP_DEV'] = '1'
os.environ['MAXIMO_DESKTOP_WAREHOUSE_DEV'] = '1'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
atexit.register(shutil.rmtree, TEST_DATA_ROOT, ignore_errors=True)
