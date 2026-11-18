import tests  # Disposable application data; never use credentials from a real profile.
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from appearance import (THEME_PALETTES, PROFILES, effective_palette, contrast_ratio,
                        legibility_css, is_dark, tracking_color, tracking_style, presence_style)
from config import AppConfig


class AppearanceTests(TestCase):
    def test_profiles_preserve_base_palettes_and_share_schema(self):
        original = {name: dict(palette) for name, palette in THEME_PALETTES.items()}
        roles = set(THEME_PALETTES["light"])
        for palette in THEME_PALETTES.values():
            self.assertEqual(set(palette), roles)
            for profile in PROFILES:
                result = effective_palette(palette, profile)
                self.assertTrue(roles <= result.keys())
                self.assertEqual(is_dark(result), is_dark(palette))
        self.assertEqual(original, THEME_PALETTES)

    def test_high_contrast_for_text_borders_and_selection_on_both_themes(self):
        for name, palette in THEME_PALETTES.items():
            colors = effective_palette(palette, "contrast")
            for bg in ("canvas", "surface", "subtle", "control", "header"):
                for role in ("text", "muted", "inactive", "header_text", "button_text"):
                    with self.subTest(theme=name, bg=bg, role=role):
                        self.assertGreaterEqual(contrast_ratio(colors[role], colors[bg]), 7)
                self.assertGreaterEqual(contrast_ratio(colors['border'], colors[bg]), 3)
            self.assertGreaterEqual(contrast_ratio(colors['text'], colors['accent_light']), 4.5)
            self.assertGreaterEqual(contrast_ratio(colors['on_accent'], colors['accent']), 4.5)

    def test_future_palette_uses_same_profiles_without_theme_conditionals(self):
        palette = dict(THEME_PALETTES["dark"], canvas="#20202b", surface="#242434")
        colors = effective_palette(palette, "contrast")
        self.assertTrue(is_dark(colors))
        self.assertGreaterEqual(contrast_ratio(colors['muted'], colors['surface']), 7)
        self.assertEqual(legibility_css("font-size: 12px; font-weight: 400;", "comfortable"),
                         "font-size: 15px; font-weight: 600;")

    def test_status_aliases_and_unknown_values_remain_readable(self):
        for palette in THEME_PALETTES.values():
            colors = effective_palette(palette)
            self.assertEqual(tracking_color('ISSUE', colors), tracking_color('dar salida', colors))
            self.assertEqual(tracking_color('WAPPR', colors), tracking_color('PDTE CONFIRMAR', colors))
            for value in ('INPRG', 'RETENIDO', 'DESECHADO', 'new status'):
                self.assertGreaterEqual(contrast_ratio(tracking_color(value, colors), colors['surface']), 4.5)

    def test_status_text_has_contrast_without_fill_and_distinguishes_closed_for_all_profiles(self):
        for palette in THEME_PALETTES.values():
            for profile in PROFILES:
                colors = effective_palette(palette, profile)
                tones = []
                for value in ('WAPPR', 'INPRG', 'ISSUE', 'CLOSE', 'RETENIDO', 'DESECHADO'):
                    foreground, emphasized = tracking_style(value, colors)
                    self.assertTrue(emphasized)
                    for background in ('surface', 'subtle'):
                        self.assertGreaterEqual(contrast_ratio(foreground, colors[background]),4.5)
                    tones.append(foreground)
                self.assertEqual(len(set(tones)),6)
                self.assertFalse(tracking_style('Unknown', colors)[1])
                self.assertEqual(tracking_color('CERRADA', colors), tracking_color('CLOSE', colors))
                self.assertNotEqual(tracking_color('DAR SALIDA', colors), tracking_color('CLOSE', colors))

    def test_presence_categories_are_distinct_and_contrasted_on_both_themes(self):
        for palette in THEME_PALETTES.values():
            for profile in PROFILES:
                colors = effective_palette(palette, profile)
                values = []
                for active, priority in ((1, False), (1, True), (0, False), (None, False)):
                    foreground, bold = presence_style(active, priority, colors)
                    self.assertTrue(bold)
                    for background in ('surface', 'subtle'):
                        self.assertGreaterEqual(contrast_ratio(foreground, colors[background]), 4.5)
                    values.append(foreground)
                self.assertEqual(len(set(values)), 4)

    def test_dracula_is_registered_and_keeps_profiles_independent(self):
        self.assertEqual(AppConfig(theme='dracula').theme,'dracula')
        self.assertEqual(THEME_PALETTES['dracula']['canvas'],'#282a36')
        for profile in PROFILES:
            colors=effective_palette(THEME_PALETTES['dracula'],profile)
            self.assertTrue(is_dark(colors))
            self.assertGreaterEqual(contrast_ratio(colors['on_accent'],colors['accent']),4.5)
            self.assertGreaterEqual(contrast_ratio(colors['on_nav'],colors['nav']),4.5)

    def test_sidebar_text_has_contrast_for_light_and_dark_sidebars(self):
        for name,palette in THEME_PALETTES.items():
            for profile in PROFILES:
                colors=effective_palette(palette,profile)
                for role in ('sidebar_text','sidebar_muted'):
                    for background in ('sidebar','sidebar_surface','sidebar_hover'):
                        with self.subTest(theme=name,profile=profile,role=role,bg=background):
                            self.assertGreaterEqual(contrast_ratio(colors[role],colors[background]),4.5)

    def test_old_configs_defaults_and_invalid_profiles(self):
        self.assertEqual(AppConfig().legibility_profile, "normal")
        self.assertFalse(AppConfig().tracking_colors)
        self.assertEqual(AppConfig(legibility_profile='missing').legibility_profile, 'normal')
        self.assertEqual(AppConfig(legibility_profile=[]).legibility_profile, 'normal')
        self.assertFalse(AppConfig(tracking_colors='yes').tracking_colors)

    def test_settings_round_trip_keeps_profile_separate_from_theme(self):
        import config
        from tests.test_support import temporary_directory
        with temporary_directory() as folder, patch.object(config, 'save_credentials'), patch.object(config, 'load_credentials', return_value=('', '')):
            with patch.object(config, 'CONFIG_PATH', Path(folder) / 'config.json'), patch.object(config, '_migrate_legacy_storage'), patch.object(config, '_sanitize_legacy_artifacts'):
                cfg = AppConfig(theme='dark', legibility_profile='contrast', tracking_colors=True)
                config.save_config(cfg)
                saved = json.loads(config.CONFIG_PATH.read_text(encoding='utf-8'))
                self.assertEqual(saved['theme'], 'dark')
                self.assertEqual(saved['legibility_profile'], 'contrast')
                self.assertTrue(saved['tracking_colors'])
                restored = config.load_config()
                self.assertEqual((restored.theme, restored.legibility_profile, restored.tracking_colors), ('dark', 'contrast', True))


