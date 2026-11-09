"""Warehouse batch identity and isolation invariants."""
import tests  # Isolate application data before importing product modules.
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import runpy
from unittest import TestCase
from unittest.mock import patch

import app_paths
from config import AppConfig
from warehouse import WarehouseItem, freeze_items


class WarehouseModelTests(TestCase):
    def test_freezes_unique_identifiers_and_rejects_ambiguous_or_empty_selection(self):
        item = WarehouseItem(' 123 ', status='WAPPR')
        batch = freeze_items([item, item])
        self.assertEqual(batch[0].ot, '123')
        self.assertEqual(len(batch), 1)
        with self.assertRaises(FrozenInstanceError):
            batch[0].ot = '456'
        for selection in ([], [WarehouseItem(' ')],
                          [WarehouseItem('123', status='WAPPR'), WarehouseItem('123', status='ISSUE')]):
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                freeze_items(selection)












    def test_warehouse_setting_is_opt_in_and_requires_a_real_boolean(self):
        self.assertFalse(AppConfig().warehouse_enabled)
        self.assertTrue(AppConfig(warehouse_enabled=True).warehouse_enabled)
        for value in ('true', 'false', 1, None):
            self.assertFalse(AppConfig(warehouse_enabled=value).warehouse_enabled)

    def test_warehouse_sandbox_never_changes_production_or_ordinary_dev_paths(self):
        for dev, warehouse, expected in (('0', '1', 'MaximoDesktop'),
                                          ('1', '0', 'MaximoDesktop-dev'),
                                          ('1', '1', 'MaximoDesktop-almacen')):
            with self.subTest(dev=dev, warehouse=warehouse), patch.dict(os.environ, {
                'MAXIMO_DESKTOP_DEV': dev, 'MAXIMO_DESKTOP_WAREHOUSE_DEV': warehouse,
            }):
                paths = runpy.run_path(str(Path(app_paths.__file__)))
                self.assertEqual(paths['APP_ROOT'].name, expected)
