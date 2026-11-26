"""Тестовая сцена: окно «как в игре» с диалогом нескольких персонажей — проверить весь путь без игры.

Реплики сменяются сами (или кнопками), программа читает их с экрана, как в настоящей игре: проверяется захват
текста при смене реплики, перевод, ИИ-редактор, кто говорит, пол, возраст, чудовище и голоса.
Для сцены заводится свой пресет «Тестовая сцена» (персонажи и кэш — отдельно, перед каждым запуском — с нуля),
поэтому персонажи сцены не попадают к вашим играм. После закрытия всё возвращается как было.
"""
import os
import tkinter as tk

from . import config, core

PID = "testscene"
# (имя, реплика); реплика без имени — рассказчик. Отрывок одной истории: в ней заняты все голоса —
# девушка, старуха, старик, барон, мальчик, чудовище, торговец.
SCRIPT = [
    ("", "Night falls over Emberhold. A low rumble echoes from the old quarry beyond the walls."),
    ("Lyra", "There you are! I was starting to think you'd gotten lost in the marsh."),
    ("Lyra", "I came back as soon as I heard the bells. I was so worried about you."),
    ("Elder Bram", "Quiet, both of you. I have lived in this town for seventy years, and I know that sound."),
    ("Old Rotild", "Bram is right. My grandmother told me about it. The quarry golem is waking up."),
    ("Old Rotild", "The archive lost 12 scrolls last night. Someone took the binding runes on purpose."),
    ("Baron Alderich", "Enough! I am the lord of this keep, and I will not have rumors spread in my hall."),
    ("Baron Alderich", "Guards, close the gates. No one leaves Emberhold until morning."),
    ("Tim", "Mister, mister! I saw it! A big stone monster near the well, taller than the church!"),
    ("Lyra", "Tim, stay with your mother. I'll go with the stranger. I'm not afraid."),
    ("Merchant Gorran", "Wait, friend! Potions, three for 50 gold. Each one restores 40% HP. You'll need them."),
    ("Stone Golem", "WHO... DISTURBS... MY... SLEEP?"),
    ("Stone Golem", "THE RUNES... ARE GONE. NOW... EMBERHOLD... WILL... FALL."),
    ("Elder Bram", "Run! Get the children inside, now!"),
    ("Lyra", "No. I found the runes. Give me a minute, and I'll put him back to sleep."),
    ("", "The ground stops shaking. Somewhere a bird starts to sing again."),
]

BG, BOX, NAME, TEXT, MUTED = "#151922", "#0b0d12", "#e8c170", "#f2f2f2", "#8a8f9c"


