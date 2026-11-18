import tests  # Keep credentials and application data isolated.
from dataclasses import asdict
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QApplication, QLabel, QDialog, QVBoxLayout
from PySide6.QtGui import QFontInfo
from config import AppConfig
from typography import FONT_OPTIONS, THEME_FONTS, resolved_font_key
import ui_qt
from tests import test_filters as fixtures

class TypographyTests(TestCase):
    def test_config_migration_validation_and_theme_defaults(self):
        self.assertEqual(AppConfig().font_family, "theme")
        for invalid in (None, [], "unknown"):
            self.assertEqual(AppConfig(font_family=invalid).font_family, "theme")
        self.assertEqual(set(THEME_FONTS), set(ui_qt.THEME_PALETTES))
        self.assertEqual(len(FONT_OPTIONS), 7)
        for key in FONT_OPTIONS:
            cfg = AppConfig(font_family=key)
            self.assertEqual(AppConfig(**asdict(cfg)).font_family, key)
            for theme in THEME_FONTS:
                expected = THEME_FONTS[theme] if key == "theme" else key
                self.assertEqual(resolved_font_key(key, theme), expected)

    def test_bundled_fonts_real_families_dialogs_and_profiles(self):
        app = QApplication.instance() or QApplication([])
        try:
            for key, option in FONT_OPTIONS.items():
                if not option.asset:
                    continue
                for profile in ui_qt.PROFILES:
                    ui_qt.apply_application_theme(app, "dark", profile, key)
                    self.assertEqual(QFontInfo(app.font()).family(), option.family)
                    dialog = QDialog(); layout = QVBoxLayout(dialog); label = QLabel("Áéñ 0O 1Il"); layout.addWidget(label)
                    dialog.show(); app.processEvents()
                    self.assertEqual(QFontInfo(label.font()).family(), option.family)
                    dialog.close(); dialog.deleteLater()
            for theme, key in THEME_FONTS.items():
                ui_qt.apply_application_theme(app, theme)
                self.assertEqual(ui_qt.ACTIVE_FONT_FAMILY, FONT_OPTIONS[key].family)
            # Switching back to System must not resolve to the last loaded font.
            ui_qt.apply_application_theme(app, "dark", "normal", "system")
            self.assertEqual(app.font().family(), app._md_system_font.family())
            with patch.dict(app._md_font_families, {}, clear=True):
                ui_qt.apply_application_theme(app, "dark", "normal", "inter")
                self.assertEqual(app.font().family(), app._md_system_font.family())
        finally:
            ui_qt.apply_application_theme(app, "light")

    def test_preview_persists_override_and_discard_restores_without_requery(self):
        fixture = fixtures.FilterTests("runTest"); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with fixture.qt_window() as (window, qt):
            cells = [window.table.item(r, 1) for r in range(window.table.rowCount())]
            selector = window._workorder_selector
            selector._toggle_row(window.table.model().index(0, 0), qt.Qt.NoModifier)
            marked = selector.selected_rows()
            with patch("ui_qt.show_activity_dialog", return_value=Mock()), patch.object(window, "refresh_table") as refresh:
                window.font_combo.setCurrentIndex(window.font_combo.findData("jetbrains_mono"))
                self.assertTrue(window.settings_dirty())
                self.assertEqual(QFontInfo(window.table.font()).family(), "JetBrains Mono")
                self.assertEqual(QFontInfo(window.table.item(0, 0).font().resolve(window.table.font())).family(), "JetBrains Mono")
                window.theme_combo.setCurrentIndex(window.theme_combo.findData("catppuccin_latte"))
                self.assertEqual(ui_qt.ACTIVE_FONT_FAMILY, "JetBrains Mono")
                self.assertEqual([window.table.item(r, 1) for r in range(window.table.rowCount())], cells)
                self.assertEqual(selector.selected_rows(), marked)
                refresh.assert_not_called()
                with patch("ui_qt.save_config"):
                    window.save_settings(show_feedback=False)
                self.assertEqual(window.cfg.font_family, "jetbrains_mono")
                window.font_combo.setCurrentIndex(window.font_combo.findData("inter"))
                window._load_config()
                self.assertEqual(window.font_combo.currentData(), "jetbrains_mono")
                self.assertEqual(ui_qt.ACTIVE_FONT_FAMILY, "JetBrains Mono")
                self.assertFalse(window.settings_dirty())

    def test_assets_include_licenses_and_build_bundles_them(self):
        assets = ui_qt.PROGRAM_DIR / "ui_assets" / "fonts"
        for option in FONT_OPTIONS.values():
            if option.asset:
                font = assets / option.asset
                self.assertGreater(font.stat().st_size, 10000)
                self.assertIn("SIL OPEN FONT LICENSE", (font.parent / "OFL.txt").read_text(encoding="utf-8"))
        self.assertIn("--include-data-dir=$projectRoot\\ui_assets=ui_assets", (ui_qt.PROGRAM_DIR / "build_app.ps1").read_text(encoding="utf-8"))
