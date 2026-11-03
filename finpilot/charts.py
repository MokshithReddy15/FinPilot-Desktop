"""
finpilot/charts.py
DPI-proof, responsive 60 FPS vector chart engines for FinPilot Desktop:
- CategoryDonutChart: Interactive exploding Donut chart + clickable legend + dynamic centre lens
- GroupedBarChart: 6-month Income vs Expenses paired bar chart with hover HUD + click-to-focus month
- CumulativeSpendLineChart: 31-day cumulative spend area/spline chart with magnetic day crosshair scrubber
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Any, Callable

# Keep matplotlib imported for environment compatibility while using DPI-proof native Canvas rendering
from layout import RetainedCanvas

from animations import Animator
from models import format_indian_currency
from theme import CHART_PALETTE, ThemeManager
import hashlib

def category_color(category):
    """Stable across ordering, filters, and app restarts."""
    index=int.from_bytes(hashlib.sha256(str(category).casefold().encode()).digest()[:4], "big")
    return CHART_PALETTE[index % len(CHART_PALETTE)]



def _compact_inr(paise: int, sym: str = "Rs. ") -> str:
    """Format paise into compact axis labels (e.g., Rs. 1.4L, Rs. 45k, Rs. 0)."""
    rupees = abs(paise) / 100.0
    if rupees >= 100_000:
        return f"{sym}{rupees / 100_000:.1f}L"
    if rupees >= 1_000:
        return f"{sym}{rupees / 1_000:.0f}k"
    return f"{sym}{rupees:.0f}"


def _annular_sector_points(
    cx: float,
    cy: float,
    r_inner: float,
    r_outer: float,
    start_deg: float,
    end_deg: float,
    steps: int = 36,
) -> list[float]:
    """Generate polygon vertices for a smooth donut wedge between start_deg and end_deg."""
    pts: list[float] = []
    for i in range(steps + 1):
        ang = math.radians(start_deg + (end_deg - start_deg) * (i / steps))
        pts.append(cx + r_outer * math.cos(ang))
        pts.append(cy - r_outer * math.sin(ang))
    for i in range(steps, -1, -1):
        ang = math.radians(start_deg + (end_deg - start_deg) * (i / steps))
        pts.append(cx + r_inner * math.cos(ang))
        pts.append(cy - r_inner * math.sin(ang))
    return pts


class BaseChartCard(RetainedCanvas):
    """
    Responsive vector chart surface backed by tk.Canvas.
    Automatically adapts to any container width/height on <Configure> with zero DPI distortion.
    Exposes `self.widget = self` so view layout code (`chart.widget.pack(...)`) works seamlessly.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        chart_id: str,
        figsize: tuple[float, float] = (5.0, 2.3),
    ) -> None:
        t = theme.tokens
        init_h = max(165, int(figsize[1] * 82))
        super().__init__(
            parent,
            bg=t["surface"],
            highlightthickness=0,
            bd=0,
            height=init_h,
            cursor="hand2",
        )
        self.parent = parent
        self.theme = theme
        self.animator = animator
        self.chart_id = chart_id
        self.widget = self


