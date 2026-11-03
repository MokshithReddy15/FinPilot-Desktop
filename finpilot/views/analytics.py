"""
finpilot/views/analytics.py
Screen C: Interactive Analytics & Visual Lens View
- Section 5 Rule 7: Lazy-loaded — Chart surfaces are constructed only the first time
  the user opens the Analytics tab.
- Month selector Combobox + click-bar month switching on GroupedBarChart.
- Interactive Expenses-by-Category Donut Chart (hover/click slice or legend row to expand radius + inspect in centre lens, plus "Reset Lens" button).
- Income vs Expenses by month (Grouped bar chart with hover HUD + click-to-select month).
- Daily Cumulative Spending Trend Line with a magnetic hover crosshair scrubber & live Day HUD readout.
- Computed natural-language insight cards (auto-sized card so text is never clipped).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from animations import Animator
from charts import CategoryDonutChart, CumulativeSpendLineChart, GroupedBarChart
from models import format_indian_currency
from store import DataStore
from theme import ThemeManager
from widgets import PillButton, RoundedCard
from layout import responsive_grid, flow_row


class AnalyticsView(ttk.Frame):
    """
    Visual analytics and computed financial insights view.
    Charts are lazily instantiated on first activation (Rule 7).
    """

    def __init__(
        self,
        parent: tk.Misc,
        store: DataStore,
        theme: ThemeManager,
        animator: Animator,
        on_select_month: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, style="App.TFrame")
        self.store = store
        self.theme = theme
        self.animator = animator
        self.on_select_month = on_select_month
        self.is_built = False
        self.is_dirty = True

        self._month_var = tk.StringVar()
        self._insight_labels: list[tk.Label] = []
        self._cards: list[RoundedCard] = []

    def set_selected_month(self, month: str) -> None:
        self._month_var.set(month)
        if self.is_built:
            self.refresh(animate=True)

    def build(self) -> None:
        """Lazy-build vector charts and insight cards on first tab open."""
        if self.is_built:
            return
        self.is_built = True
        t = self.theme.tokens

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        # ---- Row 0: Month Selector + Computed Insights Strip (Auto-height so never clipped) ----
        top_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="ana_top",
            height=110,
            auto_height=True,
        )
        top_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self._cards.append(top_card)

        ctrl_row = tk.Frame(top_card.body, bg=t["surface"])
        ctrl_row.pack(fill="x", pady=(0, 8))
        self._ctrl_row = ctrl_row

        self._hdr_lbl = tk.Label(
            ctrl_row,
            text="Monthly intelligence",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["subtitle"],
        )
        self._hdr_lbl.pack(side="left")

        self._month_combo = ttk.Combobox(
            ctrl_row,
            textvariable=self._month_var,
            state="readonly",
            style="Fin.TCombobox",
            width=12,
        )
        self._month_combo.pack(side="right")
        self._month_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._on_month_combo_selected()
        )

        self._month_caption = tk.Label(
            ctrl_row,
            text="Analysis Month:",
            bg=t["surface"],
            fg=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        self._month_caption.pack(side="right", padx=(0, 8))

        insights_row = tk.Frame(top_card.body, bg=t["surface"])
        insights_row.pack(fill="x")
        self._insights_row = insights_row
        for i in range(3):
            insights_row.columnconfigure(i, weight=1, uniform="ins")
            lbl = tk.Label(
                insights_row,
                text="",
                bg=t["surface_raised"],
                fg=t["text_primary"],
                font=self.theme.fonts["caption"],
                padx=10,
                pady=8,
                justify="left",
                anchor="w",
                wraplength=310,
            )
            lbl.grid(
                row=0,
                column=i,
                sticky="nsew",
                padx=(0, 10 if i < 2 else 0),
            )
            self._insight_labels.append(lbl)

        # ---- Row 1 Col 0: Interactive Category Donut Chart + Reset Lens ----
        donut_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="ana_donut_card",
            height=330,
            auto_height=False,
        )
        donut_card.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self._cards.append(donut_card)

        donut_hdr = tk.Frame(donut_card.body, bg=t["surface"])
        donut_hdr.pack(fill="x", pady=(0, 4))
        self._donut_hdr = donut_hdr

        self._donut_title = tk.Label(
            donut_hdr,
            text="Where it goes",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
            anchor="w",
        )
        self._donut_title.pack(side="left")

        self._reset_lens_btn = PillButton(
            donut_hdr,
            self.theme,
            text="Reset Lens",
            command=lambda: self._donut_chart.reset_lens(),
            variant="secondary",
            width=82,
            height=24,
        )
        self._reset_lens_btn.pack(side="right")

        self._donut_chart = CategoryDonutChart(
            donut_card.body,
            self.theme,
            self.animator,
            chart_id="ana_donut",
            figsize=(4.6, 2.15),
        )
        self._donut_chart.widget.pack(fill="both", expand=True)

        # ---- Row 1 Col 1: Income vs Expenses Grouped Bar Chart (Click to Switch Month) ----
        bar_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="ana_bar_card",
            height=330,
            auto_height=False,
        )
        bar_card.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        self._cards.append(bar_card)

        self._bar_title = tk.Label(
            bar_card.body,
            text="Income & expenses",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
            anchor="w",
        )
        self._bar_title.pack(fill="x", pady=(0, 4))

        self._bar_chart = GroupedBarChart(
            bar_card.body,
            self.theme,
            self.animator,
            chart_id="ana_bar",
            figsize=(4.6, 2.15),
            on_select_month=self._on_bar_month_clicked,
        )
        self._bar_chart.widget.pack(fill="both", expand=True)

        # ---- Row 2 Col 0..1: Magnetic Daily Cumulative Spend Scrubber ----
        line_card = RoundedCard(
            self,
            self.theme,
            animator=self.animator,
            card_key="ana_line_card",
            height=270,
            auto_height=False,
        )
        line_card.grid(row=2, column=0, columnspan=2, sticky="nsew")
        self._cards.append(line_card)

        line_hdr = tk.Frame(line_card.body, bg=t["surface"])
        line_hdr.pack(fill="x", pady=(0, 4))
        self._line_hdr = line_hdr

        self._line_title = tk.Label(
            line_hdr,
            text="Spending rhythm",
            bg=t["surface"],
            fg=t["text_primary"],
            font=self.theme.fonts["body_bold"],
            anchor="w",
        )
        self._line_title.pack(side="left")

        self._scrub_hud = tk.Label(
            line_hdr,
            text="",
            bg=t["surface_raised"],
            fg=t["primary"],
            font=self.theme.fonts["caption_bold"],
            padx=10,
            pady=2,
        )
        self._scrub_hud.pack(side="right")

        self._line_chart = CumulativeSpendLineChart(
            line_card.body,
            self.theme,
            self.animator,
            chart_id="ana_line",
            figsize=(9.2, 1.85),
            on_hover_day=self._on_scrub_day,
        )
        self._line_chart.widget.pack(fill="both", expand=True)
        flow_row(ctrl_row);flow_row(donut_hdr);flow_row(line_hdr)
        responsive_grid(insights_row, self._insight_labels, min_width=230, max_columns=3)
        for lbl in self._insight_labels:
            lbl.bind('<Configure>',lambda e:e.widget.configure(wraplength=max(80,e.width-24)))
        self._layout_mode=None
        self.bind('<Configure>',self._responsive,add='+')
        self.after_idle(self._responsive)


    def _responsive(self,event=None):
        split=self.winfo_width()>=900
        if self._layout_mode==split:return
        self._layout_mode=split
        for r in range(4):self.rowconfigure(r,weight=0)
        self.columnconfigure(1,weight=1 if split else 0)
        self._cards[1].grid(row=1,column=0,columnspan=1 if split else 2,padx=(0,12 if split else 0),pady=(0,12))
        self._cards[2].grid(row=1 if split else 2,column=1 if split else 0,columnspan=1 if split else 2,padx=0,pady=(0,12))
        self._cards[3].grid(row=2 if split else 3,column=0,columnspan=2)

    def _on_month_combo_selected(self) -> None:
        m = self._month_var.get()
        if self.on_select_month and m:
            self.on_select_month(m)
        self.refresh(animate=True)

    def _on_bar_month_clicked(self, month_key: str) -> None:
        self._month_var.set(month_key)
        if self.on_select_month:
            self.on_select_month(month_key)
        self.refresh(animate=True)

    def _on_scrub_day(self, day_info: dict[str, Any]) -> None:
        sym = self.store.currency_symbol
        day_num = day_info["day"]
        day_spend = format_indian_currency(day_info["daily_paise"], sym)
        cum_spend = format_indian_currency(day_info["cumulative_paise"], sym)
        self._scrub_hud.configure(
            text=f"Day {day_num:02d}  ·  Day Spend: {day_spend}  ·  Cumulative: {cum_spend}"
        )

    def refresh(self, animate: bool = True) -> None:
        """Update existing chart surfaces and insight labels for the selected month."""
        if not self.is_built:
            self.build()
        self.is_dirty = False

        months = self.store.get_available_months()
        self._month_combo["values"] = months
        selected_month = self._month_var.get()
        if not selected_month or selected_month not in months:
            selected_month = self.store.get_latest_month()
            self._month_var.set(selected_month)

        sym = self.store.currency_symbol
        insights = self.store.get_computed_insights(selected_month)
        for idx, lbl in enumerate(self._insight_labels):
            text = (
                insights[idx]
                if idx < len(insights)
                else "Track more categories to unlock deeper comparisons."
            )
            lbl.configure(text=text)

        breakdown = self.store.get_category_breakdown(selected_month)
        self._donut_chart.update_chart(breakdown, sym, animate=animate)

        series = self.store.get_last_n_months_series(6, end_month=selected_month)
        self._bar_chart.update_chart(series, sym, animate=animate)

        daily = self.store.get_daily_cumulative_spend(selected_month)
        self._line_chart.update_chart(daily, sym)

    def apply_theme(self) -> None:
        if not self.is_built:
            return
        t = self.theme.tokens
        for c in self._cards:
            c.apply_theme()
        self._ctrl_row.configure(bg=t["surface"])
        self._insights_row.configure(bg=t["surface"])
        self._donut_hdr.configure(bg=t["surface"])
        self._line_hdr.configure(bg=t["surface"])
        self._hdr_lbl.configure(bg=t["surface"], fg=t["text_primary"])
        self._month_caption.configure(bg=t["surface"], fg=t["text_muted"])
        self._donut_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._reset_lens_btn.apply_theme()
        self._bar_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._line_title.configure(bg=t["surface"], fg=t["text_primary"])
        self._scrub_hud.configure(bg=t["surface_raised"], fg=t["primary"])
        for lbl in self._insight_labels:
            lbl.configure(bg=t["surface_raised"], fg=t["text_primary"])
        self.refresh(animate=False)