class AppearanceUiTests(TestCase):
    def setUp(self):
        from tests.test_filters import FilterTests
        self.fixture = FilterTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_switching_profiles_preserves_cells_selection_and_no_query(self):
        with self.fixture.qt_window() as (window, qt):
            try:
                cells = [window.table.item(i, 1) for i in range(window.table.rowCount())]
                window.table.selectRow(1)
                selected = [i.row() for i in window.table.selectionModel().selectedRows()]
                for theme in THEME_PALETTES:
                    for profile in PROFILES:
                        with qt.QSignalBlocker(window.theme_combo), qt.QSignalBlocker(window.legibility_combo):
                            window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
                            window.legibility_combo.setCurrentIndex(window.legibility_combo.findData(profile))
                        with patch.object(qt, 'fetch_data') as fetch, patch.object(qt, 'QTableWidgetItem', wraps=qt.QTableWidgetItem) as create:
                            window.preview_theme()
                            fetch.assert_not_called()
                            create.assert_not_called()
                        self.assertEqual([window.table.item(i, 1) for i in range(window.table.rowCount())], cells)
                        self.assertEqual([i.row() for i in window.table.selectionModel().selectedRows()], selected)
                        self.assertEqual(qt.ACTIVE_PROFILE, profile)
                        self.assertEqual(window.table.verticalHeader().defaultSectionSize(), qt.ACTIVE_LEGIBILITY.row_height)
                with patch.object(qt, "fetch_data") as fetch:
                    window.tracking_colors_check.setChecked(True)
                    fetch.assert_not_called()
                row = next(i for i in range(window.table.rowCount()) if window.table.item(i, 1).text() == '2')
                tracking = window.table.item(row, 7)
                self.assertEqual(tracking.foreground().color().name(), tracking_color('RETENIDO', qt.ACTIVE_COLORS))
                self.assertEqual(tracking.background().style(), qt.Qt.NoBrush)
                self.assertEqual(tracking.font().weight(), qt.QFont.DemiBold)
                window.tracking_colors_check.setChecked(False)
                active = window.table.item(row, 0).data(qt.Qt.UserRole + 2)
                self.assertEqual(tracking.foreground().color().name(), qt.ACTIVE_COLORS['text' if active == 1 else 'inactive'])
                self.assertEqual(tracking.background().style(), qt.Qt.NoBrush)
                self.assertFalse(tracking.font().bold())
                self.assertTrue(window.settings_dirty())
            finally:
                qt.apply_application_theme(qt.QApplication.instance(), 'light', 'normal')

    def test_presence_colors_survive_priority_refresh_and_switch_off_cleanly(self):
        with self.fixture.qt_window() as (window, qt):
            window.tracking_colors_check.setChecked(True)
            for row, active in enumerate((1, 0, None, 1)):
                window.table.item(row, 0).setData(qt.Qt.UserRole + 2, active)
            window._table_palette = None
            window._refresh_table_colors()
            for row in range(window.table.rowCount()):
                cell = window.table.item(row, 0)
                expected = presence_style(cell.data(qt.Qt.UserRole + 2), False, qt.ACTIVE_COLORS)[0]
                self.assertEqual(cell.foreground().color().name(), expected)
                self.assertEqual(cell.background().style(), qt.Qt.NoBrush)
                self.assertEqual(cell.font().weight(), qt.QFont.DemiBold)
            ot = window.table.item(0, 1).text()
            with patch.object(qt, 'current_priority_ots', return_value={ot}):
                window._refresh_priority_indicators()
            cell = window.table.item(0, 0)
            self.assertEqual(cell.foreground().color().name(), presence_style(1, True, qt.ACTIVE_COLORS)[0])
            window.tracking_colors_check.setChecked(False)
            self.assertEqual(cell.foreground().color().name(), qt.ACTIVE_COLORS['priority'])
            self.assertFalse(cell.font().bold())

    def test_preview_is_saved_only_on_explicit_save_and_restored_in_settings(self):
        from tests.test_ui_workorder_start import settings_window
        import ui_qt as qt
        app = qt.QApplication.instance() or qt.QApplication([])
        window = settings_window()
        window.client_combo = Mock()  # The settings-only harness has no list page.
        try:
            with patch.object(qt, "save_config") as save:
                window.legibility_combo.setCurrentIndex(window.legibility_combo.findData('comfortable'))
                window.tracking_colors_check.setChecked(True)
                save.assert_not_called()
                self.assertEqual(window.cfg.legibility_profile, 'normal')
                self.assertTrue(window.settings_dirty())
                self.assertTrue(window.save_settings(show_feedback=False))
                self.assertEqual(save.call_args.args[0].legibility_profile, 'comfortable')
                self.assertTrue(save.call_args.args[0].tracking_colors)
                self.assertFalse(window.settings_dirty())
                with qt.QSignalBlocker(window.legibility_combo):
                    window.legibility_combo.setCurrentIndex(window.legibility_combo.findData('normal'))
                window._load_config()
                self.assertEqual(window.legibility_combo.currentData(), 'comfortable')
        finally:
            window.deleteLater()
            app.processEvents()
            qt.apply_application_theme(app, 'light', 'normal')
