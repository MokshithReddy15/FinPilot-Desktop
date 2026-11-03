"""
finpilot/widgets.py
DPI-proof, fluid, interactive Canvas-backed widgets for FinPilot Desktop:
- RoundedCard: Auto-expanding rounded surface (never clips inner content) with 60 FPS hover border glow
- StatCard: KPI card with animated count-up numbers, bbox-stacked layout, 2px hover lift, and radial arc ring
- VaultSimulatorCard: Primary Net Balance card with a live draggable Savings Rate Simulator slider
- SegmentedPillToggle: Auto-measured sliding pill segmented control on tk.Canvas (never overlaps text)
- InteractiveCashflowHorizon: Dual-stream Catmull-Rom spline + paired bars + interactive month nodes
- AnimatedProgressBar: Smooth Canvas progress bar with dynamic threshold colour
- SidebarButton: Left navigation item with animated active indicator bar and hover state
- PillButton: Auto-measured clickable action button that never clips label text
- ToastNotification: Floating bottom-right notification with 5s timer and Undo action button
"""

from __future__ import annotations

import tkinter as tk
from layout import RetainedCanvas
from typing import Any, Callable

from animations import Animator
from models import format_indian_currency
from theme import ThemeManager
from glass import photo as glass_photo


def _rounded_rect_coords(
    x1: float, y1: float, x2: float, y2: float, r: float
) -> list[float]:
    """Return polygon coordinates for a smooth rounded rectangle on a tk.Canvas."""
    r = max(2.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + r, y1,
        x1 + r, y1,
        x2 - r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1 + r,
        x1, y1,
    ]


