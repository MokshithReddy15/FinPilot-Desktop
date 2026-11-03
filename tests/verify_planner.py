"""Exercise the planner forms against an isolated workspace."""
import sys,tempfile,time,traceback
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finpilot'))
import tkinter as tk
from tkinter import ttk
from main import FinPilotApp,enable_windows_dpi_awareness
from widgets import PillButton

def run():
    enable_windows_dpi_awareness()
    with tempfile.TemporaryDirectory(prefix='planner-ui-',dir=Path(__file__).resolve().parents[1]) as tmp:
        root=tk.Tk();errors=[]
        root.report_callback_exception=lambda *e:errors.append(''.join(traceback.format_exception(*e)))
        app=FinPilotApp(root,Path(tmp)/'finance.json');app.switch_view('planner');view=app._views['planner']
        def settle():
            for _ in range(20):root.update();time.sleep(.005)
        def submit(top,values):
            form=top.winfo_children()[0]
            fields=[w for w in form.winfo_children() if isinstance(w,(ttk.Entry,ttk.Combobox))]
            for widget,value in zip(fields,values):
                if isinstance(widget,ttk.Combobox):widget.set(value)
                else:widget.delete(0,'end');widget.insert(0,value)
            next(w for w in form.winfo_children() if isinstance(w,PillButton)).command()
            settle()
        settle()
        assert len(view._suggestions)==len(view.pattern_tree.get_children())
        if view._suggestions:
            view.pattern_tree.selection_set('0');view.confirm_suggestion();settle()
            popup=next(w for w in view.winfo_children() if isinstance(w,tk.Toplevel))
            popup.destroy()
            count=len(view._suggestions);view.refresh(False,scenario_only=True)
            assert len(view._suggestions)==count
        today=date.today().isoformat()
        top=view.payment_editor();submit(top,['Payday','INCOME','30000',today,'Monthly','Salary',''])
        assert len(view.book.data['payments'])==1 and not top.winfo_exists()
        top=view.goal_editor();submit(top,['Laptop','80000','10000',today])
        assert len(view.book.data['goals'])==1
        top=view.set_balance()
        submit(top,['25000','Positive']);assert view._base['balance']==2500000
        for width in (1360,1000,640):
            root.geometry(f'{width}x760');settle()
            for tab in view.pages:
                view.show_page(tab);settle()
                assert view.pages[tab].winfo_width()<=view.winfo_width()
        base=view._base['closing'];view._purchase.set('1000');view._reduction.set(0);view.refresh(False,scenario_only=True)
        assert view._preview['closing']==base-100000
        view._purchase.set('NaN');view.refresh(False,scenario_only=True);assert 'Preview paused' in view._scenario_error.get()
        view.reset_scenario();assert view._preview['closing']==base
        app._toggle_theme();settle();app._toggle_theme();settle()
        top=view.payment_editor(view.book.data['payments'][0]);submit(top,['Payday','INCOME','0',today,'Monthly','Salary',''])
        assert top.winfo_exists() and view.book.data['payments'][0]['amount']==3000000
        top.destroy()
        from planning import PlanningBook
        assert PlanningBook(view.book.path).data==view.book.data
        assert not errors,errors
        app.shutdown()
        print('PASS: planner add/edit validation, persistence, balance snapshot, scenarios, four panels at three widths, themes; zero callback errors')

if __name__=='__main__':run()
