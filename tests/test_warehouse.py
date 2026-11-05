"""Warehouse simulation invariants: no state changes, replay or changing batches."""
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import runpy
from threading import Event
from unittest import TestCase
from unittest.mock import patch

import app_paths
from config import AppConfig
from tests.test_support import temporary_directory
from warehouse import WarehouseItem, freeze_items, run_simulation, save_simulation_report


def items(count=4, status='WAPPR'):
    return tuple(WarehouseItem(f'DEMO-{index}', status=status) for index in range(count))


class WarehouseSimulationTests(TestCase):
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

    def test_success_is_only_reported_after_all_five_steps_and_never_opens_a_socket(self):
        events = []
        with patch('socket.socket', side_effect=AssertionError('Simulation attempted network access')):
            results = run_simulation(items(2), 'receive', delay=0,
                                     progress=lambda index, result: events.append((index, result)))
        self.assertEqual([result.status for result in results], ['success', 'success'])
        self.assertTrue(all(result.completed_steps == 5 for result in results))
        self.assertEqual([index for index, result in events if result.status == 'running'], [0]*5 + [1]*5)
        self.assertEqual([result.completed_steps for index, result in events
                          if index == 0 and result.status == 'running'], [0, 1, 2, 3, 4])

    def test_ineligible_cached_status_is_rejected_but_next_item_can_complete(self):
        results = run_simulation([WarehouseItem('1', status='CLOSE'), WarehouseItem('2', status='ISSUE')],
                                 'dispatch', delay=0)
        self.assertEqual([result.status for result in results], ['failed', 'success'])
        self.assertIn('No se ha consultado Maximo', results[0].detail)

    def test_uncertain_confirmation_stops_remaining_items_without_replay(self):
        events = []
        results = run_simulation(items(), 'receive', 'incidents', delay=0,
                                 progress=lambda index, result: events.append((index, result)))
        self.assertEqual([result.status for result in results], ['success', 'failed', 'uncertain', 'stopped'])
        self.assertEqual(sum(index == 2 and result.step.startswith('Confirmar acción')
                             for index, result in events), 1)
        self.assertFalse(any(index == 3 and result.status == 'running' for index, result in events))

    def test_stop_is_applied_between_items_and_never_interrupts_current_confirmation(self):
        stop = Event()
        def progress(index, result):
            if index == 0 and result.step.startswith('Confirmar acción'):
                stop.set()
        results = run_simulation(items(2), 'receive', delay=0, stop=stop, progress=progress)
        self.assertEqual([result.status for result in results], ['success', 'stopped'])
        self.assertEqual(results[0].completed_steps, 5)

    def test_pre_cancelled_batch_does_not_attempt_any_step(self):
        stop = Event(); stop.set()
        results = run_simulation(items(), 'receive', delay=0, stop=stop)
        self.assertTrue(all(result.status == 'stopped' and result.completed_steps == 0 for result in results))

    def test_unsupported_real_mode_or_action_is_rejected_before_processing(self):
        for action, scenario in (('discard', 'success'), ('receive', 'real')):
            with self.subTest(action=action, scenario=scenario), self.assertRaises(ValueError):
                run_simulation(items(), action, scenario, delay=0)

    def test_report_is_explicitly_simulated_and_is_not_overwritten(self):
        with temporary_directory() as folder:
            results = run_simulation(items(1), 'receive', delay=0)
            one = save_simulation_report(folder, 'batch-1', 'receive', 'success', results)
            two = save_simulation_report(folder, 'batch-1', 'receive', 'success', results)
            data = json.loads(one.read_text(encoding='utf-8'))
            self.assertNotEqual(one, two)
            self.assertTrue(data['simulation'])
            self.assertEqual(data['results'][0]['item']['ot'], 'DEMO-0')

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
