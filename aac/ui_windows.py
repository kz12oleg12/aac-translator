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
        self.win = w = _normal_window(app, "AAC Translator — настройки", "1000x500")
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

        label(right, "Голос")
        vrow = tk.Frame(right, bg=right["bg"])
        vrow.pack(fill="x", padx=16)
        self.voice = tk.StringVar(value="")
        self.voice_menu = tk.OptionMenu(vrow, self.voice, "", command=lambda v: self.changed())
        menu_style(self.voice_menu, 30)
        self.voice_menu.pack(side="left")
        tk.Button(vrow, text="▶ Проверить голос", command=self._test_voice, bg="#2b3040", fg="#8cf", relief="flat",
                  bd=0, padx=8, activebackground="#3a4258", activeforeground="#fff", font=("Segoe UI", 9),
                  cursor="hand2").pack(side="left", padx=8)
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
        check(right, "Свой голос для каждого персонажа (мужской / женский)", self.per_char)
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

    def _fill_voice_menu(self):
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

    def _test_voice(self):
        self.changed()
        tts.say_test()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def changed(self):
        config.FONT = ("Segoe UI", int(self.size.get()))
        config.HISTORY_FONT = ("Segoe UI", max(8, config.FONT[1] - 2))
        config.OVERLAY_ALPHA = int(self.alpha.get()) / 100
        config.SUBS_HISTORY = int(self.hist.get())
        config.SHOW_ORIGINAL = bool(self.orig.get())
        config.SAVE_HISTORY = bool(self.save.get())
        config.SHOW_OCR_IN_LOG = bool(self.ocrlog.get())
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
        for ov in (self.app.subs, self.app.answers, self.app.quest):
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
        # голоса по умолчанию для мужчин и женщин
        drow = tk.Frame(w, bg="#1a1d23")
        drow.pack(fill="x", padx=12, pady=(0, 8))
        pool = voices.SILERO_POOL if self.engine == "silero" else voices.NEURAL_POOL
        names = dict(self.voices)
        self.AUTO = "разные (подбираются сами)"
        for g, title in (("m", "Мужчины по умолчанию:"), ("f", "Женщины по умолчанию:")):
            tk.Label(drow, text=title, fg="#ddd", bg="#1a1d23", font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
            cur = voices.default_voice(self.engine, g)
            var = tk.StringVar(value=names.get(cur, self.AUTO) if cur else self.AUTO)
            vals = [self.AUTO] + [names[v] for v in pool[g]]
            self._menu(drow, var, vals, lambda g=g, v=var: self._set_default(g, v.get()), 24).pack(side="left",
                                                                                                    padx=(0, 16))
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

    def _set_default(self, g, label):
        vid = next((v for v, lab in self.voices if lab == label), "")
        voices.set_default_voice(self.engine, g, vid)
        self.render()          # «авто (…)» у персонажей теперь показывает новый голос

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
