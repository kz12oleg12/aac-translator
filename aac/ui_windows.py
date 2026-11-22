"""Рамки областей, окно истории, окно настроек."""


import os


import threading
import tkinter as tk


from . import config, core, history, hotkeys, tts, ui_overlay, voices


class RegionFrame:
    """Полупрозрачная рамка области на экране (режим расстановки): тащите — двигается,
    тяните за край или угол — меняется размер."""
    EDGE = 12  # ширина «края» для растягивания, px

    def __init__(self, app, title, color, reg, on_change):
        self.title, self.color, self.on_change = title, color, on_change
        self.win = w = tk.Toplevel(app.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.35)
        w.geometry(f"{reg[2]}x{reg[3]}+{reg[0]}+{reg[1]}")
        self.cv = tk.Canvas(w, bg=color, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda e: self.redraw())
        self.cv.bind("<Motion>", self._hover)
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", lambda e: self.on_change())
        self.warn = False
        w.after(200, lambda: ui_overlay.exclude_from_capture(w))

    def rect(self):
        self.win.update_idletasks()
        return (self.win.winfo_x(), self.win.winfo_y(), self.win.winfo_width(), self.win.winfo_height())

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        outline = "#ff3030" if self.warn else "#ffffff"
        cv.configure(bg="#c02020" if self.warn else self.color)
        cv.create_rectangle(2, 2, w - 3, h - 3, outline=outline, width=4)
        text = self.title + ("   ⚠ ПЕРЕСЕКАЕТСЯ!" if self.warn else "")
        cv.create_text(12, 10, text=text, anchor="nw", fill="white", font=("Segoe UI", 14, "bold"))
        cv.create_text(12, 34, text=f"{w}×{h}  · тащите — двигать, края/углы — размер",
                       anchor="nw", fill="white", font=("Segoe UI", 10))
        for x, y in ((0, 0), (w, 0), (0, h), (w, h)):  # уголки
            cv.create_rectangle(x - 9, y - 9, x + 9, y + 9, fill="white", outline="")

    def set_warn(self, on):
        if on != self.warn:
            self.warn = on
            self.redraw()

    def _edges(self, e):
        w, h, m = self.cv.winfo_width(), self.cv.winfo_height(), self.EDGE
        return (e.x < m, e.y < m, e.x > w - m, e.y > h - m)  # left, top, right, bottom

    def _hover(self, e):
        l, t, r, b = self._edges(e)
        cur = ("size_nw_se" if (l and t) or (r and b) else "size_ne_sw" if (r and t) or (l and b)
               else "sb_h_double_arrow" if (l or r) else "sb_v_double_arrow" if (t or b) else "fleur")
        self.cv.config(cursor=cur)

    def _press(self, e):
        self._mode = self._edges(e)
        self._start = (e.x_root, e.y_root) + self.rect()

    def _drag(self, e):
        sx, sy, x, y, w, h = self._start
        dx, dy = e.x_root - sx, e.y_root - sy
        l, t, r, b = self._mode
        if not any(self._mode):
            x, y = x + dx, y + dy                 # перенос целиком
        else:
            if l:
                x, w = x + dx, w - dx
            if r:
                w = w + dx
            if t:
                y, h = y + dy, h - dy
            if b:
                h = h + dy
            w, h = max(w, 60), max(h, 30)
        self.win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        self.on_change(live=True)

    def destroy(self):
        self.win.destroy()


def _normal_window(app, title, size):
    w = tk.Toplevel(app.root)
    w.title(title)
    w.geometry(size)
    w.configure(bg="#1a1d23")
    w.attributes("-topmost", True)
    ico = os.path.join(config.APP_DIR, "icon.ico")
    try:
        if os.path.exists(ico):
            w.iconbitmap(ico)
    except Exception:
        pass
    return w


