"""Exercise the native clipboard reader with fake Windows APIs, not user clipboard data."""
import ctypes
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
from clipboard_text import read_text,ClipboardUnavailable


class ClipboardTests(unittest.TestCase):
    def api(self,available=True,opened=True):
        self.buf=ctypes.create_unicode_buffer('sk-or-dummy-文字')
        user=Mock();kernel=Mock()
        user.OpenClipboard.return_value=opened
        user.IsClipboardFormatAvailable.return_value=available
        user.GetClipboardData.return_value=123
        kernel.GlobalLock.return_value=ctypes.addressof(self.buf)
        return user,kernel

    def test_unicode_and_release(self):
        user,kernel=self.api()
        with patch('clipboard_text.ctypes.WinDLL',side_effect=[user,kernel]):
            self.assertEqual(read_text(None),'sk-or-dummy-文字')
        kernel.GlobalUnlock.assert_called_once_with(123)
        user.CloseClipboard.assert_called_once()

    def test_no_text_closes_clipboard(self):
        user,kernel=self.api(available=False)
        with patch('clipboard_text.ctypes.WinDLL',side_effect=[user,kernel]):
            with self.assertRaises(ClipboardUnavailable):read_text(None)
        user.CloseClipboard.assert_called_once()

    def test_busy_does_not_close_another_owner(self):
        user,kernel=self.api(opened=False)
        with patch('clipboard_text.ctypes.WinDLL',side_effect=[user,kernel]):
            with self.assertRaises(ClipboardUnavailable):read_text(None)
        user.CloseClipboard.assert_not_called()

if __name__=='__main__':unittest.main()
