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
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene")

# (имя, реплика, кадр). Реплика без имени — рассказчик. «Пропавший караван», глава первая: заняты все голоса —
# молодая путешественница, весёлый алхимик, старый волшебник, мудрая наставница, мальчик, король, голем.
# Героиня (игрок) молчит — как в играх, где за неё отвечают вариантами ответа.
SCRIPT = [
    # Рыночный квартал
    ("", "Evening falls over the market quarter. The last merchants are packing up their stalls.", "traveler"),
    ("Mira", "There you are! I've been looking for someone with a sword all day.", "traveler"),
    ("Mira", "A caravan has gone missing beyond the north gate. Will you help me find it?", "traveler"),
    ("Mira", "It carried medicine for the village. Without it, people will start getting sick within a week.", "traveler"),
    ("Mira", "The last one to see the wagons was Fenwick, the alchemist. Let's start with him.", "traveler"),
    # Лавка алхимика
    ("Alchemist Fenwick", "Ah, customers! A healing draught? A potion of courage? Today only, two for the price of three!", "alchemist"),
    ("Mira", "We're not here to buy, Fenwick. What do you know about the caravan?", "alchemist"),
    ("Alchemist Fenwick", "The caravan? Half of my herbs were on those wagons! The drivers took the old road past the ruins.", "alchemist"),
    ("Alchemist Fenwick", "Nobody takes that road anymore. They say the stones there move at night.", "alchemist"),
    # Старый волшебник
    ("Old Wizard Orren", "Moving stones, you say? Hmm... I have not heard those words in forty years.", "wizard"),
    ("Old Wizard Orren", "Long ago, the king's mages built a guardian out of the mountain itself. A golem.", "wizard"),
    ("Old Wizard Orren", "It was put to sleep when the war ended. Something must have woken it.", "wizard"),
    # Библиотека наставницы
    ("Mentor Ysolde", "Orren is right, but he is forgetting the most important part.", "mentor"),
    ("Mentor Ysolde", "The golem obeys the one who holds the Heart Stone. And the stone was given to the royal family.", "mentor"),
    ("Mentor Ysolde", "If the golem has woken up, someone has taken the stone from the palace. Go to the king.", "mentor"),
    # Мальчик у ворот
    ("Pip", "Wait! Wait! Are you going to the ruins? I saw the wagons there yesterday!", "boy"),
    ("Pip", "There was a huge stone giant! Its eyes were burning like torches! I hid in the bushes and ran all the way home.", "boy"),
    ("Pip", "Take me with you! I know a shortcut! Please?", "boy"),
    ("Mira", "Absolutely not, Pip. Go home before your mother starts looking for you.", "boy"),
    # Тронный зал
    ("King Aldric", "So the rumors are true. I hoped I would never have to tell anyone this.", "king"),
    ("King Aldric", "The Heart Stone was stolen from my treasury three nights ago. My guards found no one.", "king"),
    ("King Aldric", "Bring back the caravan and the stone, and the crown will not forget your service.", "king"),
    # Руины
    ("", "The old road leads to the ruins. Among the broken walls stands a giant of moss-covered stone.", "golem"),
    ("Stone Golem", "WHO... DISTURBS... THE GUARDIAN...", "golem"),
    ("Stone Golem", "THE HEART... IS GONE... THE THIEVES... HAVE FLED... NORTH...", "golem"),
    ("Stone Golem", "RETURN... THE HEART... AND I WILL SLEEP... AGAIN...", "golem"),
    # Ночь у замка
    ("", "Late at night, the heroes return to the castle gates.", "castle"),
    ("Mira", "The caravan is safe, and the golem let us pass. But the thieves are still out there.", "castle"),
    ("Mira", "Whoever took the Heart Stone knew exactly where the king kept it.", "castle"),
    ("Mira", "Rest tonight. Tomorrow at dawn we ride north.", "castle"),
    ("", "And so ends the first chapter. Somewhere in the northern mountains, someone is waiting for the Heart Stone to awaken...", "castle"),
    ("", "End of Chapter One.", "castle"),
]

# описание «игры» — по нему программа понимает пол и характер, как по описанию настоящей игры из Steam
ABOUT = ("Fantasy RPG, chapter one «The Lost Caravan». The player meets: a young red-haired traveler woman Mira; "
         "Fenwick the alchemist, a cheerful merchant; King Aldric; a wise old woman mentor Ysolde; "
         "an old wizard Orren; a little boy Pip who dreams of adventure; an ancient stone golem monster guarding the ruins.")

