"""Native Tk regression checks. Uses an isolated temporary finance workspace."""
import csv
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'finpilot'))
import tkinter as tk
from main import FinPilotApp, enable_windows_dpi_awareness
from models import TransactionType


def run():
    enable_windows_dpi_awareness()
    with tempfile.TemporaryDirectory(prefix='finpilot-test-', dir=Path(__file__).resolve().parents[1]) as directory:
        path = Path(directory) / 'data.json'
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
        app = FinPilotApp(root, path)
        # This test controls persistence explicitly to avoid teardown races with auto-save workers.
        original_async = app.store.save_to_disk_async
        app.store.save_to_disk_async = lambda **kw: None

        def settle(seconds=.12):
            end = time.perf_counter() + seconds
            while time.perf_counter() < end:
                root.update()
                time.sleep(.005)

        sizes = []
        for width in (1360, 1000, 640):
            root.geometry(f'{width}x760')
            for name, view in app._views.items():
                app.switch_view(name)
                settle(.6)
                assert view.winfo_width() <= app.scroll.canvas.winfo_width()
                assert app.scroll.canvas.bbox(app.scroll.window)[2] <= app.scroll.canvas.winfo_width() + 1
                if name == 'dashboard':
                    cards = [view._vault_card, *view._stat_cards.values()]
                    for card in cards:
                        for item in card.find_all():
                            if card.type(item) != 'text' or card.itemcget(item, 'state') == 'hidden': continue
                            box = card.bbox(item)
                            assert box[0] >= 0 and box[2] <= card.winfo_width(), (width, card.itemcget(item,'text'),box)
                    boxes = [(c.winfo_x(),c.winfo_y(),c.winfo_x()+c.winfo_width(),c.winfo_y()+c.winfo_height()) for c in cards]
                    for i,a in enumerate(boxes):
                        for b in boxes[i+1:]:
                            assert a[2]<=b[0] or b[2]<=a[0] or a[3]<=b[1] or b[3]<=a[1]
                sizes.append((width,name,view.winfo_width(),view.winfo_height()))

        app.switch_view('transactions');settle()
        tx = app._views['transactions']
        count = len(app.store.get_transactions())
        tx._amount_var.set('bad input');tx.submit_transaction();settle()
        assert tx._error_var.get() and len(app.store.get_transactions()) == count
        assert tx._error_lbl.winfo_width() > 100, 'Validation must remain visible after toolbar reflow'
        tx._set_form_type(TransactionType.EXPENSE,animate=False)
        tx._amount_var.set('123.45');tx._category_var.set('Food');tx._note_var.set('Regression check')
        tx.submit_transaction();settle()
        assert len(app.store.get_transactions()) == count+1
        tx._search_var.set('Regression check');settle(.25)
        rows = tx.tree.get_children()
        assert len(rows) == 1
        saved = app.store.get_transactions(search='Regression check')[0]
        assert saved.amount_paise == 12345
        tx.tree.selection_set(rows[0]);settle()
        tx.delete_selected_row();tx.delete_selected_row();settle()
        assert len(app.store.get_transactions()) == count
        app.toast._on_action(None);settle()
        assert len(app.store.get_transactions()) == count+1

        app.switch_view('budget');settle()
        budget = app._views['budget']
        budget._custom_cat_var.set('Learning');budget._limit_var.set('2500');budget._save_budget();settle()
        budget._step_budget_limit('Learning',100000);settle()
        assert next(b for b in app.store.get_budgets() if b.category=='Learning').monthly_limit_paise == 350000
        for i in range(14):app.store.set_budget(f'Custom {i}',100000)
        settle()
        assert len([s for s in budget._slots if s.winfo_manager()]) == len(app.store.get_budgets())

        app.switch_view('dashboard');settle(.6)
        hero=app._views['dashboard']._vault_card
        hero.step(100);assert hero.target_pct==75
        hero.step(-100);assert hero.target_pct==10
        app._on_month_selected(app.store.get_available_months()[-1]);settle(.6)
        app._toggle_theme();settle();assert app.theme.mode=='light'
        app._toggle_theme();settle();assert app.theme.mode=='dark'

        app.switch_view('analytics');settle(.6)
        charts=[app._views['analytics']._donut_chart,app._views['analytics']._bar_chart,app._views['analytics']._line_chart]
        timings=[]
        for chart in charts:
            before=len(chart.find_all())
            for _ in range(40):
                start=time.perf_counter();chart._redraw();timings.append((time.perf_counter()-start)*1000)
            assert len(chart.find_all())==before, 'Chart items must be reused'

        ok,msg=app.store.save_to_disk_sync();assert ok, msg
        payload=json.loads(path.read_text(encoding='utf-8'))
        assert len(payload['transactions'])==count+1
        done=threading.Event();result=[]
        csvpath=Path(directory)/'export.csv'
        app.store.export_csv_async(csvpath,app.store.get_transactions(),lambda *args:(result.append(args),done.set()))
        assert done.wait(5) and result[0][0]
        with csvpath.open(encoding='utf-8') as stream:assert len(list(csv.reader(stream)))==count+2
        assert not errors, '\n'.join(errors)
        app.store.save_to_disk_async=original_async
        app.shutdown()
        print(json.dumps({'status':'PASS','layouts':sizes,'callback_errors':len(errors),
                          'median_chart_redraw_ms':round(statistics.median(timings),2),
                          'checks':['responsive layout','metric text bounds','validation','add/search/delete/undo',
                                    'budget edits and more than 12 categories','simulator limits','month selection',
                                    'light/dark themes','retained chart objects','JSON save','CSV export']},indent=2))


if __name__=='__main__':run()
