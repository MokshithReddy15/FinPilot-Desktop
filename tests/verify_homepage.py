"""Homepage interaction, cached artwork and responsive layout regression checks."""
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'finpilot'))
from main import FinPilotApp, enable_windows_dpi_awareness


def run():
    enable_windows_dpi_awareness()
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        app = FinPilotApp(root, Path(directory)/'data.json')
        app.store.save_to_disk_async = lambda **kwargs: None
        view = app._views['dashboard']
        hero = view._vault_card

        def settle():
            until = time.perf_counter()+.7
            while time.perf_counter()<until:
                root.update()
                time.sleep(.005)

        for width in (1360,1000,640):
            root.geometry(f'{width}x760');settle()
            a,b,y = hero._track
            hero.drag(SimpleNamespace(x=a,y=y));assert hero.target_pct==10
            hero.drag(SimpleNamespace(x=b,y=y));assert hero.target_pct==75
            hero.step(-100);assert hero.target_pct==10
            original = hero._art
            before = len(hero.find_all())
            for _ in range(30):hero.draw()
            assert hero._art is original, 'Hover/value updates must reuse artwork'
            assert len(hero.find_all())==before, 'Canvas items must not accumulate'
            for metric in view._stat_cards.values():
                count = len(metric.find_all())
                for _ in range(20):metric.draw()
                assert len(metric.find_all())==count
            for row in view._recent_rows:
                assert row['title'].master is row['details']
                assert row['note'].master is row['details']
                if row['frame'].winfo_ismapped():
                    assert row['title'].winfo_ismapped()
                    assert row['title'].winfo_y()+row['title'].winfo_height()<=row['note'].winfo_y()
            for item in hero.find_all():
                if hero.type(item)=='text' and hero.itemcget(item,'state')!='hidden':
                    x0,y0,x1,y1 = hero.bbox(item)
                    assert 0<=x0<x1<=hero.winfo_width()
                    assert 0<=y0<y1<=hero.winfo_height()
        app._toggle_theme();settle()
        app._toggle_theme();settle()
        view._scope_toggle._keyboard_select(1)
        assert view._scope_mode=='MONTH'
        view._scope_toggle._keyboard_select(-1)
        assert view._scope_mode=='ALL'
        sample=view._horizon_chart._series[0]
        chart=view._horizon_chart
        chart._on_motion(SimpleNamespace(x=62))
        assert chart._hovered_idx==0
        assert any('Expenses' in chart.itemcget(i,'text') for i in chart.find_withtag('cashflow_tooltip') if chart.type(i)=='text')
        count=len(chart.find_all())
        for _ in range(20):chart._redraw()
        assert len(chart.find_all())==count
        chart._on_leave(None)
        assert chart._hovered_idx is None
        view._on_inspect_horizon_month(sample)
        assert 'Income' in view._legend_income.cget('text')
        assert 'Expenses' in view._legend_expense.cget('text')
        row=view._recent_rows[0]
        view._highlight_row(row,True)
        assert row['title'].cget('bg')==app.theme.tokens['surface_hover']
        view._highlight_row(row,False)
        from activity import date_heading
        from datetime import date
        assert date_heading('2026-11-02',date(2026,11,2))=='Today'
        assert date_heading('2026-11-01',date(2026,11,2))=='Yesterday'
        assert date_heading('2026-10-31',date(2026,11,2))=='31 Oct 2026'
        for filter_key in ('INCOME','EXPENSE','ALL'):
            view._on_recent_filter_change(filter_key);settle()
            previous=None
            for row in view._recent_rows:
                tx=row['transaction']
                if tx is None:continue
                assert filter_key=='ALL' or tx.type.value==filter_key
                assert bool(row['group'].winfo_manager())==(tx.date!=previous)
                previous=tx.date
            dialog=view._show_transaction(view._recent_rows[0])
            root.update();assert dialog.winfo_exists();dialog.destroy()
        assert not errors, errors
        app.shutdown()
        print('PASS: homepage layout, slider hit areas, cached artwork, retained objects, transaction labels and themes')


if __name__=='__main__':run()
