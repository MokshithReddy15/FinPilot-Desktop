"""Read Unicode clipboard text when a user explicitly requests Paste."""
import ctypes
import os
from ctypes import wintypes


class ClipboardUnavailable(Exception):
    pass


def read_text(widget):
    if os.name != 'nt':
        try:return widget.clipboard_get()
        except Exception:raise ClipboardUnavailable('Copy the key as text, then try Paste again.') from None
    # Tk's clipboard format conversion can fail for text copied from Chromium apps.
    # Read CF_UNICODETEXT directly, without changing clipboard ownership or contents.
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.OpenClipboard.argtypes=[wintypes.HWND];user.OpenClipboard.restype=wintypes.BOOL
    user.CloseClipboard.argtypes=[];user.CloseClipboard.restype=wintypes.BOOL
    user.GetClipboardData.argtypes=[wintypes.UINT];user.GetClipboardData.restype=wintypes.HANDLE
    user.IsClipboardFormatAvailable.argtypes=[wintypes.UINT];user.IsClipboardFormatAvailable.restype=wintypes.BOOL
    kernel.GlobalLock.argtypes=[wintypes.HANDLE];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HANDLE];kernel.GlobalUnlock.restype=wintypes.BOOL
    if not user.OpenClipboard(None):
        raise ClipboardUnavailable('Clipboard is busy. Try Paste again in a moment.')
    try:
        if not user.IsClipboardFormatAvailable(13):
            raise ClipboardUnavailable('Clipboard has no text. Copy the key itself, then paste.')
        handle=user.GetClipboardData(13)
        pointer=kernel.GlobalLock(handle) if handle else None
        if not pointer:raise ClipboardUnavailable('Clipboard text could not be opened. Copy it again.')
        try:return ctypes.wstring_at(pointer)
        finally:kernel.GlobalUnlock(handle)
    finally:user.CloseClipboard()
