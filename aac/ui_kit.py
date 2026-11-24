"""Элементы нового интерфейса: тёплый тёмный фон, синий акцент, переключатели, карточки, полоски.

Всё на обычном tkinter: плоские цвета, тонкие рамки, переключатели и полоски рисуются на Canvas.
"""
import sys
import tkinter as tk

_Canvas = getattr(tk, "Canvas", object)   # в проверках «второй копии» tkinter подменён пустышкой
_Frame = getattr(tk, "Frame", object)

BG = "#262624"          # фон разделов
SIDEBAR = "#1F1E1D"     # боковая колонка, поля ввода
CARD = "#30302E"        # карточки
CARD_OFF = "#2b2b29"    # выключенная плитка
BORDER = "#4D4C48"
LINE = "#3D3D3A"
TEXT = "#FAF9F5"
TEXT2 = "#DEDCD1"
MUTED = "#B0AEA5"
DIM = "#9C9A92"
FAINT = "#87867F"
ACCENT = "#5865F2"
ACCENT_HOVER = "#4752c4"
ACCENT_TINT = "#2f3147"   # подсветка включённой плитки (синий поверх фона)
ACCENT_LINE = "#4b53a8"
ACCENT_TEXT = "#b5baf9"
GREEN = "#23a55a"
AMBER = "#f0b232"
RED = "#f28b82"

FONT = "Segoe UI"
MONO = "Consolas"


def f(size=10, weight="normal"):
    return (FONT, size, weight)


def label(parent, text="", size=10, color=TEXT, weight="normal", bg=None, **kw):
    kw.setdefault("anchor", "w")
    kw.setdefault("justify", "left")
    return tk.Label(parent, text=text, fg=color, bg=bg or parent["bg"], font=f(size, weight), **kw)


def button(parent, text, command, kind="ghost", size=10, **kw):
    """kind: primary (синяя), ghost (с рамкой), flat (только текст), danger (красный текст)."""
    bg = parent["bg"]
    if kind == "primary":
        b = tk.Button(parent, text=text, command=command, bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER,
                      activeforeground="#ffffff", relief="flat", bd=0, highlightthickness=0, padx=14, pady=6,
                      font=f(size, "bold"), cursor="hand2", **kw)
        hover = (ACCENT_HOVER, ACCENT)
    elif kind in ("flat", "danger"):
        fg = RED if kind == "danger" else MUTED
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=CARD,
                      activeforeground=TEXT if kind == "flat" else RED, relief="flat", bd=0, highlightthickness=0,
                      padx=10, pady=5, font=f(size), cursor="hand2", anchor="w", **kw)
        hover = (CARD, bg)
    else:
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=TEXT2, activebackground=CARD,
                      activeforeground=TEXT, relief="flat", bd=0, highlightthickness=1,
                      highlightbackground=BORDER, highlightcolor=BORDER, padx=12, pady=5, font=f(size),
                      cursor="hand2", **kw)
        hover = (CARD, bg)
    b.bind("<Enter>", lambda e: b.config(bg=hover[0]))
    b.bind("<Leave>", lambda e: b.config(bg=hover[1]))
    return b


def card(parent, bg=CARD, border=BORDER, padx=16, pady=12):
    """Карточка: рамка 1 px. Возвращает (внешняя рамка, внутренняя область для содержимого)."""
    outer = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border, highlightcolor=border)
    inner = tk.Frame(outer, bg=bg)
    inner.pack(fill="both", expand=True, padx=padx, pady=pady)
    return outer, inner


def key_chip(parent, text=""):
    return tk.Label(parent, text=text, fg=TEXT2, bg=SIDEBAR, font=(MONO, 9), padx=7, pady=1,
                    highlightthickness=1, highlightbackground=LINE)


def section_title(parent, text, sub=None):
    box = tk.Frame(parent, bg=parent["bg"])
    label(box, text, 16, TEXT, "bold").pack(anchor="w")
    if sub:
        label(box, sub, 9, DIM, wraplength=640).pack(anchor="w")
    return box


def h2(parent, text):
    return label(parent, text, 12, TEXT, "bold")


def caps(parent, text):
    return label(parent, text.upper(), 8, FAINT, "bold")