class Scene:
    def __init__(self, app):
        self.app = app
        self.i = -1
        self.playing = True
        self.delay = 0             # 0 — «по озвучке»: следующая реплика, когда текущая дочитана
        self.timer = None
        self.prev = {"pid": core.active_profile, "auto": core.auto_on.is_set()}
        self._make_profile()
        w = self.win = tk.Toplevel(app.root)
        w.title("Тестовая сцена — AAC Translator")
        w.configure(bg=BG)
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        W, H = min(1100, sw - 100), min(680, sh - 120)
        w.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        w.protocol("WM_DELETE_WINDOW", self.close)
        bar = tk.Frame(w, bg="#20242e")
        bar.pack(fill="x")
        tk.Label(bar, text="Тестовая сцена", bg="#20242e", fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=12, pady=8)
        for t, fn in (("Закрыть", self.close), ("Далее ▶", self.next), ("◀ Назад", self.back)):
            tk.Button(bar, text=t, command=fn, bg="#2d3240", fg="#fff", relief="flat", padx=12,
                      activebackground="#5865f2", activeforeground="#fff").pack(side="right", padx=4, pady=6)
        self.pbtn = tk.Button(bar, text="⏸ Пауза", command=self.toggle, bg="#2d3240", fg="#fff", relief="flat",
                              padx=12, activebackground="#5865f2", activeforeground="#fff")
        self.pbtn.pack(side="right", padx=4, pady=6)
        self.spd = tk.StringVar(value="по озвучке")
        tk.OptionMenu(bar, self.spd, "по озвучке", "3 с", "6 с", "10 с", command=self._speed).pack(side="right")
        self.stage = tk.Canvas(w, bg=BG, highlightthickness=0)
        self.stage.pack(fill="both", expand=True)
        self.count = tk.Label(w, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.count.place(relx=0.07, rely=0.062)
        # окно субтитров «игры»: имя сверху, реплика ниже
        self.box = tk.Frame(w, bg=BOX, padx=24, pady=16)
        self.box.place(relx=0.5, rely=0.97, anchor="s", relwidth=0.86, relheight=0.30)
        self.name = tk.Label(self.box, text="", bg=BOX, fg=NAME, font=("Segoe UI", 13, "bold"), anchor="w")
        self.name.pack(fill="x")
        self.text = tk.Label(self.box, text="", bg=BOX, fg=TEXT, font=("Segoe UI", 14), anchor="nw",
                             justify="left")
        self.box.bind("<Configure>", lambda e: self.text.config(wraplength=max(200, e.width - 50)))
        self.text.pack(fill="both", expand=True)
        # перевод и голос — прямо в окне сцены (видно на скриншоте; окна перевода программы на время сцены не нужны)
        self.tr = tk.Frame(w, bg="#1d2230", padx=20, pady=14)
        self.tr.place(relx=0.93, rely=0.10, anchor="ne", relwidth=0.60, relheight=0.52)
        # «кадр игры»: кто говорит — простая картинка (для редактора, который смотрит на экран)
        self.pic = tk.Canvas(w, bg="#232a3a", highlightthickness=0)
        self.pic.place(relx=0.07, rely=0.10, anchor="nw", relwidth=0.24, relheight=0.52)
        tk.Label(self.tr, text="ПЕРЕВОД", bg="#1d2230", fg=MUTED, font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x")
        self.tr_text = tk.Label(self.tr, text="…", bg="#1d2230", fg=TEXT, font=("Segoe UI", 15), anchor="nw",
                                justify="left")
        self.tr_text.pack(fill="both", expand=True, pady=(4, 0))
        self.tr.bind("<Configure>", lambda e: self.tr_text.config(wraplength=max(200, e.width - 50)))
        self.voice = tk.Label(self.tr, text="", bg="#1d2230", fg="#9db0ff", font=("Segoe UI", 11), anchor="w",
                              justify="left")
        self.voice.pack(fill="x")
        self.seen = tk.Label(self.tr, text="", bg="#1d2230", fg=MUTED, font=("Segoe UI", 10), anchor="w",
                             justify="left")
        self.seen.pack(fill="x", pady=(6, 0))
        self.tr.bind("<Configure>", lambda e: (self.tr_text.config(wraplength=max(200, e.width - 50)),
                                               self.seen.config(wraplength=max(200, e.width - 50))), add="+")
        self._voice_t = 0
        self._seen_t = 0
        w.lift()
        w.attributes("-topmost", True)
        w.after(400, self._start)

    # ---------- пресет сцены ----------
    def _make_profile(self):
        from . import profiles
        profs = profiles.all_profiles()
        if PID not in profs:
            profs[PID] = {"name": "Тестовая сцена", "exes": [], "test": True,
                          "desc": "a fantasy role-playing game (built-in test scene)",
                          "about": "Fantasy RPG. Town of Emberhold: a young woman Lyra, an old archivist woman Rotild, "
                                   "old Elder Bram, Baron Alderich, a little boy Tim, a stone golem monster, "
                                   "merchant Gorran."}
            core.save_settings(profiles=profs)
        d = profiles.folder(PID)
        for f in ("characters.json", "translation_cache.json"):          # каждый раз — с нуля
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
        os.makedirs(d, exist_ok=True)

    def _start(self):
        from . import profiles
        self.win.update_idletasks()
        b = self.box
        reg = (b.winfo_rootx(), b.winfo_rooty(), b.winfo_width(), b.winfo_height())
        profs = profiles.all_profiles()
        profs[PID].update(region=list(reg), answers_region=None, region2=None, chat_region=None,
                          menu_region=None)
        core.save_settings(profiles=profs)
        core.test_scene = True
        profiles.activate(PID, hold=True)
        core.auto_on.set()
        from . import game
        game.game_active.set()            # «в игре» — иначе автоперевод стоит на паузе «жду игру»
        core.log("🧪 Тестовая сцена: реплики сменяются сами — программа читает их с экрана, как в игре", "ok")
        core.events.put(("panel", None))
        self._poll_voice()
        self.next()

    # ---------- показ ----------
    def show(self):
        name, line = SCRIPT[self.i]
        self.count.config(text=f"реплика {self.i + 1} из {len(SCRIPT)}")
        self.name.config(text=name)
        self.text.config(text=line)
        self._draw(name)
        self.tr_text.config(text="…", fg=MUTED)
        self.voice.config(text="")
        self._plan()

    def _draw(self, name):
        """Простой «портрет» говорящего: девушка, старуха, старик, барон, мальчик, голем, торговец."""
        c = self.pic
        c.delete("all")
        c.update_idletasks()
        W, H = max(120, c.winfo_width()), max(160, c.winfo_height())
        cx, base = W // 2, H - 20
        skin, k = "#e0b48f", min(W, H) / 300
        n = (name or "").lower()

        def person(h, body, hair=None, beard=False, crown=False, cane=False, bag=False, dress=False):
            top = base - h * k
            head = 26 * k * (h / 220)
            if dress:
                c.create_polygon(cx - 50 * k, base, cx + 50 * k, base, cx + 22 * k, top + head * 2.2,
                                 cx - 22 * k, top + head * 2.2, fill=body, outline="")
            else:
                c.create_rectangle(cx - 30 * k, top + head * 2.2, cx + 30 * k, base, fill=body, outline="")
            c.create_oval(cx - head, top, cx + head, top + head * 2.2, fill=skin, outline="")
            if hair:
                c.create_arc(cx - head - 2, top - 2, cx + head + 2, top + head * 2, start=0, extent=180,
                             fill=hair, outline="")
            if beard:
                c.create_polygon(cx - head * .8, top + head * 1.4, cx + head * .8, top + head * 1.4,
                                 cx, top + head * 3.2, fill="#e8e8e8", outline="")
            if crown:
                c.create_polygon(cx - head, top + 4, cx - head, top - head * .9, cx - head * .4, top - head * .3,
                                 cx, top - head, cx + head * .4, top - head * .3, cx + head, top - head * .9,
                                 cx + head, top + 4, fill="#e8c170", outline="")
            if cane:
                c.create_line(cx + 45 * k, top + head * 2.6, cx + 52 * k, base, fill="#8b5a2b", width=max(3, 5 * k))
            if bag:
                c.create_oval(cx + 26 * k, base - 70 * k, cx + 70 * k, base - 20 * k, fill="#8b6b3d", outline="")

        if "golem" in n:
            g = "#7d7f86"
            c.create_rectangle(cx - 70 * k, base - 230 * k, cx + 70 * k, base, fill=g, outline="#5c5e64", width=3)
            c.create_rectangle(cx - 45 * k, base - 300 * k, cx + 45 * k, base - 225 * k, fill=g, outline="#5c5e64",
                               width=3)
            for dx in (-20, 20):
                c.create_oval(cx + dx * k - 8, base - 270 * k - 6, cx + dx * k + 8, base - 270 * k + 6, fill="#ff8a3d")
        elif "lyra" in n:
            person(220, "#3f7d5a", hair="#b8462e", dress=True)
        elif "rotild" in n:
            person(190, "#5b4a6b", hair="#d9d9d9", dress=True, cane=True)
        elif "bram" in n:
            person(200, "#5a4a3a", hair="#d9d9d9", beard=True, cane=True)
        elif "baron" in n:
            person(240, "#7a1f2b", hair="#3a2a1a", crown=True)
        elif "tim" in n:
            person(130, "#3c6fb0", hair="#c99a4b")
        elif "merchant" in n or "gorran" in n:
            person(215, "#a86b2d", hair="#3a2a1a", beard=True, bag=True)
        else:
            c.create_text(cx, H // 2, text="🏰", font=("Segoe UI Emoji", int(48 * k) or 24), fill="#9aa")

    # ---------- перевод и голос в окне сцены ----------
    def on_translation(self, text):
        self.tr_text.config(text=text, fg=TEXT)

    def on_improve(self, draft, better):
        if self.tr_text.cget("text") == draft:
            self.tr_text.config(text=better)

    def _poll_voice(self):
        """Кем озвучивается реплика: голос, пол, характер (из озвучки)."""
        from . import tts
        try:
            lv = getattr(tts, "last_voice", None)
            if lv and lv["t"] != self._voice_t:
                self._voice_t = lv["t"]
                self.voice.config(text="🔊 " + lv["desc"])
        except Exception:
            pass
        try:                                   # что редактор понял о сцене (по скриншоту или по тексту)
            from . import editor
            st = editor._state
            if not config.EDITOR_ON:
                note = "ИИ-редактор выключен — сцену никто не «смотрит»"
            elif editor.is_custom_id(editor.name()) and config.EDITOR_SCENE_IMAGE:
                note = ("«Смотреть на экран»: свой ИИ (" + editor.name_of(editor.name()) + ") картинки не получает — "
                        "заметка о сцене только по тексту")
            else:
                note = ""
            if st.get("scene_at_t", 0) != self._seen_t and st.get("scene"):
                self._seen_t = st["scene_at_t"]
                note = ("🖼 Редактор посмотрел на экран: " if st.get("scene_shot") else "📝 Заметка о сцене по тексту: ") \
                    + st["scene"][:220]
                self.seen.config(text=note)
            elif note and not self.seen.cget("text").startswith(("🖼", "📝")):
                self.seen.config(text=note)
        except Exception:
            pass
        try:
            self.win.after(300, self._poll_voice)
        except tk.TclError:
            pass

    def _plan(self):
        if self.timer:
            self.win.after_cancel(self.timer)
            self.timer = None
        if self.playing:
            if self.delay:
                self.timer = self.win.after(self.delay * 1000, self._auto)
            else:
                import time
                self._shown_at, self._heard = time.time(), False
                self.timer = self.win.after(500, self._wait_voice)

    def _wait_voice(self):
        """Ждём, пока реплику переведут и дочитают (как игрок, который слушает), потом — следующая."""
        import time
        from . import tts
        self.timer = None
        if not self.playing:
            return
        talking = tts.speaking()
        self._heard = self._heard or talking
        waited = time.time() - self._shown_at
        if (self._heard and not talking and waited > 2) or waited > 30 or (not config.TTS_ENABLED and waited > 6):
            self.timer = self.win.after(800, self._auto)    # короткая пауза после реплики
        else:
            self.timer = self.win.after(250, self._wait_voice)

    def _auto(self):
        self.timer = None
        if self.i >= len(SCRIPT) - 1:
            self.playing = False
            self.pbtn.config(text="▶ Сначала")
            core.log("🧪 Тестовая сцена закончилась — посмотрите «Озвучка → Персонажи»: кто какого пола и характера")
            return
        self.next()

    def _blank_then(self, fn):
        """Между репликами коротко пусто — как в играх при смене реплики."""
        self.name.config(text="")
        self.text.config(text="")
        self.win.after(250, fn)

    def next(self):
        if self.i < len(SCRIPT) - 1:
            self.i += 1
            self._blank_then(self.show)

    def back(self):
        if self.i > 0:
            self.i -= 1
            self._blank_then(self.show)

    def toggle(self):
        if not self.playing and self.i >= len(SCRIPT) - 1:
            self.i = -1
            self.playing = True
            self.pbtn.config(text="⏸ Пауза")
            self.next()
            return
        self.playing = not self.playing
        self.pbtn.config(text="⏸ Пауза" if self.playing else "▶ Дальше")
        self._plan()

    def _speed(self, v):
        self.delay = 0 if str(v).startswith("по") else int(str(v).split()[0])
        self._plan()

    def close(self):
        from . import profiles
        if self.timer:
            self.win.after_cancel(self.timer)
        core.test_scene = False
        if not self.prev["auto"]:
            core.auto_on.clear()
        profiles.activate(self.prev["pid"] if self.prev["pid"] != PID else None, announce=False)
        core.log("🧪 Тестовая сцена закрыта — всё вернулось как было")
        core.events.put(("panel", None))
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app._scene = None


def open_scene(app):
    s = getattr(app, "_scene", None)
    if s:
        try:
            s.win.lift()
            return
        except tk.TclError:
            pass
    app._scene = Scene(app)