class RoundedCard(tk.Canvas):
    """
    Canvas-drawn rounded container with subtle 1px border, hover border illumination,
    and an inner frame that automatically expands the card height so child widgets are NEVER clipped.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator | None = None,
        card_key: str = "rcard",
        radius: int = 16,
        padding: int = 20,
        surface_key: str = "surface",
        height: int | None = None,
        auto_height: bool = True,
    ) -> None:
        t = theme.tokens
        self._min_height = height or 90
        super().__init__(
            parent,
            bg=t["background"],
            highlightthickness=0,
            bd=0,
            height=self._min_height,
            width=1,
        )
        self.theme = theme
        self.animator = animator
        self.card_key = card_key
        self.radius = radius
        self.padding = padding
        self.surface_key = surface_key
        self.auto_height = auto_height
        self._current_border = t["border"]
        self._glass_signature=None;self._glass_job=None;self._glass_photo=None
        self._glass_item=self.create_image(0,0,anchor='nw')

        self._bg_poly = self.create_polygon(
            _rounded_rect_coords(1, 1, 100, self._min_height - 2, self.radius),
            smooth=True,
            fill=t[self.surface_key],
            outline=t["border"],
            width=1,
            tags=("card_bg",),
        )

        self.body = tk.Frame(self, bg=t[self.surface_key], bd=0, highlightthickness=0)
        self._body_win = self.create_window(
            self.padding,
            self.padding,
            anchor="nw",
            window=self.body,
        )
        self.bind("<Configure>", self._on_configure)
        self.body.bind("<Configure>", self._on_body_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind('<Destroy>',self._glass_destroy,add='+')

    def _glass_destroy(self,event):
        if event.widget is self and self._glass_job:
            self.after_cancel(self._glass_job);self._glass_job=None

    def _paint_glass(self):
        self._glass_job=None
        w,h=self.winfo_width(),self.winfo_height()
        signature=(w,h,self.theme.mode)
        if w<40 or h<40 or signature==self._glass_signature:return
        self._glass_signature=signature
        self._glass_photo=glass_photo(self,w,h,self.theme.tokens,self.theme.mode)
        if self._glass_photo:
            self.itemconfigure(self._glass_item,image=self._glass_photo)
            self.tag_raise(self._glass_item,self._bg_poly)
            self.tag_raise(self._body_win)

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        target = t["primary"]
        if self.animator:
            self.animator.animate_color(
                f"rc_bdr_{id(self)}",
                self._current_border,
                target,
                160,
                self._set_border_color,
            )
        else:
            self._set_border_color(target)

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        target = t["border"]
        if self.animator:
            self.animator.animate_color(
                f"rc_bdr_{id(self)}",
                self._current_border,
                target,
                200,
                self._set_border_color,
            )
        else:
            self._set_border_color(target)

    def _set_border_color(self, hex_col: str) -> None:
        self._current_border = hex_col
        self.itemconfig(self._bg_poly, outline=hex_col)

    def _on_body_configure(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        """Grow Canvas height if inner body frame requires more vertical space."""
        if not self.auto_height:
            return
        req_h = self.body.winfo_reqheight() + self.padding * 2
        target_h = max(self._min_height, req_h)
        cur_h = self.winfo_height()
        if abs(target_h - cur_h) > 2 and cur_h <= req_h:
            self.configure(height=target_h)

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._glass_job:self.after_cancel(self._glass_job)
        self._glass_job=self.after(80,self._paint_glass)
        w = max(40, event.width)
        req_h = self.body.winfo_reqheight() + self.padding * 2
        h = max(40, event.height)
        if self.auto_height and req_h > h:
            h = req_h
            self.configure(height=h)

        self.coords(
            self._bg_poly,
            *_rounded_rect_coords(1, 1, w - 2, h - 2, self.radius),
        )
        self.coords(self._body_win, self.padding, self.padding)
        self.itemconfig(
            self._body_win,
            width=max(10, w - self.padding * 2),
            height=max(10, h - self.padding * 2),
        )

    def apply_theme(self) -> None:
        """Update card colours in-place without recreating widgets (Rule 2)."""
        t = self.theme.tokens
        self._current_border = t["border"]
        self.configure(bg=t["background"])
        self.itemconfig(
            self._bg_poly,
            fill=t[self.surface_key],
            outline=t["border"],
        )
        self.body.configure(bg=t[self.surface_key])
        self._glass_signature=None
        if self._glass_job:self.after_cancel(self._glass_job)
        self._glass_job=self.after_idle(self._paint_glass)


class SegmentedPillToggle(tk.Canvas):
    """
    Framer-Motion-style sliding pill segmented control drawn on a tk.Canvas.
    Automatically measures every option's rendered text width via bbox() so labels NEVER overlap.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        toggle_id: str,
        options: list[tuple[str, str]],  # [(key, label), ...]
        on_change: Callable[[str], None],
        width: int = 200,
        height: int = 30,
        active_color_key: str = "primary",
        parent_bg_key: str = "background",
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t[parent_bg_key],
            highlightthickness=0,
            bd=0,
            width=width,
            height=height,
            cursor="hand2",
        )
        self.theme = theme
        self.animator = animator
        self.toggle_id = toggle_id
        self.options = options
        self.on_change = on_change
        self.active_color_key = active_color_key
        self.parent_bg_key = parent_bg_key

        self._selected_idx = 0
        self._pill_x = 3.0

        self._track_poly = self.create_polygon(
            _rounded_rect_coords(1, 1, width - 2, height - 2, 8),
            smooth=True,
            fill=t["surface_raised"],
            outline=t["border_subtle"],
            width=1,
        )
        self._pill_poly = self.create_polygon(
            _rounded_rect_coords(3, 3, 60, height - 3, 6),
            smooth=True,
            fill=t[self.active_color_key],
            outline="",
        )

        self._text_items: list[int] = []
        max_tw = 40
        max_th = 16
        for idx, (_key, label) in enumerate(options):
            item = self.create_text(
                0,
                0,
                text=label,
                fill="#FFFFFF" if idx == 0 else t["text_secondary"],
                font=theme.fonts["caption_bold"],
            )
            self._text_items.append(item)
            bbox = self.bbox(item)
            if bbox:
                max_tw = max(max_tw, bbox[2] - bbox[0])
                max_th = max(max_th, bbox[3] - bbox[1])

        n_opts = max(1, len(options))
        auto_seg_w = float(max_tw + 24)
        req_seg_w = float((width - 6) / n_opts)
        self._seg_w = max(auto_seg_w, req_seg_w)
        self.total_w = int(self._seg_w * n_opts + 6)
        self.total_h = max(height, max_th + 14)

        self.configure(width=self.total_w, height=self.total_h)
        self._reposition_elements()
        self.bind("<ButtonRelease-1>", self._on_click)

        self.configure(takefocus=1)
        self.bind('<FocusIn>',lambda e:self.itemconfigure(self._track_poly,outline=self.theme.tokens['primary'],width=2))
        self.bind('<FocusOut>',lambda e:self.itemconfigure(self._track_poly,outline=self.theme.tokens['border_subtle'],width=1))
        self.bind('<Left>',lambda e:self._keyboard_select(-1))
        self.bind('<Right>',lambda e:self._keyboard_select(1))

    def _keyboard_select(self,direction):
        idx=max(0,min(len(self.options)-1,self._selected_idx+direction))
        self.set_selected(self.options[idx][0],notify=True)
        return 'break'

    def _reposition_elements(self) -> None:
        self.coords(
            self._track_poly,
            *_rounded_rect_coords(1, 1, self.total_w - 2, self.total_h - 2, 8),
        )
        self._pill_x = 3.0 + self._selected_idx * self._seg_w
        self.coords(
            self._pill_poly,
            *_rounded_rect_coords(
                self._pill_x,
                3,
                self._pill_x + self._seg_w,
                self.total_h - 3,
                6,
            ),
        )
        for idx, item_id in enumerate(self._text_items):
            cx = 3.0 + self._seg_w * (idx + 0.5)
            self.coords(item_id, cx, self.total_h / 2.0)

    def _on_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = int((event.x - 3) // self._seg_w)
        idx = max(0, min(len(self.options) - 1, idx))
        if idx != self._selected_idx:
            self.set_selected(self.options[idx][0], notify=True)

    def set_selected(
        self, key: str, notify: bool = False, animate: bool = True
    ) -> None:
        target_idx = 0
        for i, (k, _) in enumerate(self.options):
            if k == key:
                target_idx = i
                break

        self._selected_idx = target_idx
        target_x = 3.0 + target_idx * self._seg_w
        t = self.theme.tokens

        for i, item_id in enumerate(self._text_items):
            self.itemconfig(
                item_id,
                fill="#FFFFFF" if i == target_idx else t["text_secondary"],
            )

        if not animate:
            self._pill_x = target_x
            self.coords(
                self._pill_poly,
                *_rounded_rect_coords(
                    target_x, 3, target_x + self._seg_w, self.total_h - 3, 6
                ),
            )
        else:
            start_x = self._pill_x

            def _step(val: float) -> None:
                self._pill_x = val
                self.coords(
                    self._pill_poly,
                    *_rounded_rect_coords(
                        val, 3, val + self._seg_w, self.total_h - 3, 6
                    ),
                )

            self.animator.animate_value(
                key=f"seg_pill_{self.toggle_id}",
                start_val=start_x,
                end_val=target_x,
                duration_ms=200,
                on_update=_step,
            )

        if notify:
            self.on_change(key)

    def set_active_color_key(self, color_key: str) -> None:
        self.active_color_key = color_key
        self.itemconfig(self._pill_poly, fill=self.theme.tokens[color_key])

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t[self.parent_bg_key])
        self.itemconfig(
            self._track_poly,
            fill=t["surface_raised"],
            outline=t["border_subtle"],
        )
        self.itemconfig(self._pill_poly, fill=t[self.active_color_key])
        for i, item_id in enumerate(self._text_items):
            self.itemconfig(
                item_id,
                fill="#FFFFFF" if i == self._selected_idx else t["text_secondary"],
            )


