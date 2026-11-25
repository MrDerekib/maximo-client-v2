"""Offline tests; never print, contact Maximo or load real credentials."""
import tests
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import report_stamp as stamp
import maximo_client as client
from config import AppConfig


class ReportStampTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logs = self.root / 'almacen-operaciones'; self.logs.mkdir()
        self.db = self.root / 'data.db'
        self.connection = patch.object(stamp, 'get_connection', side_effect=lambda: sqlite3.connect(self.db))
        self.connection.start(); self.addCleanup(self.connection.stop)
        self.log_patch = patch.object(stamp, 'LOG_DIR', self.root)
        self.log_patch.start(); self.addCleanup(self.log_patch.stop)

    def test_only_verified_discard_is_remembered_and_survives_later_queries(self):
        for result in ({'ot':'4443840','status':'CLOSE'},
                       {'ot':'4443840','status':'CLOSE','action':'close'},
                       {'ot':'4443840','status':'INPRG','action':'discard'},
                       {'ot':'4443840','status':'CLOSE','action':'discard','cancelled':True}):
            self.assertFalse(stamp.record_verified_discard(result))
        self.assertEqual(stamp.verified_discard_ots(),set())
        result={'ot':'4443840','status':'CLOSE','action':'discard'}
        self.assertTrue(stamp.record_verified_discard(result))
        self.assertTrue(stamp.record_verified_discard(result))
        self.assertEqual(stamp.verified_discard_ots(),{'4443840'})

    def test_old_successful_reports_are_imported_but_timeouts_are_not(self):
        for index, (action,status,final,ot) in enumerate([
            ('technician_discard','success','CLOSE','4443840'),
            ('technician_close','success','CLOSE','4443841'),
            ('technician_discard','pending_verification','CLOSE','4443842'),
            ('technician_discard','success','INPRG','4443843')]):
            (self.logs/f'repair-{index}-result.json').write_text(json.dumps({
                'action':action,'results':[{'item':{'ot':ot},'status':status,'verified_status':final}]}))
        (self.logs/'repair-bad-result.json').write_text('{broken')
        self.assertEqual(stamp.verified_discard_ots(),{'4443840'})

    def test_color_requires_html_desktop_print_enabled_stamp_and_positive_evidence(self):
        for enabled, known, action, expected in [
            (True,True,'print',True), (False,True,'print',False),
            (True,False,'print',False), (True,True,None,False),
            (True,True,'pdf',False)]:
            with self.subTest(enabled=enabled,known=known,action=action):
                cfg=AppConfig(repair_irreparable_stamp_enabled=enabled,repair_extension_enabled=True)
                driver=Mock()
                driver.find_element.return_value.is_displayed.return_value=True
                driver.find_element.return_value.is_enabled.return_value=True
                driver.find_element.return_value.get_attribute.return_value='4443840'
                with patch.object(client,'load_config',return_value=cfg), \
                     patch.object(stamp,'verified_discard_ots',return_value={'4443840'} if known else set()), \
                     patch.object(client,'create_edge_profile',return_value='fake-profile'), \
                     patch.object(client,'setup_driver',return_value=driver) as setup, \
                     patch.object(client,'login'),patch.object(client,'open_workorders_app'), \
                     patch.object(client,'start_repair_report'),patch.object(client,'_start_ot_action_watcher'), \
                     patch.object(client,'wait_for',side_effect=lambda d,condition,*a,**k:condition(d)):
                    client.open_ot('4443840',report_action=action)
                self.assertEqual(setup.call_args.kwargs.get('report_color',False),expected)
                seed=next(c for c in driver.execute_script.call_args_list if 'discardedOts' in c.args[0])
                self.assertEqual(seed.args[1],['4443840'] if enabled and known else [])

    def test_print_preferences_default_to_bw_and_only_explicit_color_changes_it(self):
        self.assertFalse(json.loads(client.visible_ot_print_preferences()['appState'])['isColorEnabled'])
        color=json.loads(client.visible_ot_print_preferences(color=True)['appState'])
        self.assertTrue(color['isColorEnabled']); self.assertFalse(color['isHeaderFooterEnabled'])

    def test_setting_defaults_true_and_rejects_invalid_values(self):
        self.assertTrue(AppConfig().repair_irreparable_stamp_enabled)
        self.assertFalse(AppConfig(repair_irreparable_stamp_enabled=False).repair_irreparable_stamp_enabled)
        self.assertTrue(AppConfig(repair_irreparable_stamp_enabled='false').repair_irreparable_stamp_enabled)

    def test_setting_load_save_and_discard(self):
        from tests.test_ui_workorder_start import settings_window
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        w=settings_window()
        try:
            self.assertTrue(w.repair_stamp_check.isChecked())
            self.assertTrue(w.printing_card.isAncestorOf(w.repair_stamp_check))
            w.repair_stamp_check.setChecked(False)
            self.assertTrue(w.settings_dirty())
            with patch('ui_qt.save_config') as save:
                w.save_settings(show_feedback=False)
            self.assertFalse(save.call_args.args[0].repair_irreparable_stamp_enabled)
            w.repair_stamp_check.setChecked(True)
            w._load_config()
            self.assertFalse(w.repair_stamp_check.isChecked())
        finally:
            w.deleteLater();app.processEvents()

    def test_origin_company_preferences_default_to_atm_and_line_9_and_persist(self):
        from tests.test_ui_workorder_start import settings_window
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        ui = settings_window()
        try:
            self.assertEqual(ui.repair_origin_mode_combo.currentData(), "selected")
            self.assertEqual(ui.repair_origin_projects.selected_values(), ["ATM", "Línea 9"])
            ui.filter_choices_cache = {"clients": ["ATM", "TMB"]}
            ui._set_repair_origin_projects(["ATM", "TMB"])
            self.assertTrue(ui.settings_dirty())
            ui.repair_origin_mode_combo.setCurrentIndex(ui.repair_origin_mode_combo.findData("all"))
            self.assertFalse(ui.repair_origin_projects.isEnabled())
            with patch('ui_qt.save_config') as save:
                self.assertTrue(ui.save_settings(show_feedback=False))
            cfg = save.call_args.args[0]
            self.assertEqual(cfg.repair_origin_mode, "all")
            self.assertEqual(cfg.repair_origin_projects, ["ATM", "TMB"])
            self.assertFalse(ui.settings_dirty())
        finally:
            ui.deleteLater()
            app.processEvents()

    def test_extension_discard_updates_stamp_without_changing_session_color(self):
        driver=Mock();driver._maximo_report_stamp_enabled=True
        client._remember_discard_for_reports(driver,{'ot':'4443840','status':'CLOSE','action':'discard'})
        self.assertEqual(stamp.verified_discard_ots(),{'4443840'})
        self.assertIn('discardedOts',driver.execute_script.call_args.args[0])
        self.assertEqual(driver.execute_script.call_args.args[1],'4443840')
        driver.execute_cdp_cmd.assert_not_called()
        driver.execute_script.side_effect=RuntimeError('storage unavailable')
        with self.assertLogs(level='WARNING'):
            client._remember_discard_for_reports(driver,{'ot':'4443840','status':'CLOSE','action':'discard'})
        driver._maximo_report_stamp_enabled=False;driver.execute_script.reset_mock()
        client._remember_discard_for_reports(driver,{'ot':'4443840','status':'CLOSE','action':'discard'})
        driver.execute_script.assert_not_called()
