"""Responsive native Tk layout and retained Canvas drawing primitives."""
import tkinter as tk
from tkinter import ttk


class RetainedCanvas(tk.Canvas):
    """Reuse chart primitives between frames instead of deleting the scene."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('width', 1)
        super().__init__(*args, **kwargs)
        self._pool = {}
        self._counts = {}

    def begin_frame(self):
        self.itemconfigure('all', state='hidden')
        self._counts.clear()

    def _create(self, kind, args, kw):
        n = self._counts.get(kind, 0)
        self._counts[kind] = n + 1
        key = kind, n
        if key not in self._pool:
            self._pool[key] = super()._create(kind, args, kw)
        else:
            item = self._pool[key]
            self.coords(item, *args)
            self.itemconfigure(item, **kw)
        item = self._pool[key]
        self.itemconfigure(item, state='normal')
        self.tag_raise(item)
        return item


class ScrollViewport(tk.Frame):
    def __init__(self, parent, theme):
        super().__init__(parent, bg=theme.tokens['background'])
        self.theme = theme
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0,
                                bg=theme.tokens['background'], width=1)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                 style='Fin.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, style='App.TFrame', padding=(24, 8, 24, 28))
        self.body.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.canvas.bind('<Configure>', self._resize)
        self.body.bind('<Configure>', self._region)
        self.canvas.bind_all('<MouseWheel>', self._wheel, add='+')

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def _region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox(self.window))

    def _wheel(self, event):
        widget=event.widget
        while widget is not None and widget is not self:
            widget=getattr(widget,'master',None)
        if widget is None:return
        # Let the table and popup selectors retain their own scrolling.
        if isinstance(event.widget, (ttk.Treeview, ttk.Combobox)):
            return
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')

    def top(self):
        self.canvas.yview_moveto(0)

    def apply_theme(self):
        self.configure(bg=self.theme.tokens['background'])
        self.canvas.configure(bg=self.theme.tokens['background'])


def responsive_grid(frame, children, min_width=220, max_columns=4, gap=12):
    """Arrange existing children using actual container width, never requested width."""
    state = {'cols': None}
    for child in children:
        child.pack_forget()
        child.grid_forget()
    def arrange(event=None):
        width = frame.winfo_width()
        if width < 10:
            return
        cols = max(1, min(max_columns, (width + gap) // (min_width + gap)))
        if cols == state['cols']:
            return
        state['cols'] = cols
        for c in range(max_columns + 2):
            frame.columnconfigure(c, weight=1 if c < cols else 0,
                                  uniform='responsive' if c < cols else '', minsize=0)
        for i, child in enumerate(children):
            child.grid(row=i // cols, column=i % cols, sticky='nsew',
                       padx=(0, gap if i % cols < cols - 1 else 0), pady=(0, gap))
    frame._reflow = arrange
    frame.bind('<Configure>', arrange, add='+')
    frame.after_idle(arrange)
    return arrange


def flow_row(frame, children=None, gap=8):
    """Wrap toolbar controls onto extra rows; retain native keyboard focus."""
    children = children or frame.winfo_children()
    for child in children:
        child.pack_forget()
        child.grid_forget()
    state = {'layout': None}
    def arrange(event=None):
        width = frame.winfo_width()
        if width < 10:
            return
        x = y = row_h = 0
        layout = []
        for child in children:
            w, h = min(width, child.winfo_reqwidth()), child.winfo_reqheight()
            if x and x + w > width:
                x, y, row_h = 0, y + row_h + gap, 0
            layout.append((child, x, y, w, h))
            x += w + gap
            row_h = max(row_h, h)
        sig = [(x,y,w,h) for _,x,y,w,h in layout]
        if sig != state['layout']:
            state['layout'] = sig
            for child,x,y,w,h in layout:
                child.place(x=x,y=y,width=w,height=h)
            frame.configure(height=y+row_h)
    frame._reflow = arrange
    frame.bind('<Configure>', arrange, add='+')
    frame.after_idle(arrange)
    return arrange
