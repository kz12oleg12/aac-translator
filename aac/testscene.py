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
# (имя, реплика) — реплика без имени: рассказчик; список — варианты ответа
SCRIPT = [
    ("", "The gates of Emberhold creak open as the evening bell rings."),
    ("Lyra", "There you are! I was starting to think you'd gotten lost in the marsh."),
    ("Lyra", "I came back as soon as I heard. I was so worried. Tell me, are you hurt?"),
    ("", ["I'm fine. Who are you?", "What happened here?", "Leave"]),
    ("Old Rotild", "Sit down, child. These old bones have seen three wars, and this one frightens me the most."),
    ("Old Rotild", "The archive lost 12 scrolls last night. Each one is worth 300 gold."),
    ("Baron Alderich", "Enough! I am the lord of this keep, and I will not have rumors spread in my hall."),
    ("Tim", "Mister, mister! I saw a big stone monster near the well! Can I come with you?"),
    ("Stone Golem", "WHO... DISTURBS... MY... SLEEP?"),
    ("Lyra", "Stay behind me. I'll handle this."),
    ("Merchant Gorran", "Potions! Three for 50 gold, each one restores 40% HP. Don't die out there, friend."),
    ("", ["Buy 3 potions", "Ask about the golem", "Goodbye"]),
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
        self.count.place(relx=0.015, rely=0.08)
        # окно субтитров «игры»: имя сверху, реплика ниже
        self.box = tk.Frame(w, bg=BOX, padx=24, pady=16)
        self.box.place(relx=0.5, rely=0.97, anchor="s", relwidth=0.86, relheight=0.30)
        self.name = tk.Label(self.box, text="", bg=BOX, fg=NAME, font=("Segoe UI", 13, "bold"), anchor="w")
        self.name.pack(fill="x")
        self.text = tk.Label(self.box, text="", bg=BOX, fg=TEXT, font=("Segoe UI", 14), anchor="nw",
                             justify="left")
        self.box.bind("<Configure>", lambda e: self.text.config(wraplength=max(200, e.width - 50)))
        self.text.pack(fill="both", expand=True)
        # варианты ответа — справа
        self.ans = tk.Frame(w, bg=BOX, padx=18, pady=12)
        self.ans.place(relx=0.97, rely=0.08, anchor="ne", relwidth=0.36, relheight=0.30)
        self.ans_lbl = tk.Label(self.ans, text="", bg=BOX, fg=TEXT, font=("Segoe UI", 13), anchor="nw",
                                justify="left")
        self.ans.bind("<Configure>", lambda e: self.ans_lbl.config(wraplength=max(150, e.width - 40)))
        self.ans_lbl.pack(fill="both", expand=True)
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
                                   "Baron Alderich, a little boy Tim, a stone golem monster, merchant Gorran."}
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
        b, a = self.box, self.ans
        reg = (b.winfo_rootx(), b.winfo_rooty(), b.winfo_width(), b.winfo_height())
        areg = (a.winfo_rootx(), a.winfo_rooty(), a.winfo_width(), a.winfo_height())
        profs = profiles.all_profiles()
        profs[PID].update(region=list(reg), answers_region=list(areg), region2=None, chat_region=None,
                          menu_region=None)
        core.save_settings(profiles=profs)
        core.test_scene = True
        profiles.activate(PID, hold=True)
        core.auto_on.set()
        from . import game
        game.game_active.set()            # «в игре» — иначе автоперевод стоит на паузе «жду игру»
        core.log("🧪 Тестовая сцена: реплики сменяются сами — программа читает их с экрана, как в игре", "ok")
        core.events.put(("panel", None))
        self.next()

    # ---------- показ ----------
    def show(self):
        name, line = SCRIPT[self.i]
        self.count.config(text=f"реплика {self.i + 1} из {len(SCRIPT)}")
        if isinstance(line, list):
            self.ans_lbl.config(text="\n".join(f"{n}. {t}" for n, t in enumerate(line, 1)))
            self.name.config(text="")
            self.text.config(text="")
        else:
            self.ans_lbl.config(text="")
            self.name.config(text=name)
            self.text.config(text=line)
        self._plan()

    def _plan(self):
        if self.timer:
            self.win.after_cancel(self.timer)
            self.timer = None
        if self.playing:
            answers = 0 <= self.i < len(SCRIPT) and isinstance(SCRIPT[self.i][1], list)
            if self.delay or answers:             # варианты ответа не озвучиваются — просто 6 с
                self.timer = self.win.after((self.delay or 6) * 1000, self._auto)
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
        self.ans_lbl.config(text="")
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