class CategoryDonutChart(BaseChartCard):
    """
    Interactive Expenses-by-Category Donut Chart:
    - Hovering or clicking any wedge OR legend item expands that slice outward (+8px offset + larger radius)
      and updates the Centre Lens text (`Category · Amount · % share`) at 60 FPS.
    - Never clips or magnifies on Windows High-DPI screens.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        chart_id: str,
        figsize: tuple[float, float] = (4.6, 2.2),
    ) -> None:
        super().__init__(parent, theme, animator, chart_id, figsize)
        self._items: list[dict[str, Any]] = []
        self._total_paise: int = 0
        self._currency_symbol: str = "Rs. "
        self._focused_idx: int | None = None
        self._locked_idx: int | None = None
        self._anim_progress: float = 1.0
        self._slice_angles: list[tuple[float, float]] = []
        self._legend_Hitboxes: list[tuple[float, float, float, float, int]] = []

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)

    def reset_lens(self) -> None:
        self._focused_idx = None
        self._locked_idx = None
        self._redraw()

    def _hit_test(self, x: float, y: float) -> int | None:
        # Check legend hitboxes first
        for x1, y1, x2, y2, idx in self._legend_Hitboxes:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx

        # Check donut ring geometry
        w = max(220, self.winfo_width())
        h = max(160, self.winfo_height())
        donut_cx = w * 0.30
        donut_cy = h * 0.50
        radius = min(w * 0.25, h * 0.42)
        r_inner = radius * 0.58

        dx = x - donut_cx
        dy = donut_cy - y
        dist = math.hypot(dx, dy)
        if dist < r_inner * 0.85 or dist > radius * 1.18:
            return None

        ang_deg = math.degrees(math.atan2(dy, dx))
        # Normalize to clockwise angle starting from 90 deg (top)
        cw_from_top = (90.0 - ang_deg) % 360.0
        for idx, (cw_start, cw_end) in enumerate(self._slice_angles):
            if cw_start <= cw_from_top <= cw_end:
                return idx
        return None

    def _on_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._locked_idx is not None:
            return
        hit = self._hit_test(event.x, event.y)
        if hit != self._focused_idx:
            self._focused_idx = hit
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._locked_idx is None and self._focused_idx is not None:
            self._focused_idx = None
            self._redraw()

    def _on_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        hit = self._hit_test(event.x, event.y)
        if hit is not None and hit == self._locked_idx:
            self._locked_idx = None
            self._focused_idx = None
        else:
            self._locked_idx = hit
            self._focused_idx = hit
        self._redraw()

    def update_chart(
        self,
        breakdown: list[dict[str, Any]],
        currency_symbol: str = "Rs. ",
        animate: bool = True,
    ) -> None:
        self._currency_symbol = currency_symbol
        self._focused_idx = None
        self._locked_idx = None

        if not breakdown:
            self._items = []
            self._total_paise = 0
            self._redraw()
            return

        top_items = [dict(x) for x in breakdown[:6]]
        if len(breakdown) > 6:
            other_paise = sum(item["amount_paise"] for item in breakdown[6:])
            top_items.append({"category": "Other+", "amount_paise": other_paise})

        self._items = top_items
        self._total_paise = sum(item["amount_paise"] for item in top_items)

        if not animate:
            self._anim_progress = 1.0
            self._redraw()
            return

        def _step(val: float) -> None:
            self._anim_progress = val
            self._redraw()

        self.animator.animate_value(
            key=f"donut_anim_{self.chart_id}",
            start_val=0.2,
            end_val=1.0,
            duration_ms=300,
            on_update=_step,
        )

    def _redraw(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t["surface"])
        self.begin_frame()
        self._slice_angles.clear()
        self._legend_Hitboxes.clear()

        w = max(240, self.winfo_width())
        h = max(165, self.winfo_height())

        if not self._items or self._total_paise <= 0:
            self.create_text(
                w / 2,
                h / 2,
                text="No expenses in selected month",
                fill=t["text_muted"],
                font=self.theme.fonts["body"],
            )
            return

        donut_cx = w * 0.29
        donut_cy = h * 0.50
        base_r_out = max(46.0, min(w * 0.24, h * 0.42))
        base_r_in = base_r_out * 0.62

        active_idx = (
            self._locked_idx if self._locked_idx is not None else self._focused_idx
        )

        cw_cursor = 0.0
        total_sweep = 360.0 * self._anim_progress

        for idx, item in enumerate(self._items):
            share = item["amount_paise"] / self._total_paise
            sweep = max(2.0, share * total_sweep)
            cw_start = cw_cursor
            cw_end = cw_cursor + sweep
            cw_cursor = cw_end
            self._slice_angles.append((cw_start, cw_end))

            # Convert clockwise-from-top to standard math degrees (CCW from East)
            deg_start = 90.0 - cw_start
            deg_end = 90.0 - cw_end
            mid_rad = math.radians((deg_start + deg_end) / 2.0)

            is_foc = idx == active_idx
            offset = 7.0 if is_foc else 0.0
            r_out = (base_r_out + 5.0) if is_foc else base_r_out
            r_in = base_r_in

            scx = donut_cx + offset * math.cos(mid_rad)
            scy = donut_cy - offset * math.sin(mid_rad)
            color = category_color(item["category"])

            pts = _annular_sector_points(
                scx, scy, r_in, r_out, deg_start, deg_end, steps=28
            )
            self.create_polygon(
                *pts,
                fill=color,
                outline=t["surface"],
                width=2,
                smooth=False,
            )

        # Dynamic Centre Lens text inside the donut cutout
        if active_idx is not None and 0 <= active_idx < len(self._items):
            foc_item = self._items[active_idx]
            pct = (foc_item["amount_paise"] / self._total_paise) * 100.0
            lens_title = str(foc_item["category"])
            lens_val = format_indian_currency(
                foc_item["amount_paise"], self._currency_symbol
            )
            lens_sub = f"{pct:.1f}% share"
            sub_col = category_color(foc_item["category"])
        else:
            lens_title = "Total Spent"
            lens_val = format_indian_currency(
                self._total_paise, self._currency_symbol
            )
            lens_sub = "Hover slice"
            sub_col = t["primary"]

        self.create_text(
            donut_cx,
            donut_cy - 15,
            text=lens_title,
            fill=t["text_muted"],
            font=self.theme.fonts["caption_bold"],
        )
        self.create_text(
            donut_cx,
            donut_cy + 1,
            text=lens_val,
            fill=t["text_primary"],
            font=self.theme.fonts["body_bold"],
        )
        self.create_text(
            donut_cx,
            donut_cy + 17,
            text=lens_sub,
            fill=sub_col,
            font=self.theme.fonts["caption_bold"],
        )

        # Interactive Legend Table on the right side
        leg_x1 = w * 0.56
        leg_x2 = w - 10.0
        n_items = len(self._items)
        row_h = min(25.0, max(19.0, (h - 20.0) / max(1, n_items)))
        start_y = (h - row_h * n_items) / 2.0

        for idx, item in enumerate(self._items):
            y1 = start_y + idx * row_h
            y2 = y1 + row_h - 2
            cy = (y1 + y2) / 2.0
            is_foc = idx == active_idx
            color = category_color(item["category"])
            pct = (item["amount_paise"] / self._total_paise) * 100.0

            if is_foc:
                self.create_rectangle(
                    leg_x1 - 6,
                    y1,
                    leg_x2,
                    y2,
                    fill=t["surface_raised"],
                    outline=color,
                    width=1,
                )

            self.create_oval(
                leg_x1,
                cy - 4,
                leg_x1 + 8,
                cy + 4,
                fill=color,
                outline="",
            )
            self.create_text(
                leg_x1 + 14,
                cy,
                anchor="w",
                text=str(item["category"]),
                fill=t["text_primary"] if is_foc else t["text_secondary"],
                font=self.theme.fonts["caption_bold" if is_foc else "caption"],
            )
            amt_txt = f"{_compact_inr(item['amount_paise'], self._currency_symbol)} ({pct:.0f}%)"
            self.create_text(
                leg_x2 - 4,
                cy,
                anchor="e",
                text=amt_txt,
                fill=color if is_foc else t["text_muted"],
                font=self.theme.fonts["caption_bold" if is_foc else "caption"],
            )
            self._legend_Hitboxes.append((leg_x1 - 6, y1, leg_x2, y2, idx))


class GroupedBarChart(BaseChartCard):
    """
    Responsive 6-month Income vs Expenses grouped bar chart with:
    - 60 FPS ease-out-cubic entry animation
    - Hover highlight column & live tooltip readout
    - Click-any-month bar pair to focus that month across the app
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        chart_id: str,
        figsize: tuple[float, float] = (4.6, 2.2),
        on_select_month: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, theme, animator, chart_id, figsize)
        self.on_select_month = on_select_month
        self._series: list[dict[str, Any]] = []
        self._currency_symbol: str = "Rs. "
        self._anim_progress: float = 1.0
        self._hovered_idx: int | None = None

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)

    def _idx_at_x(self, x: float) -> int | None:
        n = len(self._series)
        if n == 0:
            return None
        w = max(240, self.winfo_width())
        pad_left = 54.0
        pad_right = 16.0
        plot_w = max(1.0, w - pad_left - pad_right)
        col_w = plot_w / n
        idx = int((x - pad_left) // col_w)
        if 0 <= idx < n:
            return idx
        return None

    def _on_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = self._idx_at_x(event.x)
        if idx != self._hovered_idx:
            self._hovered_idx = idx
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._hovered_idx is not None:
            self._hovered_idx = None
            self._redraw()

    def _on_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = self._idx_at_x(event.x)
        if (
            idx is not None
            and 0 <= idx < len(self._series)
            and self.on_select_month is not None
        ):
            self.on_select_month(self._series[idx]["month"])

    def update_chart(
        self,
        series: list[dict[str, Any]],
        currency_symbol: str = "Rs. ",
        animate: bool = True,
    ) -> None:
        self._series = list(series)
        self._currency_symbol = currency_symbol

        if not animate:
            self._anim_progress = 1.0
            self._redraw()
            return

        def _step(val: float) -> None:
            self._anim_progress = val
            self._redraw()

        self.animator.animate_value(
            key=f"bar_anim_{self.chart_id}",
            start_val=0.15,
            end_val=1.0,
            duration_ms=280,
            on_update=_step,
        )

    def _redraw(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t["surface"])
        self.begin_frame()

        w = max(240, self.winfo_width())
        h = max(165, self.winfo_height())
        n = len(self._series)

        if n == 0 or not any(
            item["income_paise"] > 0 or item["expense_paise"] > 0
            for item in self._series
        ):
            self.create_text(
                w / 2,
                h / 2,
                text="No monthly data available",
                fill=t["text_muted"],
                font=self.theme.fonts["body"],
            )
            return

        pad_left = 56.0
        pad_right = 14.0
        pad_top = 24.0
        pad_bot = 26.0
        plot_w = max(60.0, w - pad_left - pad_right)
        plot_h = max(40.0, h - pad_top - pad_bot)

        max_paise = max(
            1,
            max(
                max(item["income_paise"], item["expense_paise"])
                for item in self._series
            ),
        )
        y_ceil = int(max_paise * 1.12)

        # Horizontal grid lines & Y-axis labels
        for step_ratio in (0.0, 0.33, 0.66, 1.0):
            y = h - pad_bot - step_ratio * plot_h
            val_paise = int(round(step_ratio * y_ceil))
            self.create_line(
                pad_left,
                y,
                w - pad_right,
                y,
                fill=t["border_subtle"],
                dash=(3, 3) if step_ratio > 0 else (),
            )
            self.create_text(
                pad_left - 6,
                y,
                anchor="e",
                text=_compact_inr(val_paise, self._currency_symbol),
                fill=t["text_muted"],
                font=self.theme.fonts["caption"],
            )

        # Legend / Hovered month pill at top-right
        if self._hovered_idx is not None and 0 <= self._hovered_idx < n:
            hov = self._series[self._hovered_idx]
            hud_txt = (
                f"{hov['label']} · In: {format_indian_currency(hov['income_paise'], self._currency_symbol)} · "
                f"Out: {format_indian_currency(hov['expense_paise'], self._currency_symbol)}"
            )
            self.create_text(
                w - pad_right,
                10,
                anchor="e",
                text=hud_txt,
                fill=t["primary"],
                font=self.theme.fonts["caption_bold"],
            )
        else:
            # Compact legend
            self.create_rectangle(
                w - 145, 6, w - 137, 14, fill=t["success"], outline=""
            )
            self.create_text(
                w - 132,
                10,
                anchor="w",
                text="Income",
                fill=t["text_secondary"],
                font=self.theme.fonts["caption"],
            )
            self.create_rectangle(
                w - 75, 6, w - 67, 14, fill=t["danger"], outline=""
            )
            self.create_text(
                w - 62,
                10,
                anchor="w",
                text="Expenses",
                fill=t["text_secondary"],
                font=self.theme.fonts["caption"],
            )

        col_w = plot_w / n
        bar_w = max(6.0, min(16.0, col_w * 0.28))
        base_y = h - pad_bot

        for idx, item in enumerate(self._series):
            cx = pad_left + col_w * (idx + 0.5)
            is_hov = idx == self._hovered_idx

            if is_hov:
                self.create_rectangle(
                    pad_left + idx * col_w + 2,
                    pad_top,
                    pad_left + (idx + 1) * col_w - 2,
                    base_y,
                    fill=t["surface_raised"],
                    outline="",
                )

            inc_h = (
                (item["income_paise"] / y_ceil) * plot_h * self._anim_progress
            )
            exp_h = (
                (item["expense_paise"] / y_ceil) * plot_h * self._anim_progress
            )

            self.create_rectangle(
                cx - bar_w - 2,
                base_y - inc_h,
                cx - 2,
                base_y,
                fill=t["success"],
                outline="",
            )
            self.create_rectangle(
                cx + 2,
                base_y - exp_h,
                cx + bar_w + 2,
                base_y,
                fill=t["danger"],
                outline="",
            )

            self.create_text(
                cx,
                h - 11,
                text=item["label"],
                fill=t["primary"] if is_hov else t["text_muted"],
                font=self.theme.fonts["caption_bold" if is_hov else "caption"],
            )


class CumulativeSpendLineChart(BaseChartCard):
    """
    Daily cumulative spending trend line with a magnetic hover crosshair scrubber.
    Moving the pointer across the chart snaps a vertical line + glowing marker to the
    nearest day and invokes `on_hover_day(day_dict)`.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        chart_id: str,
        figsize: tuple[float, float] = (9.2, 1.85),
        on_hover_day: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent, theme, animator, chart_id, figsize)
        self.on_hover_day = on_hover_day
        self._daily_series: list[dict[str, Any]] = []
        self._currency_symbol: str = "Rs. "
        self._scrub_idx: int | None = None

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def _on_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        n = len(self._daily_series)
        if n == 0:
            return
        w = max(300, self.winfo_width())
        pad_left = 60.0
        pad_right = 18.0
        plot_w = max(1.0, w - pad_left - pad_right)
        ratio = (event.x - pad_left) / plot_w
        idx = int(round(ratio * max(1, n - 1)))
        idx = max(0, min(n - 1, idx))
        if idx != self._scrub_idx:
            self._scrub_idx = idx
            if self.on_hover_day:
                self.on_hover_day(self._daily_series[idx])
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._scrub_idx is not None:
            self._scrub_idx = None
            if self.on_hover_day and self._daily_series:
                self.on_hover_day(self._daily_series[-1])
            self._redraw()

    def update_chart(
        self,
        daily_series: list[dict[str, Any]],
        currency_symbol: str = "Rs. ",
    ) -> None:
        self._daily_series = list(daily_series)
        self._currency_symbol = currency_symbol
        self._scrub_idx = None
        if self.on_hover_day and self._daily_series:
            self.on_hover_day(self._daily_series[-1])
        self._redraw()

    def _redraw(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t["surface"])
        self.begin_frame()

        w = max(300, self.winfo_width())
        h = max(145, self.winfo_height())
        n = len(self._daily_series)

        max_cum = max(
            (item["cumulative_paise"] for item in self._daily_series),
            default=0,
        )
        if n == 0 or max_cum <= 0:
            self.create_text(
                w / 2,
                h / 2,
                text="No daily spending activity for this month",
                fill=t["text_muted"],
                font=self.theme.fonts["body"],
            )
            return

        pad_left = 60.0
        pad_right = 18.0
        pad_top = 16.0
        pad_bot = 26.0
        plot_w = max(60.0, w - pad_left - pad_right)
        plot_h = max(36.0, h - pad_top - pad_bot)
        base_y = h - pad_bot
        y_ceil = int(max_cum * 1.12)

        # Horizontal reference grid lines & Y-axis labels
        for step_ratio in (0.0, 0.5, 1.0):
            y = base_y - step_ratio * plot_h
            val_paise = int(round(step_ratio * y_ceil))
            self.create_line(
                pad_left,
                y,
                w - pad_right,
                y,
                fill=t["border_subtle"],
                dash=(3, 3) if step_ratio > 0 else (),
            )
            self.create_text(
                pad_left - 6,
                y,
                anchor="e",
                text=_compact_inr(val_paise, self._currency_symbol),
                fill=t["text_muted"],
                font=self.theme.fonts["caption"],
            )

        line_pts: list[float] = []
        xy_list: list[tuple[float, float, dict[str, Any]]] = []

        for idx, item in enumerate(self._daily_series):
            x = (
                pad_left + (idx / (n - 1)) * plot_w
                if n > 1
                else pad_left + plot_w / 2
            )
            y = base_y - (item["cumulative_paise"] / y_ceil) * plot_h
            line_pts.extend([x, y])
            xy_list.append((x, y, item))

        # Shaded area under cumulative curve
        if len(line_pts) >= 4:
            poly_pts = [
                xy_list[0][0],
                base_y,
                *line_pts,
                xy_list[-1][0],
                base_y,
            ]
            self.create_polygon(
                *poly_pts,
                fill=t["surface_raised"],
                outline="",
            )
            self.create_line(
                *line_pts,
                fill=t["primary"],
                width=2.5,
            )

        # X-axis day ticks (Day 1, 5, 10, 15, 20, 25, last)
        for idx, (x, _y, item) in enumerate(xy_list):
            d = item["day"]
            if d == 1 or d % 5 == 0 or idx == n - 1:
                self.create_text(
                    x,
                    h - 11,
                    text=f"D{d:02d}",
                    fill=t["text_muted"],
                    font=self.theme.fonts["caption"],
                )

        # Magnetic Scrubber Crosshair + Glowing Node
        focus_idx = (
            self._scrub_idx if self._scrub_idx is not None else (n - 1)
        )
        fx, fy, fitem = xy_list[focus_idx]
        self.create_line(
            fx,
            pad_top,
            fx,
            base_y,
            fill=t["primary"],
            dash=(3, 3),
            width=1.5,
        )
        self.create_oval(
            fx - 5,
            fy - 5,
            fx + 5,
            fy + 5,
            fill=t["primary"],
            outline="#FFFFFF",
            width=2,
        )
