"""Окна перевода поверх игры."""

import ctypes


import tkinter as tk


from . import config, core


# ---------- окна ----------
_exclude_warned = False


def exclude_from_capture(widget):
    """Окна перевода не попадают на скриншоты — иначе скрипт переводил бы сам себя."""
    global _exclude_warned
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return  # не Windows
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
            if user32.SetWindowDisplayAffinity(hwnd, 0x11):  # WDA_EXCLUDEFROMCAPTURE
                ok = True
        except Exception:
            pass
    if not ok and not _exclude_warned:
        _exclude_warned = True
        core.log("Не удалось скрыть окна перевода от скриншотов. Следите, чтобы окна перевода "
            "НЕ заходили на области субтитров и ответов (Ctrl+Shift+L — расставить окна).", "warn")


class Overlay:
    """Полупрозрачное окно с текстом: перетаскивается мышкой, правый клик — скрыть."""

    def __init__(self, win, name, default_pos, width, title=""):
        self.win, self.name, self.width = win, name, width
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", config.OVERLAY_ALPHA)
        win.configure(bg="#111")
        self.default_pos = default_pos
        self.anchor = None  # функция, возвращающая область, к которой «прилипает» окно
        self.anchor_side = "above"
        # «склейка»: окно-ведомый стоит вплотную под ведущим, той же ширины, и двигается вместе с ним
        self.leader = None
        self.followers = []
        self._geom = None
        # manual = вы сами перетащили окно: оно больше не прилипает к области (F11 — вернуть авто)
        self.manual = core.SETTINGS.get(f"{name}_manual", False)
        width = core.SETTINGS.get(f"{name}_width", width)
        self.width = width
        x, y = core.SETTINGS.get(f"{name}_pos", default_pos)
        # если окно сохранено за краем экрана — возвращаем на место
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        if not (0 <= x <= sw - 100 and 0 <= y <= sh - 60):
            x, y = default_pos
        win.geometry(f"{width}x10+{x}+{y}")
        self._geom = (width, 10, x, y)

        # правый край окна — «ручка»: потяните мышкой, чтобы изменить ширину
        self.grip = tk.Frame(win, width=8, bg=config.GRIP_COLOR, cursor="sb_h_double_arrow")
        self.grip.pack(side="right", fill="y")
        self.grip.bind("<ButtonPress-1>", self._grip_start)
        self.grip.bind("<B1-Motion>", self._grip_move)
        self.grip.bind("<ButtonRelease-1>", lambda e: self._save_layout())
        self.status = tk.Label(win, text=title, fg="#8cf", bg="#111", font=("Segoe UI", 10), anchor="w")
        self.status.pack(fill="x", padx=10)
        # предыдущие реплики — бледным текстом над текущей (показывается, когда есть история)
        self.history = []
        self.hist_label = tk.Label(win, text="", fg="#8a8a8a", bg="#111", font=config.HISTORY_FONT, justify="left",
                                   wraplength=width - 32, padx=12, pady=2, anchor="w")
        self.label = tk.Label(win, text="", fg="#eee", bg="#111", font=config.FONT, justify="left",
                              wraplength=width - 32, padx=12, pady=6, anchor="w")
        self.label.pack(fill="both", expand=True)
        # оригинал — мелким серым под переводом (если включено в настройках)
        self.orig_label = tk.Label(win, text="", fg="#7d8590", bg="#111", font=("Segoe UI", max(8, config.FONT[1] - 3)),
                                   justify="left", wraplength=width - 32, padx=12, anchor="w")
        for w in (self.label, self.status, self.hist_label, self.orig_label):
            w.bind("<MouseWheel>", self._wheel)  # колесо мыши — ширина окна
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._end_move)
            w.bind("<Button-3>", lambda e: self.hide())
        self.visible = True
        win.after(200, lambda: exclude_from_capture(win))

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
        """Применить размер шрифта и прозрачность из настроек."""
        self.label.config(font=config.FONT)
        self.hist_label.config(font=config.HISTORY_FONT)
        self.orig_label.config(font=("Segoe UI", max(8, config.FONT[1] - 3)))
        try:
            self.win.attributes("-alpha", config.OVERLAY_ALPHA)
        except Exception:
            pass
        if not config.SHOW_ORIGINAL and self.orig_label.winfo_manager():
            self.orig_label.pack_forget()
        if self.visible:
            self.fit()

    def highlight_grip(self, on):
        self.grip.config(bg=config.GRIP_ACTIVE_COLOR if on else config.GRIP_COLOR)

    def _wheel(self, e):
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

    def _set_wrap(self, w):
        for lab in (self.label, self.hist_label, self.orig_label):
            lab.config(wraplength=w - 32)

    def fit(self):
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
            y = max(0, min(y, self.win.winfo_screenheight() - h))
            self._place(lw, h, lx, y)
            return
        reg = self.anchor() if (self.anchor and not self.manual) else None
        if reg and self.anchor_side in ("left", "right"):
            # окно сбоку от области (для вариантов ответа), верх — на уровне области
            x0, y0, rw, rh = reg
            sw = self.win.winfo_screenwidth()
            w = self.width
            self.win.update_idletasks()
            h = self._content_height()
            left_x, right_x = x0 - w - config.ANCHOR_GAP, x0 + rw + config.ANCHOR_GAP
            if self.anchor_side == "left":
                x = left_x if left_x >= 0 else right_x
            else:
                x = right_x if right_x + w <= sw else left_x
            x = min(max(0, x), sw - w)
            y = min(max(0, y0), self.win.winfo_screenheight() - h)
            self._place(w, h, x, y)
            return
        if reg:
            # окно ровно над выделенной областью и той же ширины
            x0, y0, rw, rh = reg
            w = max(rw, 300)
            x = max(0, x0 + (rw - w) // 2)
            if self.width != w:
                self.width = w
                self.label.config(wraplength=w - 32)
                self.hist_label.config(wraplength=w - 32)
                self.orig_label.config(wraplength=w - 32)
            self.win.update_idletasks()
            h = self._content_height()
            y = y0 - h - config.ANCHOR_GAP
            if y < 0:  # над областью нет места — ставим под неё
                y = y0 + rh + config.ANCHOR_GAP
            self._place(w, h, x, y)
            return
        self.win.update_idletasks()
        h = self._content_height()
        _, _, x, y = self._pos()
        self._place(self.width, h, x, y)

    def _content_height(self):
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
