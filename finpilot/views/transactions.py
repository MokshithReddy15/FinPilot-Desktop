"""
finpilot/views/transactions.py
Screen B: Transactions View
- Add Form: Sliding SegmentedPillToggle (Expense / Income), dedicated 1-Tap Instant Log Preset strip,
  Amount, dynamic Category Combobox, Date (default today, validated YYYY-MM-DD, no future dates), Note.
- Inline error validation messages (zero messagebox popups).
- History Table (Treeview): sortable columns, live 150ms debounced search,
  instant filtering by type/category/month.
- Batched Treeview updates (Rule 4) capable of handling 5,000+ rows smoothly.
- Delete with inline confirmation + 5-second Undo toast.
- Keyboard shortcuts: Enter submits form, Delete removes selected row, Ctrl+N focuses amount.
- Export to CSV button running on a worker thread.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from animations import Animator
from models import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    Transaction,
    TransactionType,
    format_indian_currency,
    rupees_to_paise,
    validate_iso_date,
)
from store import DataStore
from theme import ThemeManager
from widgets import PillButton, RoundedCard, SegmentedPillToggle, ToastNotification
from layout import responsive_grid, flow_row

QUICK_PRESETS: list[dict[str, str]] = [
    {
        "label": "Coffee · 320",
        "type": "EXPENSE",
        "amount": "320",
        "category": "Food",
        "note": "Third Wave Specialty Coffee",
    },
    {
        "label": "Groceries · 1,850",
        "type": "EXPENSE",
        "amount": "1850",
        "category": "Groceries",
        "note": "Fresh produce & daily essentials",
    },
    {
        "label": "Fuel · 2,400",
        "type": "EXPENSE",
        "amount": "2400",
        "category": "Fuel",
        "note": "Highway full tank refill",
    },
    {
        "label": "Freelance · +25,000",
        "type": "INCOME",
        "amount": "25000",
        "category": "Freelance",
        "note": "UI Architecture Sprint Milestone",
    },
]


class TransactionsView(ttk.Frame):
    """
    Full transaction ledger with sliding type toggle, dedicated 1-tap preset chip row,
    inline validation, instant search/filtering, batched Treeview rendering, and Undo toast.
    """

    def __init__(
        self,
        parent: tk.Misc,
        store: DataStore,
        theme: ThemeManager,
        animator: Animator,
        toast: ToastNotification,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.store = store
        self.theme = theme
        self.animator = animator
        self.toast = toast
        self.is_built = False
        self.is_dirty = True

        self._form_type = TransactionType.EXPENSE
        self._amount_var = tk.StringVar()
        self._category_var = tk.StringVar()
        self._date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        self._note_var = tk.StringVar()
        self._error_var = tk.StringVar(value="")

        self._search_var = tk.StringVar()
        self._filter_type_var = tk.StringVar(value="ALL")
        self._filter_cat_var = tk.StringVar(value="ALL")
        self._filter_month_var = tk.StringVar(value="ALL")

        self._sort_col = "date"
        self._sort_desc = True
        self._pending_delete_id: str | None = None
        self._cards: list[RoundedCard] = []
        self._preset_buttons: list[PillButton] = []
        self._field_labels: list[tk.Label] = []

    def build(self) -> None:
        """Build form, 1-tap presets row, and Treeview table once (Section 5 Rule 2)."""
        if self.is_built:
            return
        self.is_built = True
        t = self.theme.tokens

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ---- Top Card: Add Transaction Form (3 clean non-overlapping rows) ----
        form_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="tx_form",
            height=176,
            auto_height=True,
        )
        form_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._cards.append(form_card)

        # Row 1: Title + Sliding Expense/Income Toggle + Inline Error Label
        top_row = tk.Frame(form_card.body, bg=t["surface"])
        top_row.pack(fill="x", pady=(0, 8))
        self._top_row = top_row

        self._form_title = tk.Label(
            top_row,
            text="New Transaction",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["subtitle"],
        )
        self._form_title.pack(side="left", padx=(0, 14))

        self._type_pill_toggle = SegmentedPillToggle(
            top_row,
            self.theme,
            self.animator,
            toggle_id="tx_type_pill",
            options=[
                ("EXPENSE", "− Expense"),
                ("INCOME", "+ Income"),
            ],
            on_change=lambda key: self._set_form_type(TransactionType(key)),
            width=190,
            height=28,
            active_color_key="danger",
            parent_bg_key="surface",
        )
        self._type_pill_toggle.pack(side="left")

        self._error_lbl = tk.Label(
            top_row,
            textvariable=self._error_var,
            bg=t["surface"],
            fg=t["danger"],
            font=self.theme.fonts["caption_bold"],
        )
        self._error_lbl.pack(side="right")

        # Row 2: Dedicated 1-Tap Instant Log Presets Strip (never crowds Row 1)
        preset_row = tk.Frame(form_card.body, bg=t["surface"])
        preset_row.pack(fill="x", pady=(0, 10))
        self._preset_row = preset_row

        preset_lbl = tk.Label(
            preset_row,
            text="ONE-TAP LOG",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        preset_lbl.pack(side="left", padx=(0, 10))
        self._field_labels.append(preset_lbl)

        for preset in QUICK_PRESETS:
            p_btn = PillButton(
                preset_row,
                self.theme,
                text=preset["label"],
                command=lambda p=preset: self._instant_log_preset(p),
                variant="secondary",
                width=120,
                height=26,
            )
            p_btn.pack(side="left", padx=(0, 8))
            self._preset_buttons.append(p_btn)

        # Row 3: Form Inputs + Add Button
        inputs_row = tk.Frame(form_card.body, bg=t["surface"])
        inputs_row.pack(fill="x")
        self._inputs_row = inputs_row
        for c in range(5):
            inputs_row.columnconfigure(c, weight=1 if c < 4 else 0)

        # Amount Field
        amt_box = tk.Frame(inputs_row, bg=t["surface"])
        amt_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._amt_box = amt_box
        lbl_amt = tk.Label(
            amt_box,
            text="Amount (Rs.) *",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_amt.pack(anchor="w")
        self._field_labels.append(lbl_amt)
        self.amount_entry = ttk.Entry(
            amt_box, textvariable=self._amount_var, style="Fin.TEntry"
        )
        self.amount_entry.pack(fill="x", pady=(4, 0))
        self.amount_entry.bind("<Return>", lambda _e: self.submit_transaction())

        # Category Combobox
        cat_box = tk.Frame(inputs_row, bg=t["surface"])
        cat_box.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self._cat_box = cat_box
        lbl_cat = tk.Label(
            cat_box,
            text="Category *",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_cat.pack(anchor="w")
        self._field_labels.append(lbl_cat)
        self._cat_combo = ttk.Combobox(
            cat_box,
            textvariable=self._category_var,
            state="readonly",
            style="Fin.TCombobox",
        )
        self._cat_combo.pack(fill="x", pady=(4, 0))

        # Date Field
        date_box = tk.Frame(inputs_row, bg=t["surface"])
        date_box.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        self._date_box = date_box
        lbl_date = tk.Label(
            date_box,
            text="Date (YYYY-MM-DD) *",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_date.pack(anchor="w")
        self._field_labels.append(lbl_date)
        self._date_entry = ttk.Entry(
            date_box, textvariable=self._date_var, style="Fin.TEntry"
        )
        self._date_entry.pack(fill="x", pady=(4, 0))
        self._date_entry.bind("<Return>", lambda _e: self.submit_transaction())

        # Note Field
        note_box = tk.Frame(inputs_row, bg=t["surface"])
        note_box.grid(row=0, column=3, sticky="ew", padx=(0, 10))
        self._note_box = note_box
        lbl_note = tk.Label(
            note_box,
            text="Note / Description",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_note.pack(anchor="w")
        self._field_labels.append(lbl_note)
        self._note_entry = ttk.Entry(
            note_box, textvariable=self._note_var, style="Fin.TEntry"
        )
        self._note_entry.pack(fill="x", pady=(4, 0))
        self._note_entry.bind("<Return>", lambda _e: self.submit_transaction())

        # Submit Button
        btn_box = tk.Frame(inputs_row, bg=t["surface"])
        btn_box.grid(row=0, column=4, sticky="s")
        self._btn_box = btn_box
        self._add_btn = PillButton(
            btn_box,
            self.theme,
            text="Add Entry (↵)",
            command=self.submit_transaction,
            variant="primary",
            width=120,
            height=34,
        )
        self._add_btn.pack(pady=(16, 0))

        # ---- Bottom Card: Filter Bar + Treeview Table ----
        table_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="tx_table",
            height=490,
            auto_height=False,
        )
        table_card.grid(row=1, column=0, sticky="nsew")
        self._cards.append(table_card)

        filter_bar = tk.Frame(table_card.body, bg=t["surface"])
        filter_bar.pack(fill="x", pady=(0, 8))
        self._filter_bar = filter_bar

        lbl_search = tk.Label(
            filter_bar,
            text="Search:",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_search.pack(side="left", padx=(0, 6))
        self._field_labels.append(lbl_search)

        search_entry = ttk.Entry(
            filter_bar,
            textvariable=self._search_var,
            style="Fin.TEntry",
            width=22,
        )
        search_entry.pack(side="left", padx=(0, 10))
        self._search_var.trace_add(
            "write",
            lambda *_: self.animator.debounce(
                "tx_search_debounce", 150, self._populate_table
            ),
        )

        # Type Filter
        self._type_filter_combo = ttk.Combobox(
            filter_bar,
            textvariable=self._filter_type_var,
            values=["ALL", "INCOME", "EXPENSE"],
            state="readonly",
            style="Fin.TCombobox",
            width=11,
        )
        self._type_filter_combo.pack(side="left", padx=(0, 8))
        self._type_filter_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._populate_table()
        )

        # Category Filter
        self._cat_filter_combo = ttk.Combobox(
            filter_bar,
            textvariable=self._filter_cat_var,
            state="readonly",
            style="Fin.TCombobox",
            width=14,
        )
        self._cat_filter_combo.pack(side="left", padx=(0, 8))
        self._cat_filter_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._populate_table()
        )

        # Month Filter
        self._month_filter_combo = ttk.Combobox(
            filter_bar,
            textvariable=self._filter_month_var,
            state="readonly",
            style="Fin.TCombobox",
            width=11,
        )
        self._month_filter_combo.pack(side="left", padx=(0, 8))
        self._month_filter_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._populate_table()
        )

        # Right side buttons: Delete selected + Export CSV
        self._csv_btn = PillButton(
            filter_bar,
            self.theme,
            text="Export CSV",
            command=self._export_csv,
            variant="secondary",
            width=100,
            height=30,
        )
        self._csv_btn.pack(side="right")

        self._del_btn = PillButton(
            filter_bar,
            self.theme,
            text="Delete Selected",
            command=self.delete_selected_row,
            variant="danger",
            width=120,
            height=30,
        )
        self._del_btn.pack(side="right", padx=(0, 8))

        self._ledger_summary = tk.Label(table_card.body, text='', bg=t['surface'], fg=t['text_muted'],
                                        font=self.theme.fonts['caption'], anchor='w', justify='left')
        self._ledger_summary.pack(fill='x',pady=(2,10))
        self._ledger_summary.bind('<Configure>',lambda e:self._ledger_summary.configure(wraplength=max(120,e.width)))

        # Treeview + Scrollbar
        tree_container = tk.Frame(table_card.body, bg=t["surface"])
        tree_container.pack(fill="both", expand=True)
        self._tree_container = tree_container

        columns = ("date", "type", "category", "note", "amount")
        self.tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            style="Fin.Treeview",
            selectmode="browse",
        )
        vsb = ttk.Scrollbar(
            tree_container,
            orient="vertical",
            command=self.tree.yview,
            style="Fin.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=vsb.set)

        headings = [
            ("date", "DATE ↕", 110, "w"),
            ("type", "TYPE ↕", 95, "w"),
            ("category", "CATEGORY ↕", 140, "w"),
            ("note", "NOTE", 300, "w"),
            ("amount", "AMOUNT ↕", 140, "e"),
        ]
        for col_id, text, width, anchor in headings:
            self.tree.heading(
                col_id,
                text=text,
                anchor=anchor,
                command=lambda c=col_id: self._sort_by_column(c),
            )
            self.tree.column(col_id, width=width, anchor=anchor)

        tree_container.columnconfigure(0,weight=1);tree_container.rowconfigure(0,weight=1)
        self.tree.grid(row=0,column=0,sticky='nsew')
        vsb.grid(row=0,column=1,sticky='ns')
        hsb=ttk.Scrollbar(tree_container,orient='horizontal',command=self.tree.xview)
        hsb.grid(row=1,column=0,sticky='ew');self.tree.configure(xscrollcommand=hsb.set)


        self.tree.bind("<Delete>", lambda _e: self.delete_selected_row())
        self.tree.bind(
            "<<TreeviewSelect>>", lambda _e: self._reset_delete_confirmation()
        )

        self._set_form_type(TransactionType.EXPENSE, animate=False)
        responsive_grid(inputs_row, [amt_box,cat_box,date_box,note_box,btn_box], min_width=190, max_columns=5)
        flow_row(top_row);flow_row(preset_row);flow_row(filter_bar)
        self._error_lbl.configure(wraplength=350,justify='left')
        self._error_var.trace_add('write',lambda *_:self.after_idle(top_row._reflow))
        self.rowconfigure(1,weight=0)


    def _instant_log_preset(self, preset: dict[str, str]) -> None:
        """One-tap instant transaction logger from preset chip."""
        tx_type = TransactionType(preset["type"])
        self._set_form_type(tx_type, animate=True)
        paise = rupees_to_paise(preset["amount"])
        try:
            iso_date = validate_iso_date(self._date_var.get())
        except ValueError:
            iso_date = date.today().strftime("%Y-%m-%d")

        tx = Transaction(
            type=tx_type,
            amount_paise=paise,
            category=preset["category"],
            date=iso_date,
            note=preset["note"],
        )
        result = self.store.add_transaction(tx)
        alert = result.get("budget_alert")
        if alert:
            self.toast.show(
                message=alert["message"],
                level=alert["level"],
                duration_ms=6000,
            )
        else:
            self.toast.show(
                message=f"Instant Logged: {preset['category']} ({format_indian_currency(paise, self.store.currency_symbol)})",
                level="success",
                duration_ms=3500,
            )

    def focus_amount_field(self) -> None:
        """Keyboard shortcut Ctrl+N handler to focus the amount entry."""
        if self.is_built:
            self.amount_entry.focus_set()
            self.amount_entry.selection_range(0, tk.END)

    def _set_form_type(
        self, tx_type: TransactionType, animate: bool = True
    ) -> None:
        self._form_type = tx_type
        cats = self.store.get_categories(tx_type)
        self._cat_combo["values"] = cats
        if self._category_var.get() not in cats:
            self._category_var.set(cats[0] if cats else "Other")

        color_key = "danger" if tx_type == TransactionType.EXPENSE else "success"
        self._type_pill_toggle.set_active_color_key(color_key)
        self._type_pill_toggle.set_selected(
            tx_type.value, notify=False, animate=animate
        )

    def submit_transaction(self) -> None:
        """Validate form fields inline and add transaction to DataStore."""
        self._error_var.set("")
        self.amount_entry.configure(style='Fin.TEntry');self._date_entry.configure(style='Fin.TEntry')
        invalid_field = self.amount_entry
        try:
            paise = rupees_to_paise(self._amount_var.get())
            cat = self._category_var.get().strip()
            if not cat:
                raise ValueError("Please select a category.")
            invalid_field = self._date_entry
            iso_date = validate_iso_date(self._date_var.get())
        except ValueError as exc:
            invalid_field.configure(style="Invalid.Fin.TEntry");invalid_field.focus_set()
            self._error_var.set(f"⚠ {exc}")
            return

        note = self._note_var.get().strip()
        tx = Transaction(
            type=self._form_type,
            amount_paise=paise,
            category=cat,
            date=iso_date,
            note=note,
        )
        result = self.store.add_transaction(tx)

        self._amount_var.set("")
        self._note_var.set("")
        self.amount_entry.focus_set()
        self._error_var.set("")

        alert = result.get("budget_alert")
        if alert:
            self.toast.show(
                message=alert["message"],
                level=alert["level"],
                duration_ms=6000,
            )
        else:
            self.toast.show(
                message=f"Added {cat} ({format_indian_currency(paise, self.store.currency_symbol)})",
                level="success",
                duration_ms=3500,
            )

    def _reset_delete_confirmation(self) -> None:
        self._pending_delete_id = None
        if self.is_built:
            self._del_btn.set_text("Delete Selected")
            self._del_btn.set_enabled(bool(self.tree.selection()))

    def delete_selected_row(self) -> None:
        selection = self.tree.selection()
        if not selection:
            self._error_var.set("⚠ Select a transaction row in the table to delete.")
            return

        tx_id = selection[0]
        if self._pending_delete_id != tx_id:
            self._pending_delete_id = tx_id
            self._del_btn.set_text("Confirm Delete?")
            self.animator.debounce(
                "reset_del_confirm", 3500, self._reset_delete_confirmation
            )
            return

        self._reset_delete_confirmation()
        deleted_tx = self.store.delete_transaction(tx_id)
        if deleted_tx is not None:
            sym = self.store.currency_symbol
            self.toast.show(
                message=(
                    f"Deleted {deleted_tx.category} "
                    f"({format_indian_currency(deleted_tx.amount_paise, sym)})"
                ),
                level="warning",
                duration_ms=5000,
                action_label="Undo",
                action_callback=lambda: self.store.restore_transaction(deleted_tx),
            )

    def _sort_by_column(self, col: str) -> None:
        if col == "note":
            return
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = True
        self._populate_table()

    def _populate_table(self) -> None:
        if not self.is_built:
            return
        t = self.theme.tokens
        sym = self.store.currency_symbol

        self.tree.tag_configure(
            "even_inc", background=t["surface"], foreground=t["text_primary"]
        )
        self.tree.tag_configure(
            "odd_inc", background=t["surface_raised"], foreground=t["text_primary"]
        )
        self.tree.tag_configure(
            "even_exp", background=t["surface"], foreground=t["text_primary"]
        )
        self.tree.tag_configure(
            "odd_exp", background=t["surface_raised"], foreground=t["text_primary"]
        )

        rows = self.store.get_transactions(
            search=self._search_var.get(),
            tx_type=self._filter_type_var.get(),
            category=self._filter_cat_var.get(),
            month=self._filter_month_var.get(),
            sort_by=self._sort_col,
            descending=self._sort_desc,
        )

        income=sum(tx.amount_paise for tx in rows if tx.type==TransactionType.INCOME)
        expense=sum(tx.amount_paise for tx in rows if tx.type==TransactionType.EXPENSE)
        self._ledger_summary.configure(text=(f"{len(rows)} records  ·  Income {format_indian_currency(income,sym)}  ·  Expenses {format_indian_currency(expense,sym)}"
            if rows else 'No matching transactions. Clear the search or change the filters to see more records.'))
        self._csv_btn.set_enabled(bool(rows))
        self._del_btn.set_enabled(False)
        for column,title in [('date','DATE'),('type','TYPE'),('category','CATEGORY'),('note','NOTE'),('amount','AMOUNT')]:
            marker=(' ↓' if self._sort_desc else ' ↑') if column==self._sort_col else ''
            self.tree.heading(column,text=title+marker)
        existing = self.tree.get_children()
        if existing:
            self.tree.delete(*existing)

        for idx, tx in enumerate(rows):
            is_inc = tx.type == TransactionType.INCOME
            signed_paise = tx.amount_paise if is_inc else -tx.amount_paise
            amt_str = format_indian_currency(
                signed_paise, sym, show_decimals=True, signed=True
            )
            parity = "even" if idx % 2 == 0 else "odd"
            kind = "inc" if is_inc else "exp"
            self.tree.insert(
                "",
                "end",
                iid=tx.id,
                values=(
                    tx.date,
                    tx.type.value,
                    tx.category,
                    tx.note or "—",
                    amt_str,
                ),
                tags=(f"{parity}_{kind}",),
            )

    def _export_csv(self) -> None:
        rows = self.store.get_transactions(
            search=self._search_var.get(),
            tx_type=self._filter_type_var.get(),
            category=self._filter_cat_var.get(),
            month=self._filter_month_var.get(),
            sort_by=self._sort_col,
            descending=self._sort_desc,
        )
        if not rows:
            self.toast.show("No transactions to export.", level="warning")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile="finpilot_transactions.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        def _done(ok: bool, msg: str) -> None:
            self.after(
                0,
                lambda: self.toast.show(
                    msg, level="success" if ok else "danger", duration_ms=4000
                ),
            )

        self.store.export_csv_async(Path(path), rows, on_complete=_done)

    def refresh(self, animate: bool = False) -> None:
        if not self.is_built:
            self.build()
        self.is_dirty = False

        all_cats = ["ALL"] + sorted(
            set(INCOME_CATEGORIES)
            | set(EXPENSE_CATEGORIES)
            | set(self.store.get_categories(TransactionType.EXPENSE))
        )
        self._cat_filter_combo["values"] = all_cats
        if self._filter_cat_var.get() not in all_cats:
            self._filter_cat_var.set("ALL")

        months = ["ALL"] + self.store.get_available_months()
        self._month_filter_combo["values"] = months
        if self._filter_month_var.get() not in months:
            self._filter_month_var.set("ALL")

        self._set_form_type(self._form_type, animate=False)
        self._populate_table()

    def apply_theme(self) -> None:
        if not self.is_built:
            return
        t = self.theme.tokens
        for c in self._cards:
            c.apply_theme()
        for f in (
            self._top_row,
            self._preset_row,
            self._inputs_row,
            self._amt_box,
            self._cat_box,
            self._date_box,
            self._note_box,
            self._btn_box,
            self._filter_bar,
            self._tree_container,
        ):
            f.configure(bg=t["surface"])
        self._ledger_summary.configure(bg=t["surface"],fg=t["text_muted"])
        self._form_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._error_lbl.configure(bg=t["surface"], fg=t["danger"])
        self._type_pill_toggle.apply_theme()
        for p_btn in self._preset_buttons:
            p_btn.apply_theme()
        for lbl in self._field_labels:
            lbl.configure(bg=t["surface"], fg=t["text_muted"])
        self._add_btn.apply_theme()
        self._csv_btn.apply_theme()
        self._del_btn.apply_theme()
        self.refresh()
