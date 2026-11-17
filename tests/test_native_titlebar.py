"""Native decoration boundaries/ABI tested with disposable Qt windows."""
import tests
import ctypes
from unittest import TestCase
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QWidget,QDialog
from appearance import THEME_PALETTES,effective_palette,readable_color
import native_titlebar as native


class NativeTitlebarTests(TestCase):
    def test_colorref_and_dwm_arguments_preserve_32_bit_color_order(self):
        self.assertEqual(native.colorref('#123456'),0x563412)
        colors=effective_palette(THEME_PALETTES['dark'])
        calls=[]
        def setter(hwnd,attribute,data,size):
            calls.append((hwnd.value,attribute,ctypes.cast(data,ctypes.POINTER(ctypes.c_uint32)).contents.value,size))
            return 0
        with patch.object(native,'_dwm_setter',return_value=setter):
            self.assertTrue(native.apply_window_titlebar(123,colors))
        self.assertEqual(calls,[(123,20,1,4),(123,35,native.colorref(colors['canvas']),4),
            (123,36,native.colorref(readable_color(colors['text'],[colors['canvas']],4.5)),4),
            (123,34,native.colorref(colors['border_strong']),4)])

    def test_unsupported_systems_or_attributes_do_not_break_windows(self):
        colors=effective_palette(THEME_PALETTES['light'])
        with patch.object(native,'_dwm_setter',return_value=None):
            self.assertFalse(native.apply_window_titlebar(123,colors))
        with patch.object(native,'_dwm_setter',return_value=lambda *_:-2147024809):
            self.assertFalse(native.apply_window_titlebar(123,colors))
        with patch.object(native,'_dwm_setter',return_value=lambda *_:(_ for _ in ()).throw(OSError())):
            self.assertFalse(native.apply_window_titlebar(123,colors))

    def test_show_theme_switch_and_new_dialog_keep_native_flags_and_cache_calls(self):
        app=QApplication.instance() or QApplication([])
        current=[effective_palette(THEME_PALETTES['light'])]
        with patch.object(native,'_is_native_windows',return_value=True),patch.object(native,'apply_window_titlebar',return_value=True) as apply:
            styler=native.NativeTitleBarStyler(app,lambda:current[0]);app.installEventFilter(styler)
            main=QWidget();dialog=QDialog(main);hidden=QDialog(main)
            frameless=QDialog(main,Qt.Dialog|Qt.FramelessWindowHint)
            try:
                original=main.windowFlags()
                main.show();dialog.show();app.processEvents()
                for widget in (main,dialog):
                    self.assertIn(int(widget.winId()),[call.args[0] for call in apply.call_args_list])
                before=apply.call_count
                styler.apply(main);styler.apply(dialog)
                self.assertEqual(apply.call_count,before)
                styler.apply(hidden)
                self.assertFalse(hidden.testAttribute(Qt.WA_WState_Created))
                frameless.show();app.processEvents()
                self.assertNotIn(int(frameless.winId()),[call.args[0] for call in apply.call_args_list])
                current[0]=effective_palette(THEME_PALETTES['dark']);styler.refresh()
                self.assertEqual(apply.call_count,before+2)
                self.assertEqual(main.windowFlags(),original)
                hidden.show();app.processEvents()
                self.assertEqual(apply.call_args.args[1]['canvas'],current[0]['canvas'])
            finally:
                app.removeEventFilter(styler)
                for widget in (frameless,hidden,dialog,main):widget.close();widget.deleteLater()
                styler.deleteLater();app.processEvents()
