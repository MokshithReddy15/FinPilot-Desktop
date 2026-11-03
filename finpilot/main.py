"""FinPilot native desktop shell. Run python finpilot/main.py."""
from pathlib import Path
from queue import SimpleQueue
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox
from animations import Animator
from seed import generate_demo_data
from store import DataStore
from theme import ThemeManager
from views.analytics import AnalyticsView
from views.budget import BudgetView
from views.planner import PlannerView
from views.assistant import AssistantView
from views.dashboard import DashboardView
from views.transactions import TransactionsView
from widgets import PillButton, ToastNotification
from layout import ScrollViewport
from surfaces import NavButton


def enable_windows_dpi_awareness():
    # One coherent 96-DPI coordinate system for fonts, widgets, and Canvas.
    # Enhanced GDI scaling preserves layout coordinates while improving text
    # rendering on high-DPI displays. Bitmap artwork still uses system scaling.
    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
        if not set_context(ctypes.c_void_p(-5)):
            set_context(ctypes.c_void_p(-1))
    except (AttributeError, OSError):
        pass


class FinPilotApp:
    def __init__(self, root, storage_path=None):
        self.root=root
        root.title('FinPilot — Your money, in perspective')
        width=min(1440,root.winfo_screenwidth()-80)
        height=min(960,root.winfo_screenheight()-100)
        root.geometry(f'{width}x{height}+30+30')
        root.minsize(640,520)
        self.theme=ThemeManager('dark');self.theme.apply_ttk_styles(root)
        self.animator=Animator(root)
        self.store=DataStore(storage_path=storage_path or Path(__file__).resolve().parent/'finpilot_data.json')
        loaded,_=self.store.load_from_disk_sync()
        if not loaded:self.store.load_seed_data(*generate_demo_data())
        self._active_month=self.store.get_latest_month()
        self._active_view_key='';self._views={};self._nav_buttons={}
        self._messages=SimpleQueue();self._closing=False;self._compact=None
        self._build_shell()
        self.store.subscribe(self._on_store_change)
        root.bind('<Configure>',self._on_window_resize)
        root.bind('<Control-n>',lambda e:self._new_transaction())
        root.protocol('WM_DELETE_WINDOW',self.shutdown)
        self.switch_view('dashboard')
        self._poll_messages()

    def _build_shell(self):
        t=self.theme.tokens
        self.root.configure(bg=t['background'])
        self.root.columnconfigure(1,weight=1);self.root.rowconfigure(0,weight=1)
        self.sidebar=tk.Frame(self.root,bg=t['surface'],width=224)
        self.sidebar.grid(row=0,column=0,sticky='nsew');self.sidebar.pack_propagate(False)
        self.brand=tk.Label(self.sidebar,text='◈  FinPilot',bg=t['surface'],fg=t['text_primary'],font=(self.theme.font_family,-25,'bold'),anchor='w',padx=22,pady=25)
        self.brand.pack(fill='x')
        self.nav_caption=tk.Label(self.sidebar,text='W O R K S P A C E',bg=t['surface'],fg=t['text_muted'],font=(self.theme.font_family,-10),anchor='w',padx=24,pady=12)
        self.nav_caption.pack(fill='x')
        for key,label in [('dashboard','Overview'),('transactions','Transactions'),('analytics','Analytics'),('budget','Budget planner'),('planner','Future planner'),('assistant','AI assistant')]:
            btn=NavButton(self.sidebar,self.theme,self.animator,key,label,lambda k=key:self.switch_view(k))
            btn.pack(fill='x',padx=8,pady=3);self._nav_buttons[key]=btn
        self.bottom=tk.Frame(self.sidebar,bg=t['surface']);self.bottom.pack(side='bottom',fill='x',padx=18,pady=24)
        self.footer=tk.Label(self.bottom,text='LOCAL WORKSPACE\nAI sharing is controlled by you.',justify='left',anchor='w',bg=t['surface'],fg=t['text_muted'],font=(self.theme.font_family,-11),pady=16)
        self.footer.pack(fill='x')
        self.theme_btn=PillButton(self.bottom,self.theme,'Switch to light',self._toggle_theme,variant='secondary',height=36)
        self.theme_btn.pack(fill='x',pady=4)
        self.demo_btn=PillButton(self.bottom,self.theme,'Reset demo data',self._load_demo_data,variant='secondary',height=34)
        self.demo_btn.pack(fill='x',pady=4)
        self.clear_btn=PillButton(self.bottom,self.theme,'Clear workspace',self._clear_all_data,variant='danger',height=32)
        self.clear_btn.pack(fill='x',pady=4)
        self.compact_theme=PillButton(self.sidebar,self.theme,'◐',self._toggle_theme,variant='secondary',width=42,height=36)
        self.content=tk.Frame(self.root,bg=t['background']);self.content.grid(row=0,column=1,sticky='nsew')
        self.content.columnconfigure(0,weight=1);self.content.rowconfigure(2,weight=1)
        self.topbar=tk.Frame(self.content,bg=t['background'],padx=26,pady=22)
        self.topbar.grid(row=0,column=0,sticky='ew');self.topbar.columnconfigure(0,weight=1)
        self.eyebrow=tk.Label(self.topbar,text='PERSONAL FINANCE  /  OVERVIEW',anchor='w',bg=t['background'],fg=t['text_muted'],font=(self.theme.font_family,-10,'bold'))
        self.eyebrow.grid(row=0,column=0,sticky='w')
        self.title=tk.Label(self.topbar,text='',anchor='w',bg=t['background'],fg=t['text_primary'],font=(self.theme.font_family,-28,'bold'))
        self.title.grid(row=1,column=0,sticky='w',pady=(7,3))
        self.subtitle=tk.Label(self.topbar,text='',anchor='w',bg=t['background'],fg=t['text_muted'],font=self.theme.fonts['body'])
        self.subtitle.grid(row=2,column=0,sticky='w')
        self.actions=tk.Frame(self.topbar,bg=t['background']);self.actions.grid(row=1,column=1,rowspan=2,sticky='e')
        self.save_btn=PillButton(self.actions,self.theme,'Save',self._save_json_now,variant='secondary',width=64,height=36,parent_bg_key='background')
        self.save_btn.pack(side='left',padx=6)
        self.add_btn=PillButton(self.actions,self.theme,'+ Add transaction',self._new_transaction,width=146,height=36,parent_bg_key='background')
        self.add_btn.pack(side='left')
        self.transition=tk.Canvas(self.content,height=2,bd=0,highlightthickness=0,bg=t['border'])
        self.transition.grid(row=1,column=0,sticky='ew')
        self.transition_line=self.transition.create_rectangle(0,0,0,2,fill=t['primary'],outline='')
        self.scroll=ScrollViewport(self.content,self.theme);self.scroll.grid(row=2,column=0,sticky='nsew')
        self.viewport=self.scroll.body
        self.toast=ToastNotification(self.root,self.theme,self.animator)
        self._views={
            'dashboard':DashboardView(self.viewport,self.store,self.theme,self.animator,self.switch_view,self._load_demo_data,self._on_month_selected,self._new_transaction),
            'transactions':TransactionsView(self.viewport,self.store,self.theme,self.animator,self.toast),
            'analytics':AnalyticsView(self.viewport,self.store,self.theme,self.animator,self._on_month_selected),
            'planner':PlannerView(self.viewport,self.store,self.theme,self.animator,self.toast),
            'budget':BudgetView(self.viewport,self.store,self.theme,self.animator,self.toast),
            'assistant':AssistantView(self.content,self.store,self.theme,self.animator,self.toast),
        }

    def switch_view(self,key):
        if key not in self._views:return
        # Finish hidden animations at their data values before cancelling their timers.
        if self._active_view_key:
            old=self._views[self._active_view_key]
            old.refresh(animate=False)
            old.grid_forget()
        for job in list(self.animator._active_jobs):
            if job not in ('toast_dismiss',):self.animator.cancel(job)
        self._active_view_key=key
        labels={'dashboard':('Your money, in perspective.','A clearer view of what comes in, goes out, and stays yours.'),'transactions':('Every detail, accounted for.','Log a moment. Keep the bigger picture.'),'analytics':('See the story in your spending.','Explore your patterns, one month at a time.'),'budget':('Make room for what matters.','Set intentional limits. Stay in control.')}
        labels['planner']=('Make your next move count.','Forecast your month. Explore a choice. Build toward a goal.')
        labels['assistant']=('Meet your money assistant.','Explore your records. Understand the story behind the numbers.')
        self.title.configure(text=labels[key][0]);self.subtitle.configure(text=labels[key][1])
        self.eyebrow.configure(text='PERSONAL FINANCE  /  '+key.upper())
        for k,b in self._nav_buttons.items():b.set_active(k==key)
        view=self._views[key]
        if not view.is_built:view.build()
        if key=='assistant':
            self.scroll.grid_remove()
            view.grid(row=2,column=0,sticky='nsew',padx=24,pady=12)
        else:
            self.scroll.grid()
            view.grid(row=0,column=0,sticky='ew')
        view.refresh(animate=True)
        self.scroll.top();self._responsive()
        self.animator.animate_value('view_transition',0,1,380,lambda v:self.transition.coords(self.transition_line,0,0,self.transition.winfo_width()*v,2))

    def _on_month_selected(self,month):
        self._active_month=month
        for key in ('dashboard','analytics'):
            v=self._views[key]
            if key=='dashboard':v._active_month=month
            else:v._month_var.set(month)
            v.is_dirty=True
        self._views[self._active_view_key].refresh(animate=True)

    def _on_store_change(self,*_):
        for key,v in self._views.items():
            if key==self._active_view_key:v.refresh(animate=True)
            else:v.is_dirty=True
        self.store.save_to_disk_async()

    def _new_transaction(self):
        self.switch_view('transactions');self._views['transactions'].focus_amount_field()

    def _on_window_resize(self,event):
        if event.widget is self.root:self.animator.debounce('shell_resize',45,self._responsive)

    def _responsive(self):
        width=self.root.winfo_width();compact=width<1100 or self.root.winfo_height()<700
        if compact!=self._compact:
            self._compact=compact;self.sidebar.configure(width=76 if compact else 224)
            self.brand.configure(text='◈' if compact else '◈  FinPilot',padx=22,pady=12 if compact else 25)
            self.nav_caption.configure(text='' if compact else 'W O R K S P A C E',pady=0 if compact else 12)
            if compact:
                self.bottom.pack_forget();self.compact_theme.pack(side='bottom',padx=12,pady=24)
            else:
                self.compact_theme.pack_forget();self.bottom.pack(side='bottom',fill='x',padx=18,pady=24)
            for b in self._nav_buttons.values():b.compact=compact;b.draw()
        self.title.configure(font=(self.theme.font_family,-21 if width<1000 else -28,'bold'),wraplength=max(300,width-(140 if compact else 290)))
        self.subtitle.configure(wraplength=max(300,width-(140 if compact else 290)))
        if width>=1200:
            self.title.configure(wraplength=width-540,font=(self.theme.font_family,-26,'bold'))
            self.subtitle.configure(wraplength=width-540)
            self.actions.grid(row=1,column=1,columnspan=1,rowspan=2,sticky='e',pady=0)
        else:
            self.actions.grid(row=3,column=0,columnspan=2,rowspan=1,sticky='w',pady=(14,0))

        short_assistant=self._active_view_key=='assistant' and self.root.winfo_height()<650
        self.topbar.configure(pady=8 if short_assistant else (12 if self._active_view_key=='dashboard' else 22))
        if short_assistant:
            self.eyebrow.grid_remove();self.subtitle.grid_remove();self.actions.grid_remove()
            self.title.configure(font=(self.theme.font_family,-20,'bold'))
        else:
            self.eyebrow.grid();self.subtitle.grid();self.actions.grid()

    def _toggle_theme(self):
        old=dict(self.theme.tokens);self.theme.toggle_mode(self.root);new=self.theme.tokens
        mapping={old[k]:new[k] for k in old}
        def recolor(w):
            for opt in ('background','foreground','highlightbackground'):
                try:
                    value=w.cget(opt)
                    if value in mapping:w.configure(**{opt:mapping[value]})
                except tk.TclError:pass
            for child in w.winfo_children():recolor(child)
        recolor(self.root)
        for v in self._views.values():
            if v.is_built:v.apply_theme()
        for b in self._nav_buttons.values():b.apply_theme()
        for b in (self.theme_btn,self.demo_btn,self.clear_btn,self.save_btn,self.add_btn,self.compact_theme):b.apply_theme()
        self.theme_btn.set_text('Switch to light' if self.theme.mode=='dark' else 'Switch to dark')
        self.scroll.apply_theme()
        self.transition.itemconfigure(self.transition_line,fill=new['primary'])

    def _load_demo_data(self):
        if messagebox.askyesno('Reset demo data','Replace this workspace with six months of demo transactions?',parent=self.root):
            self.store.load_seed_data(*generate_demo_data());self.toast.show('Demo workspace restored.',level='success')

    def _clear_all_data(self):
        if messagebox.askyesno('Clear workspace','Delete all transactions and budget limits from this workspace?',parent=self.root):self.store.clear_all_data()

    def _save_json_now(self):
        self.store.save_to_disk_async(on_complete=lambda ok,msg:self._messages.put((ok,msg)))

    def _poll_messages(self):
        while not self._messages.empty():
            ok,msg=self._messages.get();self.toast.show(msg,level='success' if ok else 'danger')
        if not self._closing:self._poll_id=self.root.after(120,self._poll_messages)

    def shutdown(self):
        self._closing=True
        self._views['assistant'].close()
        self.root.after_cancel(self._poll_id)
        self.animator.cancel_all();self.store.save_to_disk_sync();self.root.destroy()


def main():
    enable_windows_dpi_awareness()
    import argparse
    parser=argparse.ArgumentParser(description='FinPilot native desktop')
    parser.add_argument('--view',choices=['dashboard','transactions','analytics','budget','planner','assistant'],default='dashboard')
    args=parser.parse_args()
    root=tk.Tk();app=FinPilotApp(root)
    if args.view!='dashboard':app.switch_view(args.view)
    root.mainloop()

if __name__=='__main__':main()
