import tests
from dataclasses import asdict
from unittest import TestCase
from unittest.mock import patch,Mock
from PySide6.QtGui import QIcon
from appearance import (custom_legibility,default_custom_legibility,normalize_custom_legibility,
    effective_palette,THEME_PALETTES,contrast_ratio)
from config import AppConfig
from tests import test_filters as fixtures
import ui_qt as qt

class CustomLegibilityTests(TestCase):
    def test_config_compatibility_validation_and_round_trip(self):
        self.assertEqual(AppConfig().legibility_profile,"normal")
        self.assertEqual(AppConfig().legibility_custom,default_custom_legibility())
        for invalid in (None,[],"bad"):
            self.assertEqual(AppConfig(legibility_custom=invalid).legibility_custom,default_custom_legibility())
        self.assertEqual(normalize_custom_legibility({"text_size":99,"weight":"700","contrast":"yes"}),
            dict(default_custom_legibility(),text_size=20))
        self.assertEqual(normalize_custom_legibility({"text_size":1})["text_size"],12)
        options={"text_size":17,"weight":700,"contrast":True,"borders":False}
        cfg=AppConfig(legibility_profile="custom",legibility_custom=options)
        self.assertEqual(AppConfig(**asdict(cfg)).legibility_custom,options)

    def test_text_and_borders_are_independent_in_all_themes(self):
        for theme,base in THEME_PALETTES.items():
            normal=effective_palette(base,"normal")
            for text in (False,True):
                for borders in (False,True):
                    with self.subTest(theme=theme,text=text,borders=borders):
                        spec=custom_legibility({"text_size":15,"weight":400,"contrast":text,"borders":borders})
                        colors=effective_palette(base,spec)
                        self.assertEqual(spec.weight,400)
                        if not text:self.assertEqual(colors["text"],normal["text"])
                        if not borders:self.assertEqual(colors["border"],normal["border"])
                        for bg in ("canvas","surface","subtle","control","header"):
                            self.assertGreaterEqual(contrast_ratio(colors["text"],colors[bg]),7 if text else 4.5)
                            if borders:self.assertGreaterEqual(contrast_ratio(colors["border"],colors[bg]),3)

    def test_custom_preview_keeps_cells_marks_and_saves_restores_options(self):
        f=fixtures.FilterTests("runTest");f.setUp();self.addCleanup(f.doCleanups)
        with f.qt_window() as (w,_):
            cells=[w.table.item(i,1) for i in range(w.table.rowCount())]
            w._workorder_selector._toggle_row(w.table.model().index(0,0),qt.Qt.NoModifier)
            marks=w._workorder_selector.selected_rows()
            with patch("ui_qt.show_activity_dialog",return_value=Mock()),patch.object(w,"refresh_table") as refresh,patch("ui_qt.fetch_data") as fetch:
                w.legibility_combo.setCurrentIndex(w.legibility_combo.findData("custom"))
                self.assertFalse(w.custom_legibility_controls.isHidden())
                w.custom_text_size.setValue(17)
                w.custom_text_weight.setCurrentIndex(w.custom_text_weight.findData(400))
                w.custom_borders.setChecked(True)
                self.assertEqual(w.table.font().pixelSize(),17)
                self.assertEqual(qt.ACTIVE_LEGIBILITY.weight,400)
                self.assertTrue(qt.ACTIVE_LEGIBILITY.borders)
                self.assertFalse(qt.ACTIVE_LEGIBILITY.contrast)
                self.assertEqual(w._workorder_selector.selected_rows(),marks)
                self.assertEqual([w.table.item(i,1) for i in range(w.table.rowCount())],cells)
                fetch.assert_not_called();refresh.assert_not_called()
                options=w._custom_legibility_options()
                with patch("ui_qt.save_config"):self.assertTrue(w.save_settings(show_feedback=False))
                self.assertEqual(w.cfg.legibility_custom,options)
                w.legibility_combo.setCurrentIndex(w.legibility_combo.findData("normal"))
                self.assertTrue(w.custom_legibility_controls.isHidden())
                w.legibility_combo.setCurrentIndex(w.legibility_combo.findData("custom"))
                self.assertEqual(w._custom_legibility_options(),options)
                w.custom_text_size.setValue(20);w.custom_text_weight.setCurrentIndex(w.custom_text_weight.findData(700))
                w._load_config()
                self.assertEqual(w._custom_legibility_options(),options)
                self.assertEqual(w.table.font().pixelSize(),17)
                self.assertFalse(w.settings_dirty())
        with f.qt_window(AppConfig(legibility_profile="custom",legibility_custom=options)) as (w,_):
            self.assertEqual(w.table.font().pixelSize(),17)
            self.assertEqual(w._custom_legibility_options(),options)

    def test_sidebar_icon_disabled_mode_keeps_same_ink_without_enabling_delete(self):
        f=fixtures.FilterTests("runTest");f.setUp();self.addCleanup(f.doCleanups)
        with f.qt_window() as (w,_):
            self.assertFalse(w.delete_profile_button.isEnabled())
            for button in (w.save_profile_button,w.delete_profile_button):
                icon=button.icon()
                self.assertEqual(icon.pixmap(20,QIcon.Normal).toImage(),icon.pixmap(20,QIcon.Disabled).toImage())
