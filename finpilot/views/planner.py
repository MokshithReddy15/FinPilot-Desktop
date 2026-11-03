"""Interactive planning workspace: transparent forecasts, schedules, goals and scenarios."""
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import uuid
from layout import responsive_grid, flow_row
from planning import PlanningBook, forecast, suggestions, goal_status, money, apply_scenario
from models import format_indian_currency
from surfaces import MetricCard, ScenarioSlider
from widgets import RoundedCard, PillButton


class PlannerView(ttk.Frame):
    def __init__(self,parent,store,theme,animator,toast):
        super().__init__(parent,style='App.TFrame')
        self.store,self.theme,self.animator,self.toast=store,theme,animator,toast
        self.book=PlanningBook(Path(store.storage_path).with_name(Path(store.storage_path).stem+'_planning.json'))
        self.is_built=False;self.is_dirty=True;self.cards=[];self.buttons=[]
        self._reduction=tk.DoubleVar(value=0);self._purchase=tk.StringVar(value='0')
        self._error=tk.StringVar();self._scenario_error=tk.StringVar();self._preview=None
        self._suggestions=[];self._closed=False

    def currency(self,paise):return format_indian_currency(paise,self.store.currency_symbol)

    def label(self,parent,text='',kind='body',muted=False):
        t=self.theme.tokens
        label=tk.Label(parent,text=text,bg=t['surface'],fg=t['text_muted' if muted else 'text_primary'],font=self.theme.fonts[kind],anchor='w',justify='left')
        label.pack(fill='x',pady=(0,8))
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(80,e.width-4)))
        return label

    def button(self,parent,text,command,primary=False):
        b=PillButton(parent,self.theme,text,command,variant='primary' if primary else 'secondary',height=34)
        b.pack(side='left',padx=(0,8),pady=4);self.buttons.append(b);return b

    def card(self,title):
        c=RoundedCard(self,self.theme,self.animator,height=100)
        c.pack(fill='x',pady=(0,16));self.cards.append(c)
        self.label(c.body,title,'subtitle');return c.body

    def table(self,parent,columns,height=5):
        frame=tk.Frame(parent,bg=self.theme.tokens['surface']);frame.pack(fill='x',pady=(4,8))
        frame.columnconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=[c[0] for c in columns],show='headings',height=height,style='Fin.Treeview',selectmode='browse')
        for key,title,width in columns:
            tree.heading(key,text=title);tree.column(key,width=width,minwidth=min(width,70),stretch=True)
        tree.grid(row=0,column=0,sticky='nsew')
        vs=ttk.Scrollbar(frame,orient='vertical',command=tree.yview,style='Fin.Vertical.TScrollbar');vs.grid(row=0,column=1,sticky='ns')
        hs=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);hs.grid(row=1,column=0,sticky='ew')
        tree.configure(xscrollcommand=hs.set,yscrollcommand=vs.set)
        return tree

    def build(self):
        if self.is_built:return
        self.is_built=True;t=self.theme.tokens
        summary=ttk.Frame(self,style='App.TFrame');summary.pack(fill='x')
        self.metrics=[]
        for cid,title,col in [('closing','ESTIMATED MONTH-END','primary'),('remaining','EXPECTED EXPENSES','danger'),('income','EXPECTED INCOME','success')]:
            c=MetricCard(summary,self.theme,self.animator,cid,title,col)
            c.configure(height=170);self.metrics.append(c)
        responsive_grid(summary,self.metrics,min_width=245,max_columns=3)
        body=self.card('Your forecast, explained')
        self.summary_text=self.label(body,muted=True)
        self.range_text=self.label(body,kind='body_bold')
        self.formula_text=self.label(body,muted=True)
        controls=tk.Frame(body,bg=t['surface']);controls.pack(fill='x')
        self.button(controls,'Set actual balance',self.set_balance,True)
        self.button(controls,'Use recorded net balance',self.reset_balance)
        self.button(controls,'Refresh forecast',lambda:self.refresh(True))
        flow_row(controls)
        self.insight=self.label(body,kind='body_bold')
        self.error_label=self.label(body);self.error_label.configure(textvariable=self._error,fg=t['danger'])

        tabs=tk.Frame(self,bg=t['background']);tabs.pack(fill='x',pady=(0,12))
        self.tab_buttons={}
        for key,title in [('scenario','What-if studio'),('payments','Payments & patterns'),('goals','Savings goals'),('sources','Forecast sources')]:
            self.tab_buttons[key]=self.button(tabs,title,lambda k=key:self.show_page(k))
        flow_row(tabs)
        self.pages={key:ttk.Frame(self,style='App.TFrame') for key in self.tab_buttons}
        self._page='scenario'
        # Notebook-like panels use the outer scroll viewport, so no panel has a fixed height.
        def page_body(key,title):
            c=RoundedCard(self.pages[key],self.theme,self.animator,height=180)
            c.pack(fill='x');self.cards.append(c);self.label(c.body,title,'subtitle');return c.body
        body=page_body('scenario','Explore a decision before you make it')
        self.label(body,'Reduce only the estimated variable spending still ahead this month. Confirmed bills stay unchanged.',muted=True)
        self.slider_label=self.label(body,'Reduce flexible spending: 0%','body_bold')
        slider=ScenarioSlider(body,self.theme,self.animator,self._reduction,self.scenario_changed)
        self.scenario_slider=slider
        slider.pack(fill='x',pady=(4,18));slider.bind('<MouseWheel>',lambda e:'break')
        row=tk.Frame(body,bg=t['surface']);row.pack(fill='x')
        tk.Label(row,text='Additional purchase (Rs.)',bg=t['surface'],fg=t['text_muted'],font=self.theme.fonts['body']).pack(side='left')
        ttk.Entry(row,textvariable=self._purchase,style='Fin.TEntry',width=16).pack(side='left',padx=12)
        self.button(row,'Reset scenario',self.reset_scenario);flow_row(row)
        self.scenario_result=self.label(body,kind='subtitle')
        self.scenario_detail=self.label(body,muted=True)
        self.scenario_error_label=self.label(body);self.scenario_error_label.configure(textvariable=self._scenario_error,fg=t['danger'])
        self._purchase.trace_add('write',lambda *_:self.scenario_changed())
        self.label(body,'This preview never adds a transaction or changes a budget. Savings goals below compare against this scenario while it is active.',muted=True)

        body=page_body('payments','Expected income, bills, and one-off plans')
        self.label(body,'Monthly dates of 29–31 fall on the last day in shorter months. Recorded payments match by type, category, description, amount within 10% (minimum Rs. 1), and date within 7 days. Review Forecast sources to check matches.',muted=True)
        self.payments_tree=self.table(body,[('name','PAYMENT',210),('type','TYPE',95),('amount','AMOUNT',120),('date','START / DUE',110),('repeat','REPEAT',90)])
        row=tk.Frame(body,bg=t['surface']);row.pack(fill='x')
        self.button(row,'+ Add payment',lambda:self.payment_editor(),True)
        self.button(row,'Edit selected',self.edit_payment)
        self.button(row,'Remove selected',lambda:self.remove_selected('payments',self.payments_tree))
        flow_row(row)
        self.label(body,'Suggested recurring payments','subtitle')
        self.pattern_hint=self.label(body,muted=True)
        self.pattern_tree=self.table(body,[('name','PATTERN',240),('amount','AMOUNT',120),('date','DAY',80),('type','TYPE',100)],4)
        row=tk.Frame(body,bg=t['surface']);row.pack(fill='x')
        self.button(row,'Review & confirm',self.confirm_suggestion,True)
        self.button(row,'Dismiss suggestion',self.dismiss_suggestion);flow_row(row)
        self.label(body,'Only a single similar transaction in each of three consecutive months is suggested. The category, description, amount and payment day must be consistent. Suggestions are never included until confirmed.',muted=True)

        body=page_body('goals','Give your savings a destination')
        self.label(body,'Set a target, deadline, and amount already allocated. Allocations track your plan; they do not move money or create expenses.',muted=True)
        self.goals_tree=self.table(body,[('name','GOAL',180),('progress','PROGRESS',100),('saved','ALLOCATED',110),('target','TARGET',110),('date','DEADLINE',110),('monthly','NEEDED / MONTH',135),('status','STATUS',130)],6)
        row=tk.Frame(body,bg=t['surface']);row.pack(fill='x')
        self.button(row,'+ New goal',lambda:self.goal_editor(),True)
        self.button(row,'Edit / allocate savings',self.edit_goal)
        self.button(row,'Remove selected',lambda:self.remove_selected('goals',self.goals_tree));flow_row(row)
        self.goal_summary=self.label(body,kind='body_bold')
        self.label(body,'Monthly targets divide the remaining amount across calendar months through the deadline, including this month. They assume equal contributions and no investment returns. Forecast capacity is an estimate for this month only.',muted=True)

        body=page_body('sources','Trace every amount')
        self.sources_tree=self.table(body,[('name','ITEM',185),('amount','REMAINING',120),('source','SOURCE / ASSUMPTION',490)],10)
        row=tk.Frame(body,bg=t['surface']);row.pack(fill='x')
        self.button(row,'Override category estimate',self.override_estimate,True)
        self.button(row,'Clear this month’s overrides',self.clear_overrides);flow_row(row)
        self.label(body,'History uses up to three complete calendar months, excluding a partial first month. Missing months in that period count as zero, so keep your ledger complete. Confirmed monthly payment matches are removed from everyday spending. Without enough history, seven or more days of current spending enables a daily-pace estimate; otherwise enter planned payments manually.',muted=True)
        self.label(body,'The displayed range is a spending scenario range, not a statistical confidence interval. It does not cover unknown bills or unconfirmed income. At month end, estimated future everyday spending is zero.',muted=True)
        self.show_page('scenario')

    def show_page(self,key):
        self._page=key
        for name,page in self.pages.items():
            page.pack_forget()
            self.tab_buttons[name].variant='primary' if name==key else 'secondary'
            self.tab_buttons[name].apply_theme()
        self.pages[key].pack(fill='x')

    def selected(self,tree,collection):
        selected=tree.selection()
        if not selected:self._error.set('Select a row first.');return None
        return next((r for r in self.book.data[collection] if r['id']==selected[0]),None)

    def remove_selected(self,collection,tree):
        item=self.selected(tree,collection)
        if item and messagebox.askyesno('Remove plan',f"Remove {item['name']} from your plan? Transactions are retained.",parent=self):
            self.mutate(lambda:self.book.remove(collection,item['id']))

    def mutate(self,action):
        try:action()
        except (ValueError,OSError) as exc:self._error.set(str(exc));return False
        self._error.set('');self.refresh(True);return True

    def dialog(self,title,fields,save):
        top=tk.Toplevel(self);top.title(title);top.transient(self.winfo_toplevel());top.resizable(False,False)
        t=self.theme.tokens;top.configure(bg=t['surface'])
        form=tk.Frame(top,bg=t['surface'],padx=24,pady=20);form.pack(fill='both',expand=True)
        values={}
        for key,label,value,choices in fields:
            tk.Label(form,text=label,bg=t['surface'],fg=t['text_muted'],font=self.theme.fonts['body']).pack(anchor='w',pady=(8,3))
            var=tk.StringVar(value=str(value));values[key]=var
            if choices:widget=ttk.Combobox(form,textvariable=var,values=choices,state='readonly',width=42,style='Fin.TCombobox')
            else:widget=ttk.Entry(form,textvariable=var,width=44,style='Fin.TEntry')
            widget.pack(fill='x')
        error=tk.Label(form,text='',bg=t['surface'],fg=t['danger'],wraplength=380,justify='left');error.pack(fill='x',pady=10)
        def submit():
            try:save({k:v.get().strip() for k,v in values.items()})
            except (ValueError,OSError) as exc:error.configure(text=str(exc));return
            top.destroy();self._error.set('');self.refresh(True)
        PillButton(form,self.theme,'Save plan',submit,height=36).pack(fill='x')
        PillButton(form,self.theme,'Cancel',top.destroy,variant='secondary',height=32).pack(fill='x',pady=(8,0))
        top.bind('<Escape>',lambda e:top.destroy());top.bind('<Return>',lambda e:submit())
        top.grab_set();top.update_idletasks()
        root=self.winfo_toplevel();x=root.winfo_rootx()+max(0,(root.winfo_width()-top.winfo_reqwidth())//2)
        y=root.winfo_rooty()+max(0,(root.winfo_height()-top.winfo_reqheight())//2)
        top.geometry(f'+{x}+{y}')
        return top

    def payment_editor(self,item=None,suggestion=False):
        item=item or {};today=date.today()
        fields=[('name','Name',item.get('name',''),None),('type','Type',item.get('type','EXPENSE'),['EXPENSE','INCOME']),
                ('amount','Amount (Rs.)',str(item.get('amount',0)/100),None),('date','First / one-off due date (YYYY-MM-DD)',item.get('date',today.isoformat()),None),
                ('monthly','Repeat', 'Monthly' if item.get('monthly',True) else 'Once',['Monthly','Once']),
                ('category','Matching transaction category',item.get('category',''),None),('note','Matching description (exact; blank matches blank)',item.get('note',''),None)]
        def save(v):
            if not v['name'] or not v['category']:raise ValueError('Enter a name and matching category.')
            due=date.fromisoformat(v['date'])
            data={'id':str(uuid.uuid4()) if suggestion else item.get('id',str(uuid.uuid4())),
                  'name':v['name'],'type':v['type'],'amount':money(v['amount'],False),'date':due.isoformat(),
                  'monthly':v['monthly']=='Monthly','category':v['category'],'note':v['note']}
            self.book.put('payments',data)
        return self.dialog('Confirm recurring payment' if suggestion else 'Expected payment',fields,save)

    def edit_payment(self):
        item=self.selected(self.payments_tree,'payments')
        if item:self.payment_editor(item)

    def confirm_suggestion(self):
        selection=self.pattern_tree.selection()
        if selection:self.payment_editor(self._suggestions[int(selection[0])],True)
        else:self._error.set('Select a suggested pattern to review.')

    def dismiss_suggestion(self):
        selected=self.pattern_tree.selection()
        if selected:
            token=self._suggestions[int(selected[0])]['id']
            self.mutate(lambda:self.book.commit(lambda d:d['dismissed'].append(token)))

    def goal_editor(self,item=None):
        item=item or {}
        fields=[('name','Goal name',item.get('name',''),None),('target','Target (Rs.)',str(item.get('target',0)/100),None),
                ('saved','Already allocated (Rs.)',str(item.get('saved',0)/100),None),('date','Target date (YYYY-MM-DD)',item.get('date',date.today().isoformat()),None)]
        def save(v):
            if not v['name']:raise ValueError('Enter a goal name.')
            deadline=date.fromisoformat(v['date']);target=money(v['target'],False);saved=money(v['saved'])
            if deadline<date.today() and not item:raise ValueError('Choose today or a future date for a new goal.')
            self.book.put('goals',dict(id=item.get('id',str(uuid.uuid4())),name=v['name'],target=target,saved=saved,date=deadline.isoformat()))
        return self.dialog('Savings goal',fields,save)

    def edit_goal(self):
        item=self.selected(self.goals_tree,'goals')
        if item:self.goal_editor(item)

    def set_balance(self):
        def save(v):
            amount=money(v['amount']);amount=-amount if v['sign']=='Negative / overdrawn' else amount
            record={'amount':amount,'date':date.today().isoformat(),'ids':[t.id for t in self.store.get_transactions()]}
            self.book.commit(lambda d:d.__setitem__('balance',record))
        return self.dialog('Set actual balance today',[('amount','Current balance (Rs.)','0',None),('sign','Balance type','Positive',['Positive','Negative / overdrawn'])],save)

    def override_estimate(self):
        categories=[r['name'] for r in self._base['variable']]
        if not categories:self._error.set('Add an expense first, or use Payments to enter a known upcoming cost.');return
        def save(v):
            amount=money(v['amount']);key=date.today().strftime('%Y-%m')+'|'+v['category']
            self.book.commit(lambda d:d.setdefault('overrides',{}).__setitem__(key,amount))
        return self.dialog('Remaining-spend estimate',[
            ('category','Category',categories[0],categories),
            ('amount','Amount still expected THIS month (Rs.; 0 excludes it)','0',None)],save)

    def clear_overrides(self):
        prefix=date.today().strftime('%Y-%m')+'|'
        self.mutate(lambda:self.book.commit(lambda d:d.__setitem__('overrides',{k:v for k,v in d.get('overrides',{}).items() if not k.startswith(prefix)})))

    def reset_balance(self):self.mutate(lambda:self.book.commit(lambda d:d.__setitem__('balance',None)))

    def scenario_changed(self,*_):
        if self.is_built:self.animator.debounce('planning_scenario',35,lambda:self.refresh(False,scenario_only=True))

    def reset_scenario(self):
        self._reduction.set(0);self._purchase.set('0');self.refresh(False)

    @staticmethod
    def fill(tree,rows):
        selected=tree.selection();position=tree.yview()
        tree.delete(*tree.get_children())
        for identifier,values in rows:tree.insert('', 'end',iid=identifier,values=values)
        if selected and tree.exists(selected[0]):tree.selection_set(selected[0])
        if position:tree.yview_moveto(position[0])

    def refresh(self,animate=True,scenario_only=False):
        if not self.is_built:self.build()
        self.is_dirty=False;today=date.today();txs=self.store.get_transactions()
        base=self._base if scenario_only and hasattr(self,'_base') and self._base.get('asof')==today.isoformat() else forecast(txs,self.book,today)
        self._base=base
        try:
            purchase=money(self._purchase.get());self._scenario_error.set('')
        except ValueError as exc:
            self._scenario_error.set(str(exc)+' Preview paused until corrected.');purchase=None
        reduction=round(self._reduction.get())
        self.slider_label.configure(text=f'Reduce flexible spending: {reduction}%')
        result=apply_scenario(base,reduction,purchase) if purchase is not None else base
        self._preview=result
        for card,value,subtitle in zip(self.metrics,[base['closing'],base['bills']+base['variable_total'],base['income']],
                    [f"As of {today.isoformat()}",'Still ahead this month','Confirmed and not yet recorded']):
            card.set_value(value,lambda v:self.currency(round(v)),subtitle=subtitle,animate=animate)
        self.summary_text.configure(text=base['balance_source'])
        self.range_text.configure(text=f"Estimated range: {self.currency(base['lower'])} to {self.currency(base['upper'])}  ·  {base['remaining_days']} days left")
        self.formula_text.configure(text=f"{self.currency(base['balance'])} balance + {self.currency(base['income'])} income − {self.currency(base['bills'])} scheduled expenses − {self.currency(base['variable_total'])} everyday spending = {self.currency(base['closing'])}")
        if self.book.error:self._error.set(self.book.error)
        unconfirmed=self._suggestions if scenario_only else suggestions(txs,self.book,today)
        if not scenario_only:
            self._suggestions=unconfirmed
            self.pattern_hint.configure(text=f'{len(unconfirmed)} patterns awaiting review. No automatic payments are created.' if unconfirmed else 'No new matching patterns. You can add a known payment manually.')
            self.fill(self.payments_tree,[(r['id'],(r['name'],r['type'],self.currency(r['amount']),r['date'],'Monthly' if r['monthly'] else 'Once')) for r in self.book.data['payments']])
            self.fill(self.pattern_tree,[(str(i),(r['name'],self.currency(r['amount']),r['date'][-2:],r['type'])) for i,r in enumerate(unconfirmed)])
        self.scenario_result.configure(text=f"Scenario month-end: {self.currency(result['closing'])}  ·  Change {self.currency(result['closing']-base['closing'])}")
        self.scenario_detail.configure(text=f"Flexible spending saved: {self.currency(result['saved'])}. Additional purchase: {self.currency(result['purchase'])}. Scenario range: {self.currency(result['lower'])} to {self.currency(result['upper'])}.")
        goal_rows=[];required=allocated=0
        for g in self.book.data['goals']:
            status=goal_status(g,today);required+=status['monthly'];allocated+=g['saved']
            state='Complete' if status['complete'] else 'Overdue' if status['overdue'] else 'In progress'
            goal_rows.append((g['id'],(g['name'],f"{status['progress']:.0f}%",self.currency(g['saved']),self.currency(g['target']),g['date'],self.currency(status['monthly']),state)))
        self.fill(self.goals_tree,goal_rows)
        shortfall=max(0,required-result['capacity'])
        summary=f"Goals need {self.currency(required)}/month combined. This month's estimated surplus: {self.currency(result['capacity'])}. "
        summary+=f"Monthly funding gap: {self.currency(shortfall)}." if shortfall else 'The current estimate covers the combined monthly target.'
        if allocated>max(0,base['balance']):summary+=' Allocations exceed the recorded balance; check that the same money is not assigned twice.'
        self.goal_summary.configure(text=summary if goal_rows else 'Create your first goal to see its required monthly contribution and compare scenarios.')
        if base['lower']<0:insight='Your lower forecast falls below zero. Review upcoming bills and flexible spending before planning a purchase.'
        elif unconfirmed:insight=f'Review {len(unconfirmed)} recurring patterns to improve the forecast. Unconfirmed future income is not assumed.'
        elif shortfall:insight=f'Your goals need {self.currency(shortfall)} more per month than this scenario provides. Adjust the target, deadline, or spending plan.'
        elif base['history']==0:insight='Limited history: confirm known bills and expected income. The estimate will improve as your ledger fills in.'
        else:insight='Explore the what-if studio to see how spending choices change your estimated balance and goal funding.'
        self.insight.configure(text=insight)
        if scenario_only:return
        rows=[]
        for r in base['due']:rows.append((str(len(rows)),(r['name'],('+' if r['type']=='INCOME' else '−')+self.currency(r['amount']),r['source']+' · '+r['date'])))
        for r,tx in base['paid']:rows.append((str(len(rows)),(r['name'],'Already recorded',f'Matched {tx.date}; not counted again')))
        for r in base['variable']:rows.append((str(len(rows)),(r['name'],self.currency(r['amount']),r['source'])))
        self.fill(self.sources_tree,rows)

    def apply_theme(self):
        if not self.is_built:return
        for c in self.cards:c.apply_theme()
        for b in self.buttons:b.apply_theme()
        for c in self.metrics:c.apply_theme()
        self.scenario_slider.apply_theme()
        self.refresh(False)
