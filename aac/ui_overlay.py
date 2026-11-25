"""Окна перевода поверх игры."""

import ctypes


import tkinter as tk


from . import config, core, screens


# ---------- окна ----------
BOX_BG = "#14141a"            # фон окон перевода — как в образце «Вид перевода»
TITLE_FG = "#9c9a92"          # заголовок окна: мелкий серый, без цвета
_exclude_warned = False


STREAM_WINDOWS = []   # окна перевода, которые можно показывать на трансляции (субтитры, ответы, подсказки…)


def exclude_from_capture(widget):
    """Окна программы не попадают на снимки экрана и в трансляцию (Discord, OBS).
    Окна перевода — по настройке «показывать на трансляции»: тогда они видны зрителям, а на своих
    снимках программа их всё равно закрашивает (own_rects)."""
    global _exclude_warned
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return  # не Windows
    show = config.SHOW_ON_STREAM and widget in STREAM_WINDOWS
    affinity = 0x0 if show else 0x11     # WDA_NONE / WDA_EXCLUDEFROMCAPTURE
    ok = False
    handles = []
    try:
        handles.append(int(widget.wm_frame(), 16))   # внешняя рамка окна Tk
    except Exception:
        pass
    try:
        handles.append(user32.GetAncestor(widget.winfo_id(), 2))
    except Exception:
        pass
    for hwnd in dict.fromkeys(h for h in handles if h):
        try:
            if user32.SetWindowDisplayAffinity(hwnd, affinity):
                ok = True
        except Exception:
            pass
    if not ok and not show and not _exclude_warned:
        _exclude_warned = True
        core.log("Не удалось скрыть окна перевода от скриншотов. Следите, чтобы окна перевода "
            "НЕ заходили на области субтитров и ответов (Ctrl+Shift+L — расставить окна).", "warn")


def apply_stream_visibility():
    """Переключили «показывать на трансляции» — применяем ко всем окнам перевода сразу."""
    for w in list(STREAM_WINDOWS):
        try:
            if w.winfo_exists():
                exclude_from_capture(w)
        except Exception:
            pass


def release_mouse(widget=None):
    """Отпустить «захват мыши» (Tk и Windows), чтобы спрятанное окно не держало мышь у себя."""
    try:
        if widget is not None:
            widget.grab_release()
    except Exception:
        pass
    try:
        ctypes.windll.user32.ReleaseCapture()
    except Exception:
        pass


KEY_BG = "#010203"      # «прозрачный» цвет окна в режиме обводки букв (Windows не рисует его вовсе)


_Canvas = getattr(tk, "Canvas", object)     # проверки без окон подменяют tkinter пустышкой


class OutlineLabel(_Canvas):
    """Надпись без подложки, с чёрным контуром вокруг букв (как субтитры в кино).
    Понимает то же, что окна перевода спрашивают у обычной надписи: text, font, fg, wraplength, cget."""
    OWN = ("text", "font", "fg", "wraplength", "padx", "pady", "outline")

    def __init__(self, master, text="", fg="#eee", font=("Segoe UI", 13), wraplength=300, padx=12, pady=6,
                 outline="#000000", **_ignored):
        super().__init__(master, bg=KEY_BG, highlightthickness=0, bd=0, height=1, width=10)
        self._o = {"text": text, "fg": fg, "font": font, "wraplength": wraplength, "padx": padx, "pady": pady,
                   "outline": outline}
        self._draw()

    def configure(self, cnf=None, **kw):
        kw.update(cnf or {})
        mine = {k: kw.pop(k) for k in list(kw) if k in self.OWN}
        for k in ("justify", "anchor"):
            kw.pop(k, None)
        if kw:
            tk.Canvas.configure(self, **kw)
        if mine:
            self._o.update(mine)
            self._draw()
    config = configure

    def cget(self, key):
        return self._o[key] if key in self._o else tk.Canvas.cget(self, key)

    def _draw(self):
        o = self._o
        self.delete("all")
        w = max(60, int(o["wraplength"]))
        if not o["text"]:
            tk.Canvas.configure(self, height=1, width=w + 2 * int(o["padx"]))
            return
        x, y = int(o["padx"]), int(o["pady"]) + 2
        # контур 1 px со всех сторон + тень вниз-вправо: читается на любом фоне, буквы не слипаются
        for dx, dy in ((2, 2), (1, 2), (2, 1), (-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1),
                       (1, 1)):
            self.create_text(x + dx, y + dy, text=o["text"], font=o["font"], fill=o["outline"], anchor="nw", width=w)
        main = self.create_text(x, y, text=o["text"], font=o["font"], fill=o["fg"], anchor="nw", width=w)
        box = self.bbox(main) or (0, 0, w, 20)
        tk.Canvas.configure(self, height=box[3] - box[1] + 2 * int(o["pady"]) + 6, width=w + 2 * int(o["padx"]))