class HistoryWindow:
    """Все переводы этой сессии с поиском."""

    def __init__(self, app):
        self.win = w = _normal_window(app, "AAC Translator — история переводов", "760x520")
        top = tk.Frame(w, bg="#1a1d23")
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Поиск:", fg="#ccc", bg="#1a1d23", font=("Segoe UI", 10)).pack(side="left")
        self.q = tk.StringVar()
        e = tk.Entry(top, textvariable=self.q, bg="#2b3040", fg="#eee", insertbackground="#eee",
                     relief="flat", font=("Segoe UI", 10), width=30)
        e.pack(side="left", padx=6)
        self.q.trace_add("write", lambda *a: self.render())
        for text, cmd in (("Открыть папку истории", self.open_folder), ("Копировать всё", self.copy_all)):
            tk.Button(top, text=text, command=cmd, bg="#2b3040", fg="#8cf", relief="flat", bd=0, padx=8,
                      activebackground="#3a4258", activeforeground="#fff", font=("Segoe UI", 9),
                      cursor="hand2").pack(side="right", padx=(6, 0))
        frame = tk.Frame(w, bg="#1a1d23")
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")
        self.t = tk.Text(frame, bg="#111317", fg="#ddd", font=("Segoe UI", 10), wrap="word", relief="flat",
                         yscrollcommand=sb.set, padx=8, pady=6, highlightthickness=0)
        self.t.pack(fill="both", expand=True)
        sb.config(command=self.t.yview)
        self.t.tag_config("meta", foreground="#6f8bbf", font=("Segoe UI", 8))
        self.t.tag_config("orig", foreground="#7d8590", font=("Segoe UI", 9))
        self.render()
        w.after(50, e.focus_set)

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _match(self, entry):
        q = self.q.get().strip().lower()
        return not q or q in (entry[2] + " " + entry[3]).lower()

    def _insert(self, entry):
        t, kind, orig, tr = entry
        self.t.insert("end", f"{t} · {kind}\n", "meta")
        if orig:
            self.t.insert("end", orig + "\n", "orig")
        self.t.insert("end", tr + "\n\n")

    def render(self):
        self.t.config(state="normal")
        self.t.delete("1.0", "end")
        items = [e for e in history.translation_history if self._match(e)]
        if not items:
            self.t.insert("end", "Пока пусто." if not self.q.get() else "Ничего не найдено.", "meta")
        for e in items:
            self._insert(e)
        self.t.see("end")
        self.t.config(state="disabled")

    def add(self, entry):
        if not self._match(entry):
            return
        self.t.config(state="normal")
        if self.t.get("1.0", "end").strip() in ("Пока пусто.", "Ничего не найдено."):
            self.t.delete("1.0", "end")
        self._insert(entry)
        self.t.see("end")
        self.t.config(state="disabled")

    def open_folder(self):
        os.makedirs(history.HISTORY_DIR, exist_ok=True)
        try:
            os.startfile(history.HISTORY_DIR)
        except Exception as e:
            core.log(f"Не удалось открыть папку: {e}", "error")

    def copy_all(self):
        parts = []
        for t, k, o, r in history.translation_history:
            if self._match((t, k, o, r)):
                parts.append(f"{t} {k}\n" + (o + "\n" if o else "") + r)
        self.win.clipboard_clear()
        self.win.clipboard_append("\n\n".join(parts))
        core.log("История скопирована в буфер обмена", "ok")