class VaultSimulatorCard(tk.Canvas):
    """
    Primary Tactile Hero Vault Card for Dashboard:
    - Animated count-up Net Balance display
    - Interactive draggable Savings Rate Simulator slider (10%..75%) drawn on the Canvas
    - Real-time projected annual compounding readout (Rs. X/yr)
    - Uses bbox-based vertical layout so text rows NEVER collide on any resolution or DPI
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t["background"],
            highlightthickness=0,
            bd=0,
            height=138,
            cursor="hand2",
        )
        self.theme = theme
        self.animator = animator
        self._current_balance = 0.0
        self._monthly_income_paise = 143500 * 100
        self._actual_savings_rate = 48.5
        self._sim_target_pct = 45
        self._currency_symbol = "Rs. "
        self._border_col = t["primary"]
        self._slider_y = 98.0

        self._bg_poly = self.create_polygon(
            _rounded_rect_coords(1, 2, 320, 136, 12),
            smooth=True,
            fill=t["surface"],
            outline=t["primary"],
            width=1,
        )
        self._accent_strip = self.create_rectangle(
            16, 2, 86, 4, fill=t["primary"], outline=""
        )

        self._title_item = self.create_text(
            16,
            13,
            anchor="nw",
            text="TOTAL NET BALANCE",
            fill=t["primary"],
            font=theme.fonts["caption_bold"],
        )
        self._meta_item = self.create_text(
            300,
            13,
            anchor="ne",
            text="",
            fill=t["text_muted"],
            font=theme.fonts["caption"],
        )
        self._val_item = self.create_text(
            16,
            34,
            anchor="nw",
            text="Rs. 0",
            fill=t["text_primary"],
            font=theme.fonts["display"],
        )

        # Interactive Slider Elements
        self._sim_label_item = self.create_text(
            16,
            72,
            anchor="nw",
            text="Savings Simulator: 45%",
            fill=t["text_secondary"],
            font=theme.fonts["caption_bold"],
        )
        self._sim_proj_item = self.create_text(
            300,
            72,
            anchor="ne",
            text="Rs. 0/yr",
            fill=t["success"],
            font=theme.fonts["caption_bold"],
        )

        self._slider_track = self.create_rectangle(
            16, 96, 300, 100, fill=t["surface_raised"], outline=""
        )
        self._slider_fill = self.create_rectangle(
            16, 96, 160, 100, fill=t["primary"], outline=""
        )
        self._slider_thumb = self.create_oval(
            154, 92, 166, 104, fill="#FFFFFF", outline=t["primary"], width=2
        )

        self._footer_item = self.create_text(
            16,
            110,
            anchor="nw",
            text="Drag slider to simulate annual savings velocity",
            fill=t["text_muted"],
            font=theme.fonts["caption"],
        )

        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_slider_drag)
        self.bind("<B1-Motion>", self._on_slider_drag)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        self.animator.animate_color(
            "vault_bdr",
            self._border_col,
            t["primary_hover"],
            150,
            self._update_border,
        )

    def _on_leave(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        self.animator.animate_color(
            "vault_bdr",
            self._border_col,
            t["primary"],
            180,
            self._update_border,
        )

    def _update_border(self, col: str) -> None:
        self._border_col = col
        self.itemconfig(self._bg_poly, outline=col)

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        self._relayout(event.width, event.height)

    def _relayout(self, width: int | None = None, height: int | None = None) -> None:
        w = max(180, width or self.winfo_width())
        pad_x = 16.0

        # Stack rows vertically using actual rendered bounding boxes so nothing ever overlaps
        self.coords(self._title_item, pad_x, 12)
        self.coords(self._meta_item, w - pad_x, 12)
        title_bbox = self.bbox(self._title_item)
        val_y = (title_bbox[3] + 5) if title_bbox else 32
        self.coords(self._val_item, pad_x, val_y)

        val_bbox = self.bbox(self._val_item)
        sim_y = (val_bbox[3] + 8) if val_bbox else 68
        self.coords(self._sim_label_item, pad_x, sim_y)
        self.coords(self._sim_proj_item, w - pad_x, sim_y)

        sim_bbox = self.bbox(self._sim_label_item)
        self._slider_y = float((sim_bbox[3] + 9) if sim_bbox else 94)

        x1 = pad_x
        x2 = max(x1 + 60.0, float(w) - pad_x)
        ratio = max(0.0, min(1.0, (self._sim_target_pct - 10.0) / 65.0))
        cx = x1 + ratio * (x2 - x1)

        sy = self._slider_y
        self.coords(self._slider_track, x1, sy, x2, sy + 5)
        self.coords(self._slider_fill, x1, sy, cx, sy + 5)
        self.coords(self._slider_thumb, cx - 6, sy - 4, cx + 6, sy + 9)

        foot_y = sy + 13
        self.coords(self._footer_item, pad_x, foot_y)
        foot_bbox = self.bbox(self._footer_item)
        req_h = int((foot_bbox[3] + 12) if foot_bbox else 138)
        h = max(req_h, height or self.winfo_height(), 138)
        if abs(self.winfo_height() - h) > 2 and self.winfo_height() < req_h:
            self.configure(height=h)

        self.coords(self._bg_poly, *_rounded_rect_coords(1, 2, w - 2, h - 2, 12))
        self.coords(self._accent_strip, pad_x, 2, min(w - pad_x, 88), 4)

        monthly_target = int(
            round((self._monthly_income_paise * self._sim_target_pct) / 100.0)
        )
        annual_target = monthly_target * 12
        self.itemconfig(
            self._sim_label_item,
            text=f"Simulator: {self._sim_target_pct}%",
        )
        self.itemconfig(
            self._sim_proj_item,
            text=f"{format_indian_currency(annual_target, self._currency_symbol)}/yr",
        )
        self.itemconfig(
            self._footer_item,
            text=(
                f"Actual: {self._actual_savings_rate:.1f}% · "
                f"Target: {format_indian_currency(monthly_target, self._currency_symbol)}/mo"
            ),
        )

    def _on_slider_drag(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if event.y < self._slider_y - 24:
            return
        w = max(180, self.winfo_width())
        x1 = 16.0
        x2 = max(x1 + 60.0, float(w - 16))
        ratio = (event.x - x1) / (x2 - x1)
        ratio = max(0.0, min(1.0, ratio))
        self._sim_target_pct = int(round(10 + ratio * 65))
        self._relayout(w)

    def update_vault(
        self,
        balance_paise: int,
        monthly_income_paise: int,
        actual_savings_rate: float,
        record_count: int,
        currency_symbol: str,
        scope_title: str = "TOTAL NET BALANCE",
        animate: bool = True,
    ) -> None:
        self._monthly_income_paise = max(0, monthly_income_paise)
        self._actual_savings_rate = actual_savings_rate
        self._currency_symbol = currency_symbol
        self.itemconfig(self._title_item, text=scope_title)
        self.itemconfig(self._meta_item, text=f"{record_count} entries")
        self._relayout()

        target = float(balance_paise)
        if not animate:
            self._current_balance = target
            self.itemconfig(
                self._val_item,
                text=format_indian_currency(int(round(target)), currency_symbol),
            )
            self._relayout()
            return

        start = self._current_balance

        def _step(val: float) -> None:
            self._current_balance = val
            self.itemconfig(
                self._val_item,
                text=format_indian_currency(int(round(val)), currency_symbol),
            )

        self.animator.animate_value(
            key="vault_balance_countup",
            start_val=start,
            end_val=target,
            duration_ms=420,
            on_update=_step,
        )

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self._border_col = t["primary"]
        self.configure(bg=t["background"])
        self.itemconfig(self._bg_poly, fill=t["surface"], outline=t["primary"])
        self.itemconfig(self._accent_strip, fill=t["primary"])
        self.itemconfig(self._title_item, fill=t["primary"])
        self.itemconfig(self._meta_item, fill=t["text_muted"])
        self.itemconfig(self._val_item, fill=t["text_primary"])
        self.itemconfig(self._sim_label_item, fill=t["text_secondary"])
        self.itemconfig(self._sim_proj_item, fill=t["success"])
        self.itemconfig(self._slider_track, fill=t["surface_raised"])
        self.itemconfig(self._slider_fill, fill=t["primary"])
        self.itemconfig(self._slider_thumb, outline=t["primary"])
        self.itemconfig(self._footer_item, fill=t["text_muted"])


class StatCard(tk.Canvas):
    """
    Kinetic KPI stat card drawn on a single Canvas with:
    - Animated ease-out-cubic count-up numbers
    - Optional animated SVG-style radial progress ring (show_radial=True) positioned cleanly below the badge
    - Bbox-driven vertical stacking so text rows never overlap
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        card_id: str,
        label: str,
        accent_key: str = "primary",
        show_radial: bool = False,
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t["background"],
            highlightthickness=0,
            bd=0,
            height=138,
            cursor="hand2",
        )
        self.theme = theme
        self.animator = animator
        self.card_id = card_id
        self.accent_key = accent_key
        self.show_radial = show_radial
        self._current_numeric: float = 0.0
        self._current_border = t["border"]

        self._bg_poly = self.create_polygon(
            _rounded_rect_coords(1, 3, 220, 136, 12),
            smooth=True,
            fill=t["surface"],
            outline=t["border"],
            width=1,
        )
        self._accent_bar = self.create_rectangle(
            16, 3, 66, 5, fill=t[self.accent_key], outline=""
        )
        self._label_item = self.create_text(
            16,
            14,
            anchor="nw",
            text=label,
            fill=t["text_muted"],
            font=theme.fonts["caption_bold"],
        )
        self._badge_item = self.create_text(
            200,
            14,
            anchor="ne",
            text="",
            fill=t[self.accent_key],
            font=theme.fonts["caption_bold"],
        )
        self._value_item = self.create_text(
            16,
            42,
            anchor="nw",
            text="Rs. 0",
            fill=t[self.accent_key]
            if accent_key in ("success", "danger")
            else t["text_primary"],
            font=theme.fonts["kpi"],
        )
        self._sub_item = self.create_text(
            16,
            96,
            anchor="nw",
            text="",
            fill=t["text_secondary"],
            font=theme.fonts["caption"],
        )

        # Optional Radial Ring positioned below the top-right badge so it never overlaps
        self._ring_track = self.create_oval(
            160,
            44,
            196,
            80,
            outline=t["surface_raised"] if show_radial else "",
            width=4 if show_radial else 0,
        )
        self._ring_arc = self.create_arc(
            160,
            44,
            196,
            80,
            start=90,
            extent=0,
            style="arc",
            outline=t[self.accent_key] if show_radial else "",
            width=4 if show_radial else 0,
        )

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        w = max(80, self.winfo_width())
        h = max(80, self.winfo_height())
        self.coords(self._bg_poly, *_rounded_rect_coords(1, 1, w - 2, h - 4, 12))
        self.animator.animate_color(
            f"sc_bdr_{self.card_id}",
            self._current_border,
            t[self.accent_key],
            160,
            self._set_border,
        )

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        t = self.theme.tokens
        w = max(80, self.winfo_width())
        h = max(80, self.winfo_height())
        self.coords(self._bg_poly, *_rounded_rect_coords(1, 3, w - 2, h - 2, 12))
        self.animator.animate_color(
            f"sc_bdr_{self.card_id}",
            self._current_border,
            t["border"],
            200,
            self._set_border,
        )

    def _set_border(self, col: str) -> None:
        self._current_border = col
        self.itemconfig(self._bg_poly, outline=col)

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        w = max(80, event.width)
        h = max(130, event.height)
        pad_x = 16
        self.coords(self._bg_poly, *_rounded_rect_coords(1, 3, w - 2, h - 2, 12))
        self.coords(self._accent_bar, pad_x, 3, min(w - pad_x, 72), 5)
        self.coords(self._label_item, pad_x, 14)
        self.coords(self._badge_item, w - pad_x, 14)

        lbl_bbox = self.bbox(self._label_item)
        val_y = (lbl_bbox[3] + 12) if lbl_bbox else 42
        self.coords(self._value_item, pad_x, val_y)

        val_bbox = self.bbox(self._value_item)
        sub_y = max((val_bbox[3] + 16) if val_bbox else 92, h - 32)
        self.coords(self._sub_item, pad_x, sub_y)

        if self.show_radial:
            # Place radial ring below the top-right badge so it never collides with badge text
            r_size = 36
            rx2 = w - pad_x
            rx1 = rx2 - r_size
            ry1 = val_y + 2
            ry2 = ry1 + r_size
            self.coords(self._ring_track, rx1, ry1, rx2, ry2)
            self.coords(self._ring_arc, rx1, ry1, rx2, ry2)

    def set_value(
        self,
        target_value: float,
        formatter: Callable[[float], str],
        subtitle: str = "",
        badge_text: str = "",
        badge_color_key: str | None = None,
        animate: bool = True,
    ) -> None:
        """Animate from current numeric value to target_value using ease-out-cubic."""
        t = self.theme.tokens
        self.itemconfig(self._sub_item, text=subtitle)
        self.itemconfig(
            self._badge_item,
            text=badge_text,
            fill=t[badge_color_key or self.accent_key],
        )

        if not animate:
            self._current_numeric = target_value
            self.itemconfig(self._value_item, text=formatter(target_value))
            if self.show_radial:
                pct = max(0.0, min(100.0, target_value))
                self.itemconfig(self._ring_arc, extent=-3.6 * pct)
            return

        start_val = self._current_numeric

        def _update(val: float) -> None:
            self._current_numeric = val
            self.itemconfig(self._value_item, text=formatter(val))
            if self.show_radial:
                pct = max(0.0, min(100.0, val))
                self.itemconfig(self._ring_arc, extent=-3.6 * pct)

        self.animator.animate_value(
            key=f"stat_{self.card_id}",
            start_val=start_val,
            end_val=target_value,
            duration_ms=420,
            on_update=_update,
        )

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self._current_border = t["border"]
        self.configure(bg=t["background"])
        self.itemconfig(self._bg_poly, fill=t["surface"], outline=t["border"])
        self.itemconfig(self._accent_bar, fill=t[self.accent_key])
        self.itemconfig(self._label_item, fill=t["text_muted"])
        self.itemconfig(
            self._value_item,
            fill=t[self.accent_key]
            if self.accent_key in ("success", "danger")
            else t["text_primary"],
        )
        self.itemconfig(self._sub_item, fill=t["text_secondary"])
        if self.show_radial:
            self.itemconfig(self._ring_track, outline=t["surface_raised"])
            self.itemconfig(self._ring_arc, outline=t[self.accent_key])