class Overlay:
    """Полупрозрачное окно с текстом: перетаскивается мышкой, правый клик — скрыть."""

    def __init__(self, win, name, default_pos, width, title=""):
        self.win, self.name, self.width = win, name, width
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", config.OVERLAY_ALPHA)
        win.configure(bg=BOX_BG)
        self.default_pos = default_pos
        self.anchor = None  # функция, возвращающая область, к которой «прилипает» окно
        self.anchor_side = "above"
        # «склейка»: окно-ведомый стоит вплотную под ведущим, той же ширины, и двигается вместе с ним
        self.leader = None
        self.followers = []
        self._geom = None
        # своё оформление (окно чата): прозрачность, цвет текста, «поверх области», предельная высота
        self.style_alpha = None       # функция → число или None (как у всех окон)
        self.style_fg = None          # функция → цвет или None
        self.cover = None             # функция → прямоугольник, который окно должно накрыть целиком, или None
        self.max_height = None        # функция → px или None
        # manual = вы сами перетащили окно: оно больше не прилипает к области (F11 — вернуть авто)
        self.manual = core.SETTINGS.get(f"{name}_manual", False)
        width = core.SETTINGS.get(f"{name}_width", width)
        self.width = width
        x, y = core.SETTINGS.get(f"{name}_pos", default_pos)
        # если окно сохранено за краем экрана — возвращаем на место
        if not screens.on_screen(x, y):          # монитор отключили — окно вернуть на место
            x, y = default_pos
        win.geometry(f"{width}x10+{x}+{y}")
        self._geom = (width, 10, x, y)

        # правый край окна — «ручка»: потяните мышкой, чтобы изменить ширину
        self.grip = tk.Frame(win, width=8, bg=config.GRIP_COLOR, cursor="sb_h_double_arrow")
        self.grip.pack(side="right", fill="y")
        self.grip.bind("<ButtonPress-1>", self._grip_start)
        self.grip.bind("<B1-Motion>", self._grip_move)
        self.grip.bind("<ButtonRelease-1>", lambda e: self._save_layout())
        self.status = tk.Label(win, text=title, fg=TITLE_FG, bg=BOX_BG, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(6, 0))
        # предыдущие реплики — бледным текстом над текущей (показывается, когда есть история)
        self.history = []
        self.mode = None
        self.label = self.hist_label = self.orig_label = None
        self._make_labels("box")
        self._bind_mouse(self.status)
        self.visible = True
        STREAM_WINDOWS.append(win)
        win.after(200, lambda: exclude_from_capture(win))

    def _bind_mouse(self, w):
        w.bind("<MouseWheel>", self._wheel)  # колесо мыши — ширина окна
        w.bind("<ButtonPress-1>", self._start_move)
        w.bind("<B1-Motion>", self._move)
        w.bind("<ButtonRelease-1>", self._end_move)
        # прячем на ОТПУСКАНИЕ правой кнопки и чуть позже: если спрятать окно, пока кнопка ещё зажата,
        # Windows оставляет «захват мыши» за невидимым окном — и программа перестаёт реагировать
        w.bind("<ButtonRelease-3>", lambda e: self.win.after(30, self.hide))

    def _make_labels(self, mode):
        """Надписи окна: обычные (на плашке) или с обводкой букв. Текст при пересоздании сохраняется."""
        old = (self.label, self.hist_label, self.orig_label)
        texts = [w.cget("text") if w is not None else "" for w in old]
        shown = [w is not None and bool(w.winfo_manager()) for w in old]
        for w in old:
            if w is not None:
                w.destroy()
        wrap = self.width - 32
        fam = config.FONT[0]
        if mode == "outline":
            mk = lambda **kw: OutlineLabel(self.win, **kw)
        else:
            mk = lambda **kw: tk.Label(self.win, bg=BOX_BG, justify="left", anchor="w", **kw)
        self.hist_label = mk(text=texts[1], fg="#9a9a9a", font=config.HISTORY_FONT, wraplength=wrap, padx=12, pady=2)
        self.label = mk(text=texts[0], fg="#eee", font=config.FONT, wraplength=wrap, padx=12, pady=6)
        # оригинал — мелким серым под переводом (если включено в настройках)
        self.orig_label = mk(text=texts[2], fg="#8d95a0", font=(fam, max(8, config.FONT[1] - 3)), wraplength=wrap,
                             padx=12, pady=0)
        if shown[1]:
            self.hist_label.pack(fill="x")
        self.label.pack(fill="both", expand=True)
        if shown[2]:
            self.orig_label.pack(fill="x", after=self.label, pady=(0, 6))
        for w in (self.label, self.hist_label, self.orig_label):
            self._bind_mouse(w)
        bg = KEY_BG if mode == "outline" else BOX_BG
        self.win.configure(bg=bg)
        self.status.configure(bg=bg)
        if not getattr(self, "_grip_on", False):
            self.grip.configure(bg=bg if mode == "outline" else config.GRIP_COLOR)
        try:
            self.win.attributes("-transparentcolor", KEY_BG if mode == "outline" else "")
        except tk.TclError:
            pass                                    # не Windows — прозрачного цвета нет, просто тёмный фон
        self.mode = mode

    # --- склейка окон ---
    def dock(self, leader):
        """leader — окно, под которым стоять вплотную (None — снова отдельное окно)."""
        if self.leader is not None and self in self.leader.followers:
            self.leader.followers.remove(self)
        self.leader = leader
        if leader is not None:
            leader.followers.append(self)
            self.win.configure(highlightthickness=0)
        if self.visible:
            self.fit()

    def _pos(self):
        """Где окно сейчас (по последней заданной геометрии — надёжнее, чем спрашивать Windows)."""
        if self._geom:
            return self._geom
        self.win.update_idletasks()
        return self.width, self.win.winfo_height(), self.win.winfo_x(), self.win.winfo_y()

    def _place(self, w, h, x, y):
        w, h, x, y = int(w), int(h), int(x), int(y)   # Tk не принимает «+889.0» (дробные координаты)
        self._geom = (w, h, x, y)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self._notify()

    def _notify(self):
        for f in self.followers:
            if f.visible:
                f.fit()

    def _start_move(self, e):
        if self.leader is not None:           # склеенное окно тащит за собой ведущее
            return self.leader._start_move(e)
        _, _, x, y = self._pos()
        self._dx, self._dy = e.x_root - x, e.y_root - y
        self._moved = False

    def _move(self, e):
        if self.leader is not None:
            return self.leader._move(e)
        self._moved = True
        self.manual = True  # перетащили — окно теперь стоит там, где вы его оставили
        w, h, _, _ = self._pos()
        self._place(w, h, e.x_root - self._dx, e.y_root - self._dy)

    def _end_move(self, e):
        if self.leader is not None:
            return self.leader._end_move(e)
        if getattr(self, "_moved", False):
            self._save_layout()

    def _grip_start(self, e):
        if self.leader is not None:
            return self.leader._grip_start(e)
        self._gx, self._gw = e.x_root, self.width

    def _grip_move(self, e):
        if self.leader is not None:
            return self.leader._grip_move(e)
        self.set_width(self._gw + (e.x_root - self._gx))

    def set_width(self, w):
        sw = self.win.winfo_screenwidth()
        self.manual = True
        self.width = max(220, min(sw, int(w)))
        self.label.config(wraplength=self.width - 32)
        self.hist_label.config(wraplength=self.width - 32)
        self.orig_label.config(wraplength=self.width - 32)
        self.fit()

    def apply_style(self):
        """Применить вид из настроек: шрифт, цвет, плашка/обводка, прозрачность (окно чата — своё оформление)."""
        mode = "box" if self.style_fg else getattr(config, "TEXT_MODE", "box")
        if mode != self.mode:
            self._make_labels(mode)
        fg = (self.style_fg() if self.style_fg else None) or getattr(config, "TEXT_COLOR", "#eee")
        self.label.config(font=config.FONT, fg=fg)
        self.hist_label.config(font=config.HISTORY_FONT)
        self.orig_label.config(font=(config.FONT[0], max(8, config.FONT[1] - 3)))
        try:
            self.win.attributes("-alpha", (self.style_alpha() if self.style_alpha else None) or config.OVERLAY_ALPHA)
        except Exception:
            pass
        if not config.SHOW_ORIGINAL and self.orig_label.winfo_manager():
            self.orig_label.pack_forget()
        if self.visible:
            self.fit()

    def highlight_grip(self, on):
        self._grip_on = on
        rest = KEY_BG if self.mode == "outline" else config.GRIP_COLOR
        self.grip.config(bg=config.GRIP_ACTIVE_COLOR if on else rest)
        if getattr(self, "vgrip", None) is not None:
            self.vgrip.config(bg=config.GRIP_ACTIVE_COLOR if on else config.GRIP_COLOR)

    wheel_handler = None   # своя реакция на колесо мыши (окно чата — прокрутка)

    def _wheel(self, e):
        if self.wheel_handler is not None:
            return self.wheel_handler(e)
        if self.leader is not None:
            return self.leader._wheel(e)
        step = 40 if e.delta > 0 else -40
        sw = self.win.winfo_screenwidth()
        self.manual = True
        self.width = max(220, min(sw, self.width + step))
        self.label.config(wraplength=self.width - 32)
        self.hist_label.config(wraplength=self.width - 32)
        self.orig_label.config(wraplength=self.width - 32)
        self.fit()
        self._save_layout()

    def _save_layout(self):
        if self.leader is not None:
            return self.leader._save_layout()
        _, _, x, y = self._pos()
        core.save_settings(**{f"{self.name}_pos": (x, y),
                         f"{self.name}_manual": self.manual,
                         f"{self.name}_width": self.width})

    def enable_height_grip(self, on_drag, on_release):
        """Нижний край окна можно тянуть мышкой — меняется высота (для окна чата)."""
        self.vgrip = tk.Frame(self.win, height=6, bg=config.GRIP_COLOR, cursor="sb_v_double_arrow")
        self.vgrip.pack(side="bottom", fill="x", before=self.status)

        def start(e):
            self._vy, self._vh = e.y_root, self._pos()[1]

        def move(e):
            on_drag(max(40, self._vh + (e.y_root - self._vy)))

        self.vgrip.bind("<ButtonPress-1>", start)
        self.vgrip.bind("<B1-Motion>", move)
        self.vgrip.bind("<ButtonRelease-1>", lambda e: on_release())

    def _set_wrap(self, w):
        for lab in (self.label, self.hist_label, self.orig_label):
            lab.config(wraplength=w - 32)

    def fit(self):
        rect = self.cover() if self.cover else None
        if rect:
            # окно лежит точно поверх области (перевод на месте оригинала)
            x0, y0, rw, rh = (int(v) for v in rect)
            if self.width != rw:
                self.width = rw
                self._set_wrap(rw)
            self._place(rw, rh, x0, y0)
            return
        if self.leader is not None:
            # склеено: вплотную под окном субтитров, та же ширина (если субтитров нет — на их месте)
            lw, lh, lx, ly = self.leader._pos()
            if self.width != lw:
                self.width = lw
                self._set_wrap(lw)
            self.win.update_idletasks()
            h = self._content_height()
            y = ly + lh if self.leader.visible else ly
            reg = self.leader.anchor() if (self.leader.anchor and not self.leader.manual) else None
            if reg and self.leader.visible and y < reg[1] + reg[3] and y + h > reg[1]:
                y = ly - h        # снизу — субтитры игры: ставим ответы над окном субтитров
            _, y = screens.clamp(lx, y, lw, h, near=(lx + lw // 2, ly))
            self._place(lw, h, lx, y)
            return
        reg = self.anchor() if (self.anchor and not self.manual) else None
        if reg and self.anchor_side in ("left", "right"):
            # окно сбоку от области (для вариантов ответа), верх — на уровне области
            x0, y0, rw, rh = reg
            ml, mt, mr, mb = screens.monitor_at(x0 + rw // 2, y0 + rh // 2)   # монитор, где область
            w = self.width
            self.win.update_idletasks()
            h = self._content_height()
            left_x, right_x = x0 - w - config.ANCHOR_GAP, x0 + rw + config.ANCHOR_GAP
            if self.anchor_side == "left":
                x = left_x if left_x >= ml else right_x
            else:
                x = right_x if right_x + w <= mr else left_x
            x = min(max(ml, x), mr - w)
            y = min(max(mt, y0), mb - h)
            self._place(w, h, x, y)
            return
        if reg:
            # окно ровно над выделенной областью и той же ширины
            x0, y0, rw, rh = reg
            ml, mt, mr, mb = screens.monitor_at(x0 + rw // 2, y0 + rh // 2)   # монитор, где область
            w = max(rw, 300)
            x = max(ml, x0 + (rw - w) // 2)
            if self.width != w:
                self.width = w
                self.label.config(wraplength=w - 32)
                self.hist_label.config(wraplength=w - 32)
                self.orig_label.config(wraplength=w - 32)
            self.win.update_idletasks()
            h = self._content_height()
            y = y0 - h - config.ANCHOR_GAP
            if y < mt:  # над областью нет места — ставим под неё
                y = y0 + rh + config.ANCHOR_GAP
            self._place(w, h, x, y)
            return
        self.win.update_idletasks()
        h = self._content_height()
        _, _, x, y = self._pos()
        self._place(self.width, h, x, y)

    def _content_height(self):
        h = sum(w.winfo_reqheight() for w in self.win.pack_slaves() if w is not self.grip)
        limit = self.max_height() if self.max_height else None
        return int(limit) if limit else h      # задана высота — окно ровно такой высоты

    def natural_height(self):
        """Сколько окну нужно по содержимому (без ограничения высоты)."""
        self.win.update_idletasks()
        return sum(w.winfo_reqheight() for w in self.win.pack_slaves() if w is not self.grip)

    def push(self, text, orig=None):
        """Новая реплика: текущая уходит в историю (бледным сверху), новая — основным текстом."""
        if isinstance(text, tuple):
            text, orig = text
        cur = self.label.cget("text")
        if config.SUBS_HISTORY > 0 and cur and cur != text:
            self.history.append(cur)
            self.history = self.history[-config.SUBS_HISTORY:]
        if self.history:
            self.hist_label.config(text="\n".join(self.history))
            if not self.hist_label.winfo_manager():
                self.hist_label.pack(fill="x", before=self.label)
        self.show(text, orig)

    def clear_history(self):
        self.history = []
        self.hist_label.config(text="")
        self.hist_label.pack_forget()

    def show(self, text, orig=None):
        if isinstance(text, tuple):
            text, orig = text
        self.label.config(text=text)
        if config.SHOW_ORIGINAL and orig:
            self.orig_label.config(text=orig)
            if not self.orig_label.winfo_manager():
                self.orig_label.pack(fill="x", after=self.label, pady=(0, 6))
        elif self.orig_label.winfo_manager():
            self.orig_label.pack_forget()
        self.win.deiconify()
        self.visible = True
        self.fit()

    on_hide = None   # что сделать, когда окно прячут (например, остановить чтение вслух)

    def hide(self):
        was = self.visible
        release_mouse(self.win)
        self.win.withdraw()
        self.visible = False
        if was and self.on_hide:
            try:
                self.on_hide()
            except Exception:
                pass
        self._notify()   # склеенное окно ответов поднимается на место субтитров

    def reset_pos(self):
        if self.leader is not None:
            if self.visible:
                self.fit()
            return
        x, y = self.default_pos
        self.manual = False   # снова прилипает к своей области (если она есть)
        w, h, _, _ = self._pos()
        self._place(w, h, x, y)
        core.save_settings(**{f"{self.name}_pos": (x, y), f"{self.name}_manual": False})
        core.save_settings(**{f"{self.name}_width": self.width})
        if self.visible:
            self.fit()

    def set_status(self, text):
        if self.status.cget("text") != text:
            self.status.config(text=text)


class WordTip:
    """Маленькая плашка с переводом надписи под мышкой (имя НПС, табличка). Правый клик — убрать."""

    def __init__(self, win):
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.92)
        win.configure(bg="#3a3f4b")
        inner = tk.Frame(win, bg="#14161c")
        inner.pack(padx=1, pady=1)
        self.label = tk.Label(inner, text="", fg="#fff", bg="#14161c", font=("Segoe UI", config.FONT[1], "bold"),
                              padx=10, pady=2, justify="center", wraplength=520)
        self.label.pack()
        self.orig = tk.Label(inner, text="", fg="#8b93a3", bg="#14161c", font=("Segoe UI", 8),
                             padx=10, pady=0, justify="center", wraplength=520)
        self.orig.pack(pady=(0, 2))
        for w in (win, inner, self.label, self.orig):
            w.bind("<ButtonRelease-3>", lambda e: self.hide())
        self.visible = False
        win.withdraw()
        STREAM_WINDOWS.append(win)
        win.after(200, lambda: exclude_from_capture(win))

    def show(self, text, orig=None):
        self.label.config(text=text, font=("Segoe UI", config.FONT[1], "bold"))
        self.orig.config(text=orig or "")
        (self.orig.pack(pady=(0, 2)) if orig and config.SHOW_ORIGINAL else self.orig.pack_forget())
        self.win.update_idletasks()
        return self.win.winfo_reqwidth(), self.win.winfo_reqheight()

    def move(self, x, y):
        """Поставить и показать (сначала место, потом показ — иначе окно может мелькнуть в углу)."""
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        self.win.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        if not self.visible:
            self.win.deiconify()
            self.visible = True
        self.win.lift()

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False


class Indicator:
    """Маленький значок поверх игры: автоперевод включён (виден, даже когда все окна перевода скрыты).
    Тащите мышкой — положение запоминается; левый клик — показать/скрыть панель; правый — выключить автоперевод."""

    def __init__(self, win):
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.85)
        win.configure(bg=BOX_BG)
        self.label = tk.Label(win, text="", fg="#6f6", bg=BOX_BG, font=("Segoe UI", 9, "bold"), padx=8, pady=2)
        self.label.pack()
        x, y = core.SETTINGS.get("indicator_pos", (12, 12))
        if not screens.on_screen(x, y, 40, 20):
            x, y = 12, 12
        win.geometry(f"+{x}+{y}")
        self.label.bind("<ButtonPress-1>", self._start)
        self.label.bind("<B1-Motion>", self._move)
        self.label.bind("<ButtonRelease-1>", self._end)
        self.label.bind("<ButtonRelease-3>", lambda e: core.events.put(("auto", None)))
        self.state = None
        self.visible = True
        win.after(200, lambda: exclude_from_capture(win))

    def _start(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()
        self._moved = False

    def _move(self, e):
        self._moved = True
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _end(self, e):
        if getattr(self, "_moved", False):
            core.save_settings(indicator_pos=(self.win.winfo_x(), self.win.winfo_y()))
        else:
            core.events.put(("panel_toggle", None))

    def update(self, auto_on, paused=False, busy=False, tts_on=False):
        """Показать текущее состояние (перерисовывается, только если что-то изменилось)."""
        show = config.SHOW_INDICATOR and auto_on
        state = (show, paused, busy, tts_on)
        if state == self.state:
            return
        self.state = state
        if not show:
            if self.visible:
                self.win.withdraw()
                self.visible = False
            return
        if paused:
            text, color = "⏸ AAC: пауза", "#fc6"
        elif busy:
            text, color = "⏳ AAC: перевожу", "#8cf"
        else:
            text, color = "● AAC: перевод вкл", "#6f6"
        if tts_on:
            text += "  🔊"
        self.label.config(text=text, fg=color)
        if not self.visible:
            self.win.deiconify()
            self.visible = True
        self.win.lift()
