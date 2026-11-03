"""
finpilot/views/budget.py
Screen D: Tactile Budget Planner View
- Set or update a monthly limit per category (standard + custom categories).
- Pool of reusable budget cards (updated in-place via config()/set_progress(), Rule 2):
  animated progress bar, spent / limit, % used, remaining amount.
- Tactile `-1k` and `+1k` quick-step buttons on every budget card for instant cap tuning.
- Auto-expanding RoundedCard geometry so form inputs and card bottom rows are NEVER clipped.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from animations import Animator
from models import (
    CATEGORY_ICONS,
    EXPENSE_CATEGORIES,
    TransactionType,
    format_indian_currency,
    rupees_to_paise,
)
from store import BudgetStatus, DataStore
from theme import ThemeManager
from widgets import AnimatedProgressBar, PillButton, RoundedCard, ToastNotification
from layout import responsive_grid, flow_row


class BudgetCardSlot(RoundedCard):
    """
    Pre-allocated budget card widget updated in-place via `update_slot()` (Rule 2).
    Includes tactile `-1k` and `+1k` quick-step buttons for live cap adjustment.
    Auto-expands its height so the bottom row is never clipped on any DPI.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        slot_idx: int,
        on_edit: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_step_limit: Callable[[str, int], None],
    ) -> None:
        super().__init__(
            parent,
            theme,
            animator=animator,
            card_key=f"bslot_{slot_idx}",
            height=174,
            padding=12,
            auto_height=True,
        )
        self.slot_idx = slot_idx
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_step_limit = on_step_limit
        self.current_category: str = ""
        self.current_limit_paise: int = 0

        t = theme.tokens
        self._top = tk.Frame(self.body, bg=t["surface"])
        self._top.pack(fill="x")

        self.title_lbl = tk.Label(
            self._top,
            text="",
            bg=t["surface"],
            fg=t["text_primary"],
            font=theme.fonts["body_bold"],
        )
        self.title_lbl.pack(side="left")

        self.del_lbl = tk.Label(
            self._top,
            text="Delete",
            bg=t["surface"],
            fg=t["danger"],
            font=theme.fonts["caption_bold"],
            cursor="hand2",
            padx=6,
        )
        self.del_lbl.pack(side="right")
        self.del_lbl.bind(
            "<ButtonRelease-1>", lambda _e: self.on_delete(self.current_category)
        )

        self.edit_lbl = tk.Label(
            self._top,
            text="Edit",
            bg=t["surface"],
            fg=t["primary"],
            font=theme.fonts["caption_bold"],
            cursor="hand2",
            padx=6,
        )
        self.edit_lbl.pack(side="right")
        self.edit_lbl.bind(
            "<ButtonRelease-1>", lambda _e: self.on_edit(self.current_category)
        )

        self._mid = tk.Frame(self.body, bg=t["surface"])
        self._mid.pack(fill="x", pady=(6, 4))

        self.spent_lbl = tk.Label(
            self._mid,
            text="",
            bg=t["surface"],
            fg=t["text_secondary"],
            font=theme.fonts["caption"],
        )
        self.spent_lbl.pack(side="left")

        self.pct_lbl = tk.Label(
            self._mid,
            text="",
            bg=t["surface"],
            fg=t["success"],
            font=theme.fonts["caption_bold"],
        )
        self.pct_lbl.pack(side="bottom", anchor="w",pady=(5,0))

        self.progress = AnimatedProgressBar(
            self.body,
            theme,
            animator,
            bar_id=f"budget_slot_{slot_idx}",
            height=8,
        )
        self.progress.pack(fill="x", pady=(2, 8))

        self._bot = tk.Frame(self.body, bg=t["surface"])
        self._bot.pack(fill="x")

        self.rem_lbl = tk.Label(
            self._bot,
            text="",
            bg=t["surface"],
            fg=t["text_muted"],
            font=theme.fonts["caption"],
            anchor="w",
        )
        self.rem_lbl.pack(side="left")

        self.plus_btn = PillButton(
            self._bot,
            theme,
            text="+1k",
            command=lambda: self.on_step_limit(self.current_category, 1000 * 100),
            variant="secondary",
            width=44,
            height=22,
        )
        self.plus_btn.pack(side="right")

        self.minus_btn = PillButton(
            self._bot,
            theme,
            text="−1k",
            command=lambda: self.on_step_limit(self.current_category, -1000 * 100),
            variant="secondary",
            width=44,
            height=22,
        )
        self.minus_btn.pack(side="right", padx=(0, 6))

    def update_slot(
        self, status: BudgetStatus, currency_symbol: str, animate: bool = True
    ) -> None:
        t = self.theme.tokens
        self.current_category = status.category
        self.current_limit_paise = status.limit_paise
        icon = status.category[:2].upper()
        self.title_lbl.configure(text=f"{icon}  {status.category}")
        self.spent_lbl.configure(
            text=(
                f"Spent {format_indian_currency(status.spent_paise, currency_symbol)} "
                f"of {format_indian_currency(status.limit_paise, currency_symbol)}"
            )
        )

        col_map = {
            "ok": t["success"],
            "warning": t["warning"],
            "danger": t["danger"],
        }
        status_text_map = {
            "ok": "On Track",
            "warning": "Near Limit",
            "danger": "Over Budget",
        }
        col = col_map.get(status.level, t["success"])
        self.pct_lbl.configure(
            text=f"{status.percent_used:.0f}% · {status_text_map[status.level]}",
            fg=col,
        )
        self.progress.set_progress(status.percent_used, status.level, animate=animate)

        if status.remaining_paise >= 0:
            self.rem_lbl.configure(
                text=f"Left: {format_indian_currency(status.remaining_paise, currency_symbol)}",
                fg=t["text_muted"],
            )
        else:
            self.rem_lbl.configure(
                text=f"Over by {format_indian_currency(abs(status.remaining_paise), currency_symbol)}",
                fg=t["danger"],
            )

    def apply_slot_theme(self) -> None:
        self.apply_theme()
        t = self.theme.tokens
        self._top.configure(bg=t["surface"])
        self._mid.configure(bg=t["surface"])
        self._bot.configure(bg=t["surface"])
        self.title_lbl.configure(bg=t["surface"], fg=t["text_primary"])
        self.edit_lbl.configure(bg=t["surface"], fg=t["primary"])
        self.del_lbl.configure(bg=t["surface"], fg=t["danger"])
        self.spent_lbl.configure(bg=t["surface"], fg=t["text_secondary"])
        self.pct_lbl.configure(bg=t["surface"])
        self.rem_lbl.configure(bg=t["surface"])
        self.minus_btn.apply_theme()
        self.plus_btn.apply_theme()
        self.progress.apply_theme()