class InteractiveCashflowHorizon(RetainedCanvas):
    """
    Interactive 6-Month Cashflow Horizon drawn on a tk.Canvas:
    - Smooth Catmull-Rom spline curves (create_line(..., smooth=True)) for Income & Expenses
    - Paired tactile bar columns + glowing nodes
    - Hovering over any month draws a vertical laser crosshair and updates on_inspect_month
    - Clicking any month node calls on_select_month to time-travel across the app
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        on_inspect_month: Callable[[dict[str, Any]], None],
        on_select_month: Callable[[str], None],
        height: int = 190,
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t["surface"],
            highlightthickness=0,
            bd=0,
            height=height,
            cursor="hand2",
        )
        self.theme = theme
        self.animator = animator
        self.on_inspect_month = on_inspect_month
        self.on_select_month = on_select_month
        self._series: list[dict[str, Any]] = []
        self._hovered_idx: int | None = None
        self._active_month: str = ""
        self._anim_progress: float = 1.0

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)

    def set_series(
        self,
        series: list[dict[str, Any]],
        active_month: str,
        animate: bool = True,
    ) -> None:
        self._series = list(series)
        self._active_month = active_month
        if self._series:
            self.on_inspect_month(self._series[-1])

        if not animate:
            self._anim_progress = 1.0
            self._redraw()
            return

        def _step(val: float) -> None:
            self._anim_progress = val
            self._redraw()

        self.animator.animate_value(
            key="horizon_spline_entry",
            start_val=0.15,
            end_val=1.0,
            duration_ms=320,
            on_update=_step,
        )

    def _idx_at_x(self, x: float) -> int | None:
        n = len(self._series)
        if n == 0:
            return None
        w = max(200, self.winfo_width())
        pad_x = 62.0
        span = max(1.0, w - pad_x - 24)
        step = span / max(1, n - 1)
        idx = int(round((x - pad_x) / step))
        return max(0, min(n - 1, idx))

    def _on_motion(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = self._idx_at_x(event.x)
        if idx is not None and idx != self._hovered_idx:
            self._hovered_idx = idx
            self.on_inspect_month(self._series[idx])
            self._redraw()

    def _on_leave(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        if self._hovered_idx is not None:
            self._hovered_idx = None
            if self._series:
                self.on_inspect_month(self._series[-1])
            self._redraw()

    def _on_click(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        idx = self._idx_at_x(event.x)
        if idx is not None and idx < len(self._series):
            m = self._series[idx]["month"]
            self.on_select_month(m)

    def _redraw(self) -> None:
        from animations import lerp_color
        self.begin_frame()
        t = self.theme.tokens
        w,h = max(220,self.winfo_width()),max(130,self.winfo_height())
        left,right,top,bottom = 62,24,24,h-30
        n = len(self._series)
        if not n:
            self.create_text(w/2,h/2,text='Add transactions to see your cashflow',
                fill=t['text_muted'],font=self.theme.fonts['caption'])
            return
        maximum=max(100,max(max(i['income_paise'],i['expense_paise']) for i in self._series))*1.12
        symbol=getattr(self,'currency_symbol','₹')
        def short(value):
            value=value/100
            if value>=100000:return f'{symbol}{value/100000:.1f}L'
            if value>=1000:return f'{symbol}{value/1000:.0f}k'
            return f'{symbol}{value:.0f}'
        for fraction in (0,.25,.5,.75,1):
            y=bottom-fraction*(bottom-top)
            self.create_line(left,y,w-right,y,fill=t['border_subtle'],dash=(2,6))
            self.create_text(left-10,y,text=short(maximum*fraction),anchor='e',
                fill=t['text_muted'],font=self.theme.fonts['caption'])
        nodes=[]
        for idx,item in enumerate(self._series):
            x=left+idx*(w-left-right)/max(1,n-1) if n>1 else (left+w-right)/2
            iy=bottom-item['income_paise']/maximum*(bottom-top)*self._anim_progress
            ey=bottom-item['expense_paise']/maximum*(bottom-top)*self._anim_progress
            nodes.append((x,iy,ey,item))
        for col,key in ((1,'success'),(2,'danger')):
            coords=[v for node in nodes for v in (node[0],node[col])]
            if n>1:
                self.create_polygon(nodes[0][0],bottom,*coords,nodes[-1][0],bottom,
                    fill=lerp_color(t['surface'],t[key],.07),outline='')
        for col,key in ((1,'success'),(2,'danger')):
            coords=[v for node in nodes for v in (node[0],node[col])]
            if n>1:self.create_line(*coords,fill=t[key],width=2.2,joinstyle='round')
        for idx,(x,iy,ey,item) in enumerate(nodes):
            active=item['month']==self._active_month
            focused=idx==self._hovered_idx
            if focused:self.create_line(x,top,x,bottom,fill=t['text_muted'],dash=(3,4))
            for y,key in ((iy,'success'),(ey,'danger')):
                radius=4 if focused else 2.5
                self.create_oval(x-radius,y-radius,x+radius,y+radius,
                    fill=t[key],outline=t['surface'],width=1.5)
            self.create_text(x,h-11,text=item['label'],fill=t['primary'] if active else t['text_muted'],
                font=self.theme.fonts['caption_bold' if active else 'caption'])
        if self._hovered_idx is not None and self._hovered_idx<n:
            x,iy,ey,item=nodes[self._hovered_idx]
            tooltip_width=min(230,w-20)
            tx=max(10,min(w-tooltip_width-10,x+12))
            ty=top+6
            label=(f"{item['label']}\n"
                   f"Income   {format_indian_currency(item['income_paise'],symbol)}\n"
                   f"Expenses   {format_indian_currency(item['expense_paise'],symbol)}\n"
                   f"Net   {format_indian_currency(item['income_paise']-item['expense_paise'],symbol,signed=True)}")
            text_id=self.create_text(tx+10,ty+8,text=label,anchor='nw',width=tooltip_width-20,
                fill=t['text_primary'],font=self.theme.fonts['caption'],tags=('cashflow_tooltip',))
            box=self.bbox(text_id)
            self.create_polygon(*_rounded_rect_coords(tx,ty,max(tx+tooltip_width,box[2]+10),box[3]+8,9),
                smooth=True,fill=t['surface_raised'],outline=t['border'],tags=('cashflow_tooltip_bg',))
            self.tag_raise(text_id)

    def apply_theme(self) -> None:
        self.configure(bg=self.theme.tokens["surface"])
        self._redraw()


class AnimatedProgressBar(tk.Canvas):
    """
    Smooth Canvas progress bar that animates width changes via coords() and
    changes colour based on budget usage (<70% green, 70-99% amber, 100%+ red).
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        animator: Animator,
        bar_id: str,
        height: int = 10,
        surface_bg_key: str = "surface",
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t[surface_bg_key],
            highlightthickness=0,
            bd=0,
            height=height,
        )
        self.theme = theme
        self.animator = animator
        self.bar_id = bar_id
        self.bar_height = height
        self.surface_bg_key = surface_bg_key
        self._current_pct: float = 0.0
        self._target_pct: float = 0.0
        self._level: str = "ok"

        self._track_rect = self.create_rectangle(
            0, 0, 200, height, fill=t["surface_raised"], outline="", width=0
        )
        self._fill_rect = self.create_rectangle(
            0, 0, 0, height, fill=t["success"], outline="", width=0
        )
        self.bind("<Configure>", self._on_configure)

    def _color_for_level(self, level: str) -> str:
        t = self.theme.tokens
        if level == "danger":
            return t["danger"]
        if level == "warning":
            return t["warning"]
        return t["success"]

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        w = max(20, event.width)
        self.coords(self._track_rect, 0, 0, w, self.bar_height)
        fill_w = max(0.0, min(1.0, self._current_pct / 100.0)) * w
        self.coords(self._fill_rect, 0, 0, fill_w, self.bar_height)

    def set_progress(
        self, percent: float, level: str = "ok", animate: bool = True
    ) -> None:
        """Animate bar fill to `percent` (0..100) and apply status colour."""
        self._target_pct = max(0.0, min(100.0, percent))
        self._level = level
        self.itemconfig(self._fill_rect, fill=self._color_for_level(level))

        if not animate:
            self._current_pct = self._target_pct
            w = max(20, self.winfo_width())
            self.coords(
                self._fill_rect,
                0,
                0,
                (self._current_pct / 100.0) * w,
                self.bar_height,
            )
            return

        start = self._current_pct

        def _step(val: float) -> None:
            self._current_pct = val
            w = max(20, self.winfo_width())
            self.coords(
                self._fill_rect,
                0,
                0,
                (val / 100.0) * w,
                self.bar_height,
            )

        self.animator.animate_value(
            key=f"prog_{self.bar_id}",
            start_val=start,
            end_val=self._target_pct,
            duration_ms=340,
            on_update=_step,
        )

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t[self.surface_bg_key])
        self.itemconfig(self._track_rect, fill=t["surface_raised"])
        self.itemconfig(self._fill_rect, fill=self._color_for_level(self._level))


