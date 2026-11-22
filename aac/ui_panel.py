"""Системная панель."""


import os


import threading

import tkinter as tk


from . import config, core, game, glossary, hotkeys, limits, llm, translate, tts, ui_overlay


PROVIDER_LABELS = {  # как переводчики называются в выпадающем списке панели
    "groq_ocr": "Groq (OCR + ИИ)",
    "gemini_ocr": "Gemini (OCR + ИИ)",
    "claude_ocr": "Claude (OCR + ИИ, платно)",
    "google": "Google Переводчик (OCR)",
    "microsoft": "Microsoft Переводчик (OCR)",
    "deepl": "DeepL (OCR, ключ)",
    "mistral": "Mistral (бесплатно)",
    "gemini": "Gemini (бесплатно)",
    "groq": "Groq (бесплатно)",
    "claude": "Claude (платно)",
    "ollama": "Ollama (локально)",
}
PROVIDER_NAMES = {"gemini": "Gemini", "claude": "Claude", "ollama": "Ollama (локально)",
                  "mistral": "Mistral", "groq": "Groq", "google": "Google (OCR)", "deepl": "DeepL (OCR)",
                  "microsoft": "Microsoft (OCR)", "groq_ocr": "Groq (OCR+ИИ)", "gemini_ocr": "Gemini (OCR+ИИ)",
                  "claude_ocr": "Claude (OCR+ИИ)", "mistral_ocr": "Mistral (OCR+ИИ)"}
LOG_COLORS = {"info": "#ccc", "ok": "#7d7", "warn": "#fc6", "error": "#f77"}


