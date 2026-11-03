"""Synthetic reports: table wrapping, pagination, resize and composer visibility."""
import sys,time,tempfile,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
import tkinter as tk
from main import FinPilotApp,enable_windows_dpi_awareness
from rich_report import blocks

assert list(blocks('| A | B |\n|---|---:|\n| one | two |'))[0][1][1]==[['one','two']]
assert list(blocks('| A | B |\n|---|---|\n| one | two | extra |'))[0][1][1]==[['one','two | extra']]
enable_windows_dpi_awareness()
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
    root=tk.Tk();errors=[]
    root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
    app=FinPilotApp(root,Path(d)/'data.json');app.store.save_to_disk_async=lambda **kw:None
    app.switch_view('assistant');view=app._views['assistant']
    def settle():
        end=time.monotonic()+.3
        while time.monotonic()<end:root.update();time.sleep(.005)
    sample='## Synthetic table\n**Readable figures**\n| Category | Description | Amount |\n|---|---|---:|\n'
    sample+='\n'.join('| Food | A long description with enough words to wrap across multiple lines in a narrow column | ₹1,250 |' for _ in range(25))
    view.append('Renderer test',sample);settle()
    table=view.transcript.tables[-1]
    assert len(table.rows)==25
    assert len(table.canvas.find_all())<150
    table.turn(1);assert table.page==1
    for width,height in [(1360,800),(1000,760),(640,520)]:
        root.geometry(f'{width}x{height}');settle()
        view.select_panel('chat');settle()
        assert view.question.winfo_ismapped()
        bottom=view.send_btn.winfo_rooty()+view.send_btn.winfo_height()
        assert bottom<=root.winfo_rooty()+root.winfo_height(),(width,height,bottom,root.winfo_height())
        assert int(table.cget('width'))<=view.transcript.winfo_width()
        if table.winfo_ismapped():assert table.winfo_width()<=view.transcript.winfo_width()
        view.select_panel('report');settle();view.select_panel('chat');settle()
    view.clear_chat();assert not view.transcript.tables
    app._toggle_theme();settle();app._toggle_theme();settle()
    assert not errors,errors
    app.shutdown()
print('PASS: table parsing, wrapping, pagination, responsive panels, composer bounds and theme changes')