class SettingsWindow:
    """Внешний вид, озвучка и поведение — без правки файла."""

    def __init__(self, app):
        self.app = app
        self.win = w = _normal_window(app, "AAC Translator — настройки", "1000x840")
        left = tk.Frame(w, bg="#1a1d23")
        left.pack(side="left", fill="both", expand=True, pady=6)
        right = tk.Frame(w, bg="#1d2129")
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)
        pad = {"padx": 16, "pady": 4}

        def title(parent, text):
            tk.Label(parent, text=text, fg="#8cf", bg=parent["bg"], font=("Segoe UI", 11, "bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(6, 2))

        def label(parent, text):
            tk.Label(parent, text=text, fg="#ddd", bg=parent["bg"], font=("Segoe UI", 10),
                     anchor="w").pack(fill="x", **pad)

        def scale(parent, var, a, b, res=1):
            tk.Scale(parent, variable=var, from_=a, to=b, resolution=res, orient="horizontal",
                     command=lambda v: self.changed(), bg=parent["bg"], fg="#ddd", troughcolor="#2b3040",
                     highlightthickness=0, relief="flat", activebackground="#4d86ff", length=430).pack(padx=16,
                                                                                                    anchor="w")

        def check(parent, text, var):
            tk.Checkbutton(parent, text=text, variable=var, command=self.changed, bg=parent["bg"], fg="#ddd",
                           selectcolor="#2b3040", activebackground=parent["bg"], activeforeground="#fff",
                           font=("Segoe UI", 10), anchor="w", highlightthickness=0, bd=0).pack(fill="x", **pad)

        # ----- внешний вид -----
        title(left, "Окна перевода")
        label(left, "Размер шрифта перевода")
        self.size = tk.IntVar(value=config.FONT[1])
        scale(left, self.size, 10, 26)
        label(left, "Непрозрачность окон перевода, %")
        self.alpha = tk.IntVar(value=int(round(config.OVERLAY_ALPHA * 100)))
        scale(left, self.alpha, 40, 100, 5)
        label(left, "Сколько прошлых реплик показывать над текущей")
        self.hist = tk.IntVar(value=config.SUBS_HISTORY)
        scale(left, self.hist, 0, 3)
        label(left, "Убирать перевод через … секунд после того, как реплика исчезла")
        self.hide_delay = tk.DoubleVar(value=config.HIDE_DELAY)
        scale(left, self.hide_delay, 0, 30, 0.5)
        self.keep = tk.BooleanVar(value=config.KEEP_UNTIL_NEXT)
        check(left, "Не убирать перевод, пока не появится новая реплика", self.keep)
        self.orig = tk.BooleanVar(value=config.SHOW_ORIGINAL)
        check(left, "Показывать оригинал (английский) под переводом", self.orig)
        self.save = tk.BooleanVar(value=config.SAVE_HISTORY)
        check(left, "Сохранять историю переводов в файл (папка history)", self.save)
        self.ocrlog = tk.BooleanVar(value=config.SHOW_OCR_IN_LOG)
        check(left, "Показывать распознанный текст в журнале панели", self.ocrlog)
        self.skip_sys = tk.BooleanVar(value=config.SKIP_SYSTEM)
        check(left, "Не переводить и не озвучивать системные сообщения игры", self.skip_sys)
        self.gl_auto = tk.BooleanVar(value=config.GLOSSARY_AUTO)
        check(left, "Пополнять словарь сам (имена, предметы, места)", self.gl_auto)
        self.cache_on = tk.BooleanVar(value=config.CACHE_ENABLED)
        check(left, "Кэш переводов: повторы фраз — мгновенно и без запросов", self.cache_on)
        tk.Button(left, text="🗑 Очистить кэш переводов", command=self._clear_cache,
                  relief="flat", bg="#3a3f4b", fg="white", activebackground="#4a5060",
                  cursor="hand2").pack(anchor="w", padx=24, pady=(0, 6))
        self.indicator = tk.BooleanVar(value=config.SHOW_INDICATOR)
        check(left, "Значок «● AAC» поверх игры, пока включён автоперевод", self.indicator)

        # ----- окно чата -----
        title(left, "Окно перевода чата")
        self.chat_cover = tk.BooleanVar(value=config.CHAT_COVER)
        check(left, "Показывать перевод прямо поверх чата игры (та же область)", self.chat_cover)
        label(left, "Предельная высота окна чата, px (0 — сколько займут сообщения)")
        self.chat_height = tk.IntVar(value=config.CHAT_HEIGHT)
        scale(left, self.chat_height, 0, 600, 20)
        label(left, "Сколько сообщений чата хранить (для прокрутки)")
        self.chat_hist = tk.IntVar(value=config.CHAT_HISTORY)
        scale(left, self.chat_hist, 20, 1000, 10)
        label(left, "Непрозрачность окна чата, %")
        self.chat_alpha = tk.IntVar(value=int(round(config.CHAT_ALPHA * 100)))
        scale(left, self.chat_alpha, 20, 100, 5)
        crow = tk.Frame(left, bg=left["bg"])
        crow.pack(fill="x", padx=16, pady=(6, 0))
        tk.Label(crow, text="Цвет текста:", fg="#ddd", bg=left["bg"], font=("Segoe UI", 10)).pack(side="left")
        self.chat_fg_btn = tk.Button(crow, text="  Аа  ", bg="#111", fg=config.CHAT_FG, relief="flat", bd=0,
                                     font=("Segoe UI", 10, "bold"), activebackground="#222", cursor="hand2",
                                     command=self._pick_chat_color)
        self.chat_fg_btn.pack(side="left", padx=8)
        for col in ("#eeeeee", "#ffe08a", "#8cf0ff", "#9dff9d", "#ffb3e6"):
            tk.Button(crow, text=" ", bg=col, activebackground=col, relief="flat", bd=0, width=2, cursor="hand2",
                      command=lambda c=col: self._set_chat_color(c)).pack(side="left", padx=2)

        # ----- озвучка -----
        title(right, "Озвучка субтитров")
        self.tts_on = tk.BooleanVar(value=config.TTS_ENABLED)
        check(right, f"Озвучивать перевод субтитров  ({hotkeys.K('tts')})", self.tts_on)
        self.tts_name = tk.BooleanVar(value=config.TTS_READ_NAME)
        check(right, "Читать имя говорящего перед репликой", self.tts_name)
        self.tts_finish = tk.BooleanVar(value=config.TTS_FINISH_LINE)
        check(right, "Дочитывать реплику до конца (новая не обрывает старую)", self.tts_finish)

        def menu_style(m, width):
            m.config(bg="#2b3040", fg="#eee", activebackground="#3a4258", activeforeground="#fff",
                     relief="flat", highlightthickness=0, font=("Segoe UI", 9), bd=0, width=width)
            m["menu"].config(bg="#2b3040", fg="#eee", activebackground="#3a4258", font=("Segoe UI", 9))

        label(right, "Голоса")
        self.ENGINES = {"neural": "Microsoft — живые, онлайн (задержка 2–3 с)",
                        "silero": "Silero — нейросетевые, офлайн, быстрые",
                        "windows": "Windows — роботизированные, без интернета"}
        self.engine = tk.StringVar(value=self.ENGINES.get(config.TTS_ENGINE, self.ENGINES["neural"]))
        em = tk.OptionMenu(right, self.engine, *self.ENGINES.values(), command=lambda v: self._engine_changed())
        menu_style(em, 46)
        em.pack(anchor="w", padx=16)

        # голоса: мужчины / женщины / реплики без имени (у голосов Windows — один общий)
        grid = tk.Frame(right, bg=right["bg"])
        grid.pack(fill="x", padx=16, pady=(6, 0))

        def play_btn(row, cmd):
            return tk.Button(grid, text="▶", command=cmd, bg="#2b3040", fg="#8cf", relief="flat", bd=0, padx=10,
                             activebackground="#3a4258", activeforeground="#fff", font=("Segoe UI", 9),
                             cursor="hand2")
        self.gender_rows = {}
        self.gender_vars = {}
        for r, (g, title) in enumerate((("m", "Мужчины"), ("f", "Женщины"))):
            lab = tk.Label(grid, text=title, fg="#ddd", bg=right["bg"], font=("Segoe UI", 10), anchor="w", width=11)
            var = tk.StringVar(value="")
            om = tk.OptionMenu(grid, var, "", command=lambda v: self.changed())
            menu_style(om, 30)
            btn = play_btn(r, lambda g=g: self._test_gender(g))
            lab.grid(row=r, column=0, sticky="w", pady=2)
            om.grid(row=r, column=1, sticky="w", pady=2)
            btn.grid(row=r, column=2, padx=6, pady=2)
            self.gender_rows[g] = (lab, om, btn)
            self.gender_vars[g] = (var, om)
        self.vary = tk.BooleanVar(value=config.TTS_VARY_IN_GENDER)
        self.vary_cb = tk.Checkbutton(grid, text="Разные голоса внутри пола (у каждого персонажа свой)",
                                      variable=self.vary, command=self._vary_changed, bg=right["bg"], fg="#ddd",
                                      selectcolor="#2b3040", activebackground=right["bg"], activeforeground="#fff",
                                      font=("Segoe UI", 9), anchor="w", highlightthickness=0, bd=0)
        self.vary_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.voice_title = tk.Label(grid, text="Без имени", fg="#ddd", bg=right["bg"], font=("Segoe UI", 10),
                                    anchor="w", width=11)
        self.voice_title.grid(row=3, column=0, sticky="w", pady=2)
        self.voice = tk.StringVar(value="")
        self.voice_menu = tk.OptionMenu(grid, self.voice, "", command=lambda v: self.changed())
        menu_style(self.voice_menu, 30)
        self.voice_menu.grid(row=3, column=1, sticky="w", pady=2)
        play_btn(2, self._test_voice).grid(row=3, column=2, padx=6, pady=2)
        self.expressive = tk.BooleanVar(value=config.TTS_EXPRESSIVE)
        tk.Checkbutton(grid, text="Интонация: «!» — живее, «?» — вопросом, «…» — медленнее",
                       variable=self.expressive, command=self._expressive_changed, bg=right["bg"], fg="#ddd",
                       selectcolor="#2b3040", activebackground=right["bg"], activeforeground="#fff",
                       font=("Segoe UI", 9), anchor="w", highlightthickness=0, bd=0
                       ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.voice_note = tk.Label(right, text="", fg="#7d8590", bg=right["bg"],
                                   font=("Segoe UI", 8), anchor="w", justify="left", wraplength=440)
        self.voice_note.pack(fill="x", padx=16)
        label(right, "Скорость речи")
        self.rate = tk.IntVar(value=config.TTS_RATE)
        scale(right, self.rate, -5, 6)
        label(right, "Громкость, %")
        self.volume = tk.IntVar(value=config.TTS_VOLUME)
        scale(right, self.volume, 10, 100, 5)
        self.per_char = tk.BooleanVar(value=config.TTS_PER_CHARACTER)
        check(right, "Голос по полу персонажа (выкл — всем голос «без имени»)", self.per_char)
        crow = tk.Frame(right, bg=right["bg"])
        crow.pack(fill="x", padx=16)
        self.ru_only = tk.BooleanVar(value=config.TTS_RUSSIAN_ONLY)
        tk.Checkbutton(crow, text="Только русские голоса", variable=self.ru_only, command=self.changed,
                       bg=right["bg"], fg="#ddd", selectcolor="#2b3040", activebackground=right["bg"],
                       activeforeground="#fff", font=("Segoe UI", 10), highlightthickness=0, bd=0).pack(side="left")
        tk.Button(crow, text="🎭 Голоса персонажей…", command=lambda: CharactersWindow(app),
                  bg="#2b3040", fg="#8cf", relief="flat", bd=0, padx=8, activebackground="#3a4258",
                  activeforeground="#fff", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=12)
        self._win_voices = None
        self._ready = True
        self._fill_voice_menu()

    def _engine_key(self):
        for k, v in self.ENGINES.items():
            if v == self.engine.get():
                return k
        return "neural"

    def _engine_changed(self):
        tts.stop()
        config.TTS_ENGINE = self._engine_key()
        self._fill_voice_menu()
        self.changed()
        tts.warm()

    def _set_voice_items(self, names, current):
        menu = self.voice_menu["menu"]
        menu.delete(0, "end")
        for n in names:
            menu.add_command(label=n, command=lambda v=n: (self.voice.set(v), self.changed()))
        self.voice.set(current if current in names else (names[0] if names else ""))

    def _fill_gender_menus(self):
        """Голос для всех мужчин и для всех женщин (для движков с нейроголосами)."""
        eng = self._engine_key()
        neural_like = eng in ("neural", "silero")
        for g, (lab, om, btn) in self.gender_rows.items():
            for wdg in (lab, om, btn):
                (wdg.grid() if neural_like else wdg.grid_remove())
        (self.vary_cb.grid() if neural_like else self.vary_cb.grid_remove())
        self.voice_title.config(text="Без имени" if neural_like else "Голос")
        if not neural_like:
            return
        labels = dict(tts.tts_silero.VOICES) if eng == "silero" else dict(tts.NEURAL_VOICES)
        pool = voices.SILERO_POOL if eng == "silero" else voices.NEURAL_POOL
        vary = bool(self.vary.get())
        for g, (var, om) in self.gender_vars.items():
            names = [labels.get(v, v) for v in pool[g]]
            menu = om["menu"]
            menu.delete(0, "end")
            for n in names:
                menu.add_command(label=n, command=lambda v=n, var=var: (var.set(v), self.changed()))
            if vary:
                var.set("разные — у каждого свой")
                om.config(state="disabled")
            else:
                cur = voices.default_voice(eng, g) or pool[g][0]
                var.set(labels.get(cur, names[0]))
                om.config(state="normal")

    def _expressive_changed(self):
        config.TTS_EXPRESSIVE = bool(self.expressive.get())
        core.save_settings(tts_expressive=config.TTS_EXPRESSIVE)

    def _vary_changed(self):
        config.TTS_VARY_IN_GENDER = bool(self.vary.get())
        core.save_settings(tts_vary_in_gender=config.TTS_VARY_IN_GENDER)
        self._fill_gender_menus()
        self.changed()

    def _gender_voice_id(self, g):
        eng = self._engine_key()
        labels = tts.tts_silero.VOICES if eng == "silero" else tts.NEURAL_VOICES
        return next((v for v, lab in labels if lab == self.gender_vars[g][0].get()), "")

    def _test_gender(self, g):
        self.changed()
        eng = self._engine_key()
        vid = self._gender_voice_id(g) or (voices.SILERO_POOL if eng == "silero" else voices.NEURAL_POOL)[g][0]
        tts.say_test((vid, 0), "Так звучит мужской голос персонажей." if g == "m" else
                     "Так звучит женский голос персонажей.")

    def _fill_voice_menu(self):
        self._fill_gender_menus()
        if self._engine_key() == "silero":
            names = [lab for _, lab in tts.tts_silero.VOICES]
            self._set_voice_items(names, tts.tts_silero.label(config.TTS_SILERO_VOICE))
            if tts.tts_silero.installed():
                self.voice_note.config(text="Голоса считаются прямо на компьютере, без интернета — почти без задержки. "
                                            "В первый раз скачается модель (~100 МБ) и загрузится за 5–20 с.")
            else:
                self.voice_note.config(text="Нужна установка: закройте программу и запустите install_silero.bat "
                                            "из папки программы (скачает PyTorch, около 1 ГБ). "
                                            "Пока не установлено — читает голос Windows.")
        elif self._engine_key() == "neural":
            names = [label for _, label in tts.NEURAL_VOICES]
            self._set_voice_items(names, tts.neural_label(config.TTS_NEURAL_VOICE))
            self.voice_note.config(text="Бесплатные нейроголоса Microsoft (как «Читать вслух» в Edge). "
                                        "Русские звучат чище всего; многоязычные — живее, но с лёгким акцентом.")
        elif self._win_voices is None:
            self._set_voice_items(["по умолчанию"], "по умолчанию")
            self.voice_note.config(text="Загружаю список голосов Windows…")
            threading.Thread(target=lambda: core.events.put(("tts_voices", tts.list_voices())), daemon=True).start()
        else:
            self.fill_voices(self._win_voices)

    def fill_voices(self, voices):
        """Список голосов Windows (русские — первыми)."""
        if not self.alive():
            return
        self._win_voices = voices
        if self._engine_key() != "windows":
            return
        names = ["по умолчанию"] + [n for n, lang in sorted(voices, key=lambda v: (not v[1].startswith("ru"), v[0]))]
        self._set_voice_items(names, config.TTS_VOICE or "по умолчанию")
        ru = [n for n, lang in voices if lang.lower().startswith("ru")]
        if not voices:
            self.voice_note.config(text="Голоса не найдены (озвучка работает только в Windows).")
        elif not ru:
            self.voice_note.config(text="Русского голоса нет: Параметры → Время и язык → Речь → Добавить голоса.")
        else:
            self.voice_note.config(text=f"Русские голоса: {', '.join(ru)}")

    def _pick_chat_color(self):
        from tkinter import colorchooser
        col = colorchooser.askcolor(color=config.CHAT_FG, title="Цвет текста перевода чата", parent=self.win)[1]
        if col:
            self._set_chat_color(col)

    def _set_chat_color(self, col):
        config.CHAT_FG = col
        core.save_settings(chat_fg=col)
        self.chat_fg_btn.config(fg=col)
        self.changed()

    def _test_voice(self):
        self.changed()
        tts.say_test()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _clear_cache(self):
        from . import tcache
        n = tcache.size()
        tcache.clear()
        core.log(f"Кэш переводов очищен ({n} фраз).")
        core.events.put(("panel", None))

    def changed(self):
        config.FONT = ("Segoe UI", int(self.size.get()))
        config.HISTORY_FONT = ("Segoe UI", max(8, config.FONT[1] - 2))
        config.OVERLAY_ALPHA = int(self.alpha.get()) / 100
        config.SUBS_HISTORY = int(self.hist.get())
        config.SHOW_ORIGINAL = bool(self.orig.get())
        config.SAVE_HISTORY = bool(self.save.get())
        config.SHOW_OCR_IN_LOG = bool(self.ocrlog.get())
        config.SHOW_INDICATOR = bool(self.indicator.get())
        config.GLOSSARY_AUTO = bool(self.gl_auto.get())
        config.CACHE_ENABLED = bool(self.cache_on.get())
        core.save_settings(cache_enabled=config.CACHE_ENABLED)
        config.SKIP_SYSTEM = bool(self.skip_sys.get())
        if config.CHAT_COVER != bool(self.chat_cover.get()):
            from . import chat
            chat._state["cover_mode"] = None     # заново проверить, прячет ли Windows окно от снимков
        config.CHAT_COVER = bool(self.chat_cover.get())
        config.CHAT_HEIGHT = int(self.chat_height.get())
        config.CHAT_HISTORY = int(self.chat_hist.get())
        core.save_settings(chat_history=config.CHAT_HISTORY)
        app_lines = getattr(self.app, "chat_lines", None)
        if app_lines is not None and len(app_lines) > config.CHAT_HISTORY:
            del app_lines[:-config.CHAT_HISTORY]
        config.CHAT_ALPHA = int(self.chat_alpha.get()) / 100
        core.save_settings(chat_cover=config.CHAT_COVER, chat_height=config.CHAT_HEIGHT, chat_alpha=config.CHAT_ALPHA)
        core.save_settings(skip_system=config.SKIP_SYSTEM)
        core.save_settings(glossary_auto=config.GLOSSARY_AUTO)
        core.save_settings(show_indicator=config.SHOW_INDICATOR)
        config.HIDE_DELAY = float(self.hide_delay.get())
        config.KEEP_UNTIL_NEXT = bool(self.keep.get())
        # перевод висит дольше обычной «страховки» — страховку отодвигаем
        config.MAX_SHOW_TIME = max(60, config.HIDE_DELAY + 30)
        core.save_settings(hide_delay=config.HIDE_DELAY, keep_until_next=config.KEEP_UNTIL_NEXT)
        core.save_settings(font_size=config.FONT[1], overlay_alpha=config.OVERLAY_ALPHA, subs_history=config.SUBS_HISTORY,
                      show_original=config.SHOW_ORIGINAL, save_history=config.SAVE_HISTORY, show_ocr_in_log=config.SHOW_OCR_IN_LOG)
        if getattr(self, "_ready", False):
            was_on = config.TTS_ENABLED
            config.TTS_ENABLED = bool(self.tts_on.get())
            config.TTS_READ_NAME = bool(self.tts_name.get())
            config.TTS_FINISH_LINE = bool(self.tts_finish.get())
            config.TTS_ENGINE = self._engine_key()
            v = self.voice.get()
            if config.TTS_ENGINE == "silero":
                if v:
                    config.TTS_SILERO_VOICE = tts.tts_silero.voice_id(v)
            elif config.TTS_ENGINE == "neural":
                if v:
                    config.TTS_NEURAL_VOICE = tts.neural_id(v)
            else:
                config.TTS_VOICE = "" if v == "по умолчанию" else v
            if config.TTS_ENGINE in ("neural", "silero") and not self.vary.get():
                for g in ("m", "f"):
                    vid = self._gender_voice_id(g)
                    if vid:
                        voices.set_default_voice(config.TTS_ENGINE, g, vid)
            config.TTS_PER_CHARACTER = bool(self.per_char.get())
            config.TTS_RUSSIAN_ONLY = bool(self.ru_only.get())
            core.save_settings(tts_per_character=config.TTS_PER_CHARACTER, tts_russian_only=config.TTS_RUSSIAN_ONLY)
            config.TTS_RATE = int(self.rate.get())
            config.TTS_VOLUME = int(self.volume.get())
            core.save_settings(tts_enabled=config.TTS_ENABLED, tts_read_name=config.TTS_READ_NAME,
                               tts_voice=config.TTS_VOICE, tts_engine=config.TTS_ENGINE, tts_finish_line=config.TTS_FINISH_LINE,
                               tts_neural_voice=config.TTS_NEURAL_VOICE,
                               tts_silero_voice=config.TTS_SILERO_VOICE, tts_rate=config.TTS_RATE, tts_volume=config.TTS_VOLUME)
            tts.apply_settings()
            if was_on and not config.TTS_ENABLED:
                tts.stop()
        for ov in (self.app.subs, self.app.answers, self.app.quest, getattr(self.app, "chat", None)):
            if ov is not None:
                ov.apply_style()
        if config.SUBS_HISTORY == 0:
            self.app.subs.clear_history()


class CharactersWindow:
    """Персонажи, которых уже слышали: пол и голос (авто или свой)."""
    GENDERS = {"": "авто", "m": "мужской", "f": "женский"}

    def __init__(self, app):
        old = getattr(app, "chars_win", None)
        if old is not None and old.alive():
            old.win.lift()
            return
        app.chars_win = self
        self.win = w = _normal_window(app, "AAC Translator — голоса персонажей", "900x540")
        engine = config.TTS_ENGINE
        if engine == "silero":
            self.voices = [(v, tts.tts_silero.label(v)) for v in voices.SILERO_POOL["f"] + voices.SILERO_POOL["m"]]
        else:
            self.voices = [(v, tts.neural_label(v)) for v in voices.NEURAL_POOL["f"] + voices.NEURAL_POOL["m"]]
        self.engine = "silero" if engine == "silero" else "neural"
        note = ("Имена берутся из субтитров. Пол угадывается по речи («я пришла» / «я пришёл») и по имени — "
                "поправьте, если ошиблось. «авто» — голос подбирается сам, у каждого персонажа свой.")
        if engine == "windows":
            note = "Сейчас выбраны голоса Windows — разные голоса персонажей работают только с Microsoft или Silero. " + note
        tk.Label(w, text=note, fg="#9aa4b2", bg="#1a1d23", font=("Segoe UI", 9), justify="left",
                 wraplength=870, anchor="w").pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(w, text="Голос для всех мужчин и для всех женщин задаётся в Настройках (раздел «Озвучка»), "
                         "здесь — исключения для отдельных персонажей.", fg="#7d8590", bg="#1a1d23",
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=12, pady=(0, 8))
        outer = tk.Frame(w, bg="#1a1d23")
        outer.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        canvas = tk.Canvas(outer, bg="#1a1d23", highlightthickness=0)
        sb = tk.Scrollbar(outer, command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=sb.set)
        self.body = tk.Frame(canvas, bg="#1a1d23")
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        wheel = lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self.render()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _menu(self, parent, var, values, cmd, width):
        m = tk.OptionMenu(parent, var, *values, command=lambda v: cmd())
        m.config(bg="#2b3040", fg="#eee", activebackground="#3a4258", activeforeground="#fff", relief="flat",
                 highlightthickness=0, font=("Segoe UI", 9), bd=0, width=width)
        m["menu"].config(bg="#2b3040", fg="#eee", activebackground="#3a4258", font=("Segoe UI", 9))
        return m

    def render(self):
        for ch in self.body.winfo_children():
            ch.destroy()
        chars = voices.all_chars()
        if not chars:
            tk.Label(self.body, text="Пока никого — персонажи появятся здесь, когда заговорят в субтитрах.",
                     fg="#ccc", bg="#1a1d23", font=("Segoe UI", 10)).pack(anchor="w", pady=20)
            return
        for key, c in chars:
            av = voices.voice_for(key, self.engine, auto_only=True)
            auto = "авто" + (f" ({dict(self.voices).get(av[0], av[0]).split(' — ')[0]})" if av else "")
            labels = [auto] + [lab for _, lab in self.voices]
            row = tk.Frame(self.body, bg="#1a1d23")
            row.pack(fill="x", pady=2)
            name = c.get("ru") or c.get("en") or key
            if c.get("en") and c.get("ru") and c["en"] != c["ru"]:
                name += f" ({c['en']})"
            tk.Label(row, text=name, fg="#eee", bg="#1a1d23", font=("Segoe UI", 10), width=28,
                     anchor="w").pack(side="left")
            auto_g = voices.gender({k: v for k, v in c.items() if k != "gender_manual"})
            gvals = [f"авто ({self.GENDERS[auto_g]})", "мужской", "женский"]
            gman = c.get("gender_manual", "")
            gv = tk.StringVar(value=gvals[0] if not gman else self.GENDERS[gman])
            self._menu(row, gv, gvals, lambda k=key, v=gv: self._set_gender(k, v.get()), 14).pack(side="left", padx=4)
            cur = c.get(f"voice_{self.engine}", "")
            vv = tk.StringVar(value=dict(self.voices).get(cur, auto) if cur else auto)
            self._menu(row, vv, labels, lambda k=key, v=vv: self._set_voice(k, v.get()), 30).pack(side="left", padx=4)
            tk.Button(row, text="▶", command=lambda k=key, n=name: self._test(k, n), bg="#2b3040", fg="#8cf",
                      relief="flat", bd=0, padx=8, activebackground="#3a4258", activeforeground="#fff",
                      cursor="hand2").pack(side="left", padx=4)
            tk.Button(row, text="✕", command=lambda k=key: (voices.forget(k), self.render()), bg="#1a1d23",
                      fg="#a66", relief="flat", bd=0, padx=6, activebackground="#3a4258", cursor="hand2").pack(side="left")

    def _set_gender(self, key, label):
        g = "m" if label == "мужской" else "f" if label == "женский" else ""
        voices.set_manual(key, gender_value=g)
        self.render()

    def _set_voice(self, key, label):
        vid = next((v for v, lab in self.voices if lab == label), "")
        voices.set_manual(key, voice=vid, engine=self.engine)

    def _test(self, key, name):
        vp = voices.voice_for(key, self.engine)
        tts.say_test(vp, f"{name.split(' (')[0]}. Привет, путник! Так звучит мой голос.")


def regions_overlap(a, b):
    if not a or not b:
        return False
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