class BudgetView(ttk.Frame):
    """
    Monthly category budget planner with animated progress bars, tactile ±1k steppers,
    and status colour thresholds.
    """

    MAX_SLOTS = 12

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

        self._cat_var = tk.StringVar(value=EXPENSE_CATEGORIES[0])
        self._custom_cat_var = tk.StringVar()
        self._limit_var = tk.StringVar()
        self._error_var = tk.StringVar()
        self._slots: list[BudgetCardSlot] = []
        self._labels: list[tk.Label] = []

    def build(self) -> None:
        if self.is_built:
            return
        self.is_built = True
        t = self.theme.tokens

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ---- Top Card: Set / Edit Budget Form (Auto-height so fields & button are NEVER clipped) ----
        self._form_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="budget_form",
            height=115,
            auto_height=True,
        )
        self._form_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        hdr = tk.Frame(self._form_card.body, bg=t["surface"])
        hdr.pack(fill="x", pady=(0, 8))
        self._hdr = hdr
        self._title_lbl = tk.Label(
            hdr,
            text="Configure Monthly Category Budget",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["subtitle"],
        )
        self._title_lbl.pack(side="left")

        self._err_lbl = tk.Label(
            hdr,
            textvariable=self._error_var,
            bg=t["surface"],
            fg=t["danger"],
            font=self.theme.fonts["caption_bold"],
        )
        self._err_lbl.pack(side="right")

        row = tk.Frame(self._form_card.body, bg=t["surface"])
        row.pack(fill="x")
        self._row = row
        for c in range(4):
            row.columnconfigure(c, weight=1 if c < 3 else 0)

        # Category Selector
        c_box = tk.Frame(row, bg=t["surface"])
        c_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._c_box = c_box
        lbl_cat = tk.Label(
            c_box,
            text="Category",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_cat.pack(anchor="w")
        self._labels.append(lbl_cat)
        self._cat_combo = ttk.Combobox(
            c_box,
            textvariable=self._cat_var,
            state="readonly",
            style="Fin.TCombobox",
        )
        self._cat_combo.pack(fill="x", pady=(4, 0))

        # Optional Custom Category
        cust_box = tk.Frame(row, bg=t["surface"])
        cust_box.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self._cust_box = cust_box
        lbl_cust = tk.Label(
            cust_box,
            text="Or New Custom Category",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_cust.pack(anchor="w")
        self._labels.append(lbl_cust)
        ttk.Entry(
            cust_box, textvariable=self._custom_cat_var, style="Fin.TEntry"
        ).pack(fill="x", pady=(4, 0))

        # Monthly Limit
        lim_box = tk.Frame(row, bg=t["surface"])
        lim_box.grid(row=0, column=2, sticky="ew", padx=(0, 12))
        self._lim_box = lim_box
        lbl_lim = tk.Label(
            lim_box,
            text="Monthly Limit (Rs.) *",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        lbl_lim.pack(anchor="w")
        self._labels.append(lbl_lim)
        self._limit_entry = ttk.Entry(
            lim_box, textvariable=self._limit_var, style="Fin.TEntry"
        )
        self._limit_entry.pack(fill="x", pady=(4, 0))
        self._limit_entry.bind("<Return>", lambda _e: self._save_budget())

        btn_box = tk.Frame(row, bg=t["surface"])
        btn_box.grid(row=0, column=3, sticky="s")
        self._btn_box = btn_box
        self._save_btn = PillButton(
            btn_box,
            self.theme,
            text="Save Budget",
            command=self._save_budget,
            variant="primary",
            width=120,
            height=34,
        )
        self._save_btn.pack(pady=(16, 0))

        # ---- Grid Container for Pre-allocated Budget Cards ----
        self._grid_frame = ttk.Frame(self, style="App.TFrame")
        self._grid_frame.grid(row=1, column=0, sticky="nsew")
        for col in range(3):
            self._grid_frame.columnconfigure(col, weight=1, uniform="bcard")

        for i in range(self.MAX_SLOTS):
            slot = BudgetCardSlot(
                self._grid_frame,
                self.theme,
                self.animator,
                slot_idx=i,
                on_edit=self._load_for_edit,
                on_delete=self._delete_budget,
                on_step_limit=self._step_budget_limit,
            )
            self._slots.append(slot)

        responsive_grid(row,[c_box,cust_box,lim_box,btn_box],min_width=190,max_columns=4)
        flow_row(self._hdr)
        self._err_lbl.configure(wraplength=350,justify='left')
        self._error_var.trace_add('write',lambda *_:self.after_idle(self._hdr._reflow))
        self._grid_frame.bind('<Configure>',lambda e:self._layout_slots(),add='+')
        self._empty_lbl = ttk.Label(
            self._grid_frame,
            text="No monthly budgets configured yet. Use the form above to set category spending limits.",
            style="Muted.TLabel",
        )

    def _step_budget_limit(self, category: str, delta_paise: int) -> None:
        """Tactile ±1k stepper callback to adjust category limit in-place."""
        if not category:
            return
        current_paise = 0
        for b in self.store.get_budgets():
            if b.category == category:
                current_paise = b.monthly_limit_paise
                break
        next_paise = max(500 * 100, current_paise + delta_paise)
        self.store.set_budget(category, next_paise)
        sym = self.store.currency_symbol
        self.toast.show(
            f"Adjusted {category} cap to {format_indian_currency(next_paise, sym)}",
            level="info",
            duration_ms=2500,
        )

    def _save_budget(self) -> None:
        self._error_var.set("")
        custom = self._custom_cat_var.get().strip()
        category = custom if custom else self._cat_var.get().strip()
        if not category:
            self._error_var.set("⚠ Please select or enter a category.")
            return

        raw_limit = self._limit_var.get().strip().replace(",", "")
        if raw_limit == "0":
            paise = 0
        else:
            try:
                paise = rupees_to_paise(raw_limit)
            except ValueError as exc:
                self._error_var.set(f"⚠ {exc}")
                return

        self.store.set_budget(category, paise)
        self._custom_cat_var.set("")
        self._limit_var.set("")
        self.toast.show(
            f"Saved budget for {category}: {format_indian_currency(paise, self.store.currency_symbol)}",
            level="success",
        )

    def _load_for_edit(self, category: str) -> None:
        if not category:
            return
        self._cat_var.set(category)
        for b in self.store.get_budgets():
            if b.category == category:
                self._limit_var.set(f"{b.monthly_limit_paise // 100}")
                break
        self._limit_entry.focus_set()

    def _delete_budget(self, category: str) -> None:
        if self.store.delete_budget(category):
            self.toast.show(
                f"Removed budget limit for {category} (transactions kept intact).",
                level="info",
            )

    def refresh(self, animate: bool = True) -> None:
        if not self.is_built:
            self.build()
        self.is_dirty = False

        cats = self.store.get_categories(TransactionType.EXPENSE)
        self._cat_combo["values"] = cats
        if self._cat_var.get() not in cats and cats:
            self._cat_var.set(cats[0])

        statuses = self.store.get_budget_statuses()
        sym = self.store.currency_symbol

        if not statuses:
            for slot in self._slots:
                slot.grid_forget()
            self._empty_lbl.grid(row=0, column=0, columnspan=3, pady=32)
            return

        self._empty_lbl.grid_forget()
        while len(self._slots)<len(statuses):
            self._slots.append(BudgetCardSlot(self._grid_frame,self.theme,self.animator,len(self._slots),self._load_for_edit,self._delete_budget,self._step_budget_limit))
        for idx, slot in enumerate(self._slots):
            if idx < len(statuses):
                r, c = divmod(idx, 3)
                pad_r = 12 if c < 2 else 0
                slot.grid(row=r, column=c, sticky="ew", padx=(0, pad_r), pady=(0, 12))
                slot.update_slot(statuses[idx], sym, animate=animate)
            else:
                slot.grid_forget()
        self.after_idle(self._layout_slots)

    def _layout_slots(self):
        width=self._grid_frame.winfo_width()
        cols=max(1,min(3,(width+12)//342))
        for c in range(3):self._grid_frame.columnconfigure(c,weight=1 if c<cols else 0,uniform='bcard' if c<cols else '')
        visible=[s for s in self._slots if s.current_category and s.winfo_manager()]
        for i,slot in enumerate(visible):
            slot.grid(row=i//cols,column=i%cols,sticky='ew',padx=(0,12 if i%cols<cols-1 else 0),pady=(0,12))

    def apply_theme(self) -> None:
        if not self.is_built:
            return
        t = self.theme.tokens
        self._form_card.apply_theme()
        for f in (
            self._hdr,
            self._row,
            self._c_box,
            self._cust_box,
            self._lim_box,
            self._btn_box,
        ):
            f.configure(bg=t["surface"])
        self._title_lbl.configure(bg=t["surface"], fg=t["text_primary"])
        self._err_lbl.configure(bg=t["surface"], fg=t["danger"])
        for lbl in self._labels:
            lbl.configure(bg=t["surface"], fg=t["text_muted"])
        self._save_btn.apply_theme()
        for slot in self._slots:
            slot.apply_slot_theme()
        self.refresh(animate=False)
