"""Native AI workspace with Windows-encrypted credentials and a read-only report."""
import tkinter as tk
from tkinter import ttk
from queue import SimpleQueue
from threading import Thread
from assistant import make_report, ask_openrouter, AssistantError
from credentials import connection_path, load_connection, save_connection, DEFAULT_MODEL
from clipboard_text import read_text, ClipboardUnavailable
from charts import CategoryDonutChart, GroupedBarChart
from layout import responsive_grid, flow_row, ScrollViewport
from rich_report import RichTranscript
from models import format_indian_currency
from report_surfaces import ReportMetric as MetricCard
from widgets import RoundedCard, PillButton


class AssistantView(ttk.Frame):
    def __init__(self, parent, store, theme, animator, toast):
        super().__init__(parent, style='App.TFrame')
        self.store,self.theme,self.animator,self.toast=store,theme,animator,toast
        self.is_built=False; self.is_dirty=True
        self.cards=[]; self.buttons=[]; self.history=[]
        self.key=''; self.model=''; self.generation=0; self.busy=False; self.closed=False
        self.connection_path=connection_path(store.storage_path)
        self.connection_error=''
        try:self.key,self.model=load_connection(self.connection_path)
        except (OSError,ValueError):self.connection_error='Saved connection could not be opened. Re-enter your key in Connection settings.'
        self.results=SimpleQueue(); self.poll_id=None; self.signature=None
        self.month=tk.StringVar(value='ALL'); self.notes=tk.BooleanVar(value=True)
        self.consent=tk.BooleanVar(value=False)

    def label(self, parent, text, kind='body', muted=False):
        t=self.theme.tokens
        w=tk.Label(parent,text=text,bg=t['surface'],fg=t['text_muted' if muted else 'text_primary'],
                   font=self.theme.fonts[kind],anchor='w',justify='left')
        w.pack(fill='x',pady=(0,8))
        w.bind('<Configure>',lambda e:w.configure(wraplength=max(80,e.width-4)))
        return w

    def card(self, title):
        c=RoundedCard(self,self.theme,self.animator,height=120)
        c.pack(fill='x',pady=(0,16)); self.cards.append(c)
        self.label(c.body,title,'subtitle')
        return c.body

    def button(self, parent, text, command, primary=False):
        b=PillButton(parent,self.theme,text,command,variant='primary' if primary else 'secondary',height=36)
        b.pack(side='left',padx=(0,8),pady=4); self.buttons.append(b)
        return b

    def build(self):
        if self.is_built:return
        self.is_built=True;t=self.theme.tokens
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        toolbar=tk.Frame(self,bg=t['background']);toolbar.grid(row=0,column=0,sticky='ew',pady=(0,8))
        self.month_box=ttk.Combobox(toolbar,textvariable=self.month,state='readonly',width=10,style='Fin.TCombobox')
        self.month_box.pack(side='left');self.month_box.bind('<<ComboboxSelected>>',lambda e:self.scope_changed())
        self.button(toolbar,'Local report',self.preview,True)
        self.button(toolbar,'Connection',self.settings)
        self.button(toolbar,'Data sharing',self.toggle_data)
        self.button(toolbar,'Clear chat',self.clear_chat)
        flow_row(toolbar)
        self.data_panel=tk.Frame(self,bg=t['surface'])
        self.label(self.data_panel,'Send shares the selected records with OpenRouter and its model provider. Nothing is sent automatically.',muted=True)
        ttk.Checkbutton(self.data_panel,text='Include recorded descriptions',variable=self.notes,command=self.scope_changed).pack(anchor='w')
        ttk.Checkbutton(self.data_panel,text='Allow sending selected records to OpenRouter',variable=self.consent).pack(anchor='w')
        self.data_panel.grid(row=1,column=0,sticky='ew',pady=(0,8))
        self.data_visible=True
        self.workspace=ttk.Frame(self,style='App.TFrame');self.workspace.grid(row=2,column=0,sticky='nsew')
        self.workspace.rowconfigure(1,weight=1)
        self.tabs=tk.Frame(self.workspace,bg=t['background'])
        self.chat_tab=self.button(self.tabs,'Conversation',lambda:self.select_panel('chat'),True)
        self.report_tab=self.button(self.tabs,'Financial report',lambda:self.select_panel('report'))
        self.panel='chat';self.layout_mode=None
        self.chat_card=RoundedCard(self.workspace,self.theme,self.animator,auto_height=False,height=300,padding=16)
        self.cards.append(self.chat_card);body=self.chat_card.body
        body.columnconfigure(0,weight=1);body.rowconfigure(1,weight=1)
        heading=tk.Label(body,text='Ask FinPilot  ·  Your money, explained',bg=t['surface'],fg=t['primary'],font=self.theme.fonts['body_bold'],anchor='w')
        heading.grid(row=0,column=0,sticky='ew',pady=(0,10))
        reading=tk.Frame(body,bg=t['surface']);reading.grid(row=1,column=0,sticky='nsew')
        self.transcript=RichTranscript(reading,self.theme,height=4,width=1,wrap='word',font=self.theme.fonts['body'],relief='flat',padx=8,pady=4,state='disabled')
        bar=ttk.Scrollbar(reading,command=self.transcript.yview,style='Fin.Vertical.TScrollbar');bar.pack(side='right',fill='y')
        self.transcript.configure(yscrollcommand=bar.set);self.transcript.pack(fill='both',expand=True)
        self.transcript.bind('<MouseWheel>',self.chat_scroll)
        self.question=tk.Text(body,height=2,width=1,wrap='word',font=self.theme.fonts['body'],relief='flat',padx=12,pady=10)
        self.question.grid(row=2,column=0,sticky='ew',pady=(10,6))
        self.question.insert('1.0','Evaluate my spending by category, merchant and date. Compare months and suggest three practical improvements.')
        self.question.bind('<Control-Return>',lambda e:self.send())
        actions=tk.Frame(body,bg=t['surface']);actions.grid(row=3,column=0,sticky='ew')
        self.send_btn=self.button(actions,'Send  ↗',self.send,True)
        self.cancel_btn=self.button(actions,'Cancel',self.cancel)
        self.cancel_btn.set_enabled(False)
        self.button(actions,'Review spending',lambda:self.set_question('Give a detailed spending review with a category table and practical suggestions.'))
        flow_row(actions)
        self.progress=ttk.Progressbar(body,mode='indeterminate',style='AI.Horizontal.TProgressbar')
        self.progress.grid(row=4,column=0,sticky='ew',pady=3)
        self.status=tk.Label(body,text=self.connection_error or ('Ready · '+self.model if self.key else 'Add a key in Connection.'),bg=t['surface'],fg=t['text_muted'],font=self.theme.fonts['caption'],anchor='w',justify='left')
        self.status.grid(row=5,column=0,sticky='ew')
        self.status.bind('<Configure>',lambda e:self.status.configure(wraplength=max(100,e.width)))
        self.report_scroll=ScrollViewport(self.workspace,self.theme)
        self.report_scroll.body.configure(padding=(0,0,8,0));report=self.report_scroll.body
        self.report_heading=tk.Label(report,text='YOUR FINANCIAL SNAPSHOT',bg=t['background'],fg=t['text_muted'],font=self.theme.fonts['caption_bold'],anchor='w')
        self.report_heading.pack(fill='x',pady=(2,10))
        self.metrics=[]
        for name,color in [('RECORDED INCOME','success'),('RECORDED EXPENSES','danger'),('NET CASH FLOW','primary')]:
            c=MetricCard(report,self.theme,self.animator,'ai_'+color,name,color);c.configure(height=82);c.pack(fill='x',pady=(0,8));self.metrics.append(c)
        c=RoundedCard(report,self.theme,self.animator,height=160,padding=16)
        c.pack(fill='x',pady=(0,12));self.cards.append(c)
        self.label(c.body,'At a glance','subtitle')
        self.insight=self.label(c.body,'',muted=True)
        insight_actions=tk.Frame(c.body,bg=t['surface']);insight_actions.pack(fill='x')
        self.button(insight_actions,'Explore this category',self.explore_category)
        self.button(insight_actions,'Compare months',lambda:self.prepare_question('Compare the recorded months. Show income, expenses and net cash flow in a table, and explain changes. Flag partial months.'))
        flow_row(insight_actions)
        for title,cls,cid in [('Where it goes',CategoryDonutChart,'ai_categories'),('Income & expenses',GroupedBarChart,'ai_months')]:
            c=RoundedCard(report,self.theme,self.animator,height=280,auto_height=False,padding=14)
            c.pack(fill='x',pady=(0,12));self.cards.append(c);self.label(c.body,title,'subtitle')
            chart=cls(c.body,self.theme,self.animator,cid);chart.pack(fill='both',expand=True)
            if cls is CategoryDonutChart:self.donut=chart
            else:self.bars=chart
        c=RoundedCard(report,self.theme,self.animator,height=120);c.pack(fill='x');self.cards.append(c)
        self.label(c.body,'Source & scope','subtitle');self.provenance=self.label(c.body,'',muted=True)
        self.label(c.body,'Calculated from recorded transactions. Net cash flow is not bank balance. Check AI explanations against the records.',muted=True)
        self.bind('<Configure>',lambda e:self.reflow(),add='+')
        self.append('FinPilot','Your money, explained clearly. Ask a question or generate a local report. Tables will appear as aligned cells. No request has been sent.')
        self.apply_theme();self.refresh(False);self.poll();self.after_idle(self.reflow)

    def toggle_data(self):
        if self.winfo_toplevel().winfo_height()<650:
            top=tk.Toplevel(self);top.title('Data sharing');top.geometry('460x230');top.transient(self.winfo_toplevel())
            body=tk.Frame(top,bg=self.theme.tokens['surface'],padx=20,pady=20);body.pack(fill='both',expand=True)
            self.label(body,'Send shares the selected records with OpenRouter and its model provider. Nothing is sent automatically.',muted=True)
            ttk.Checkbutton(body,text='Include descriptions',variable=self.notes,command=self.scope_changed).pack(anchor='w',pady=8)
            ttk.Checkbutton(body,text='Allow sending selected records',variable=self.consent).pack(anchor='w',pady=8)
            ttk.Button(body,text='Done',command=top.destroy).pack(anchor='w',pady=8)
            return
        self.data_visible=not self.data_visible
        if self.data_visible:self.data_panel.grid()
        else:self.data_panel.grid_remove()

    def select_panel(self,panel):
        self.panel=panel;self.layout_mode=None
        for button,active in ((self.chat_tab,panel=='chat'),(self.report_tab,panel=='report')):
            button.variant='primary' if active else 'secondary';button.apply_theme()
        self.reflow()

    def reflow(self):
        if self.winfo_toplevel().winfo_height()<650 and self.data_visible:
            self.data_panel.grid_remove();self.data_visible=False
        wide=self.winfo_width()>=1000
        signature=(wide,self.panel)
        if signature==self.layout_mode:return
        self.layout_mode=signature
        self.workspace.columnconfigure(0,weight=3)
        self.workspace.columnconfigure(1,weight=2 if wide else 0)
        self.chat_card.grid_forget();self.report_scroll.grid_forget();self.tabs.grid_forget()
        if wide:
            self.chat_card.grid(row=1,column=0,sticky='nsew',padx=(0,14))
            self.report_scroll.grid(row=1,column=1,sticky='nsew')
        else:
            self.tabs.grid(row=0,column=0,sticky='ew',pady=(0,8))
            target=self.chat_card if self.panel=='chat' else self.report_scroll
            target.grid(row=1,column=0,sticky='nsew')

    def chat_scroll(self,event):
        self.transcript.yview_scroll(-int(event.delta/120),'units');return 'break'

    def set_question(self,text):
        self.question.delete('1.0','end');self.question.insert('1.0',text);self.question.focus_set()

    def prepare_question(self,text):
        self.select_panel('chat');self.set_question(text)

    def explore_category(self):
        r=self.snapshot()
        if not r['categories']:
            self.prepare_question('Explain what information I need to record to review my spending.');return
        category=r['categories'][0]['category']
        self.prepare_question(f'Review the {category} category in this snapshot. Show the largest recorded expenses with dates and descriptions, then suggest practical next steps.')

    def append(self,role,text):
        self.transcript.add_message(role,text)

    def snapshot(self):
        return make_report(self.store.get_transactions(),self.month.get(),self.notes.get())

    def render(self,report,animate=True):
        fmt=lambda n:format_indian_currency(n,self.store.currency_symbol)
        self.report_heading.configure(text=f"{'ALL TIME' if report['scope']=='ALL' else report['scope']}  /  {report['count']} RECORDS")
        if report['categories']:
            top=report['categories'][0];share=top['amount_paise']/max(1,report['expense_paise'])*100
            self.insight.configure(text=f"{top['category']} accounts for {share:.1f}% of recorded expenses ({fmt(top['amount_paise'])}).\n\nChoose a question below to explore the records. Nothing is sent until you press Send.")
        else:self.insight.configure(text='No expenses in this scope. Record a transaction or select another month to build your report.')
        for c,k in zip(self.metrics,('income_paise','expense_paise','net_paise')):
            c.set_value(report[k],fmt,subtitle=report['scope'],animate=animate)
        self.donut.update_chart(report['categories'],self.store.currency_symbol,animate)
        self.bars.update_chart(report['months'][-12:],self.store.currency_symbol,animate)
        self.provenance.configure(text=f"Scope: {report['scope']} · {report['count']} records · Snapshot: {report['as_of']}\nAll selected records contribute to totals. Cash-flow chart shows the latest 12 recorded months. Descriptions: {'included' if report['notes_included'] else 'excluded'}.")

    def refresh(self,animate=True):
        if not self.is_built:return
        months=['ALL']+list(self.store.get_available_months())
        self.month_box.configure(values=months)
        if self.month.get() not in months:self.month.set('ALL')
        report=self.snapshot();signature=repr(report)
        if self.signature is not None and self.signature!=signature:
            self.cancel();self.history.clear()
            self.append('Scope updated','Data or filters changed. Earlier messages refer to their original snapshots; follow-up context has been reset.')
        self.signature=signature;self.render(report,animate);self.is_dirty=False

    def scope_changed(self):
        self.consent.set(False);self.refresh()

    def preview(self):
        self.refresh()
        r=self.snapshot();fmt=lambda n:format_indian_currency(n,self.store.currency_symbol)
        text=f"## Your report at a glance\n{r['count']} recorded transactions · {'All time' if r['scope']=='ALL' else r['scope']}\n\n**Income:** {fmt(r['income_paise'])}\n**Expenses:** {fmt(r['expense_paise'])}\n**Net cash flow:** {fmt(r['net_paise'])}\n\nNet cash flow reflects these records, not your bank balance."
        if r['categories']:
            top=r['categories'][0];text+=f" Largest expense category: {top['category']} ({fmt(top['amount_paise'])})."
            text+='\n\n## Where your money goes\n| Category | Recorded spending | Share |\n| --- | ---: | ---: |\n'
            for item in r['categories']:
                category=item['category'].replace('|',r'\|')
                share=item['amount_paise']/max(1,r['expense_paise'])*100
                text+=f"| {category} | {fmt(item['amount_paise'])} | {share:.1f}% |\n"
            text+='\n## Next steps\n- Explore the largest category to review the individual purchases.\n- Compare recorded months, checking whether each month is complete.\n- Add missing descriptions so merchant and purpose reviews are more useful.'
        self.append('Local report · no AI',text)
        self.select_panel('chat')

    def settings(self):
        existing=getattr(self,'connection_dialog',None)
        if existing is not None and existing.winfo_exists():
            existing.lift();return
        t=self.theme.tokens
        top=tk.Toplevel(self);self.connection_dialog=top
        top.title('OpenRouter connection');top.geometry('560x490');top.minsize(460,490)
        top.transient(self.winfo_toplevel());top.configure(bg=t['surface'])
        frame=tk.Frame(top,bg=t['surface'],padx=22,pady=22);frame.pack(fill='both',expand=True)
        self.label(frame,'Connect to OpenRouter','subtitle')
        self.label(frame,'API key · saved with Windows encryption')
        key=tk.StringVar(value=self.key);model=tk.StringVar(value=self.model)
        notice=tk.StringVar()
        def field(variable,masked=False):
            widget=tk.Entry(frame,textvariable=variable,show='*' if masked else '',
                font=self.theme.fonts['body'],bg=t['surface_raised'],fg=t['text_primary'],
                insertbackground=t['text_primary'],selectbackground=t['primary'],
                selectforeground=t['background'],relief='flat',highlightthickness=1,
                highlightbackground=t['border'],highlightcolor=t['primary'])
            widget.pack(fill='x',ipady=9,pady=(0,8))
            def paste(event=None):
                try:
                    value=read_text(widget).strip()
                    if not value:
                        notice.set('Clipboard text is empty. Copy the key itself first.');return 'break'
                    if masked:
                        if not value.startswith('sk-or-') or any(c.isspace() for c in value):
                            notice.set('Copy only the OpenRouter key (starting sk-or-), without surrounding text.')
                            return 'break'
                        # Replace the saved masked value instead of appending to it.
                        variable.set(value)
                    else:
                        if widget.selection_present():widget.delete('sel.first','sel.last')
                        widget.insert('insert',value)
                    widget.icursor('end');widget.xview_moveto(1)
                    notice.set('Key pasted and masked. Click Save connection.' if masked else 'Model ID pasted.')
                except ClipboardUnavailable as exc:
                    notice.set(str(exc))
                widget.focus_set()
                return 'break'
            def select_all(event=None):
                widget.selection_range(0,'end');widget.icursor('end');return 'break'
            for sequence in ('<Control-v>','<Control-V>','<Shift-Insert>','<<Paste>>'):
                widget.bind(sequence,paste)
            widget.bind('<Control-a>',select_all)
            menu=tk.Menu(widget,tearoff=False)
            menu.add_command(label='Paste',command=paste)
            menu.add_command(label='Select all',command=select_all)
            def popup(event):
                widget.focus_set()
                try:menu.tk_popup(event.x_root,event.y_root)
                finally:menu.grab_release()
            widget.bind('<Button-3>',popup)
            return widget,paste
        entry,paste_key=field(key,True)
        controls=tk.Frame(frame,bg=t['surface']);controls.pack(fill='x',pady=(0,12))
        paste_button=PillButton(controls,self.theme,'Paste key',paste_key,variant='secondary',height=32)
        paste_button.pack(side='left')
        self.label(frame,'Model ID from OpenRouter (provider/model)')
        model_entry,_=field(model)
        self.label(frame,'Saved for your Windows account. Free-only models; no paid fallback.',muted=True)
        self.label(frame,'',muted=True).configure(textvariable=notice)
        def dismiss():
            key.set('');top.destroy()
        def save():
            new_key,new_model=key.get().strip(),model.get().strip()
            try:save_connection(self.connection_path,new_key,new_model)
            except (OSError,ValueError) as exc:
                notice.set(str(exc));return
            self.cancel();self.key=new_key;self.model=new_model
            self.status.configure(text='OpenRouter configured · '+self.model if self.key and self.model else 'Local mode · Connection incomplete.')
            dismiss()
        button=PillButton(frame,self.theme,'Save connection',save,height=36)
        button.pack(anchor='w',pady=(4,0))
        def forget():
            try:self.connection_path.unlink(missing_ok=True)
            except OSError:
                notice.set('Could not remove saved connection.');return
            self.cancel();self.key='';self.model=DEFAULT_MODEL;key.set('');model.set(DEFAULT_MODEL)
            self.status.configure(text='Saved key forgotten.');notice.set('Saved key removed from this device.')
        forget_button=PillButton(frame,self.theme,'Forget saved key',forget,variant='secondary',height=32)
        forget_button.pack(anchor='w',pady=6)
        top.protocol('WM_DELETE_WINDOW',dismiss)
        top.bind('<Escape>',lambda e:dismiss())
        top.after_idle(entry.focus_set)
        # Expose widgets for native regression checks, never log their contents.
        top.key_entry=entry;top.model_entry=model_entry;top.paste_key=paste_key
        return top

    def send(self):
        if self.busy:return
        if not self.key or not self.model:
            self.status.configure(text='Add your OpenRouter key and model ID in Connection settings.');self.settings();return
        if not self.consent.get():
            self.status.configure(text='Enable data sharing above before sending.');self.data_visible=False;self.toggle_data();return
        question=self.question.get('1.0','end').strip()
        if not question or len(question)>3000:
            self.status.configure(text='Enter a question of 1–3,000 characters.');return
        self.refresh(False);report=self.snapshot()
        self.generation+=1;generation=self.generation;self.busy=True
        self.send_btn.set_enabled(False);self.send_btn.set_text('Analysing…');self.cancel_btn.set_enabled(True)
        self.progress.start(12);self.status.configure(text='Analysing your selected records… You can keep using the app.')
        self.append('You · '+self.month.get(),question)
        key,model,history=self.key,self.model,list(self.history)
        def worker():
            try:result=(True,ask_openrouter(key,model,question,report,history))
            except AssistantError as exc:result=(False,str(exc))
            except Exception:result=(False,'The request failed unexpectedly. Please retry.')
            self.results.put((generation,question,result))
        Thread(target=worker,daemon=True).start()

    def poll(self):
        if self.closed:return
        while not self.results.empty():
            generation,question,(ok,text)=self.results.get()
            if generation!=self.generation:continue
            if repr(self.snapshot())!=self.signature:
                self.refresh(False)
                self.status.configure(text='Records changed during the request. Ask again for an up-to-date explanation.')
                continue
            self.busy=False;self.progress.stop()
            self.send_btn.set_enabled(True);self.send_btn.set_text('Send  ↗');self.cancel_btn.set_enabled(False)
            self.status.configure(text='Response received · Charts remain locally calculated.' if ok else text)
            self.append('AI explanation' if ok else 'Connection notice',text)
            if ok:self.history=(self.history+[('user',question),('assistant',text)])[-6:]
        self.poll_id=self.after(120,self.poll)

    def cancel(self):
        was_busy=self.busy;self.generation+=1;self.busy=False
        if self.is_built:
            self.progress.stop()
            self.send_btn.set_enabled(True);self.send_btn.set_text('Send  ↗');self.cancel_btn.set_enabled(False)
            if was_busy:self.status.configure(text='Response cancelled locally. A request already sent may still incur API charges.')

    def clear_chat(self):
        self.cancel();self.history.clear()
        self.transcript.clear()

    def close(self):
        self.cancel();self.closed=True;self.key='';self.history.clear()
        if self.poll_id:self.after_cancel(self.poll_id)

    def apply_theme(self):
        if not self.is_built:return
        t=self.theme.tokens
        ttk.Style(self).configure('AI.Horizontal.TProgressbar',background=t['primary'],troughcolor=t['surface'],bordercolor=t['surface'],lightcolor=t['primary'],darkcolor=t['primary'],thickness=4)
        for w in (self.question,):
            w.configure(bg=t['background'],fg=t['text_primary'],insertbackground=t['primary'],selectbackground=t['primary'],selectforeground='#101828',highlightthickness=1,highlightbackground=t['border_subtle'],highlightcolor=t['primary'])
        self.transcript.apply_theme()
        self.report_scroll.apply_theme()
        for c in self.cards:c.apply_theme()
        for b in self.buttons:b.apply_theme()
        for c in self.metrics:c.apply_theme()
        self.render(self.snapshot(),False)