def separator(parent, color=LINE):
    return tk.Frame(parent, bg=color, height=1)


def _round_rect(c, x0, y0, x1, y1, r, **kw):
    c.create_oval(x0, y0, x0 + 2 * r, y1, **kw)
    c.create_oval(x1 - 2 * r, y0, x1, y1, **kw)
    if x1 - x0 > 2 * r:
        c.create_rectangle(x0 + r, y0, x1 - r, y1, **kw)


class Toggle(_Canvas):
    """Переключатель-«таблетка». command(новое_значение) вызывается при щелчке."""

    def __init__(self, parent, value=False, command=None, small=False):
        self.w, self.h = (34, 20) if small else (40, 22)
        super().__init__(parent, width=self.w, height=self.h, bg=parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self.value = bool(value)
        self.command = command
        self.bind("<Button-1>", lambda e: self.click())
        self.draw()

    def click(self):
        self.set(not self.value)
        if self.command:
            self.command(self.value)

    def set(self, v):
        if bool(v) == self.value and self.find_all():
            return                     # без изменений — не перерисовываем (иначе мигает)
        self.value = bool(v)
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.w, self.h
        col = ACCENT if self.value else BORDER
        _round_rect(self, 0, 0, w - 1, h - 1, (h - 1) // 2, fill=col, outline=col)
        k = h - 6
        x = w - 3 - k if self.value else 3
        knob = "#ffffff" if self.value else MUTED
        self.create_oval(x, 3, x + k, 3 + k, fill=knob, outline=knob)

    def set_bg(self, bg):
        if self["bg"] != bg:
            self.config(bg=bg)


class Bar(_Canvas):
    """Полоска заполнения (лимиты)."""

    def __init__(self, parent, width=300, height=6):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0)
        self.h = height
        self.frac, self.color = 0.0, ACCENT
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, frac, color=ACCENT):
        frac = max(0.0, min(1.0, frac or 0.0))
        if (frac, color) == (self.frac, self.color) and self.find_all():
            return
        self.frac, self.color = frac, color
        self.draw()

    def draw(self):
        self.delete("all")
        w = max(self.winfo_width(), int(self["width"]) if self.winfo_width() < 2 else 0)
        h = self.h
        _round_rect(self, 0, 0, w - 1, h - 1, (h - 1) // 2, fill=LINE, outline=LINE)
        fw = max(h, int((w - 1) * self.frac)) if self.frac > 0 else 0
        if fw:
            _round_rect(self, 0, 0, fw, h - 1, (h - 1) // 2, fill=self.color, outline=self.color)


class Dot(_Canvas):
    def __init__(self, parent, color=GREEN, size=10):
        super().__init__(parent, width=size, height=size, bg=parent["bg"], highlightthickness=0, bd=0)
        self.size = size
        self.set(color)

    def set(self, color):
        if getattr(self, "_color", None) == color:
            return
        self._color = color
        self.delete("all")
        self.create_oval(0, 0, self.size - 1, self.size - 1, fill=color, outline=color)


class ToggleRow(_Frame):
    """Строка «название / пояснение … переключатель» с линией снизу."""

    def __init__(self, parent, title, sub, get, set_, last=False):
        super().__init__(parent, bg=parent["bg"])
        self.get = get
        body = tk.Frame(self, bg=self["bg"])
        body.pack(fill="x", pady=8)
        txt = tk.Frame(body, bg=self["bg"])
        txt.pack(side="left", fill="x", expand=True)
        label(txt, title, 10, TEXT).pack(anchor="w")
        if sub:
            label(txt, sub, 9, DIM, wraplength=520).pack(anchor="w")
        self.toggle = Toggle(body, get(), lambda v: (set_(v), self.sync()))
        self.toggle.pack(side="right")
        if not last:
            separator(self).pack(fill="x")

    def sync(self):
        self.toggle.set(self.get())


class Tile(_Frame):
    """Плитка с переключателем: включённая подсвечена синим. Щелчок в любом месте — переключить."""

    def __init__(self, parent, icon, title, sub, key, get, set_):
        super().__init__(parent, highlightthickness=1)
        self.get, self.set_ = get, set_
        self.inner = tk.Frame(self)
        self.inner.pack(fill="both", expand=True, padx=12, pady=12)
        top = tk.Frame(self.inner)
        top.pack(fill="x")
        self.icon = tk.Label(top, text=icon, width=3, font=f(11, "bold"))
        self.icon.pack(side="left")
        self.toggle = Toggle(top, get(), lambda v: self._set(v), small=True)
        self.toggle.pack(side="right")
        self.title = tk.Label(self.inner, text=title, font=f(10, "bold"), anchor="w", justify="left", wraplength=150)
        self.title.pack(fill="x", pady=(10, 0))
        self.sub = tk.Label(self.inner, text=sub, font=f(9), anchor="w", justify="left", wraplength=150)
        self.sub.pack(fill="x")
        self.key = key_chip(self.inner, key) if key else None
        if self.key:
            self.key.pack(anchor="w", pady=(8, 0))
        self.frames = [self, self.inner, top]
        self._wrap_w = None

        def rewrap(e):
            # перенос строк по ширине плитки; мелкие колебания ширины пропускаем — иначе перенос меняет ширину,
            # ширина — перенос, и окно бесконечно перестраивается (зависание)
            w = max(60, e.width - 4)
            if self._wrap_w is not None and abs(w - self._wrap_w) < 12:
                return
            self._wrap_w = w
            self.title.config(wraplength=w)
            self.sub.config(wraplength=w)
        self.inner.bind("<Configure>", rewrap)
        for w in (self, self.inner, top, self.icon, self.title, self.sub):
            w.bind("<Button-1>", lambda e: self.toggle.click())
            w.config(cursor="hand2")
        self.sync()

    def _set(self, v):
        self.set_(v)
        self.sync()

    def set_sub(self, text):
        self.sub.config(text=text)

    def sync(self):
        on = bool(self.get())
        if getattr(self, "_on", None) == on:
            return
        self._on = on
        bg = ACCENT_TINT if on else CARD_OFF
        self.config(bg=bg, highlightbackground=ACCENT_LINE if on else LINE, highlightcolor=ACCENT_LINE if on else LINE)
        for w in self.frames[1:]:
            w.config(bg=bg)
        self.icon.config(bg=ACCENT if on else LINE, fg="#ffffff" if on else MUTED)
        self.title.config(bg=bg, fg=TEXT if on else MUTED)
        self.sub.config(bg=bg, fg=DIM)
        self.toggle.set(on)
        self.toggle.set_bg(bg)


def select(parent, var, options, command=None, width=28):
    """Выпадающий список в стиле поля ввода."""
    om = tk.OptionMenu(parent, var, *options, command=(lambda v: command()) if command else None)
    om.config(bg=SIDEBAR, fg=TEXT, activebackground=CARD, activeforeground=TEXT, relief="flat", bd=0,
              highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER, font=f(10), anchor="w",
              width=width, indicatoron=False, padx=10, pady=6, cursor="hand2")
    om["menu"].config(bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="#ffffff", font=f(10), bd=0)
    return om


class Scroll(_Frame):
    """Прокручиваемая область. Колесо мыши обрабатывает общий «маршрутизатор» окна (install_wheel)."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=24)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._region())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width),
                                                   self._region()))

    def _region(self):
        h = max(self.body.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), h))

    def wheel(self, delta):
        if self.body.winfo_reqheight() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)
            return
        steps = -3 if delta > 0 else 3
        self.canvas.yview_scroll(steps, "units")

    def top(self):
        self.canvas.yview_moveto(0)


# Windows: физические клавиши V, C, X, A, Z (на любой раскладке)
_EDIT_KEYS = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>", 65: "<<SelectAll>>", 90: "<<Undo>>"}
_EDIT_CHARS = {"м": "<<Paste>>", "с": "<<Copy>>", "ч": "<<Cut>>", "ф": "<<SelectAll>>", "я": "<<Undo>>"}


def on_ctrl_key(e):
    """Ctrl+буква в поле ввода: на русской раскладке Tk не узнаёт Ctrl+V и др. — узнаём по коду клавиши."""
    ev = None
    if e.keysym.lower() in ("v", "c", "x", "a", "z"):
        return None                      # английская раскладка — Tk справится сам
    if sys.platform == "win32" and getattr(e, "keycode", None) in _EDIT_KEYS:    # код клавиши Windows
        ev = _EDIT_KEYS[e.keycode]
    elif (e.char or "").lower() in _EDIT_CHARS:
        ev = _EDIT_CHARS[(e.char or "").lower()]
    else:
        ev = {"cyrillic_em": "<<Paste>>", "cyrillic_es": "<<Copy>>", "cyrillic_che": "<<Cut>>",
              "cyrillic_ef": "<<SelectAll>>", "cyrillic_ya": "<<Undo>>"}.get(e.keysym.lower())
    if not ev:
        return None
    if ev == "<<SelectAll>>" and isinstance(e.widget, tk.Entry):
        e.widget.select_range(0, "end")
        e.widget.icursor("end")
    else:
        e.widget.event_generate(ev)
    return "break"


def install_clipboard(root):
    """Ctrl+V / Ctrl+C / Ctrl+X / Ctrl+A в полях ввода на русской раскладке (Tk понимает их только на английской)
    и меню «Вставить / Копировать» по правой кнопке мыши."""
    def menu(e):
        w = e.widget
        m = tk.Menu(w, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT, activeforeground="#ffffff", bd=0)
        m.add_command(label="Вставить", command=lambda: w.event_generate("<<Paste>>"))
        m.add_command(label="Копировать", command=lambda: w.event_generate("<<Copy>>"))
        m.add_command(label="Вырезать", command=lambda: w.event_generate("<<Cut>>"))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()
    for cls in ("Entry", "Text"):
        root.bind_class(cls, "<Control-KeyPress>", on_ctrl_key, add="+")
        root.bind_class(cls, "<Button-3>", menu, add="+")


def install_wheel(toplevel, current_scroll):
    """Колесо мыши для всего окна: прокручивает раздел под курсором, где бы курсор ни был
    (над карточкой, плиткой, кнопкой). Списки (Text) крутятся сами."""
    def handler(e):
        try:
            w = toplevel.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        if w is None or not str(w).startswith(str(toplevel)):
            return
        if w.winfo_class() in ("Text", "Listbox"):
            return
        sc = current_scroll()
        if sc is not None and str(w).startswith(str(sc)):
            sc.wheel(e.delta)
    toplevel.bind_all("<MouseWheel>", handler, add="+")


class Slider(_Canvas):
    """Ползунок: дорожка, заполнение синим, белая ручка. Значение справа от подписи (рисует владелец)."""

    def __init__(self, parent, lo, hi, step, value, command=None, width=300):
        super().__init__(parent, width=width, height=22, bg=parent["bg"], highlightthickness=0, bd=0,
                         cursor="hand2")
        self.lo, self.hi, self.step = lo, hi, step
        self.value = value
        self.command = command
        self.bind("<Button-1>", self._at)
        self.bind("<B1-Motion>", self._at)
        self.bind("<ButtonRelease-1>", lambda e: self.command and self.command(self.value, True))
        self.bind("<Configure>", lambda e: self.draw())
        self.draw()

    def _at(self, e):
        w = max(1, self.winfo_width() - 16)
        frac = min(1.0, max(0.0, (e.x - 8) / w))
        v = self.lo + frac * (self.hi - self.lo)
        v = round(round(v / self.step) * self.step, 4)
        if v != self.value:
            self.value = v
            self.draw()
            if self.command:
                self.command(v, False)

    def set(self, v):
        if v == self.value and self.find_all():
            return
        self.value = v
        self.draw()

    def draw(self):
        self.delete("all")
        w = max(int(self["width"]) if self.winfo_width() < 2 else self.winfo_width(), 40)
        frac = (self.value - self.lo) / (self.hi - self.lo) if self.hi != self.lo else 0
        x = 8 + frac * (w - 16)
        _round_rect(self, 8, 8, w - 8, 14, 3, fill=LINE, outline=LINE)
        if x > 9:
            _round_rect(self, 8, 8, x, 14, 3, fill=ACCENT, outline=ACCENT)
        self.create_oval(x - 8, 3, x + 8, 19, fill="#ffffff", outline="#ffffff")


class SliderRow(_Frame):
    """Подпись + значение справа + ползунок под ними."""

    def __init__(self, parent, title, lo, hi, step, get, set_, fmt=lambda v: f"{v:g}"):
        super().__init__(parent, bg=parent["bg"])
        self.get, self.fmt = get, fmt
        top = tk.Frame(self, bg=self["bg"])
        top.pack(fill="x")
        label(top, title, 10, TEXT2).pack(side="left")
        self.val = label(top, fmt(get()), 10, ACCENT_TEXT, "bold")
        self.val.pack(side="right")

        def changed(v, final):
            self.val.config(text=fmt(v))
            set_(v, final)
        self.slider = Slider(self, lo, hi, step, get(), changed)
        self.slider.pack(fill="x", pady=(4, 0))

    def sync(self):
        self.slider.set(self.get())
        self.val.config(text=self.fmt(self.get()))


class Segmented(_Frame):
    """Переключатель вариантов (как вкладки): [(ключ, название, пояснение)]."""

    def __init__(self, parent, options, get, set_):
        super().__init__(parent, bg=SIDEBAR, highlightthickness=1, highlightbackground=BORDER)
        self.get, self.set_ = get, set_
        self.items = {}
        for i, (key, title, sub) in enumerate(options):
            cell = tk.Frame(self, bg=SIDEBAR, cursor="hand2")
            cell.grid(row=0, column=i, sticky="nsew", padx=3, pady=3)
            self.columnconfigure(i, weight=1, uniform="s")
            t = tk.Label(cell, text=title, font=f(10, "bold"), bg=SIDEBAR, cursor="hand2")
            t.pack(pady=(6, 0))
            s_ = tk.Label(cell, text=sub, font=f(8), bg=SIDEBAR, cursor="hand2")
            s_.pack(pady=(0, 6))
            for w in (cell, t, s_):
                w.bind("<Button-1>", lambda e, k=key: self._pick(k))
            self.items[key] = (cell, t, s_)
        self.sync()

    def _pick(self, key):
        self.set_(key)
        self.sync()

    def sync(self):
        cur = self.get()
        for key, (cell, t, s_) in self.items.items():
            on = key == cur
            bg = ACCENT if on else SIDEBAR
            cell.config(bg=bg)
            t.config(bg=bg, fg="#ffffff" if on else MUTED)
            s_.config(bg=bg, fg="#dfe1ff" if on else FAINT)


def set_options(om, var, names, command=None):
    """Заменить пункты выпадающего списка."""
    menu = om["menu"]
    menu.delete(0, "end")
    for n in names:
        menu.add_command(label=n, command=lambda v=n: (var.set(v), command and command()))


def entry(parent, var, placeholder="", width=24):
    """Поле ввода в стиле приложения (с подсказкой, пока пусто)."""
    e = tk.Entry(parent, textvariable=var, bg=SIDEBAR, fg=TEXT, insertbackground=TEXT, relief="flat", bd=6,
                 highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, font=f(10), width=width)
    if placeholder:
        def show_ph(_e=None):
            if not var.get():
                e.config(fg=FAINT)
                e.insert(0, placeholder)
                e._ph = True

        def hide_ph(_e=None):
            if getattr(e, "_ph", False):
                e.delete(0, "end")
                e.config(fg=TEXT)
                e._ph = False
        e._ph = False
        e.bind("<FocusIn>", hide_ph)
        e.bind("<FocusOut>", show_ph)
        e.value = lambda: "" if getattr(e, "_ph", False) else var.get()
        show_ph()
    else:
        e.value = var.get
    return e


def chip(parent, text, on, command):
    """Кнопка-фильтр (таблетка)."""
    b = tk.Label(parent, text=text, font=f(9), padx=10, pady=3, cursor="hand2",
                 bg=ACCENT if on else CARD, fg="#ffffff" if on else TEXT2,
                 highlightthickness=1, highlightbackground=ACCENT if on else BORDER)
    b.bind("<Button-1>", lambda e: command())
    return b


class Avatar(_Canvas):
    """Кружок с первой буквой имени (цвет — по полу)."""

    def __init__(self, parent, letter, color, size=32):
        super().__init__(parent, width=size, height=size, bg=parent["bg"], highlightthickness=0, bd=0)
        self.create_oval(0, 0, size - 1, size - 1, fill=color, outline=color)
        self.create_text(size // 2, size // 2, text=letter.upper()[:1], fill="#141413", font=f(11, "bold"))