class Panel:
    """Системное окно: статус, горячие клавиши, журнал ошибок."""

    def __init__(self, win):
        self.win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.92)
        win.configure(bg="#1a1d23")
        sh = win.winfo_screenheight()
        default = (win.winfo_screenwidth() - config.PANEL_WIDTH - 20, 60)  # правый верхний угол
        x, y = core.SETTINGS.get("panel_pos", default)
        sw = win.winfo_screenwidth()
        if not (0 <= x <= sw - 100 and 0 <= y <= sh - 60):
            x, y = default
        x = max(0, min(x, sw - config.PANEL_WIDTH))   # панель стала шире — не уезжает за правый край
        self.default_pos = default
        win.geometry(f"{config.PANEL_WIDTH}x830+{x}+{y}")

        # логотип в заголовке (icon_22.png рядом с программой; если файла нет — значок ⚙)
        self._logo = None
        logo_path = os.path.join(config.APP_DIR, "icon_22.png")
        try:
            if os.path.exists(logo_path):
                self._logo = tk.PhotoImage(file=logo_path)
        except Exception:
            self._logo = None
        top = tk.Frame(win, bg="#1a1d23")
        top.pack(fill="x", padx=10, pady=(8, 2))
        tk.Button(top, text="⟳ Перезапустить", font=("Segoe UI", 8), relief="flat", bd=0, highlightthickness=0,
                  padx=8, bg="#2b3040", fg="#8cf", activebackground="#3a4258", activeforeground="#fff",
                  cursor="hand2", command=lambda: core.events.put(("restart", None))).pack(side="right")
        tk.Button(top, text="⬇ Проверить обновления", font=("Segoe UI", 8), relief="flat", bd=0,
                  highlightthickness=0, padx=8, bg="#2b3040", fg="#8cf", activebackground="#3a4258",
                  activeforeground="#fff", cursor="hand2",
                  command=lambda: core.events.put(("update_check", None))).pack(side="right", padx=(0, 4))
        hdr = tk.Label(top, text=f"  AAC Translator v{config.VERSION} — система   (тащите мышкой)" if self._logo
                       else f"⚙ AAC Translator v{config.VERSION} — система   (тащите мышкой)",
                       image=self._logo, compound="left",
                       fg="#8cf", bg="#1a1d23", font=("Segoe UI", 10, "bold"), anchor="w")
        hdr.pack(side="left", fill="x", expand=True)
        self.state = tk.Label(win, text="", fg="#eee", bg="#1a1d23", font=("Consolas", 10),
                              justify="left", anchor="w", wraplength=config.PANEL_WIDTH - 24)
        self.state.pack(fill="x", padx=10)

        # выбор переводчика — запоминается в настройках
        sel = tk.Frame(win, bg="#1a1d23")
        sel.pack(fill="x", padx=10, pady=(6, 0))
        self.main_var = tk.StringVar(value=PROVIDER_LABELS.get(config.PROVIDER, config.PROVIDER))
        self.fb_var = tk.StringVar(value=PROVIDER_LABELS.get(config.FALLBACK_PROVIDERS[0], "нет")
                                   if config.FALLBACK_PROVIDERS else "нет")
        for text, var, options in (("Основной:", self.main_var, list(PROVIDER_LABELS.values())),
                                   ("Запасной:", self.fb_var, ["нет"] + list(PROVIDER_LABELS.values()))):
            tk.Label(sel, text=text, fg="#aaa", bg="#1a1d23", font=("Segoe UI", 9)).pack(side="left")
            om = tk.OptionMenu(sel, var, *options, command=lambda _v: self._provider_changed())
            om.config(bg="#2b3040", fg="#eee", activebackground="#3a4258", activeforeground="#fff",
                      relief="flat", highlightthickness=0, font=("Segoe UI", 9), bd=0, width=16)
            om["menu"].config(bg="#2b3040", fg="#eee", activebackground="#3a4258", font=("Segoe UI", 9))
            om.pack(side="left", padx=(4, 14))
        self.answers_auto_var = tk.BooleanVar(value=core.answers_auto)
        row2 = tk.Frame(win, bg="#1a1d23")
        row2.pack(fill="x", padx=10, pady=(2, 0))
        tk.Checkbutton(row2, text="Автоперевод ответов (если выкл — по кнопке «перевести ответы»)", variable=self.answers_auto_var,
                       command=self._answers_auto_changed, bg="#1a1d23", fg="#ccc", selectcolor="#2b3040",
                       activebackground="#1a1d23", activeforeground="#fff", font=("Segoe UI", 9),
                       highlightthickness=0, bd=0).pack(side="left")
        self.docked_var = tk.BooleanVar(value=config.ANSWERS_DOCKED)
        row2b = tk.Frame(win, bg="#1a1d23")
        row2b.pack(fill="x", padx=10, pady=(2, 0))
        tk.Checkbutton(row2b, text="Ответы и субтитры одним окном", variable=self.docked_var,
                       command=lambda: core.events.put(("dock_toggle", bool(self.docked_var.get()))),
                       bg="#1a1d23", fg="#ccc", selectcolor="#2b3040",
                       activebackground="#1a1d23", activeforeground="#fff", font=("Segoe UI", 9),
                       highlightthickness=0, bd=0).pack(side="left")
        self.chat_auto_var = tk.BooleanVar(value=core.chat_auto)
        tk.Checkbutton(row2b, text="Автоперевод чата", variable=self.chat_auto_var, command=self._chat_auto_changed,
                       bg="#1a1d23", fg="#ccc", selectcolor="#2b3040", activebackground="#1a1d23",
                       activeforeground="#fff", font=("Segoe UI", 9), highlightthickness=0, bd=0).pack(side="left",
                                                                                                        padx=(16, 0))
        row3 = tk.Frame(win, bg="#1a1d23")
        row3.pack(fill="x", padx=10, pady=(2, 0))
        self.pause_var = tk.BooleanVar(value=config.PAUSE_OUTSIDE_GAME)
        tk.Checkbutton(row3, text="Пауза, когда игра не на экране", variable=self.pause_var,
                       command=self._pause_changed, bg="#1a1d23", fg="#ccc", selectcolor="#2b3040",
                       activebackground="#1a1d23", activeforeground="#fff", font=("Segoe UI", 9),
                       highlightthickness=0, bd=0).pack(side="left")
        # появляется, когда на GitHub есть новая версия
        self.update_btn = tk.Button(row3, text="⬇ Обновить", font=("Segoe UI", 8, "bold"), relief="flat", bd=0,
                                    highlightthickness=0, padx=8, bg="#1f6f3f", fg="#fff",
                                    activebackground="#2a8a50", activeforeground="#fff", cursor="hand2",
                                    command=lambda: core.events.put(("update_install", None)))
        for text, cmd in (("⚙ Настройки", lambda: core.events.put(("settings_open", None))),
                          ("🕘 История", lambda: core.events.put(("history_open", None))),
                          ("📖 Словарь имён", glossary.open_glossary)):
            tk.Button(row3, text=text, font=("Segoe UI", 8), relief="flat", bd=0, highlightthickness=0,
                      padx=8, bg="#2b3040", fg="#8cf", activebackground="#3a4258", activeforeground="#fff",
                      cursor="hand2", command=cmd).pack(side="right", padx=(4, 0))
        keys = tk.Frame(win, bg="#1a1d23")
        keys.pack(fill="x", padx=10, pady=(6, 4))
        tk.Label(keys, text="Клавиши (кнопка «изменить» — назначить свою):", fg="#aaa", bg="#1a1d23",
                 font=("Segoe UI", 9), anchor="w").grid(row=0, column=0, columnspan=8, sticky="w")
        self.key_labels = {}
        for n, (hid, desc, _, _) in enumerate(hotkeys.HOTKEY_DEFS):
            # две колонки, в каждой: клавиша | что делает | кнопка «изменить» (справа, ровно в столбик)
            r, c = 1 + n // 2, (n % 2) * 4
            kl = tk.Label(keys, text="", width=15, anchor="w", fg="#eee", bg="#1a1d23", font=("Consolas", 9))
            kl.grid(row=r, column=c, sticky="w", pady=1)
            tk.Label(keys, text=desc, fg="#aaa", bg="#1a1d23", font=("Segoe UI", 9), anchor="w").grid(
                row=r, column=c + 1, sticky="w", padx=(0, 6))
            tk.Button(keys, text="изменить", font=("Segoe UI", 7), relief="flat", bd=0, highlightthickness=0, padx=4,
                      bg="#2b3040", fg="#8cf", activebackground="#3a4258", activeforeground="#fff",
                      cursor="hand2", command=lambda h=hid: threading.Thread(
                          target=hotkeys.capture_hotkey, args=(h,), daemon=True).start()).grid(
                row=r, column=c + 2, sticky="w", padx=(0, 14))
            self.key_labels[hid] = kl
        self.update_keys()
        tk.Label(win, text="Журнал:", fg="#8cf", bg="#1a1d23", font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=10)
        self.log = tk.Text(win, height=9, bg="#111317", fg="#ccc", font=("Consolas", 9), relief="flat", highlightthickness=0,
                           wrap="word", padx=6, pady=4, state="disabled", cursor="arrow")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for tag, color in LOG_COLORS.items():
            self.log.tag_config(tag, foreground=color)

        for w in (hdr, self.state, keys):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._end_move)
        self.visible = True
        self.busy = False
        win.after(200, lambda: ui_overlay.exclude_from_capture(win))

    def _start_move(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _end_move(self, e):
        core.save_settings(panel_pos=(self.win.winfo_x(), self.win.winfo_y()))

    def reset_pos(self):
        x, y = self.default_pos
        self.win.geometry(f"+{x}+{y}")
        core.save_settings(panel_pos=(x, y))

    def toggle(self):
        if self.visible:
            self.win.withdraw()
        else:
            self.win.deiconify()
        self.visible = not self.visible

    def show_update(self, version):
        self.update_btn.config(text=f"⬇ Обновить до {version}")
        if not self.update_btn.winfo_manager():
            self.update_btn.pack(side="right", padx=(4, 0))

    def sync_vars(self):
        if hasattr(self, "docked_var") and self.docked_var.get() != config.ANSWERS_DOCKED:
            self.docked_var.set(config.ANSWERS_DOCKED)

    def _pause_changed(self):
        config.PAUSE_OUTSIDE_GAME = bool(self.pause_var.get())
        core.save_settings(pause_outside_game=config.PAUSE_OUTSIDE_GAME)
        core.log("Пауза вне игры " + ("включена" if config.PAUSE_OUTSIDE_GAME else "выключена"))
        if not config.PAUSE_OUTSIDE_GAME:
            game.game_active.set()
        self.refresh()

    def _chat_auto_changed(self):
        core.chat_auto = bool(self.chat_auto_var.get())
        core.save_settings(chat_auto=core.chat_auto)
        core.log("Автоперевод чата " + ("включён" if core.chat_auto else "выключен"), "ok")
        self.refresh()

    def _answers_auto_changed(self):
        core.answers_auto = bool(self.answers_auto_var.get())
        core.save_settings(answers_auto=core.answers_auto)
        if core.answers_auto:
            core.log("Автоперевод ответов включён", "ok")
        else:
            core.events.put(("answers_hide", None))
            core.log(f"Автоперевод ответов выключен — переводите их кнопкой {hotkeys.K('answers_once')}")
        self.refresh()

    def _provider_changed(self):
        by_label = {v: k for k, v in PROVIDER_LABELS.items()}
        config.PROVIDER = by_label.get(self.main_var.get(), config.PROVIDER)
        fb = by_label.get(self.fb_var.get())
        config.FALLBACK_PROVIDERS = [fb] if fb and fb != config.PROVIDER else []
        core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
        chain = translate.provider_chain()
        core.log(f"Переводчик: {' → '.join(PROVIDER_NAMES.get(p, p) for p in chain) or 'нет ключей!'} (сохранено)", "ok")
        for p in [config.PROVIDER] + config.FALLBACK_PROVIDERS:
            if not translate.provider_has_key(p):
                core.log(f"У «{PROVIDER_NAMES.get(p, p)}» нет ключа — он будет пропущен", "warn")
        self.refresh()

    def _game_status(self):
        if not config.PAUSE_OUTSIDE_GAME:
            return "пауза вне игры выключена"
        if not game.game_exe:
            return f"не запомнена — включите автоперевод ({hotkeys.K('auto')}), находясь в игре"
        return f"{game.game_exe} · " + ("на экране" if game.game_active.is_set() else "⏸ свёрнута — пауза")

    def update_keys(self):
        for hid, kl in self.key_labels.items():
            if hotkeys.capturing == hid:
                kl.config(text="нажмите…", fg="#fc6")
            else:
                kl.config(text=hotkeys.K(hid), fg="#eee")

    def refresh(self):
        self.sync_vars()
        auto = "● ВКЛ" if core.auto_on.is_set() else "○ выкл"
        if self.busy:
            auto += "   ⏳ перевожу..."
        reg = f"{core.region[2]}×{core.region[3]} (x={core.region[0]}, y={core.region[1]})" if core.region else f"не выбрана ({hotkeys.K('select')})"
        areg = (f"{core.answers_region[2]}×{core.answers_region[3]} (x={core.answers_region[0]}, y={core.answers_region[1]})"
                + ("  · авто" if core.answers_auto else f"  · по кнопке {hotkeys.K('answers_once')}")
                if core.answers_region else f"не выбрана ({hotkeys.K('select_answers')})")
        creg = (f"{core.chat_region[2]}×{core.chat_region[3]} (x={core.chat_region[0]}, y={core.chat_region[1]})"
                + ("  · авто" if core.chat_auto else "  · выкл")
                if core.chat_region else f"нет ({hotkeys.K('select_chat')} — обвести окно чата)")
        reg2 = (f"{core.region2[2]}×{core.region2[3]} (x={core.region2[0]}, y={core.region2[1]})"
                if core.region2 else f"нет ({hotkeys.K('select_subs2')} — если НПС говорят ещё и в другом месте)")
        self.state.config(text=(
            f"Автоперевод:       {auto}\n"
            f"Область субтитров: {reg}\n"
            f"Область реплик 2:  {reg2}\n"
            f"Область ответов:   {areg}\n"
            f"Область чата:      {creg}\n"
            f"Игра:              {self._game_status()}\n"
            f"Озвучка:           {('вкл · ' + tts.voice_title()) if config.TTS_ENABLED else 'выкл'}\n"
            f"Переводчики:       {' → '.join(PROVIDER_NAMES.get(p, p) for p in translate.provider_chain()) or 'нет ключей!'}\n"
            f"Последний ответ:   {core.stats['last']}\n"
            f"Лимиты:            {limits.summary()}\n"
            + (f"Модели на паузе:   {llm.models_status()}\n" if any(p in translate.provider_chain() for p in ("gemini", "groq")) else "")
            + (f"Потрачено Claude:  ${core.stats['cost']:.4f} за сессию, ${llm.spent_total():.3f} всего"
               + (f" (~${core.stats['cost'] / core.stats['requests'] * 1000:.2f} за 1000 переводов)" if core.stats['requests'] else "")
               + "\n" if "claude" in translate.provider_chain() else "") +
            f"Запросов: {core.stats['requests']}   ошибок: {core.stats['errors']}"))

    def add_log(self, t, msg, level):
        self.log.config(state="normal")
        self.log.insert("end", f"{t} {msg}\n", level)
        # храним последние 100 строк
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 100:
            self.log.delete("1.0", f"{lines - 100}.0")
        self.log.see("end")
        self.log.config(state="disabled")
        if level == "error" and not self.visible:
            self.toggle()  # при ошибке панель сама показывается
