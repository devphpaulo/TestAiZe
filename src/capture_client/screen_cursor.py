"""Composite the Windows cursor into the frozen desktop before showing the editor."""

from contextlib import contextmanager
from ctypes import Structure, byref, sizeof
from ctypes import wintypes as win
from dataclasses import dataclass
import sys

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter


class _CursorInfo(Structure):
    # Python 3.12 does not expose HCURSOR. Like HICON, it is a HANDLE.
    _fields_ = [('size', win.DWORD), ('flags', win.DWORD),
                ('handle', win.HANDLE), ('position', win.POINT)]


class _IconInfo(Structure):
    _fields_ = [('is_icon', win.BOOL), ('hot_x', win.DWORD), ('hot_y', win.DWORD),
                ('mask', win.HBITMAP), ('color', win.HBITMAP)]


class _Bitmap(Structure):
    _fields_ = [('kind', win.LONG), ('width', win.LONG), ('height', win.LONG),
                ('stride', win.LONG), ('planes', win.WORD), ('bits_per_pixel', win.WORD),
                ('bits', win.LPVOID)]


if sys.platform == 'win32':
    from ctypes import POINTER, WinDLL

    _user = WinDLL('user32')
    _gdi = WinDLL('gdi32')
    _user.GetCursorInfo.argtypes = [POINTER(_CursorInfo)]
    _user.CopyIcon.argtypes = [win.HICON]
    _user.CopyIcon.restype = win.HICON
    _user.DestroyIcon.argtypes = [win.HICON]
    _user.GetIconInfo.argtypes = [win.HICON, POINTER(_IconInfo)]
    _user.DrawIconEx.argtypes = [win.HDC, win.INT, win.INT, win.HICON, win.INT, win.INT,
                                win.UINT, win.HBRUSH, win.UINT]
    _gdi.GetObjectW.argtypes = [win.HGDIOBJ, win.INT, win.LPVOID]
    _gdi.CreateCompatibleDC.argtypes = [win.HDC]
    _gdi.CreateCompatibleDC.restype = win.HDC
    _gdi.SelectObject.argtypes = [win.HDC, win.HGDIOBJ]
    _gdi.SelectObject.restype = win.HGDIOBJ
    _gdi.DeleteObject.argtypes = [win.HGDIOBJ]
    _gdi.DeleteDC.argtypes = [win.HDC]


@dataclass(frozen=True)
class _ScreenCursor:
    handle: int
    bounds: QRect

    def paint(self, image: QImage, origin_x: int, origin_y: int) -> bool:
        local = self.bounds.translated(-origin_x, -origin_y)
        region = local.intersected(image.rect())
        if region.isEmpty():
            return False

        # Draw over the original pixels so monochrome cursors can invert the background.
        tile = image.copy(region).convertToFormat(QImage.Format.Format_RGB32)
        bitmap = tile.toHBITMAP()
        if not bitmap:
            return False
        try:
            dc = _gdi.CreateCompatibleDC(None)
            if not dc:
                return False
            try:
                previous = _gdi.SelectObject(dc, bitmap)
                if not previous:
                    return False
                try:
                    di_normal = 0x0003
                    drawn = _user.DrawIconEx(dc, local.x() - region.x(), local.y() - region.y(),
                                             self.handle, 0, 0, 0, None, di_normal)
                    _gdi.GdiFlush()
                finally:
                    _gdi.SelectObject(dc, previous)
            finally:
                _gdi.DeleteDC(dc)
            if not drawn:
                return False
            tile = QImage.fromHBITMAP(bitmap)
        finally:
            _gdi.DeleteObject(bitmap)
        if tile.isNull():
            return False

        dpr = image.devicePixelRatio()
        image.setDevicePixelRatio(1)
        with QPainter(image) as painter:
            painter.drawImage(region.topLeft(), tile)
        image.setDevicePixelRatio(dpr)
        return True


def _bounds(handle, position):
    icon = _IconInfo()
    if not _user.GetIconInfo(handle, byref(icon)):
        return None
    try:
        bitmap = _Bitmap()
        if not _gdi.GetObjectW(icon.color or icon.mask, sizeof(bitmap), byref(bitmap)):
            return None
        # Monochrome cursors store their AND and XOR masks one above the other.
        height = bitmap.height if icon.color else bitmap.height // 2
        return QRect(position.x - icon.hot_x, position.y - icon.hot_y, bitmap.width, height)
    finally:
        if icon.color:
            _gdi.DeleteObject(icon.color)
        if icon.mask:
            _gdi.DeleteObject(icon.mask)


@contextmanager
def snapshot_cursor():
    if sys.platform != 'win32':
        yield None
        return
    info = _CursorInfo(size=sizeof(_CursorInfo))
    cursor_showing = 0x0001
    handle = None
    if _user.GetCursorInfo(byref(info)) and info.flags == cursor_showing and info.handle:
        handle = _user.CopyIcon(info.handle)
    try:
        bounds = _bounds(handle, info.position) if handle else None
        yield _ScreenCursor(handle, bounds) if bounds is not None else None
    finally:
        if handle:
            _user.DestroyIcon(handle)
