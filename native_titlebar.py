"""Theme native Windows captions without changing window styles or controls.

DWM attributes: https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
Unsupported platforms/attributes leave the system decoration in place.
"""
import ctypes
from ctypes import wintypes
from functools import lru_cache
import sys
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtWidgets import QWidget
from appearance import is_dark,readable_color


def colorref(color):
    return int(color[1:3],16) | int(color[3:5],16)<<8 | int(color[5:7],16)<<16


@lru_cache(maxsize=1)
def _dwm_setter():
    if sys.platform!='win32':return None
    try:
        function=ctypes.WinDLL('dwmapi',use_last_error=True).DwmSetWindowAttribute
        function.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        function.restype=ctypes.c_long
        return function
    except (OSError,AttributeError):return None


def apply_window_titlebar(hwnd,colors):
    setter=_dwm_setter()
    if setter is None or not hwnd:return False
    text=readable_color(colors['text'],[colors['canvas']],4.5)
    values=((20,int(is_dark(colors))), (35,colorref(colors['canvas'])),
            (36,colorref(text)), (34,colorref(colors['border_strong'])))
    supported=True
    for attribute,value in values:
        data=ctypes.c_uint32(value)
        try:
            result=setter(wintypes.HWND(hwnd),attribute,ctypes.byref(data),ctypes.sizeof(data))
            supported=(result==0) and supported
        except (OSError,ctypes.ArgumentError):supported=False
    return supported


def _is_native_windows(app):
    return sys.platform=='win32' and app.platformName()=='windows'


class NativeTitleBarStyler(QObject):
    """Apply on native handle creation/show and update already open windows."""
    _events=(QEvent.Show,QEvent.WinIdChange,QEvent.WindowStateChange)

    def __init__(self,app,palette):
        super().__init__(app)
        self.app=app;self.palette=palette;self.enabled=_is_native_windows(app)
        self._applying=False

    def refresh(self):
        if self.enabled:
            for widget in self.app.topLevelWidgets():
                if widget.isVisible():self.apply(widget)

    def apply(self,widget):
        if not self.enabled or self._applying or not isinstance(widget,QWidget):return
        if not widget.isWindow() or widget.windowType() not in (Qt.Window,Qt.Dialog,Qt.Tool,Qt.Sheet):return
        if widget.windowFlags() & Qt.FramelessWindowHint:return
        # Never create native handles just to recolor a hidden/control widget.
        if not widget.testAttribute(Qt.WA_WState_Created):return
        colors=self.palette()
        self._applying=True
        try:
            hwnd=int(widget.winId())
            signature=(hwnd,colors['canvas'],colors['text'],colors['border_strong'])
            if widget.property('_md_caption_signature')==signature:return
            apply_window_titlebar(hwnd,colors)
            # Cache unsupported attributes too: no repeated calls on old Windows.
            widget.setProperty('_md_caption_signature',signature)
        finally:self._applying=False

    def eventFilter(self,watched,event):
        if event.type() in self._events:self.apply(watched)
        return False
