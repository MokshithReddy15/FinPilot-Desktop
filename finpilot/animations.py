"""
finpilot/animations.py
Non-blocking 60 FPS time-based animation engine built strictly on root.after().
Includes ease_out_cubic, hex colour interpolation (lerp_color), and tracked timer IDs
so pending animations cancel cleanly on view switch, debounce reset, or shutdown
(Section 5 Rules 1, 5, 10).
"""

from __future__ import annotations

import time
import tkinter as tk
from typing import Callable


def ease_out_cubic(t: float) -> float:
    """Smooth deceleration easing function for t in [0.0, 1.0]."""
    clamped = max(0.0, min(1.0, t))
    return 1.0 - pow(1.0 - clamped, 3)


def parse_hex_color(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' into an (r, g, b) integer tuple."""
    cleaned = hex_str.lstrip("#")
    if len(cleaned) != 6:
        return (99, 102, 241)
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
    )


def lerp_color(hex_start: str, hex_end: str, t: float) -> str:
    """
    Linearly interpolate between two '#RRGGBB' colours for t in [0.0, 1.0].
    Enables smooth 60 FPS hover border glows and surface colour transitions on tk.Canvas.
    """
    clamped = max(0.0, min(1.0, t))
    r1, g1, b1 = parse_hex_color(hex_start)
    r2, g2, b2 = parse_hex_color(hex_end)
    r = int(round(r1 + (r2 - r1) * clamped))
    g = int(round(g1 + (g2 - g1) * clamped))
    b = int(round(b1 + (b2 - b1) * clamped))
    return f"#{r:02x}{g:02x}{b:02x}"


class Animator:
    """
    Central scheduler for root.after() animations and debounced callbacks.
    Prevents orphan timers and TclError exceptions when views hide or app exits.
    """

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._active_jobs: dict[str, str] = {}

    def cancel(self, key: str) -> None:
        """Cancel a specific named after() job if currently scheduled."""
        after_id = self._active_jobs.pop(key, None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass

    def cancel_prefix(self, prefix: str) -> None:
        """Cancel all active jobs whose key starts with `prefix` (e.g. when hiding a view)."""
        keys = [k for k in self._active_jobs if k.startswith(prefix)]
        for k in keys:
            self.cancel(k)

    def cancel_all(self) -> None:
        """Cancel every pending after() job before application shutdown."""
        for key in list(self._active_jobs.keys()):
            self.cancel(key)

    def debounce(self, key: str, delay_ms: int, callback: Callable[[], None]) -> None:
        """
        Schedule `callback` to run after `delay_ms`, resetting the timer if called again
        with the same `key` before expiry (Section 5 Rule 5: 150ms search, 100ms resize).
        """
        self.cancel(key)

        def _fire() -> None:
            self._active_jobs.pop(key, None)
            callback()

        try:
            self._active_jobs[key] = self.root.after(delay_ms, _fire)
        except tk.TclError:
            pass

    def animate_value(
        self,
        key: str,
        start_val: float,
        end_val: float,
        duration_ms: int,
        on_update: Callable[[float], None],
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """
        Time-based value interpolation at ~60 FPS (16 ms interval) using ease_out_cubic.
        Progress is computed from elapsed wall-clock time (time.perf_counter), ensuring
        consistent animation duration regardless of machine speed (Section 5 Rule 1).
        """
        self.cancel(key)
        if duration_ms <= 0 or abs(end_val - start_val) < 1e-6:
            on_update(end_val)
            if on_complete:
                on_complete()
            return

        start_time = time.perf_counter()
        duration_sec = duration_ms / 1000.0

        def _step() -> None:
            self._active_jobs.pop(key, None)
            elapsed = time.perf_counter() - start_time
            raw_t = min(1.0, elapsed / duration_sec)
            eased_t = ease_out_cubic(raw_t)
            current = start_val + (end_val - start_val) * eased_t
            on_update(current)

            if raw_t < 1.0:
                try:
                    self._active_jobs[key] = self.root.after(16, _step)
                except tk.TclError:
                    pass
            else:
                on_update(end_val)
                if on_complete:
                    on_complete()

        _step()

    def animate_color(
        self,
        key: str,
        start_hex: str,
        end_hex: str,
        duration_ms: int,
        on_update: Callable[[str], None],
    ) -> None:
        """Smoothly transition a Canvas item or widget colour from start_hex to end_hex."""
        if start_hex.lower() == end_hex.lower() or duration_ms <= 0:
            on_update(end_hex)
            return

        self.animate_value(
            key=key,
            start_val=0.0,
            end_val=1.0,
            duration_ms=duration_ms,
            on_update=lambda t: on_update(lerp_color(start_hex, end_hex, t)),
        )
