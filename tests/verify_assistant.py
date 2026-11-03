"""Native assistant integration; fake network response, no financial data transmitted."""
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
import tkinter as tk
from main import FinPilotApp, enable_windows_dpi_awareness

enable_windows_dpi_awareness()
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
    root=tk.Tk();errors=[]
    root.report_callback_exception=lambda *e:errors.append(e)
    app=FinPilotApp(root,Path(directory)/'test.json')
    app.store.save_to_disk_async=lambda **kw:None
    app.switch_view('assistant');v=app._views['assistant']
    def settle(seconds=.2):
        end=time.monotonic()+seconds
        while time.monotonic()<end:root.update();time.sleep(.005)
    v.preview();settle()
    assert 'Local report'.upper() in v.transcript.get('1.0','end')
    v.key='fake-test-key';v.model='test/model:free';v.consent.set(True)
    with patch('views.assistant.ask_openrouter',return_value='Mock explanation') as call:
        v.send();settle(.4)
        assert not v.busy and len(v.history)==2
        assert call.call_count==1
    gate=Event()
    def slow(*a,**kw):gate.wait(3);return 'Cancelled result must not appear'
    with patch('views.assistant.ask_openrouter',side_effect=slow):
        v.send();v.cancel();gate.set();settle(.4)
        assert 'Cancelled result must not appear' not in v.transcript.get('1.0','end')
    v.month.set(app.store.get_latest_month());v.scope_changed()
    assert not v.history and not v.consent.get()
    root.geometry('640x520');settle()
    nav=app._nav_buttons['assistant']
    assert nav.winfo_ismapped() and nav.winfo_y()+nav.winfo_height()<root.winfo_height()
    app._toggle_theme();settle();app._toggle_theme();settle()
    for mode in range(2):
        dialog=v.settings();settle()
        entry=dialog.key_entry
        assert entry.cget('foreground') != entry.cget('background')
        assert entry.cget('insertbackground') != entry.cget('background')
        assert entry.cget('show') == '*'
        # Mock clipboard reads: never inspect or overwrite the user's clipboard.
        with patch('views.assistant.read_text',return_value='sk-or-dummy-paste-value'):
            entry.delete(0,'end');entry.insert(0,'old-key');dialog.paste_key()
            assert entry.get()=='sk-or-dummy-paste-value'
            entry.selection_range(0,'end');entry.event_generate('<<Paste>>');settle()
            assert entry.get()=='sk-or-dummy-paste-value'
        from clipboard_text import ClipboardUnavailable
        with patch('views.assistant.read_text',side_effect=ClipboardUnavailable('no text')):
            dialog.paste_key()
        assert dialog.model_entry.cget('foreground') != dialog.model_entry.cget('background')
        dialog.destroy();app._toggle_theme();settle()
    assert not errors,errors
    app.shutdown()
    assert not v.key
    assert all('fake-test-key' not in p.read_text(encoding='utf-8') for p in Path(directory).glob('*.json'))
print('PASS: local preview, mock chat, cancellation, scope reset, minimum window, themes, session key cleanup')
