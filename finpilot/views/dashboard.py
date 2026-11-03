"""Homepage: gradient balance hero, savings simulator, metric row and activity."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from animations import Animator
from models import CATEGORY_ICONS, TransactionType, format_indian_currency
from store import DataStore
from theme import ThemeManager
from widgets import (
    AnimatedProgressBar,
    InteractiveCashflowHorizon,
    PillButton,
    RoundedCard,
    SegmentedPillToggle,

)

from home_surfaces import BalanceHero as VaultSimulatorCard, HomeMetric as StatCard
from layout import responsive_grid, flow_row
from activity import CategoryBadge, date_heading

class DashboardView(ttk.Frame):
    """
    Main interactive dashboard. Built once in `build()`, updated in-place in `refresh()`.
    """

    def __init__(
        self,
        parent: tk.Misc,
        store: DataStore,
        theme: ThemeManager,
        animator: Animator,
        on_navigate: Callable[[str], None],
        on_load_demo: Callable[[], None],
        on_select_month: Callable[[str], None] | None = None,
        on_add_transaction: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.store = store
        self.theme = theme
        self.animator = animator
        self.on_navigate = on_navigate
        self.on_load_demo = on_load_demo
        self.on_select_month = on_select_month
        self.on_add_transaction = on_add_transaction
        self.is_built = False
        self.is_dirty = True

        self._scope_mode: str = "ALL"  # "ALL" or "MONTH"
        self._recent_filter: str = "ALL"  # "ALL", "EXPENSE", "INCOME"
        self._active_month: str = ""

        self._stat_cards: dict[str, StatCard] = {}
        self._recent_rows: list[dict[str, tk.Label | tk.Frame]] = []
        self._budget_rows: list[dict[str, tk.Label | AnimatedProgressBar | tk.Frame]] = []
        self._cards: list[RoundedCard] = []

    def set_active_month(self, month: str) -> None:
        """Switch active month from Cashflow Horizon click or top bar."""
        self._active_month = month
        if self.is_built:
            self.refresh(animate=True)

    def build(self) -> None:
        """Construct all dashboard widgets once (Section 5 Rule 2)."""
        if self.is_built:
            return
        self.is_built = True
        t = self.theme.tokens

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=1)

        # ---- Row 0: Interactive Scope Control Strip ----
        scope_bar = tk.Frame(self, bg=t["background"])
        scope_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._scope_bar = scope_bar

        self._scope_toggle = SegmentedPillToggle(
            scope_bar,
            self.theme,
            self.animator,
            toggle_id="dash_scope",
            options=[
                ("ALL", "All time"),
                ("MONTH", "Selected month"),
            ],
            on_change=self._on_scope_change,
            width=260,
            height=28,
            active_color_key="primary",
            parent_bg_key="background",
        )
        self._scope_toggle.pack(side="left")

        self._comp_label = tk.Label(
            scope_bar,
            text="",
            bg=t["background"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        self._comp_label.pack(side="right")

        # ---- Row 1: Vault Simulator Hero Card + 3 Kinetic Stat Cards ----
        kpi_frame = ttk.Frame(self, style="App.TFrame")
        kpi_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        kpi_frame.columnconfigure(0, weight=13, uniform="kpi")
        kpi_frame.columnconfigure(1, weight=10, uniform="kpi")
        kpi_frame.columnconfigure(2, weight=10, uniform="kpi")
        kpi_frame.columnconfigure(3, weight=10, uniform="kpi")

        self._kpi_frame = kpi_frame
        self._vault_card = VaultSimulatorCard(kpi_frame, self.theme, self.animator)
        self._vault_card.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        specs = [
            ("income", "TOTAL INCOME", "success", False),
            ("expense", "TOTAL EXPENSES", "danger", False),
            ("savings", "SAVINGS RATE", "primary", True),
        ]
        for idx, (cid, title, accent, radial) in enumerate(specs, start=1):
            card = StatCard(
                kpi_frame,
                self.theme,
                self.animator,
                cid,
                title,
                accent,
                show_radial=radial,
            )
            pad_r = 10 if idx < 3 else 0
            card.grid(row=0, column=idx, sticky="ew", padx=(0, pad_r))
            self._stat_cards[cid] = card

        # ---- Row 2 Col 0: Interactive 6-Month Cashflow Horizon (Spline + Bars + HUD) ----
        chart_card = RoundedCard(
            self, self.theme, animator=self.animator, card_key="dash_horizon", height=290
        )
        chart_card.grid(row=2, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self._cards.append(chart_card)

        header_row = tk.Frame(chart_card.body, bg=t["surface"])
        header_row.pack(fill="x", pady=(0, 4))
        self._chart_title = tk.Label(
            header_row,
            text="Your cashflow story",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
        )
        self._chart_title.pack(side="left")

        self._horizon_hud = tk.Label(
            header_row,
            text="",
            bg=t["surface_raised"],
            fg=t["text_primary"],
            font=self.theme.fonts["caption_bold"],
            padx=8,
            pady=2,
        )
        self._horizon_hud.pack(side="right")
        flow_row(header_row)

        self._horizon_chart = InteractiveCashflowHorizon(
            chart_card.body,
            self.theme,
            self.animator,
            on_inspect_month=self._on_inspect_horizon_month,
            on_select_month=self._on_click_horizon_month,
            height=206,
        )
        self._horizon_chart.pack(fill="both", expand=True)
        legend = tk.Frame(chart_card.body,bg=t['surface'])
        legend.pack(fill='x',pady=(6,0))
        self._legend_income = tk.Label(legend,text='● Income',bg=t['surface'],fg=t['success'],font=self.theme.fonts['caption_bold'])
        self._legend_income.pack(side='left',padx=(0,16))
        self._legend_expense = tk.Label(legend,text='● Expenses',bg=t['surface'],fg=t['danger'],font=self.theme.fonts['caption_bold'])
        self._legend_expense.pack(side='left')
        flow_row(legend)
        self._chart_hint = tk.Label(chart_card.body, text="Hover for details · Select a month to explore",
            bg=t['surface'], fg=t['text_muted'], font=self.theme.fonts['caption'], anchor='w')
        self._chart_hint.pack(fill='x', pady=(8,0))

        # ---- Row 2 Col 1: Budget Health Strip (Top 3 closest to limit) ----
        budget_card = RoundedCard(
            self, self.theme, animator=self.animator, card_key="dash_budget", height=290
        )
        budget_card.grid(row=2, column=1, sticky="nsew", pady=(0, 12))
        self._cards.append(budget_card)

        b_hdr = tk.Frame(budget_card.body, bg=t["surface"])
        b_hdr.pack(fill="x", pady=(0, 6))
        self._b_title = tk.Label(
            b_hdr,
            text="Monthly budget pulse",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
        )
        self._b_title.pack(side="left")

        self._b_manage_btn = PillButton(
            b_hdr,
            self.theme,
            text="Manage →",
            command=lambda: self.on_navigate("budget"),
            variant="secondary",
            width=90,
            height=26,
        )
        self._b_manage_btn.pack(side="right")
        self._budget_context = tk.Label(budget_card.body,text='',bg=t['surface'],
            fg=t['text_muted'],font=self.theme.fonts['caption'],anchor='w')
        self._budget_context.pack(fill='x',pady=(0,8))

        for i in range(3):
            row_f = tk.Frame(budget_card.body, bg=t["surface"])
            row_f.pack(fill="x", pady=4)
            top_line = tk.Frame(row_f, bg=t["surface"])
            top_line.pack(fill="x")
            cat_lbl = tk.Label(
                top_line,
                text="",
                bg=t["surface"],
                fg=t["text_primary"],
                font=self.theme.fonts["body_bold"],
            )
            cat_lbl.pack(side="left")
            meta_lbl = tk.Label(
                top_line,
                text="",
                bg=t["surface"],
                fg=t["text_muted"],
                font=self.theme.fonts["caption"],
            )
            meta_lbl.pack(side="bottom", anchor="w", pady=(4,0))
            pbar = AnimatedProgressBar(
                row_f,
                self.theme,
                self.animator,
                bar_id=f"dash_b_{i}",
                height=8,
            )
            pbar.pack(fill="x", pady=(4, 0))
            self._budget_rows.append(
                {"frame": row_f, "cat": cat_lbl, "meta": meta_lbl, "bar": pbar}
            )

        self._budget_empty_lbl = tk.Label(
            budget_card.body,
            text="No budgets set. Open Budget Planner to configure monthly caps.",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["body"],
            wraplength=280,
            justify="left",
        )

        # ---- Row 3 Col 0..1: Recent Transactions (Last 6) + Sliding Stream Filter ----
        recent_card = RoundedCard(
            self, self.theme, animator=self.animator, card_key="dash_recent", height=340
        )
        recent_card.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self._cards.append(recent_card)

        r_hdr = tk.Frame(recent_card.body, bg=t["surface"])
        r_hdr.pack(fill="x", pady=(0, 6))
        self._r_title = tk.Label(
            r_hdr,
            text="Recent activity",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
        )
        self._r_title.pack(side="left")

        self._view_all_btn = PillButton(
            r_hdr,
            self.theme,
            text="Full Ledger →",
            command=lambda: self.on_navigate("transactions"),
            variant="secondary",
            width=105,
            height=26,
        )
        self._view_all_btn.pack(side="right", padx=(8, 0))

        self._stream_toggle = SegmentedPillToggle(
            r_hdr,
            self.theme,
            self.animator,
            toggle_id="dash_stream_filter",
            options=[
                ("ALL", "All"),
                ("EXPENSE", "Expenses"),
                ("INCOME", "Income"),
            ],
            on_change=self._on_recent_filter_change,
            width=210,
            height=26,
            active_color_key="primary",
            parent_bg_key="surface",
        )
        self._stream_toggle.pack(side="right")

        self._recent_list_frame = tk.Frame(recent_card.body, bg=t["surface"])
        self._recent_list_frame.pack(fill="both", expand=True)

        for _ in range(6):
            group = tk.Label(self._recent_list_frame,text='',bg=t['surface'],fg=t['text_muted'],font=self.theme.fonts['caption_bold'],anchor='w')
            rf = tk.Frame(self._recent_list_frame, bg=t['surface'], pady=8,takefocus=1)
            separator = tk.Frame(rf,bg=t['border_subtle'],height=1)
            separator.pack(side='bottom',fill='x',pady=(8,0))
            icon_lbl = CategoryBadge(rf,self.theme)
            icon_lbl.pack(side="left")
            details = tk.Frame(rf, bg=t['surface'])
            details.pack(side='left', fill='x', expand=True, padx=12)
            title_lbl = tk.Label(
                details,
                text="",
                bg=t["surface"],
                fg=t["text_primary"],
                font=self.theme.fonts["body_bold"],
                anchor="w",
            )
            title_lbl.pack(anchor='w')
            note_lbl = tk.Label(
                details,
                text="",
                bg=t["surface"],
                fg=t["text_muted"],
                font=self.theme.fonts["caption"],
                anchor="w",
            )
            note_lbl.pack(anchor='w', pady=(3,0))
            date_lbl = tk.Label(
                rf,
                text="",
                bg=t["surface"],
                fg=t["text_muted"],
                font=self.theme.fonts["caption"],
                padx=12,
            )
            date_lbl.pack(side="right")
            amt_lbl = tk.Label(
                rf,
                text="",
                bg=t["surface"],
                fg=t["success"],
                font=self.theme.fonts["body_bold"],
                width=14,
                anchor="e",
            )
            amt_lbl.pack(side="right")
            self._recent_rows.append(
                {
                    "group": group,
                    "transaction": None,
                    "frame": rf,
                    "details": details,
                    "icon": icon_lbl,
                    "title": title_lbl,
                    "note": note_lbl,
                    "date": date_lbl,
                    "amount": amt_lbl,
                }
            )
            row = self._recent_rows[-1]
            for widget in (rf,details,icon_lbl,title_lbl,note_lbl,date_lbl,amt_lbl):
                widget.configure(cursor='hand2')
                widget.bind('<ButtonRelease-1>',lambda e,r=row:self._show_transaction(r))
                widget.bind('<Enter>',lambda e,r=row:self._highlight_row(r,True))
                widget.bind('<Leave>',lambda e,r=row:self.after_idle(lambda:self._row_leave(r)))

            rf.bind('<Return>',lambda e,r=row:self._show_transaction(r))
            rf.bind('<space>',lambda e,r=row:self._show_transaction(r))
            rf.bind('<FocusIn>',lambda e,r=row:self._highlight_row(r,True))
            rf.bind('<FocusOut>',lambda e,r=row:self._highlight_row(r,False))

        # Empty-state frame with CTA
        self._empty_frame = tk.Frame(recent_card.body, bg=t["surface"])
        self._empty_lbl = tk.Label(
            self._empty_frame,
            text="Your activity starts here. Add your first transaction.",
            wraplength=340,
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["body"],
        )
        self._empty_lbl.pack(pady=(12, 8))
        self._empty_cta = PillButton(
            self._empty_frame,
            self.theme,
            text="+ Add transaction",
            command=self._add_transaction,
            variant="primary",
            width=140,
            height=32,
        )
        self._empty_cta.pack()
        flow_row(scope_bar)
        flow_row(r_hdr)
        flow_row(b_hdr)
        self._chart_card, self._budget_card, self._recent_card = chart_card, budget_card, recent_card
        self._layout_mode = None
        self.bind('<Configure>', self._responsive, add='+')
        self.after_idle(self._responsive)


    def _responsive(self, event=None):
        if not self.is_built:return
        w = self.winfo_width()
        mode = 'wide' if w >= 1000 else ('medium' if w >= 700 else 'narrow')
        layout_key=(mode,w>=900)
        if layout_key == self._layout_mode:return
        self._layout_mode = layout_key
        for c in range(4):self._kpi_frame.columnconfigure(c, weight=0, uniform='')
        for r in range(6):self.rowconfigure(r, weight=0)
        cards = [self._vault_card, *self._stat_cards.values()]
        if mode in ('wide','medium'):
            for c in range(3):self._kpi_frame.columnconfigure(c,weight=1,uniform='kpi')
            cards[0].configure(height=220);cards[0].grid(row=0,column=0,columnspan=3,sticky='ew',padx=0,pady=(0,12))
            for i,card in enumerate(cards[1:]):
                card.configure(height=156);card.grid(row=1,column=i,columnspan=1,sticky='ew',padx=(0,14 if i<2 else 0),pady=(0,8))
        else:
            for c in range(2):self._kpi_frame.columnconfigure(c,weight=1,uniform='kpi')
            cards[0].configure(height=338);cards[0].grid(row=0,column=0,columnspan=2,sticky='ew',padx=0,pady=(0,12))
            for i,card in enumerate(cards[1:]):
                card.configure(height=164)
                card.grid(row=1+i//2,column=i%2,columnspan=2 if i==2 else 1,sticky='ew',padx=(0,12 if i==0 else 0),pady=(0,12))
        split = w >= 900
        self.columnconfigure(0,weight=3 if split else 1)
        self.columnconfigure(1,weight=2 if split else 0)
        self._chart_card.grid(row=2,column=0,columnspan=1 if split else 2,sticky='nsew',padx=(0,12 if split else 0),pady=(0,12))
        self._budget_card.grid(row=2 if split else 3,column=1 if split else 0,columnspan=1 if split else 2,sticky='nsew',padx=0,pady=(0,12))
        self._recent_card.grid(row=3 if split else 4,column=0,columnspan=2,sticky='ew')
        for row in self._recent_rows:
            row['note'].configure(wraplength=max(100,w-320))
            row['date'].pack_forget()
            row['title'].configure(wraplength=max(100,w-320))

    def _add_transaction(self):
        if self.on_add_transaction:self.on_add_transaction()
        else:self.on_navigate('transactions')

    def _show_transaction(self,row):
        tx=row.get('transaction')
        if tx is None:return
        old=getattr(self,'_detail_window',None)
        if old is not None and old.winfo_exists():old.destroy()
        t=self.theme.tokens
        win=tk.Toplevel(self);self._detail_window=win
        win.title('Transaction details');win.transient(self.winfo_toplevel())
        win.configure(bg=t['surface']);win.geometry('480x420');win.minsize(360,340)
        win.columnconfigure(0,weight=1);win.rowconfigure(4,weight=1)
        income=tx.type==TransactionType.INCOME
        tk.Label(win,text='INCOME' if income else 'EXPENSE',bg=t['surface'],
            fg=t['text_muted'],font=self.theme.fonts['caption_bold']).grid(row=0,column=0,sticky='w',padx=24,pady=(24,6))
        tk.Label(win,text=format_indian_currency(tx.amount_paise if income else -tx.amount_paise,
            self.store.currency_symbol,show_decimals=True,signed=True),bg=t['surface'],
            fg=t['success'] if income else t['danger'],font=self.theme.fonts['display']).grid(row=1,column=0,sticky='w',padx=24)
        tk.Label(win,text=f'{tx.category}  ·  {tx.date}',bg=t['surface'],fg=t['text_primary'],
            font=self.theme.fonts['body_bold'],wraplength=310,justify='left').grid(row=2,column=0,sticky='w',padx=24,pady=(12,18))
        tk.Label(win,text='DESCRIPTION',bg=t['surface'],fg=t['text_muted'],font=self.theme.fonts['caption_bold']).grid(row=3,column=0,sticky='w',padx=24)
        body=tk.Frame(win,bg=t['surface']);body.grid(row=4,column=0,sticky='nsew',padx=24,pady=8)
        text=tk.Text(body,bg=t['background'],fg=t['text_primary'],font=self.theme.fonts['body'],
            wrap='word',height=5,width=1,bd=0,highlightthickness=0,padx=12,pady=12)
        bar=ttk.Scrollbar(body,command=text.yview,style='Fin.Vertical.TScrollbar')
        bar.pack(side='right',fill='y');text.pack(side='left',fill='both',expand=True)
        text.configure(yscrollcommand=bar.set);text.insert('1.0',tx.note or 'No description recorded.');text.configure(state='disabled')
        close=PillButton(win,self.theme,'Close',win.destroy,variant='secondary',width=80)
        close.grid(row=5,column=0,sticky='e',padx=24,pady=(8,20))
        win.bind('<Escape>',lambda e:win.destroy());win.grab_set();close.focus_set()
        return win

    def _highlight_row(self,row,active):
        color=self.theme.tokens['surface_hover' if active else 'surface']
        for key in ('frame','details','title','note','date','amount'):
            row[key].configure(bg=color)

    def _row_leave(self,row):
        frame=row['frame']
        if not frame.winfo_exists():return
        x,y=frame.winfo_pointerxy()
        inside=(frame.winfo_rootx()<=x<frame.winfo_rootx()+frame.winfo_width() and
                frame.winfo_rooty()<=y<frame.winfo_rooty()+frame.winfo_height())
        if not inside:self._highlight_row(row,False)

    def _on_scope_change(self, mode: str) -> None:
        self._scope_mode = mode
        self.refresh(animate=True)

    def _on_recent_filter_change(self, filter_key: str) -> None:
        self._recent_filter = filter_key
        self._refresh_recent_rows()

    def _on_inspect_horizon_month(self, item: dict[str, Any]) -> None:
        sym = self.store.currency_symbol
        inc = format_indian_currency(item["income_paise"], sym)
        exp = format_indian_currency(item["expense_paise"], sym)
        net = format_indian_currency(
            item["income_paise"] - item["expense_paise"], sym, signed=True
        )
        self._horizon_hud.configure(
            text=f"{item['label']}   ·   Net {net}"
        )
        self._legend_income.configure(text=f'● Income {inc}')
        self._legend_expense.configure(text=f'● Expenses {exp}')

    def _on_click_horizon_month(self, month_key: str) -> None:
        self._active_month = month_key
        self._scope_mode = "MONTH"
        self._scope_toggle.set_selected("MONTH", notify=False, animate=True)
        if self.on_select_month:
            self.on_select_month(month_key)
        self.refresh(animate=True)

    def _refresh_recent_rows(self) -> None:
        t = self.theme.tokens
        sym = self.store.currency_symbol
        recent_txs = self.store.get_transactions(tx_type=self._recent_filter)[:6]
        for row in self._recent_rows:
            row['group'].pack_forget();row['frame'].pack_forget();row['transaction']=None
        previous_date=None
        if not recent_txs:
            self._recent_list_frame.pack_forget()
            self._empty_lbl.configure(text="Your activity starts here. Add your first transaction." if self._recent_filter=="ALL" else f"No {self._recent_filter.lower()} transactions yet.")
            self._empty_frame.pack(fill="both", expand=True)
        else:
            self._empty_frame.pack_forget()
            self._recent_list_frame.pack(fill="both", expand=True)
            for idx, r_item in enumerate(self._recent_rows):
                if idx < len(recent_txs):
                    tx = recent_txs[idx]
                    r_item['transaction']=tx
                    if tx.date!=previous_date:
                        r_item['group'].configure(text=date_heading(tx.date))
                        r_item['group'].pack(fill='x',pady=(14,4))
                        previous_date=tx.date
                    r_item["frame"].pack(fill="x")  # type: ignore[union-attr]
                    r_item["icon"].set_category(tx.category,tx.type==TransactionType.INCOME)  # type: ignore[union-attr]
                    r_item["title"].configure(text=tx.category)  # type: ignore[union-attr]
                    r_item["note"].configure(text=tx.note or "—")  # type: ignore[union-attr]
                    r_item["date"].configure(text=tx.date)  # type: ignore[union-attr]
                    is_inc = tx.type == TransactionType.INCOME
                    sign_paise = tx.amount_paise if is_inc else -tx.amount_paise
                    r_item["amount"].configure(  # type: ignore[union-attr]
                        text=format_indian_currency(sign_paise, sym, signed=True),
                        fg=t["success"] if is_inc else t["danger"],
                    )
                else:
                    r_item["frame"].pack_forget()  # type: ignore[union-attr]

    def refresh(self, animate: bool = True) -> None:
        """Update existing widgets in-place with latest DataStore aggregations."""
        if not self.is_built:
            self.build()
        self.is_dirty = False
        t = self.theme.tokens
        sym = self.store.currency_symbol

        months = self.store.get_available_months()
        if not self._active_month or self._active_month not in months:
            self._active_month = self.store.get_latest_month()

        scope_arg = "ALL" if self._scope_mode == "ALL" else self._active_month
        metrics = self.store.get_summary_metrics(scope_arg)
        comp = self.store.get_monthly_comparison(self._active_month)

        scope_title = (
            "TOTAL NET BALANCE"
            if self._scope_mode == "ALL"
            else f"{self._active_month} NET SURPLUS"
        )
        monthly_inc_for_sim = (
            comp.current_income_paise
            if comp.current_income_paise > 0
            else int(metrics["income_paise"] // 6)
        )
        tx_count = len(self.store.get_transactions(month=scope_arg))

        self._vault_card.update_vault(
            balance_paise=int(metrics["balance_paise"]),
            monthly_income_paise=monthly_inc_for_sim,
            actual_savings_rate=float(metrics["savings_rate"]),
            record_count=tx_count,
            currency_symbol=sym,
            scope_title=scope_title,
            animate=animate,
        )

        self._stat_cards["income"].set_value(
            float(metrics["income_paise"]),
            lambda v: format_indian_currency(int(round(v)), sym),
            subtitle=f"Active ({comp.current_month}): {format_indian_currency(comp.current_income_paise, sym)}",
            badge_text="INFLOW",
            badge_color_key="success",
            animate=animate,
        )

        exp_badge = "OUTFLOW"
        exp_badge_col = "danger"
        if comp.expense_change_pct is not None:
            arrow = "▲" if comp.expense_change_pct > 0 else "▼"
            exp_badge = f"{arrow} {abs(comp.expense_change_pct):.1f}% MoM"
            exp_badge_col = "danger" if comp.expense_change_pct > 0 else "success"

        self._stat_cards["expense"].set_value(
            float(metrics["expense_paise"]),
            lambda v: format_indian_currency(int(round(v)), sym),
            subtitle=f"Prev ({comp.previous_month}): {format_indian_currency(comp.previous_expense_paise, sym)}",
            badge_text=exp_badge,
            badge_color_key=exp_badge_col,
            animate=animate,
        )

        sav_rate = float(metrics["savings_rate"])
        sav_badge = "EXCELLENT" if sav_rate >= 30 else ("HEALTHY" if sav_rate >= 15 else "LOW")
        self._stat_cards["savings"].set_value(
            sav_rate,
            lambda v: f"{v:.1f}%",
            subtitle="Share of income kept",
            badge_text=sav_badge,
            badge_color_key="success" if sav_rate >= 20 else "warning",
            animate=animate,
        )

        if comp.expense_change_pct is None:
            self._comp_label.configure(
                text=f"Active Month ({comp.current_month}): {format_indian_currency(comp.current_expense_paise, sym)}",
                fg=t["text_muted"],
            )
        else:
            arrow = "▲" if comp.expense_change_pct >= 0 else "▼"
            col = t["danger"] if comp.expense_change_pct > 0 else t["success"]
            self._comp_label.configure(
                text=(
                    f"Spending vs last month: "
                    f"{arrow} {abs(comp.expense_change_pct):.1f}%"
                ),
                fg=col,
            )

        series = self.store.get_last_n_months_series(6)
        for key,card in self._stat_cards.items():
            card.series=[float(item['income_paise'] if key=='income' else item['expense_paise'] if key=='expense' else (item['income_paise']-item['expense_paise'])) for item in series]
            card.draw()
        self._horizon_chart.currency_symbol = sym
        self._horizon_chart.set_series(
            series, active_month=self._active_month, animate=animate
        )

        statuses = self.store.get_budget_statuses(comp.current_month)[:3]
        self._budget_context.configure(text=f'{comp.current_month}  ·  Closest to their limits')
        if not statuses:
            for item in self._budget_rows:
                item["frame"].pack_forget()  # type: ignore[union-attr]
            self._budget_empty_lbl.pack(fill="x", pady=16)
        else:
            self._budget_empty_lbl.pack_forget()
            for idx, item in enumerate(self._budget_rows):
                if idx < len(statuses):
                    st = statuses[idx]
                    item["frame"].pack(fill="x", pady=4)  # type: ignore[union-attr]
                    item["cat"].configure(text=st.category)  # type: ignore[union-attr]
                    remaining=st.limit_paise-st.spent_paise
                    state=(f'{format_indian_currency(abs(remaining),sym)} over budget' if remaining<0 else
                           ('Limit reached' if remaining==0 else f'{format_indian_currency(remaining,sym)} remaining'))
                    level='danger' if remaining<=0 else ('warning' if st.percent_used>=90 else 'ok')
                    item['meta'].configure(text=f'{state}  ·  {st.percent_used:.0f}% used',
                        fg=t['danger'] if remaining<0 else t['text_muted'])
                    item['meta'].configure(justify='left',wraplength=280)
                    item["bar"].set_progress(st.percent_used, level, animate=animate)
                else:
                    item["frame"].pack_forget()  # type: ignore[union-attr]

        self._refresh_recent_rows()

    def apply_theme(self) -> None:
        """Re-theme all child widgets without rebuilding."""
        if not self.is_built:
            return
        t = self.theme.tokens
        self._scope_bar.configure(bg=t["background"])
        self._scope_toggle.apply_theme()
        self._comp_label.configure(bg=t["background"])
        self._vault_card.apply_theme()
        for card in self._stat_cards.values():
            card.apply_theme()
        for rcard in self._cards:
            rcard.apply_theme()
        self._horizon_chart.apply_theme()
        self._horizon_hud.configure(bg=t["surface_raised"], fg=t["text_primary"])
        self._b_manage_btn.apply_theme()
        self._view_all_btn.apply_theme()
        self._stream_toggle.apply_theme()
        self._empty_cta.apply_theme()
        self._chart_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._chart_hint.configure(bg=t['surface'], fg=t['text_muted'])
        self._legend_income.configure(bg=t['surface'],fg=t['success'])
        self._legend_expense.configure(bg=t['surface'],fg=t['danger'])
        self._b_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._budget_context.configure(bg=t['surface'],fg=t['text_muted'])
        self._r_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._budget_empty_lbl.configure(bg=t["surface"], fg=t["text_muted"])
        self._recent_list_frame.configure(bg=t["surface"])
        self._empty_frame.configure(bg=t["surface"])
        self._empty_lbl.configure(bg=t["surface"], fg=t["text_muted"])
        for b_item in self._budget_rows:
            b_item["frame"].configure(bg=t["surface"])  # type: ignore[union-attr]
            b_item["cat"].configure(bg=t["surface"], fg=t["text_primary"])  # type: ignore[union-attr]
            b_item["meta"].configure(bg=t["surface"], fg=t["text_muted"])  # type: ignore[union-attr]
            b_item["bar"].apply_theme()  # type: ignore[union-attr]
        for r_item in self._recent_rows:
            r_item['details'].configure(bg=t['surface'])
            r_item["frame"].configure(bg=t["surface"])  # type: ignore[union-attr]
            r_item['group'].configure(bg=t['surface'],fg=t['text_muted'])
            r_item["icon"].draw()  # type: ignore[union-attr]
            r_item["title"].configure(bg=t["surface"], fg=t["text_primary"])  # type: ignore[union-attr]
            r_item["note"].configure(bg=t["surface"], fg=t["text_muted"])  # type: ignore[union-attr]
            r_item["date"].configure(bg=t["surface"], fg=t["text_muted"])  # type: ignore[union-attr]
            r_item["amount"].configure(bg=t["surface"])  # type: ignore[union-attr]
        self.refresh(animate=False)
