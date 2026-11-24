"""Разделы главного окна, перенесённые из старых окон: Окна перевода, Голос и интонация, Персонажи,
История, Словарь. Подмешиваются в ui_shell.Shell."""
import os
import threading
import tkinter as tk

from . import config, core, glossary, history, hotkeys, tts, voices
from . import ui_kit as K

GENDER_COLORS = {"f": "#ffb3d9", "m": "#8ce0ff"}
KIND_COLORS = {"Субтитры": K.ACCENT_TEXT, "Ответы": K.AMBER, "Задание": "#3fb37f", "Подсказка": "#ffb3d9",
               "Надпись": "#8ce0ff", "Чат": "#9be89b", "Чат (вы)": "#9be89b"}
CHAT_COLORS = ("#eeeeee", "#ffe08a", "#8cf0ff", "#9dff9d", "#ffb3e6")


class SectionsMixin:
    # ---------- общее ----------
    def _apply_overlays(self):
        for ov in (self.app.subs, self.app.answers, self.app.quest, getattr(self.app, "chat", None)):
            if ov is not None:
                ov.apply_style()
        if config.SUBS_HISTORY == 0:
            self.app.subs.clear_history()

    def _rebuild(self, sid):
        """Пересобрать раздел (например, сменился движок голосов) и показать его снова."""
        old = self.sections.pop(sid, None)
        if old is not None:
            old.destroy()
        if self.current == sid:
            self.current = None
            self.show(sid)

    def _page_plain(self, title, sub=None):
        """Раздел без общей прокрутки (у списка своя)."""
        frame = tk.Frame(self.content, bg=K.BG)
        body = tk.Frame(frame, bg=K.BG)
        body.pack(fill="both", expand=True, padx=26, pady=20)
        hdr = K.section_title(body, title, sub)
        hdr.pack(fill="x", pady=(0, 14))
        for w in [hdr] + hdr.winfo_children():
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._end_move)
        return frame, body

    # ---------- Окна перевода ----------
    def _build_win(self):
        sc, b = self._page("Окна перевода", "Как выглядят субтитры, ответы и подсказки поверх игры. "
                                            "Образец справа меняется сразу.")
        cols = tk.Frame(b, bg=K.BG)
        cols.pack(fill="x")
        left = tk.Frame(cols, bg=K.BG)
        left.pack(side="left", fill="both", expand=True)
        c, ci = K.card(left, padx=16, pady=14)
        c.pack(fill="x")

        def font_set(v, final):
            config.FONT = ("Segoe UI", int(v))
            config.HISTORY_FONT = ("Segoe UI", max(8, int(v) - 2))
            self._win_preview()
            if final:
                core.save_settings(font_size=config.FONT[1])
                self._apply_overlays()

        def alpha_set(v, final):
            config.OVERLAY_ALPHA = v / 100
            if final:
                core.save_settings(overlay_alpha=config.OVERLAY_ALPHA)
                self._apply_overlays()

        def hist_set(v, final):
            config.SUBS_HISTORY = int(v)
            self._win_preview()
            if final:
                core.save_settings(subs_history=config.SUBS_HISTORY)
                self._apply_overlays()

        def delay_set(v, final):
            config.HIDE_DELAY = float(v)
            config.MAX_SHOW_TIME = max(60, config.HIDE_DELAY + 30)
            if final:
                core.save_settings(hide_delay=config.HIDE_DELAY)
        self.win_sliders = [
            K.SliderRow(ci, "Размер шрифта", 10, 26, 1, lambda: config.FONT[1], font_set, lambda v: f"{int(v)}"),
            K.SliderRow(ci, "Непрозрачность", 40, 100, 5, lambda: int(round(config.OVERLAY_ALPHA * 100)), alpha_set,
                        lambda v: f"{int(v)}%"),
            K.SliderRow(ci, "Прошлых реплик над текущей", 0, 3, 1, lambda: config.SUBS_HISTORY, hist_set,
                        lambda v: f"{int(v)}"),
            K.SliderRow(ci, "Убирать через, после того как реплика исчезла", 0, 30, 0.5,
                        lambda: config.HIDE_DELAY, delay_set, lambda v: f"{v:g} с"),
        ]
        for i, r in enumerate(self.win_sliders):
            r.pack(fill="x", pady=(0 if i == 0 else 14, 0))

        def flag(attr, key, extra=None):
            def s(v):
                setattr(config, attr, bool(v))
                core.save_settings(**{key: bool(v)})
                if extra:
                    extra()
                self._win_preview()
            return s
        c, ci = K.card(left, padx=16, pady=4)
        c.pack(fill="x", pady=(12, 0))
        self.win_rows = [
            K.ToggleRow(ci, "Не убирать, пока нет новой реплики", None, lambda: config.KEEP_UNTIL_NEXT,
                        flag("KEEP_UNTIL_NEXT", "keep_until_next")),
            K.ToggleRow(ci, "Показывать оригинал под переводом", None, lambda: config.SHOW_ORIGINAL,
                        flag("SHOW_ORIGINAL", "show_original", self._apply_overlays)),
            K.ToggleRow(ci, "Значок «AAC» поверх игры", "виден, даже когда окна перевода скрыты",
                        lambda: config.SHOW_INDICATOR, flag("SHOW_INDICATOR", "show_indicator"), last=True),
        ]
        for r in self.win_rows:
            r.pack(fill="x")

        # образец
        prev = tk.Frame(cols, bg="#2b2119", width=300)
        prev.pack(side="left", fill="y", padx=(14, 0))
        prev.pack_propagate(False)
        K.label(prev, "Образец", 9, "#c9b9a6", bg="#2b2119").pack(anchor="w", padx=14, pady=(12, 0))
        tk.Frame(prev, bg="#2b2119").pack(fill="both", expand=True)
        box = tk.Frame(prev, bg="#14141a")
        box.pack(fill="x", padx=12, pady=(0, 8))
        self.pv_prev = tk.Label(box, text="Кеспер: Принеси кости — и я расскажу.", bg="#14141a", fg=K.DIM,
                                anchor="w", justify="left", wraplength=230)
        self.pv_main = tk.Label(box, text="Ренальд: Держись рядом! Ты слышал это?", bg="#14141a", fg="#ffffff",
                                anchor="w", justify="left", wraplength=230)
        self.pv_orig = tk.Label(box, text="Renald: Stay close! Did you hear that?", bg="#14141a", fg=K.DIM,
                                anchor="w", justify="left", wraplength=230, font=K.f(8))
        self.pv_box = box
        ans = tk.Frame(prev, bg="#14141a")
        ans.pack(fill="x", padx=12, pady=(0, 12))
        self.pv_ans = [tk.Label(ans, text=t, bg="#14141a", fg="#ffffff", anchor="w") for t in
                       ("1. Я пойду первым.", "2. Что там может быть?")]
        for w in self.pv_ans:
            w.pack(fill="x", padx=10, pady=1)

        # окно чата
        c, ci = K.card(b, padx=16, pady=12)
        c.pack(fill="x", pady=(14, 0))
        K.h2(ci, "Окно чата").pack(anchor="w")

        def cover_set(v):
            from . import chat
            config.CHAT_COVER = bool(v)
            chat._state["cover_mode"] = None
            core.save_settings(chat_cover=config.CHAT_COVER)
            self.app.chat.apply_style()
        self.chat_cover_row = K.ToggleRow(ci, "Перевод прямо поверх чата игры", "та же область, что и чат",
                                          lambda: config.CHAT_COVER, cover_set)
        self.chat_cover_row.pack(fill="x")
        grid = tk.Frame(ci, bg=K.CARD)
        grid.pack(fill="x", pady=(10, 0))

        def ch_h(v, final):
            config.CHAT_HEIGHT = int(v)
            if final:
                core.save_settings(chat_height=config.CHAT_HEIGHT)
                self.app.chat.apply_style()

        def ch_hist(v, final):
            config.CHAT_HISTORY = int(v)
            if final:
                core.save_settings(chat_history=config.CHAT_HISTORY)
                lines = getattr(self.app, "chat_lines", None)
                if lines is not None and len(lines) > config.CHAT_HISTORY:
                    del lines[:-config.CHAT_HISTORY]

        def ch_alpha(v, final):
            config.CHAT_ALPHA = v / 100
            if final:
                core.save_settings(chat_alpha=config.CHAT_ALPHA)
                self.app.chat.apply_style()
        self.chat_sliders = [
            K.SliderRow(grid, "Высота, px (0 — по сообщениям)", 0, 600, 20, lambda: config.CHAT_HEIGHT, ch_h,
                        lambda v: f"{int(v)}"),
            K.SliderRow(grid, "Хранить сообщений", 20, 1000, 10, lambda: config.CHAT_HISTORY, ch_hist,
                        lambda v: f"{int(v)}"),
            K.SliderRow(grid, "Непрозрачность", 20, 100, 5, lambda: int(round(config.CHAT_ALPHA * 100)), ch_alpha,
                        lambda v: f"{int(v)}%"),
        ]
        for i, r in enumerate(self.chat_sliders):
            r.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0 if i % 2 == 0 else 20, 0), pady=(0, 12))
            grid.columnconfigure(i % 2, weight=1, uniform="c")
        crow = tk.Frame(ci, bg=K.CARD)
        crow.pack(fill="x")
        K.label(crow, "Цвет текста", 10, K.TEXT2).pack(side="left")
        self.chat_swatches = {}
        for col in CHAT_COLORS:
            sw = tk.Frame(crow, bg=col, width=24, height=24, cursor="hand2", highlightthickness=2)
            sw.pack(side="left", padx=(10, 0))
            sw.bind("<Button-1>", lambda e, c_=col: self._chat_color(c_))
            self.chat_swatches[col] = sw
        K.button(crow, "Другой…", self._chat_color_pick, kind="ghost", size=9).pack(side="left", padx=(12, 0))
        return sc

    def _chat_color(self, col):
        config.CHAT_FG = col
        core.save_settings(chat_fg=col)
        self.app.chat.apply_style()
        self._refresh_win()

    def _chat_color_pick(self):
        from tkinter import colorchooser
        col = colorchooser.askcolor(color=config.CHAT_FG, title="Цвет текста перевода чата", parent=self.win)[1]
        if col:
            self._chat_color(col)

    def _win_preview(self):
        if not hasattr(self, "pv_main"):
            return
        size = config.FONT[1]
        for w in (self.pv_prev, self.pv_main, self.pv_orig):
            w.pack_forget()
        if config.SUBS_HISTORY > 0:
            self.pv_prev.config(font=K.f(max(8, size - 2)))
            self.pv_prev.pack(fill="x", padx=10, pady=(8, 0))
        self.pv_main.config(font=K.f(size, "bold"))
        self.pv_main.pack(fill="x", padx=10, pady=(8 if config.SUBS_HISTORY == 0 else 2, 2))
        if config.SHOW_ORIGINAL:
            self.pv_orig.pack(fill="x", padx=10, pady=(0, 8))
        else:
            self.pv_main.pack_configure(pady=(8 if config.SUBS_HISTORY == 0 else 2, 8))
        for w in self.pv_ans:
            w.config(font=K.f(size))

    def _refresh_win(self):
        for r in self.win_sliders + self.chat_sliders:
            r.sync()
        for r in self.win_rows + [self.chat_cover_row]:
            r.sync()
        for col, sw in self.chat_swatches.items():
            on = col.lower() == str(config.CHAT_FG).lower()
            sw.config(highlightbackground="#ffffff" if on else K.CARD, highlightcolor="#ffffff" if on else K.CARD)
        self._win_preview()

    # ---------- Голос и интонация ----------
    ENGINES = [("windows", "Windows", "встроенный"), ("neural", "Нейроголоса", "онлайн, Microsoft"),
               ("silero", "Silero", "офлайн, быстро")]

    def _save_tts(self):
        core.save_settings(tts_enabled=config.TTS_ENABLED, tts_read_name=config.TTS_READ_NAME,
                           tts_voice=config.TTS_VOICE, tts_engine=config.TTS_ENGINE,
                           tts_finish_line=config.TTS_FINISH_LINE, tts_neural_voice=config.TTS_NEURAL_VOICE,
                           tts_silero_voice=config.TTS_SILERO_VOICE, tts_rate=config.TTS_RATE,
                           tts_volume=config.TTS_VOLUME, tts_per_character=config.TTS_PER_CHARACTER,
                           tts_russian_only=config.TTS_RUSSIAN_ONLY)
        tts.apply_settings()

    def _build_voice(self):
        sc, b = self._page("Голос и интонация")
        hdr = b.winfo_children()[0]
        right = tk.Frame(hdr, bg=K.BG)
        right.place(relx=1.0, rely=0.0, anchor="ne")
        K.label(right, "Озвучивать субтитры", 10, K.TEXT2).pack(side="left")
        self.tts_chip = K.key_chip(right, hotkeys.K("tts"))
        self.tts_chip.pack(side="left", padx=8)

        def tts_set(v):
            config.TTS_ENABLED = bool(v)
            if not v:
                tts.stop()
            self._save_tts()
        self.tts_toggle = K.Toggle(right, config.TTS_ENABLED, tts_set)
        self.tts_toggle.pack(side="left")

        def engine_set(k):
            if k == config.TTS_ENGINE:
                return
            tts.stop()
            config.TTS_ENGINE = k
            self._save_tts()
            tts.warm()
            self.after_idle_rebuild("voice")
        K.Segmented(b, self.ENGINES, lambda: config.TTS_ENGINE, engine_set).pack(fill="x")

        c, ci = K.card(b, padx=16, pady=12)
        c.pack(fill="x", pady=(14, 0))
        K.h2(ci, "Голоса").pack(anchor="w", pady=(0, 8))
        self._voice_rows(ci)
        self.voice_note = K.label(ci, "", 9, K.DIM, wraplength=600)
        self.voice_note.pack(anchor="w", pady=(8, 0))
        link = K.label(ci, "Голоса персонажей →", 9, K.ACCENT_TEXT)
        link.config(cursor="hand2")
        link.bind("<Button-1>", lambda e: self.show("chars"))
        link.pack(anchor="e")

        c, ci = K.card(b, padx=16, pady=12)
        c.pack(fill="x", pady=(12, 0))
        g = tk.Frame(ci, bg=K.CARD)
        g.pack(fill="x")

        def rate_set(v, final):
            config.TTS_RATE = int(v)
            if final:
                self._save_tts()

        def vol_set(v, final):
            config.TTS_VOLUME = int(v)
            if final:
                self._save_tts()
        self.voice_sliders = [
            K.SliderRow(g, "Скорость речи", -5, 6, 1, lambda: config.TTS_RATE, rate_set, lambda v: f"{int(v):+d}"),
            K.SliderRow(g, "Громкость", 10, 100, 5, lambda: config.TTS_VOLUME, vol_set, lambda v: f"{int(v)}%"),
        ]
        for i, r in enumerate(self.voice_sliders):
            r.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 24, 0))
            g.columnconfigure(i, weight=1, uniform="v")

        tiles = tk.Frame(b, bg=K.BG)
        tiles.pack(fill="x", pady=(12, 0))

        def flag(attr, key, extra=None):
            def s(v):
                setattr(config, attr, bool(v))
                core.save_settings(**{key: bool(v)})
                tts.apply_settings()
                if extra:
                    extra()
            return s
        specs = [("♂♀", "Голос по полу", "мужчинам мужской", "TTS_PER_CHARACTER", "tts_per_character", None),
                 ("≈", "Разные внутри пола", "у каждого свой", "TTS_VARY_IN_GENDER", "tts_vary_in_gender",
                  lambda: self.after_idle_rebuild("voice")),
                 ("!?", "Интонация", "«!», «?», «…»", "TTS_EXPRESSIVE", "tts_expressive", None),
                 ("⏵", "Дочитывать", "новая не обрывает", "TTS_FINISH_LINE", "tts_finish_line", None),
                 ("Аа", "Читать имя", "«Ренальд: …»", "TTS_READ_NAME", "tts_read_name", None),
                 ("RU", "Только русские", "без многоязычных", "TTS_RUSSIAN_ONLY", "tts_russian_only",
                  lambda: self.after_idle_rebuild("voice"))]
        self.voice_tiles = []
        for i, (ic, t, s_, attr, key, extra) in enumerate(specs):
            tile = K.Tile(tiles, ic, t, s_, None, lambda a=attr: getattr(config, a), flag(attr, key, extra))
            tile.grid(row=i // 3, column=i % 3, sticky="nsew", padx=(0 if i % 3 == 0 else 10, 0), pady=(0, 10))
            tiles.columnconfigure(i % 3, weight=1, uniform="vt")
            self.voice_tiles.append(tile)

        bar = tk.Frame(b, bg=K.SIDEBAR, highlightthickness=1, highlightbackground=K.LINE)
        bar.pack(fill="x", pady=(4, 0))
        tx = tk.Frame(bar, bg=K.SIDEBAR)
        tx.pack(side="left", fill="x", expand=True, padx=16, pady=10)
        K.label(tx, "Проверить на фразе", 9, K.DIM, bg=K.SIDEBAR).pack(anchor="w")
        K.label(tx, "«Ренальд: Держись рядом! Ты слышал это?..»", 10, K.TEXT, bg=K.SIDEBAR).pack(anchor="w")
        K.button(bar, "▶ Прослушать", lambda: tts.say_test(), kind="primary").pack(side="right", padx=14)
        return sc

    def after_idle_rebuild(self, sid):
        self.win.after_idle(lambda: self._rebuild(sid))

    def _voice_rows(self, parent):
        eng = config.TTS_ENGINE
        grid = tk.Frame(parent, bg=K.CARD)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        self.voice_vars = {}

        def row(r, title, var, names, cmd, test, disabled=False):
            K.label(grid, title, 10, K.TEXT2, width=11).grid(row=r, column=0, sticky="w", pady=3)
            om = K.select(grid, var, names or [""], cmd, width=34)
            if disabled:
                om.config(state="disabled", disabledforeground=K.DIM)
            om.grid(row=r, column=1, sticky="ew", pady=3)
            pb = tk.Label(grid, text="▶", bg=K.ACCENT_TINT, fg=K.ACCENT_TEXT, font=K.f(10), width=3, cursor="hand2")
            pb.grid(row=r, column=2, padx=(8, 0), pady=3, sticky="ns")
            pb.bind("<Button-1>", lambda e: test())
            return om

        if eng in ("neural", "silero"):
            labels = dict(tts.tts_silero.VOICES) if eng == "silero" else dict(tts.NEURAL_VOICES)
            pool = voices.SILERO_POOL if eng == "silero" else voices.NEURAL_POOL
            vary = config.TTS_VARY_IN_GENDER
            for r, (g, title) in enumerate((("m", "Мужчины"), ("f", "Женщины"))):
                names = [labels.get(v, v) for v in pool[g]]
                var = tk.StringVar()
                if vary:
                    var.set("разные — у каждого свой")
                else:
                    cur = voices.default_voice(eng, g) or pool[g][0]
                    var.set(labels.get(cur, names[0] if names else ""))

                def set_g(g=g, var=var):
                    vid = next((v for v, lab in labels.items() if lab == var.get()), "")
                    if vid:
                        voices.set_default_voice(eng, g, vid)

                def test_g(g=g, var=var):
                    vid = next((v for v, lab in labels.items() if lab == var.get()), "") or pool[g][0]
                    tts.say_test((vid, 0), "Так звучит мужской голос персонажей." if g == "m" else
                                 "Так звучит женский голос персонажей.")
                row(r, title, var, names, set_g, test_g, disabled=vary)
                self.voice_vars[g] = var
            names = [lab for _, lab in (tts.tts_silero.VOICES if eng == "silero" else tts.NEURAL_VOICES)]
            cur = (tts.tts_silero.label(config.TTS_SILERO_VOICE) if eng == "silero"
                   else tts.neural_label(config.TTS_NEURAL_VOICE))
            var = tk.StringVar(value=cur)

            def set_main(var=var):
                if eng == "silero":
                    config.TTS_SILERO_VOICE = tts.tts_silero.voice_id(var.get())
                else:
                    config.TTS_NEURAL_VOICE = tts.neural_id(var.get())
                self._save_tts()
            row(2, "Без имени", var, names, set_main, lambda: tts.say_test())
        else:
            var = tk.StringVar(value=config.TTS_VOICE or "по умолчанию")

            def set_win(var=var):
                config.TTS_VOICE = "" if var.get() == "по умолчанию" else var.get()
                self._save_tts()
            self.win_voice_menu = row(0, "Голос", var, ["по умолчанию"], set_win, lambda: tts.say_test())
            self.win_voice_var = var
            if getattr(self, "_win_voices", None) is None:
                threading.Thread(target=lambda: core.events.put(("tts_voices", tts.list_voices())),
                                 daemon=True).start()
            else:
                self.win.after_idle(lambda: self.fill_voices(self._win_voices))

    def fill_voices(self, found):
        """Список голосов Windows пришёл из фонового потока."""
        self._win_voices = found
        menu = getattr(self, "win_voice_menu", None)
        if menu is None or config.TTS_ENGINE != "windows":
            return
        try:
            names = ["по умолчанию"] + [n for n, lang in sorted(found, key=lambda v: (not v[1].startswith("ru"), v[0]))]

            def set_win():
                config.TTS_VOICE = "" if self.win_voice_var.get() == "по умолчанию" else self.win_voice_var.get()
                self._save_tts()
            K.set_options(menu, self.win_voice_var, names, set_win)
            ru = [n for n, lang in found if lang.lower().startswith("ru")]
            self.voice_note.config(text="Голоса не найдены (озвучка работает только в Windows)." if not found else
                                   ("Русского голоса нет: Параметры → Время и язык → Речь → Добавить голоса."
                                    if not ru else f"Русские голоса: {', '.join(ru)}"))
        except tk.TclError:
            pass

    def _refresh_voice(self):
        self.tts_toggle.set(config.TTS_ENABLED)
        self.tts_chip.config(text=hotkeys.K("tts"))
        for r in self.voice_sliders:
            r.sync()
        for t in self.voice_tiles:
            t.sync()
        eng = config.TTS_ENGINE
        if eng == "silero":
            note = ("Голоса считаются прямо на компьютере, без интернета — почти без задержки. В первый раз "
                    "скачается модель (~100 МБ) и загрузится за 5–20 с." if tts.tts_silero.installed() else
                    "Нужна установка: закройте программу и запустите install_silero.bat из папки программы "
                    "(скачает PyTorch, около 1 ГБ). Пока не установлено — читает голос Windows.")
            self.voice_note.config(text=note)
        elif eng == "neural":
            self.voice_note.config(text="Бесплатные нейроголоса Microsoft (как «Читать вслух» в Edge). "
                                        "Нужен интернет, задержка 2–3 с.")
        elif getattr(self, "_win_voices", None) is None:
            self.voice_note.config(text="Загружаю список голосов Windows…")

    # ---------- Персонажи ----------
    def _build_chars(self):
        sc, b = self._page("Персонажи", "Имена берутся из субтитров. Пол угадывается по речи («я пришла / пришёл») "
                                        "и по имени — поправьте, если ошиблось.")
        self.chars_q = tk.StringVar()
        self.chars_filter = "all"
        top = tk.Frame(b, bg=K.BG)
        top.pack(fill="x")
        e = K.entry(top, self.chars_q, "Найти персонажа", width=30)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        self.chars_entry = e
        self.chars_q.trace_add("write", lambda *a: self._chars_render())
        self.chars_chips = tk.Frame(b, bg=K.BG)
        self.chars_chips.pack(fill="x", pady=(10, 0))
        self.chars_note = K.label(b, "", 9, K.AMBER, wraplength=640)
        self.chars_note.pack(anchor="w")
        c, ci = K.card(b, padx=16, pady=4)
        c.pack(fill="x", pady=(8, 0))
        self.chars_box = ci
        return sc

    def _refresh_chars(self):
        self._chars_render()

    def _chars_render(self):
        if not hasattr(self, "chars_box"):
            return
        eng = "silero" if config.TTS_ENGINE == "silero" else "neural"
        self.chars_note.config(text="Сейчас выбраны голоса Windows — разные голоса персонажей работают только "
                                    "с нейроголосами или Silero." if config.TTS_ENGINE == "windows" else "")
        if eng == "silero":
            pool = [(v, tts.tts_silero.label(v)) for v in voices.SILERO_POOL["f"] + voices.SILERO_POOL["m"]]
        else:
            pool = [(v, tts.neural_label(v)) for v in voices.NEURAL_POOL["f"] + voices.NEURAL_POOL["m"]]
        chars = voices.all_chars()
        counts = {"all": len(chars), "f": 0, "m": 0}
        for _, c in chars:
            counts[voices.gender(c)] = counts.get(voices.gender(c), 0) + 1
        for w in self.chars_chips.winfo_children():
            w.destroy()
        for key, title in (("all", "Все"), ("f", "Женщины"), ("m", "Мужчины")):
            K.chip(self.chars_chips, f"{title}  {counts.get(key, 0)}", self.chars_filter == key,
                   lambda k=key: self._chars_set_filter(k)).pack(side="left", padx=(0, 8))
        q = self.chars_entry.value().strip().lower()
        for w in self.chars_box.winfo_children():
            w.destroy()
        rows = []
        for key, c in chars:
            g = voices.gender(c)
            if self.chars_filter in ("f", "m") and g != self.chars_filter:
                continue
            if q and q not in f"{c.get('ru', '')} {c.get('en', '')} {key}".lower():
                continue
            rows.append((key, c, g))
        if not rows:
            K.label(self.chars_box, "Пока никого — персонажи появятся здесь, когда заговорят в субтитрах."
                    if not chars else "Никого не нашлось.", 10, K.MUTED).pack(anchor="w", pady=14)
            return
        labels = dict(pool)
        for n, (key, c, g) in enumerate(rows[:200]):
            r = tk.Frame(self.chars_box, bg=K.CARD)
            r.pack(fill="x")
            line = tk.Frame(r, bg=K.CARD)
            line.pack(fill="x", pady=7)
            name = c.get("ru") or c.get("en") or key
            K.Avatar(line, name, GENDER_COLORS.get(g, K.AMBER), 32).pack(side="left", padx=(0, 12))
            txt = tk.Frame(line, bg=K.CARD)
            txt.pack(side="left", fill="x", expand=True)
            K.label(txt, name, 10, K.TEXT, "bold").pack(anchor="w")
            if c.get("gender_manual") in ("m", "f"):
                how = "вы указали"
            elif c.get("ai") in ("m", "f"):
                how = "угадано нейросетью"
            elif c.get("f", 0) or c.get("m", 0):
                how = "по речи"
            else:
                how = "по имени"
            sub = " · ".join(x for x in ((c.get("en") if c.get("en") and c.get("en") != name else ""),
                                         f"{'женский' if g == 'f' else 'мужской'}, {how}") if x)
            K.label(txt, sub, 9, K.DIM).pack(anchor="w")
            x = tk.Label(line, text="✕", bg=K.CARD, fg=K.FAINT, font=K.f(10), cursor="hand2", padx=6)
            x.pack(side="right")
            x.bind("<Button-1>", lambda e, k=key: (voices.forget(k), self._chars_render()))
            pb = tk.Label(line, text="▶", bg=K.ACCENT_TINT, fg=K.ACCENT_TEXT, font=K.f(10), width=3, cursor="hand2")
            pb.pack(side="right", padx=(8, 4), ipady=4)
            pb.bind("<Button-1>", lambda e, k=key, nm=name: tts.say_test(
                voices.voice_for(k, eng), f"{nm}. Привет, путник! Так звучит мой голос."))
            av = voices.voice_for(key, eng, auto_only=True)
            auto = "авто" + (f" · {labels.get(av[0], av[0]).split(' — ')[0]}" if av else "")
            cur = c.get(f"voice_{eng}", "")
            vv = tk.StringVar(value=labels.get(cur, auto) if cur else auto)
            om = K.select(line, vv, [auto] + [lab for _, lab in pool],
                          lambda k=key, v=vv: voices.set_manual(
                              k, voice=next((i for i, lab in pool if lab == v.get()), ""), engine=eng), width=22)
            om.pack(side="right", padx=(8, 0))
            seg = tk.Frame(line, bg=K.SIDEBAR, highlightthickness=1, highlightbackground=K.BORDER)
            seg.pack(side="right")
            man = c.get("gender_manual", "")
            for val, t in (("f", "Ж"), ("m", "М"), ("", "авто")):
                on = man == val
                lab = tk.Label(seg, text=t, bg=K.ACCENT if on else K.SIDEBAR, fg="#ffffff" if on else K.MUTED,
                               font=K.f(9), padx=8, pady=3, cursor="hand2")
                lab.pack(side="left", padx=1, pady=1)
                lab.bind("<Button-1>", lambda e, k=key, v=val: (voices.set_manual(k, gender_value=v),
                                                                 self._chars_render()))
            if n < len(rows) - 1:
                K.separator(r).pack(fill="x")

    def _chars_set_filter(self, k):
        self.chars_filter = k
        self._chars_render()

    # ---------- История ----------
    def _build_hist(self):
        frame, b = self._page_plain("История", "Всё, что переведено за эту сессию. ▶ — прослушать снова.")
        top = tk.Frame(b, bg=K.BG)
        top.pack(fill="x")
        self.hist_q = tk.StringVar()
        e = K.entry(top, self.hist_q, "Поиск по переводу и оригиналу", width=30)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        self.hist_entry = e
        self.hist_q.trace_add("write", lambda *a: self._hist_render())
        K.button(top, "Открыть папку", self._hist_folder, kind="ghost", size=9).pack(side="right", padx=(8, 0))
        K.button(top, "Копировать всё", self._hist_copy, kind="ghost", size=9).pack(side="right", padx=(8, 0))
        self.hist_kind = "Все"
        self.hist_chips = tk.Frame(b, bg=K.BG)
        self.hist_chips.pack(fill="x", pady=(10, 10))
        box = tk.Frame(b, bg=K.CARD, highlightthickness=1, highlightbackground=K.BORDER)
        box.pack(fill="both", expand=True)
        self.hist_text = tk.Text(box, bg=K.CARD, fg=K.TEXT, font=K.f(10), relief="flat", highlightthickness=0,
                                 wrap="word", padx=16, pady=10, cursor="arrow", spacing1=1, spacing3=2)
        self.hist_text.pack(fill="both", expand=True)
        t = self.hist_text
        t.tag_config("time", foreground=K.FAINT, font=(K.MONO, 9))
        t.tag_config("orig", foreground=K.DIM, font=K.f(9))
        t.tag_config("tr", foreground=K.TEXT, font=K.f(10))
        t.tag_config("gap", font=K.f(4))
        t.tag_config("empty", foreground=K.MUTED)
        for kind, col in KIND_COLORS.items():
            t.tag_config("k_" + kind, foreground=col, font=K.f(9, "bold"))
        t.tag_config("play", foreground=K.ACCENT_TEXT, font=K.f(10))
        t.tag_bind("play", "<Enter>", lambda e: t.config(cursor="hand2"))
        t.tag_bind("play", "<Leave>", lambda e: t.config(cursor="arrow"))
        self._hist_n = 0
        return frame

    def _hist_match(self, entry):
        _, kind, orig, tr = entry
        if self.hist_kind != "Все" and not kind.startswith(self.hist_kind):
            return False
        q = self.hist_entry.value().strip().lower()
        return not q or q in f"{orig} {tr}".lower()

    def _hist_insert(self, entry):
        t = self.hist_text
        tm, kind, orig, tr = entry
        tag = f"p{self._hist_n}"
        self._hist_n += 1
        t.insert("end", f"{tm}  ", "time")
        t.insert("end", kind, "k_" + kind if kind in KIND_COLORS else "time")
        t.insert("end", "   ▶ прослушать", ("play", tag))
        t.tag_bind(tag, "<Button-1>", lambda e, s=tr: threading.Thread(target=tts.speak_text, args=(s,),
                                                                        daemon=True).start())
        t.insert("end", "\n")
        t.insert("end", tr.strip() + "\n", "tr")
        if orig:
            t.insert("end", orig.strip() + "\n", "orig")
        t.insert("end", "\n", "gap")

    def _hist_render(self):
        if not hasattr(self, "hist_text"):
            return
        kinds = ["Все"] + sorted({e[1] for e in history.translation_history},
                                 key=lambda k: list(KIND_COLORS).index(k) if k in KIND_COLORS else 99)
        for w in self.hist_chips.winfo_children():
            w.destroy()
        for k in kinds:
            n = len(history.translation_history) if k == "Все" else sum(1 for e in history.translation_history
                                                                         if e[1] == k)
            K.chip(self.hist_chips, f"{k}  {n}", self.hist_kind == k,
                   lambda k=k: self._hist_set_kind(k)).pack(side="left", padx=(0, 8))
        t = self.hist_text
        t.config(state="normal")
        t.delete("1.0", "end")
        items = [e for e in history.translation_history if self._hist_match(e)]
        if not items:
            t.insert("end", "Пока пусто." if not history.translation_history else "Ничего не найдено.", "empty")
        for e in items[-500:]:
            self._hist_insert(e)
        t.see("end")
        t.config(state="disabled")

    def _hist_set_kind(self, k):
        self.hist_kind = k
        self._hist_render()

    def history_new(self, entry):
        """Новый перевод — дописать в открытый раздел «История»."""
        if self.current != "hist" or not hasattr(self, "hist_text"):
            return
        if not self._hist_match(entry):
            return
        t = self.hist_text
        t.config(state="normal")
        if t.get("1.0", "end").strip() in ("Пока пусто.", "Ничего не найдено."):
            t.delete("1.0", "end")
        self._hist_insert(entry)
        t.see("end")
        t.config(state="disabled")

    def _refresh_hist(self):
        if not getattr(self, "_hist_shown", False):
            self._hist_shown = True
            self._hist_render()

    def _hist_folder(self):
        os.makedirs(history.HISTORY_DIR, exist_ok=True)
        try:
            os.startfile(history.HISTORY_DIR)
        except Exception as e:
            core.log(f"Не удалось открыть папку: {e}", "error")

    def _hist_copy(self):
        parts = [f"{t} {k}\n" + (o + "\n" if o else "") + r for t, k, o, r in history.translation_history
                 if self._hist_match((t, k, o, r))]
        self.win.clipboard_clear()
        self.win.clipboard_append("\n\n".join(parts))
        core.log("История скопирована в буфер обмена", "ok")

    # ---------- Словарь ----------
    def _build_gloss(self):
        sc, b = self._page("Словарь", "Имена и названия, которые всегда переводятся одинаково. "
                                      "Щёлкните строку, чтобы исправить её.")
        hdr = b.winfo_children()[0]
        right = tk.Frame(hdr, bg=K.BG)
        right.place(relx=1.0, rely=0.0, anchor="ne")
        K.label(right, "Пополнять сам", 10, K.TEXT2).pack(side="left", padx=(0, 8))

        def auto_set(v):
            config.GLOSSARY_AUTO = bool(v)
            core.save_settings(glossary_auto=config.GLOSSARY_AUTO)
        self.gl_toggle = K.Toggle(right, config.GLOSSARY_AUTO, auto_set)
        self.gl_toggle.pack(side="left")

        c, ci = K.card(b, padx=14, pady=12)
        c.pack(fill="x")
        self.gl_en, self.gl_ru = tk.StringVar(), tk.StringVar()
        self.gl_en_e = K.entry(ci, self.gl_en, "Оригинал, например Renald", width=24)
        self.gl_en_e.pack(side="left", fill="x", expand=True, ipady=5)
        K.label(ci, "→", 11, K.FAINT).pack(side="left", padx=10)
        self.gl_ru_e = K.entry(ci, self.gl_ru, "Перевод, например Ренальд", width=24)
        self.gl_ru_e.pack(side="left", fill="x", expand=True, ipady=5)
        K.button(ci, "Добавить", self._gl_add, kind="primary").pack(side="left", padx=(10, 0))
        self.gl_ru_e.bind("<Return>", lambda e: self._gl_add())

        top = tk.Frame(b, bg=K.BG)
        top.pack(fill="x", pady=(12, 0))
        self.gl_q = tk.StringVar()
        self.gl_q_e = K.entry(top, self.gl_q, "Найти в словаре", width=24)
        self.gl_q_e.pack(side="left", fill="x", expand=True, ipady=5)
        self.gl_q.trace_add("write", lambda *a: self._gl_render())
        self.gl_filter = "all"
        self.gl_chips = tk.Frame(top, bg=K.BG)
        self.gl_chips.pack(side="left", padx=(10, 0))
        open_link = K.label(top, "Открыть файл", 9, K.ACCENT_TEXT)
        open_link.config(cursor="hand2")
        open_link.bind("<Button-1>", lambda e: glossary.open_glossary())
        open_link.pack(side="right", padx=(10, 0))

        c, ci = K.card(b, padx=16, pady=4)
        c.pack(fill="x", pady=(10, 0))
        self.gl_box = ci

        c, ci = K.card(b, padx=16, pady=12)
        c.pack(fill="x", pady=(12, 0))
        t = tk.Frame(ci, bg=K.CARD)
        t.pack(fill="x")
        K.h2(t, "Не переводить").pack(side="left")
        K.label(t, "слова интерфейса, которые программа пропускает", 9, K.DIM).pack(side="left", padx=(10, 0))
        self.ign_box = tk.Frame(ci, bg=K.CARD)
        self.ign_box.pack(fill="x", pady=(10, 0))
        add = tk.Frame(ci, bg=K.CARD)
        add.pack(fill="x", pady=(10, 0))
        self.ign_var = tk.StringVar()
        self.ign_e = K.entry(add, self.ign_var, "Слово или фраза", width=24)
        self.ign_e.pack(side="left", ipady=4)
        self.ign_e.bind("<Return>", lambda e: self._ign_add())
        K.button(add, "Добавить", self._ign_add, kind="ghost", size=9).pack(side="left", padx=(8, 0))
        return sc

    def _gl_add(self):
        en, ru = self.gl_en_e.value().strip(), self.gl_ru_e.value().strip()
        if not en or not ru:
            core.log("Словарь: впишите и оригинал, и перевод", "warn")
            return
        if glossary.set_entry(en, ru):
            core.log(f"📖 Словарь: {en} = {ru}", "ok")
            for e, v in ((self.gl_en_e, self.gl_en), (self.gl_ru_e, self.gl_ru)):
                v.set("")
                e.event_generate("<FocusOut>")
            self.win.focus_set()
            self._gl_render()

    def _gl_edit(self, en, ru):
        for e, v, val in ((self.gl_en_e, self.gl_en, en), (self.gl_ru_e, self.gl_ru, ru)):
            if getattr(e, "_ph", False):
                e.event_generate("<FocusIn>")
            v.set(val)
            e.config(fg=K.TEXT)
        self.gl_ru_e.focus_set()

    def _gl_render(self):
        if not hasattr(self, "gl_box"):
            return
        items = glossary.entries()
        counts = {"all": len(items), "man": sum(1 for *_, a in items if not a), "auto": sum(1 for *_, a in items if a)}
        for w in self.gl_chips.winfo_children():
            w.destroy()
        for key, title in (("all", "Все"), ("man", "Вручную"), ("auto", "Авто")):
            K.chip(self.gl_chips, f"{title}  {counts[key]}", self.gl_filter == key,
                   lambda k=key: self._gl_set_filter(k)).pack(side="left", padx=(0, 6))
        q = self.gl_q_e.value().strip().lower()
        rows = [(en, ru, a) for en, ru, a in items
                if (self.gl_filter == "all" or (self.gl_filter == "auto") == a)
                and (not q or q in f"{en} {ru}".lower())]
        for w in self.gl_box.winfo_children():
            w.destroy()
        if not rows:
            K.label(self.gl_box, "Пусто." if not items else "Ничего не нашлось.", 10, K.MUTED).pack(anchor="w", pady=12)
        for n, (en, ru, a) in enumerate(rows[:400]):
            r = tk.Frame(self.gl_box, bg=K.CARD, cursor="hand2")
            r.pack(fill="x")
            line = tk.Frame(r, bg=K.CARD, cursor="hand2")
            line.pack(fill="x", pady=6)
            line.columnconfigure(0, weight=1, uniform="g")
            line.columnconfigure(2, weight=1, uniform="g")
            w1 = K.label(line, en, 10, K.TEXT)
            w1.grid(row=0, column=0, sticky="w")
            w2 = K.label(line, "→", 10, K.FAINT)
            w2.grid(row=0, column=1, padx=10)
            w3 = K.label(line, ru, 10, K.TEXT)
            w3.grid(row=0, column=2, sticky="w")
            badge = tk.Label(line, text="авто" if a else "вручную", font=K.f(8), padx=8, width=8,
                             bg=K.SIDEBAR if a else K.ACCENT_TINT, fg=K.DIM if a else K.ACCENT_TEXT)
            badge.grid(row=0, column=3, padx=(10, 6))
            x = tk.Label(line, text="✕", bg=K.CARD, fg=K.FAINT, font=K.f(10), cursor="hand2", padx=4)
            x.grid(row=0, column=4)
            x.bind("<Button-1>", lambda e, en=en: (glossary.remove_entry(en), self._gl_render()))
            for w in (r, line, w1, w2, w3, badge):
                w.bind("<Button-1>", lambda e, en=en, ru=ru: self._gl_edit(en, ru))
            if n < len(rows) - 1:
                K.separator(r).pack(fill="x")
        for w in self.ign_box.winfo_children():
            w.destroy()
        row = tk.Frame(self.ign_box, bg=K.CARD)
        row.pack(fill="x")
        width = 0
        for word, builtin in glossary.ignore_entries():
            if width > 560:
                row = tk.Frame(self.ign_box, bg=K.CARD)
                row.pack(fill="x", pady=(6, 0))
                width = 0
            pill = tk.Frame(row, bg=K.SIDEBAR, highlightthickness=1, highlightbackground=K.LINE)
            pill.pack(side="left", padx=(0, 6))
            tk.Label(pill, text=word, bg=K.SIDEBAR, fg=K.DIM if builtin else K.TEXT2, font=K.f(9),
                     padx=8, pady=2).pack(side="left")
            if not builtin:
                x = tk.Label(pill, text="✕", bg=K.SIDEBAR, fg=K.FAINT, font=K.f(8), cursor="hand2", padx=4)
                x.pack(side="left")
                x.bind("<Button-1>", lambda e, w=word: (glossary.remove_ignore(w), self._gl_render()))
            width += len(word) * 8 + 40

    def _gl_set_filter(self, k):
        self.gl_filter = k
        self._gl_render()

    def _ign_add(self):
        w = self.ign_e.value().strip()
        if w and glossary.add_ignore(w):
            core.log(f"Не переводить: {w}", "ok")
        self.ign_var.set("")
        self.ign_e.event_generate("<FocusOut>")
        self.win.focus_set()
        self._gl_render()

    def _refresh_gloss(self):
        self.gl_toggle.set(config.GLOSSARY_AUTO)
        self._gl_render()


class GamesMixin:
    # ---------- Игры (пресеты) ----------
    def _build_games(self):
        from . import profiles
        sc, b = self._page("Игры", "У каждой игры свой пресет: области, образец меню, словарь, персонажи с голосами "
                                   "и кэш переводов. Программа сама переключается, когда игра на экране.")
        tip, ti = K.card(b, bg=K.ACCENT_TINT, border=K.ACCENT_LINE, padx=16, pady=10)
        tip.pack(fill="x", pady=(0, 14))
        K.button(ti, "+ Добавить игру", self._game_add, kind="primary").pack(side="right", padx=(12, 0))
        K.label(ti, "Новую игру программа узнаёт сама и заводит ей пресет. Не узнала — запустите игру "
                    "и нажмите «+ Добавить игру».",
                10, K.TEXT, bg=K.ACCENT_TINT, wraplength=470).pack(side="left", anchor="w")
        self.games_box = tk.Frame(b, bg=K.BG)
        self.games_box.pack(fill="x")
        self._games_render()
        return sc

    def _games_render(self):
        from . import profiles
        for w in self.games_box.winfo_children():
            w.destroy()
        profs = profiles.game_profiles()          # «🧪 Без игры» — не игра, её здесь нет
        for pid, p in profs.items():
            on = pid == core.active_profile
            c, ci = K.card(self.games_box, bg=K.CARD, border=K.ACCENT_LINE if on else K.BORDER, padx=16, pady=12)
            c.pack(fill="x", pady=(0, 12))
            top = tk.Frame(ci, bg=K.CARD)
            top.pack(fill="x")
            var = tk.StringVar(value=p.get("name", pid))
            e = tk.Entry(top, textvariable=var, bg=K.CARD, fg=K.TEXT, insertbackground=K.TEXT, relief="flat",
                         bd=0, highlightthickness=0, font=K.f(13, "bold"), width=max(8, len(var.get()) + 1))
            var.trace_add("write", lambda *a, e=e, var=var: e.config(width=max(8, len(var.get()) + 1)))
            e.pack(side="left")
            save = lambda ev=None, pid=pid, var=var: (profiles.rename(pid, var.get()), self.refresh())
            e.bind("<Return>", lambda ev, s=save: (s(), self.win.focus_set()))
            e.bind("<FocusOut>", save)
            live = profiles.is_running(pid)
            if on and (live or core.SETTINGS.get("profile_lock") == pid):
                tk.Label(top, text="сейчас", bg=K.ACCENT, fg="#ffffff", font=K.f(8, "bold"), padx=8).pack(
                    side="left", padx=(8, 0))
            elif on:
                tk.Label(top, text="настраиваете", bg=K.LINE, fg=K.TEXT2, font=K.f(8, "bold"), padx=8).pack(
                    side="left", padx=(8, 0))
            elif live:
                tk.Label(top, text="запущена", bg=K.LINE, fg=K.TEXT2, font=K.f(8, "bold"), padx=8).pack(
                    side="left", padx=(8, 0))
            if core.SETTINGS.get("profile_lock") == pid:
                tk.Label(top, text="📌 закреплён", bg=K.AMBER, fg="#141413", font=K.f(8, "bold"), padx=8).pack(
                    side="left", padx=(6, 0))
            K.label(top, "✎ имя можно исправить прямо здесь", 8, K.FAINT).pack(side="right")
            files = tk.Frame(ci, bg=K.CARD)
            files.pack(fill="x", pady=(6, 8))
            K.label(files, "Файлы игры:", 9, K.DIM).pack(side="left", padx=(0, 6))
            exes = p.get("exes", [])
            for exe in exes:
                pill = tk.Frame(files, bg=K.SIDEBAR, highlightthickness=1, highlightbackground=K.LINE)
                pill.pack(side="left", padx=(0, 6))
                tk.Label(pill, text=exe, bg=K.SIDEBAR, fg=K.TEXT2, font=K.f(9), padx=6, pady=1).pack(side="left")
                if len(exes) > 1 or p.get("match"):
                    x = tk.Label(pill, text="✕", bg=K.SIDEBAR, fg=K.FAINT, font=K.f(8), cursor="hand2", padx=3)
                    x.pack(side="left")
                    x.bind("<Button-1>", lambda e, pid=pid, exe=exe: (profiles.remove_exe(pid, exe),
                                                                       self._games_render()))
            add = tk.Label(files, text="+ ещё файл", bg=K.CARD, fg=K.ACCENT_TEXT, font=K.f(9), cursor="hand2")
            add.pack(side="left", padx=(2, 0))
            add.bind("<Button-1>", lambda e, pid=pid: self._game_add_exe(pid))
            regs = tk.Frame(ci, bg=K.CARD)
            regs.pack(fill="x")
            for key, title in (("region", "Субтитры"), ("region2", "Реплики 2"), ("answers_region", "Ответы"),
                               ("chat_region", "Чат"), ("menu_region", "Меню")):
                has = bool(p.get(key))
                tk.Label(regs, text=("✓ " if has else "— ") + title, font=K.f(9), padx=8, pady=2,
                         bg=K.ACCENT_TINT if has else K.SIDEBAR, fg=K.ACCENT_TEXT if has else K.FAINT
                         ).pack(side="left", padx=(0, 6))
            if on and not live and core.SETTINGS.get("profile_lock") != pid:
                K.label(ci, "Игра не запущена — вы выбрали этот пресет, чтобы настроить его (области, словарь, "
                            "персонажи). Переводить он начнёт, когда игра будет запущена.", 9, K.DIM,
                        wraplength=600).pack(anchor="w", pady=(8, 0))
            chars, gl = profiles.stats(pid)
            bottom = tk.Frame(ci, bg=K.CARD)
            bottom.pack(fill="x", pady=(10, 0))
            K.label(bottom, f"персонажей: {chars} · в словаре: {gl}", 9, K.MUTED).pack(side="left")
            K.button(bottom, "Удалить", lambda pid=pid: self._game_delete(pid), kind="danger", size=9).pack(
                side="right")
            if not on and not core.SETTINGS.get("profile_lock"):
                K.button(bottom, "Настроить", lambda pid=pid: (profiles.activate(pid, hold=True), self._games_render()),
                         kind="ghost", size=9).pack(side="right", padx=(0, 8))
            else:
                K.button(bottom, "Области →", lambda: self.show("areas"), kind="ghost", size=9).pack(
                    side="right", padx=(0, 8))
            is_locked = core.SETTINGS.get("profile_lock") == pid
            K.button(bottom, "Открепить" if is_locked else "📌 Закрепить",
                     lambda pid=pid, l=is_locked: (profiles.lock(None if l else pid), self._games_render()),
                     kind="ghost", size=9).pack(side="right", padx=(0, 8))
        from . import game
        ng = sorted(game.not_games())
        if ng:      # что вы отметили «не игра» — видно и можно вернуть
            c, ci = K.card(self.games_box, bg=K.CARD, padx=16, pady=12)
            c.pack(fill="x", pady=(0, 12))
            K.label(ci, "Не игры", 11, K.TEXT, "bold").pack(anchor="w")
            K.label(ci, "Эти программы вы отметили «не игра» — программа их не узнаёт и не переводит в них. "
                        "Ошиблись — нажмите ✕.", 9, K.DIM, wraplength=600).pack(anchor="w", pady=(2, 8))
            row = tk.Frame(ci, bg=K.CARD)
            row.pack(fill="x")
            for exe in ng:
                pill = tk.Frame(row, bg=K.SIDEBAR, highlightthickness=1, highlightbackground=K.LINE)
                pill.pack(side="left", padx=(0, 6))
                tk.Label(pill, text=exe, bg=K.SIDEBAR, fg=K.TEXT2, font=K.f(9), padx=6, pady=1).pack(side="left")
                x = tk.Label(pill, text="✕", bg=K.SIDEBAR, fg=K.FAINT, font=K.f(8), cursor="hand2", padx=3)
                x.pack(side="left")
                x.bind("<Button-1>", lambda e, exe=exe: (game.unmark_not_game(exe), self._games_render()))

    def _game_add(self):
        """«+ Добавить игру»: выбрать из запущенных сейчас программ."""
        from . import game, profiles

        def pick(exe):
            if profiles.for_exe(exe):
                core.log(f"{exe} уже есть в списке игр — «{profiles.name(profiles.for_exe(exe))}»", "warn")
                return
            if exe in game.not_games():
                game.unmark_not_game(exe)
            game.create_profile_for(exe, profiles._pretty(exe))
            self._games_render()
        self.pick_program("Добавить игру", "Выберите игру из запущенных сейчас программ. Название потом можно "
                                           "исправить прямо в карточке.", pick, hide_known=True)

    def _game_add_exe(self, pid):
        from . import profiles
        self.pick_program(f"Ещё файл для «{profiles.name(pid)}»",
                          "Пригодится, если игра запускается через лаунчер или защиту от читов, или файл игры "
                          "переименовали после обновления. Выберите его из запущенных программ:",
                          lambda exe: (profiles.add_exe(pid, exe), self._games_render()))

    def _game_delete(self, pid):
        from . import profiles
        self.ask(f"Удалить пресет «{profiles.name(pid)}»?",
                 "Пропадут его области; словарь, персонажи и кэш уйдут в папку backups. "
                 "Сама игра и другие пресеты не затронуты.", "Удалить",
                 lambda: (profiles.delete(pid), self._games_render(), self.refresh()))

    def _refresh_games(self):
        pass