class PillButton(tk.Canvas):
    """
    Auto-measuring clickable button with hover & focus states and hand2 cursor.
    Measures its rendered text bbox so the label is NEVER clipped on any DPI.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        text: str,
        command: Callable[[], None],
        variant: str = "primary",  # "primary", "secondary", "danger"
        width: int = 90,
        height: int = 32,
        parent_bg_key: str = "surface",
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t[parent_bg_key],
            highlightthickness=0,
            bd=0,
            width=width,
            height=height,
            cursor="hand2",
            takefocus=1,
        )
        self.theme = theme
        self.text = text
        self.command = command
        self.variant = variant
        self._min_width = width
        self._min_height = height
        self.parent_bg_key = parent_bg_key
        self._hovered = False
        self._enabled = True
        self._pressed = False

        fill, fg, outline = self._resolve_colors()
        self._poly = self.create_polygon(
            _rounded_rect_coords(1, 1, width - 2, height - 2, 8),
            smooth=True,
            fill=fill,
            outline=outline,
            width=1,
        )
        self._label = self.create_text(
            width // 2,
            height // 2,
            text=text,
            fill=fg,
            font=theme.fonts["caption_bold" if height <= 28 else "body_bold"],
        )

        self._fit_to_text()

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_click)
        self.bind("<Return>", lambda _e: self.invoke())
        self.bind('<space>',lambda e:self.invoke())
        self.bind('<FocusIn>',lambda e:self._refresh_colors())
        self.bind('<FocusOut>',lambda e:self._refresh_colors())

    def _fit_to_text(self) -> None:
        bbox = self.bbox(self._label)
        if bbox:
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            w = max(self._min_width, tw + 24)
            h = max(self._min_height, th + 12)
            self.btn_width = w
            self.btn_height = h
            self.configure(width=w, height=h)
            self.coords(self._poly, *_rounded_rect_coords(1, 1, w - 2, h - 2, 8))
            self.coords(self._label, w / 2.0, h / 2.0)

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        w = max(24, event.width)
        h = max(20, event.height)
        self.coords(self._poly, *_rounded_rect_coords(1, 1, w - 2, h - 2, 8))
        self.coords(self._label, w / 2.0, h / 2.0)

    def _resolve_colors(self) -> tuple[str, str, str]:
        t = self.theme.tokens
        if not self._enabled:
            return t["surface_raised"], t["text_muted"], t["border_subtle"]
        if self._pressed:
            return t["surface_hover"], t["text_primary"], t["primary"]
        if self.variant == "primary":
            fill = t["primary_hover"] if self._hovered else t["primary"]
            return fill, "#101828", fill
        if self.variant == "danger":
            fill = t["danger"] if self._hovered else t["danger_bg"]
            fg = "#FFFFFF" if self._hovered else t["danger"]
            return fill, fg, t["danger"]
        fill = t["surface_hover"] if self._hovered else t["surface_raised"]
        outline = t["primary"] if self._hovered else t["border_subtle"]
        return fill, t["text_primary"], outline

    def _on_enter(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._hovered = True
        self._refresh_colors()

    def _on_leave(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._hovered = False
        self._refresh_colors()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._pressed = False
        self.configure(cursor="hand2" if enabled else "arrow", takefocus=int(enabled))
        self._refresh_colors()

    def invoke(self):
        if self._enabled:
            self.command()
        return "break"

    def _on_press(self, event):
        if self._enabled:
            self.focus_set()
            self._pressed = True
            self._refresh_colors()

    def _on_click(self, event):
        activate = self._pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._pressed = False
        self._refresh_colors()
        if activate:
            self.invoke()

    def set_text(self, text: str) -> None:
        self.text = text
        self.itemconfig(self._label, text=text)
        self._fit_to_text()

    def _refresh_colors(self) -> None:
        fill, fg, outline = self._resolve_colors()
        focused=self.focus_get() is self
        self.itemconfig(self._poly, fill=fill, outline=self.theme.tokens['text_primary'] if focused else outline,width=2 if focused else 1)
        self.itemconfig(self._label, fill=fg)

    def apply_theme(self) -> None:
        self.configure(bg=self.theme.tokens[self.parent_bg_key])
        self._refresh_colors()


class SidebarButton(tk.Canvas):
    """
    Left sidebar navigation button with icon, label, active indicator bar, and hover effect.
    """

    def __init__(
        self,
        parent: tk.Misc,
        theme: ThemeManager,
        icon: str,
        label: str,
        command: Callable[[], None],
    ) -> None:
        t = theme.tokens
        super().__init__(
            parent,
            bg=t["surface"],
            highlightthickness=0,
            bd=0,
            height=42,
            cursor="hand2",
        )
        self.theme = theme
        self.command = command
        self._active = False
        self._hovered = False

        self._bg_rect = self.create_polygon(
            _rounded_rect_coords(8, 2, 212, 40, 9),
            smooth=True,
            fill=t["surface"],
            outline="",
        )
        self._indicator = self.create_rectangle(
            0, 10, 4, 32, fill=t["surface"], outline=""
        )
        self._icon_item = self.create_text(
            26, 21, text=icon, fill=t["text_muted"], font=theme.fonts["body"]
        )
        self._text_item = self.create_text(
            48,
            21,
            anchor="w",
            text=label,
            fill=t["text_secondary"],
            font=theme.fonts["body_bold"],
        )

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", lambda _e: self.command())
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        w = max(120, event.width)
        self.coords(self._bg_rect, *_rounded_rect_coords(8, 2, w - 8, 40, 9))

    def set_active(self, active: bool) -> None:
        self._active = active
        self.apply_theme()

    def _on_enter(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        self._hovered = True
        self.apply_theme()

    def _on_leave(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        self._hovered = False
        self.apply_theme()

    def apply_theme(self) -> None:
        t = self.theme.tokens
        self.configure(bg=t["surface"])
        if self._active:
            bg = t["surface_raised"]
            fg = t["text_primary"]
            ind = t["primary"]
            outline = t["primary"]
        elif self._hovered:
            bg = t["surface_hover"]
            fg = t["text_primary"]
            ind = t["surface"]
            outline = ""
        else:
            bg = t["surface"]
            fg = t["text_muted"]
            ind = t["surface"]
            outline = ""

        self.itemconfig(self._bg_rect, fill=bg, outline=outline)
        self.itemconfig(self._indicator, fill=ind)
        self.itemconfig(self._icon_item, fill=t["primary"] if self._active else fg)
        self.itemconfig(self._text_item, fill=fg)


class ToastNotification(tk.Frame):
    """
    Non-blocking floating bottom-right toast banner with optional 'Undo' action button.
    Uses Animator.debounce() so it auto-dismisses cleanly after 5 seconds.
    """

    def __init__(
        self, root: tk.Misc, theme: ThemeManager, animator: Animator
    ) -> None:
        t = theme.tokens
        super().__init__(
            root,
            bg=t["surface_raised"],
            highlightbackground=t["primary"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        self.root = root
        self.theme = theme
        self.animator = animator
        self._action_cb: Callable[[], None] | None = None

        self.msg_label = tk.Label(
            self,
            text="",
            bg=t["surface_raised"],
            fg=t["text_primary"],
            font=theme.fonts["body"],
        )
        self.msg_label.pack(side="left", padx=(0, 12))

        self.action_btn = tk.Label(
            self,
            text="",
            bg=t["primary"],
            fg="#FFFFFF",
            font=theme.fonts["caption_bold"],
            padx=10,
            pady=3,
            cursor="hand2",
        )
        self.action_btn.bind("<ButtonRelease-1>", self._on_action)

        self.close_btn = tk.Label(
            self,
            text="✕",
            bg=t["surface_raised"],
            fg=t["text_muted"],
            font=theme.fonts["caption_bold"],
            cursor="hand2",
            padx=4,
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<ButtonRelease-1>", lambda _e: self.hide())

    def show(
        self,
        message: str,
        level: str = "info",
        duration_ms: int = 5000,
        action_label: str | None = None,
        action_callback: Callable[[], None] | None = None,
    ) -> None:
        t = self.theme.tokens
        border_map = {
            "info": t["primary"],
            "success": t["success"],
            "warning": t["warning"],
            "danger": t["danger"],
        }
        accent = border_map.get(level, t["primary"])
        self.configure(bg=t["surface_raised"], highlightbackground=accent)
        self.msg_label.configure(
            text=message, bg=t["surface_raised"], fg=t["text_primary"], wraplength=max(200, min(520, self.root.winfo_width()-180)), justify="left"
        )
        self.close_btn.configure(bg=t["surface_raised"], fg=t["text_muted"])

        self._action_cb = action_callback
        if action_label and action_callback:
            self.action_btn.configure(text=action_label, bg=accent)
            self.action_btn.pack(side="left", padx=(0, 8))
        else:
            self.action_btn.pack_forget()

        self.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        self.lift()
        self.animator.debounce("toast_dismiss", duration_ms, self.hide)

    def _on_action(self, _e: tk.Event) -> None:  # type: ignore[type-arg]
        cb = self._action_cb
        self.hide()
        if cb is not None:
            cb()

    def hide(self) -> None:
        self.animator.cancel("toast_dismiss")
        self.place_forget()