BG, NAME, TEXT, MUTED, INFO = "#0b0d12", "#e8c170", "#f4f1ea", "#8a8f9c", "#161a22"
SUB_TOP, SUB_BOTTOM, SUB_SIDE = 0.775, 0.985, 0.11     # где на «экране игры» субтитры (доли кадра)


class Scene:
    def __init__(self, app):
        self.app = app
        self.i = -1
        self.playing = True
        self.delay = 0             # 0 — «по озвучке»: следующая реплика, когда текущая дочитана
        self.timer = None
        self.cur_line = ""
        self._frame_key = None
        self._reg = None
        self._reg_job = None
        self.prev = {"pid": core.active_profile, "auto": core.auto_on.is_set()}
        self._make_profile()
        w = self.win = tk.Toplevel(app.root)
        w.title("Тестовая сцена — AAC Translator")
        w.configure(bg=BG)
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        W = min(1280, sw - 80, int((sh - 220) * 16 / 9))
        H = W * 9 // 16 + 130
        w.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(0, (sh - H) // 2 - 20)}")
        w.protocol("WM_DELETE_WINDOW", self.close)
        bar = tk.Frame(w, bg="#20242e")
        bar.pack(fill="x")
        tk.Label(bar, text="Тестовая сцена", bg="#20242e", fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=(12, 6), pady=8)
        self.count = tk.Label(bar, text="", bg="#20242e", fg=MUTED, font=("Segoe UI", 9))
        self.count.pack(side="left", pady=8)
        for t, fn in (("Закрыть", self.close), ("Далее ▶", self.next), ("◀ Назад", self.back)):
            tk.Button(bar, text=t, command=fn, bg="#2d3240", fg="#fff", relief="flat", padx=12,
                      activebackground="#5865f2", activeforeground="#fff").pack(side="right", padx=4, pady=6)
        self.pbtn = tk.Button(bar, text="⏸ Пауза", command=self.toggle, bg="#2d3240", fg="#fff", relief="flat",
                              padx=12, activebackground="#5865f2", activeforeground="#fff")
        self.pbtn.pack(side="right", padx=4, pady=6)
        self.spd = tk.StringVar(value="по озвучке")
        tk.OptionMenu(bar, self.spd, "по озвучке", "3 с", "6 с", "10 с", command=self._speed).pack(side="right")
        # перевод и голос — полоса над «экраном игры» (на сам кадр не ложится)
        self.tr = tk.Frame(w, bg=INFO, padx=14, pady=6)
        self.tr.pack(fill="x")
        self.tr_text = tk.Label(self.tr, text="…", bg=INFO, fg=MUTED, font=("Segoe UI", 12), anchor="w",
                                justify="left")
        self.tr_text.pack(fill="x")
        self.voice = tk.Label(self.tr, text="", bg=INFO, fg="#9db0ff", font=("Segoe UI", 10), anchor="w",
                              justify="left")
        self.voice.pack(fill="x")
        self.seen = tk.Label(self.tr, text="", bg=INFO, fg=MUTED, font=("Segoe UI", 9), anchor="w", justify="left")
        self.seen.pack(fill="x")
        self.tr.bind("<Configure>", lambda e: [x.config(wraplength=max(200, e.width - 30))
                                               for x in (self.tr_text, self.voice, self.seen)])
        # «экран игры»: кадр во всё окно, субтитры внизу поверх кадра
        self.stage = tk.Canvas(w, bg=BG, highlightthickness=0)
        self.stage.pack(fill="both", expand=True)
        self.stage.bind("<Configure>", lambda e: self._redraw())
        w.bind("<Configure>", lambda e: self._follow(), add="+")      # окно двигают — область едет вместе с ним
        self._voice_t = 0
        self._seen_t = 0
        w.lift()
        w.attributes("-topmost", True)
        w.after(400, self._start)

    # ---------- пресет сцены ----------
    def _make_profile(self):
        from . import profiles
        profs = profiles.all_profiles()
        if PID not in profs or profs[PID].get("about") != ABOUT:
            profs.setdefault(PID, {"name": "Тестовая сцена", "exes": [], "test": True})
            profs[PID].update(desc="a fantasy role-playing game (built-in test scene)", about=ABOUT)
            core.save_settings(profiles=profs)
        d = profiles.folder(PID)
        for f in ("characters.json", "translation_cache.json"):          # каждый раз — с нуля
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
        os.makedirs(d, exist_ok=True)

    def sub_rect(self):
        """Где субтитры на экране (left, top, width, height) — это и есть область, которую читает программа."""
        c = self.stage
        W, H = c.winfo_width(), c.winfo_height()
        x0, y0 = c.winfo_rootx(), c.winfo_rooty()
        return (x0 + int(W * SUB_SIDE), y0 + int(H * SUB_TOP), int(W * (1 - 2 * SUB_SIDE)),
                int(H * (SUB_BOTTOM - SUB_TOP)))

    def _start(self):
        from . import profiles
        self.win.update_idletasks()
        reg = self._reg = self.sub_rect()
        profs = profiles.all_profiles()
        profs[PID].update(region=list(reg), answers_region=None, region2=None, chat_region=None,
                          menu_region=None)
        core.save_settings(profiles=profs)
        core.test_scene = True
        profiles.activate(PID, hold=True)
        core.auto_on.set()
        from . import game
        game.game_active.set()            # «в игре» — иначе автоперевод стоит на паузе «жду игру»
        core.log("🧪 Тестовая сцена: реплики сменяются сами — программа читает их с экрана, как в игре. "
                 "Окно можно двигать и растягивать — область субтитров едет вместе с ним", "ok")
        core.events.put(("panel", None))
        self._poll_voice()
        self.next()

    def _follow(self):
        """Окно сцены сдвинули или растянули — область субтитров переезжает следом (с небольшой задержкой)."""
        if self._reg is None:
            return
        if self._reg_job:
            self.win.after_cancel(self._reg_job)
        self._reg_job = self.win.after(120, self._move_region)

    def _move_region(self):
        from . import profiles
        self._reg_job = None
        try:
            reg = self.sub_rect()
        except tk.TclError:
            return
        if reg == self._reg or reg[2] < 50 or reg[3] < 20 or core.active_profile != PID:
            return
        self._reg = reg
        core.region = reg
        profs = profiles.all_profiles()
        if PID in profs:
            profs[PID]["region"] = list(reg)
            core.save_settings(profiles=profs)

    # ---------- показ ----------
    def show(self):
        name, line, _bg = SCRIPT[self.i]
        self.count.config(text=f"· реплика {self.i + 1} из {len(SCRIPT)}")
        self.cur_line = line
        self._redraw()
        self.tr_text.config(text="…", fg=MUTED)
        self.voice.config(text="")
        self._plan()

    def _frame(self, bg, W, H):
        """Кадр «игры»: картинка во всё окно (лишнее по краям обрезается), низ затемнён под субтитры."""
        from PIL import Image, ImageTk
        key = (bg, W, H)
        if self._frame_key == key:
            return self._ph
        path = os.path.join(IMG_DIR, bg + ".jpg")
        if os.path.exists(path):
            im = Image.open(path).convert("RGB")
            k = max(W / im.width, H / im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
            x, y = (im.width - W) // 2, (im.height - H) // 2
            im = im.crop((x, y, x + W, y + H))
        else:
            im = Image.new("RGB", (W, H), "#1d2230")
        top = int(H * (SUB_TOP - 0.10))
        shade = Image.new("L", (1, H), 0)
        for yy in range(top, H):
            shade.putpixel((0, yy), min(215, int(215 * (yy - top) / max(1, H * 0.12))))
        im = Image.composite(Image.new("RGB", (W, H), "#000000"), im, shade.resize((W, H)))
        self._ph, self._frame_key = ImageTk.PhotoImage(im), key
        return self._ph

    def _redraw(self, blank=False):
        c = self.stage
        W, H = c.winfo_width(), c.winfo_height()
        if W < 50 or H < 50:
            return
        name, line, bg = SCRIPT[max(0, self.i)] if self.i >= 0 else ("", "", "traveler")
        c.delete("all")
        try:
            c.create_image(0, 0, image=self._frame(bg, W, H), anchor="nw")
        except Exception:
            pass
        if blank or self.i < 0:
            return
        fs = max(11, int(H / 34))
        y = int(H * (SUB_TOP + 0.02))
        if name:
            c.create_text(W // 2, y, text=name, fill=NAME, font=("Georgia", max(10, int(fs * 0.85))), anchor="n")
            y += int(fs * 1.9)
        c.create_text(W // 2, y, text=line, fill=TEXT, font=("Georgia", fs), anchor="n", justify="center",
                      width=int(W * (1 - 2 * SUB_SIDE) - 20))

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
                self._shown_at, self._heard, self._quiet_since = time.time(), False, None
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
        now = time.time()
        if talking:
            self._quiet_since = None
        elif self._heard and getattr(self, "_quiet_since", None) is None:
            self._quiet_since = now
        quiet = self._heard and not talking and now - (self._quiet_since or now) >= 1.2   # между фразами бывают паузы
        waited = now - self._shown_at
        if (quiet and waited > 2) or waited > 30 or (not config.TTS_ENABLED and waited > 6):
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
        self.cur_line = ""
        self._redraw(blank=True)
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
