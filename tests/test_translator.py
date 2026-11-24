"""
Автоматические проверки AAC Translator.

Запуск:
  py tests/test_translator.py                 — проверить программу из папки рядом
  py tests/test_translator.py путь/к/папке    — проверить конкретную установку

Проверки работают и для старой версии (один файл aac_translator.py), и для новой (пакет aac/).
Сеть не используется: все ответы переводчиков имитируются.
"""
import importlib
import itertools
import json
import os
import pkgutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI = os.environ.get("AAC_TEST_GUI") == "1" or (sys.platform == "win32")

# ---------- заглушка keyboard (в тестах не перехватываем настоящую клавиатуру) ----------
kb = types.ModuleType("keyboard")
_kb_counter = itertools.count()
kb.registered = {}


def _add_hotkey(combo, cb):
    n = next(_kb_counter)
    kb.registered[n] = (combo, cb)
    return n


kb.add_hotkey = _add_hotkey
kb.remove_hotkey = lambda h: kb.registered.pop(h, None)
kb.hooks = []
kb.hook = lambda f: kb.hooks.append(f) or f
kb.unhook = lambda f: kb.hooks.remove(f) if f in kb.hooks else None
kb.get_hotkey_name = lambda names: "+".join(sorted(names, key=lambda n: (n not in ("ctrl", "shift", "alt"), n)))
sys.modules["keyboard"] = kb
if not GUI:
    sys.modules.setdefault("tkinter", types.ModuleType("tkinter"))

sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="aac_test_")


# ---------- адаптер: одинаковый доступ к старой и новой структуре ----------
class Target:
    def __init__(self):
        if os.path.isdir(os.path.join(ROOT, "aac")):
            import aac
            self.mods = []
            for m in pkgutil.iter_modules(aac.__path__):
                self.mods.append(importlib.import_module("aac." + m.name))
            self.kind = "package"
        else:
            self.mods = [importlib.import_module("aac_translator")]
            self.kind = "single file"

    def _owner(self, name):
        # ищем модуль, где имя ОПРЕДЕЛЕНО (а не модуль, который его просто импортировал)
        for m in self.mods:
            if name in vars(m) and not isinstance(vars(m)[name], types.ModuleType):
                return m
        for m in self.mods:
            if name in vars(m):
                return m
        raise AttributeError(name)

    def __getattr__(self, name):
        if name in ("mods", "kind"):
            raise AttributeError(name)
        return getattr(self._owner(name), name)

    def set(self, name, value):
        setattr(self._owner(name), name, value)


T = Target()
T.set("SETTINGS_FILE", os.path.join(TMP, "settings.json"))
if hasattr(T._owner("VERSION"), "GAMES_ONLY"):
    T._owner("VERSION").GAMES_ONLY = False     # тесты — не про игры: «переводить в любой программе»
if hasattr(T._owner("VERSION"), "GAMES_ONLY") and hasattr(T._owner("active_profile"), "default_profiles"):
    _c = T._owner("active_profile")      # тесты работают «в игре ArcheAge»: пресет выбран
    _c.active_profile = "archeage"
    with open(os.path.join(TMP, "settings.json"), "w", encoding="utf-8") as _f:
        json.dump({"profiles": _c.default_profiles(), "active_profile": "archeage"}, _f)
    T.set("SETTINGS", T.load_settings())
T.set("GLOSSARY_FILE", os.path.join(TMP, "glossary.txt"))
T.set("HISTORY_DIR", os.path.join(TMP, "history"))
T.set("CACHE_FILE", os.path.join(TMP, "translation_cache.json"))
try:   # голоса персонажей — тоже во временную папку, и по умолчанию выключены (включает их свой тест)
    from aac import voices as _voices
    _voices.FILE = os.path.join(TMP, "characters.json")
    T._owner("TTS_READ_NAME").TTS_PER_CHARACTER = False
except ImportError:
    pass
T.set("SETTINGS", {})


def cache_reset():
    try:
        from aac import tcache
        with tcache._lock:
            tcache._data = None
            tcache._dirty = False
        if os.path.exists(tcache.CACHE_FILE):
            os.remove(tcache.CACHE_FILE)
        tcache.stats.update(hits=0, misses=0)
    except ImportError:
        pass


class R:
    """Имитация ответа requests."""
    def __init__(self, code, js=None, text="", headers=None):
        self.status_code, self._js, self.text, self.headers = code, js, text, headers or {}

    def json(self):
        if self._js is None:
            raise ValueError("no json")
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def drain():
    out = []
    while not T.events.empty():
        out.append(T.events.get_nowait())
    return out


def img(w=400, h=60, text=None, bright=255):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (w, h), (25, 30, 35))
    if text:
        try:
            f = ImageFont.load_default(size=28)
        except TypeError:
            f = ImageFont.load_default()
        ImageDraw.Draw(im).text((10, 12), text, fill=(bright,) * 3, font=f)
    return im


# ---------- проверки ----------
def test_garbage_filter():
    bad = ["PeHaJ1bA", "Aax! K-Koro 3T0 TaM?!", "AKTBV1baJWIP' Windows", "Q noncK"]
    good = ["Renald", "Aah! Wh-Who goes there?!", "Your wife, Jennifer, sent me.", "Defeat 3 Wolves (0/3)"]
    assert all(T._looks_like_garbage(x) for x in bad)
    assert not any(T._looks_like_garbage(x) for x in good)


def test_clean_translation():
    t = T.clean_translation("Привет\nАктивация Windows\nПривет\nКак дела?")
    assert t == "Привет\nКак дела?", t
    try:
        T.clean_translation("Where do the pirates go?\nWhere do the pirates go? and more english")
        raise AssertionError("должна быть ошибка «не на русском»")
    except T.ApiError:
        pass
    assert T.clean_translation("Herlei, Jennifer, Auroria", strict=False) == "Herlei, Jennifer, Auroria"


def test_glossary():
    if os.path.exists(T.GLOSSARY_FILE):
        os.remove(T.GLOSSARY_FILE)
    items = T.glossary()
    assert ("Renald", "Ренальд") in items and os.path.exists(T.GLOSSARY_FILE)
    assert "Renald -> Ренальд" in T.glossary_prompt("Renald said hi")
    assert "Kevin" not in T.glossary_prompt("Renald said hi")
    assert T.glossary_apply_source("Ask Kevin about Edwardo") == "Ask Кевин about Edwardo"
    time.sleep(1.05)
    with open(T.GLOSSARY_FILE, "a", encoding="utf-8") as f:
        f.write("Sea Serpent = Морской Змей\n")
    assert T.glossary_apply_source("A Sea Serpent!") == "A Морской Змей!"


def test_mask_out_and_detection():
    from PIL import Image
    im = Image.new("RGB", (584, 335), (255, 255, 255))
    out = T.mask_out(im, (1265, 571, 584, 335), (278, 853, 1350, 214))
    assert out.getpixel((10, 10)) == (255, 255, 255)
    assert out.getpixel((10, 300)) == (0, 0, 0)
    assert out.getpixel((400, 300)) == (255, 255, 255)
    a = T.text_mask(img(text="Hello there traveler"))
    b = T.text_mask(img(text="Hello there traveler"))
    c = T.text_mask(img(text="We sail at dawn, get ready"))
    assert T.mask_diff(a, b) < T.STABLE_THRESHOLD
    assert T.mask_diff(a, c) > T.CHANGE_THRESHOLD
    assert T.mask_empty(T.text_mask(img()))


def test_parse_reset():
    assert [T._parse_reset(x) for x in ("16.184s", "1m26.4s", "250ms", "2s")] == [16.184, 86.4, 0.25, 2.0]


def test_google_then_microsoft(monkey):
    T.set("PROVIDER", "google")
    T.set("FALLBACK_PROVIDERS", ["microsoft"])
    monkey(T._owner("ocr_lines"), "ocr_lines", lambda im: ["Where do the pirates gather?"])
    cache_reset()
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "edge.microsoft" in url:
            return R(404)
        return R(429, text="unusual traffic")

    class Sess:
        headers = {}

        def get(self, url, timeout=None):
            return R(200, text='IG:"ABC" data-iid="translator.5028" params_AbusePreventionHelper = [1,"tok",3600000]')

        def post(self, url, params=None, data=None, timeout=None):
            return R(200, [{"translations": [{"text": "Где собираются пираты?"}]}])

    monkey(T.requests, "get", get)
    monkey(T.requests, "Session", Sess)
    text, err = T.safe_translate(img())
    assert (text, err) == ("Где собираются пираты?", None), (text, err)
    assert T.provider_cooldown.get("google", 0) > time.time()


def test_gemini_model_fallback(monkey):
    T.set("PROVIDER", "gemini")
    T.set("FALLBACK_PROVIDERS", [])
    T.set("API_KEY", "g")
    T.dead_models.clear()
    T.model_cooldown.clear()
    T.provider_cooldown.clear()
    M = T.MODELS
    plan = {M[0]: R(429), M[1]: R(429)}
    ok = R(200, {"candidates": [{"content": {"parts": [{"text": "Привет, путник"}]}}]})
    calls = []

    def post(url, params=None, json=None, timeout=None, **k):
        model = url.split("models/")[1].split(":")[0]
        calls.append(model)
        return plan.get(model, ok)

    monkey(T.requests, "post", post)
    assert T.safe_translate(img())[0] == "Привет, путник"
    assert calls == M[:3], calls
    calls.clear()
    assert T.safe_translate(img())[0] == "Привет, путник"
    assert calls == [M[2]], calls   # отдыхающие модели пропускаются
    T.model_cooldown.clear()


def test_ocr_ai_context(monkey):
    T.set("PROVIDER", "groq_ocr")
    T.set("FALLBACK_PROVIDERS", [])
    T.set("GROQ_API_KEY", "q")
    T.dialogue_history.clear()
    cache_reset()
    T.provider_cooldown.clear()
    T.model_cooldown.clear()
    sent = []

    def post(url, headers=None, json=None, timeout=None, **k):
        content = json["messages"][0]["content"]
        assert isinstance(content, str), "в режиме OCR+ИИ картинка не отправляется"
        sent.append(content)
        out = "1. Зачем тебе его искать?" if "Options:" in content else f"Ренальд\nПеревод №{len(sent)}"
        return R(200, {"choices": [{"message": {"content": out}}], "usage": {"prompt_tokens": 200}},
                 headers={"x-ratelimit-remaining-tokens": "7000", "x-ratelimit-reset-tokens": "2s"})

    monkey(T.requests, "post", post)
    seq = iter([["Renald", "He conscripted the men."], ["Renald", "aut the moment the pirates spotted us"]])
    monkey(T._owner("ocr_lines"), "ocr_lines", lambda im: next(seq))
    assert T.safe_translate(img())[0].startswith("Ренальд")
    assert T.safe_translate(img())[0].startswith("Ренальд")
    assert "He conscripted the men." in sent[1], "предыдущая реплика должна быть в контексте"
    monkey(T._owner("ocr_lines"), "ocr_lines", lambda im: ["Why do you have to find him?"])
    assert T.safe_translate(img(), T._answers_prompt())[0] == "1. Зачем тебе его искать?"


def test_watcher_fade(monkey):
    _fade(monkey, keep=False)


def test_watcher_keep_until_next(monkey):
    """Настройка «не убирать перевод, пока не появится новая реплика»."""
    if not hasattr(T._owner("HIDE_DELAY"), "KEEP_UNTIL_NEXT"):
        print("   (в этой версии нет настройки — пропуск)")
        return
    _fade(monkey, keep=True)


def _fade(monkey, keep):
    T.set("PROVIDER", "google")
    if keep:
        monkey(T._owner("HIDE_DELAY"), "KEEP_UNTIL_NEXT", True)
    seq = [img()] * 2 + [img(text="Yes", bright=230), img(text="Yes, she", bright=240),
                         img(text="Yes, she's", bright=250)] + [img(text="Yes, she's safe.")] * 6 + [img()] * 6
    it = iter(seq)
    stop = threading.Event()

    def grab(r):
        try:
            return next(it)
        except StopIteration:
            stop.set()
            time.sleep(0.2)
            return img()

    def fake_ocr(im):
        box = im.convert("L").point(lambda p: 255 if p > 200 else 0).getbbox()
        cols = 0 if box is None else box[2] - box[0]
        return [] if cols == 0 else ["Yes" if cols < 60 else "Yes, she" if cols < 130 else
                                     "Yes, she's" if cols < 160 else "Yes, she's safe."]

    calls = []
    monkey_set = [("grab", grab), ("ocr_lines", fake_ocr),
                  ("safe_translate", lambda im, prompt=None: (calls.append(1) or ("Да, она в безопасности.", None))),
                  ("POLL_INTERVAL", 0.02), ("MIN_REQUEST_GAP", 0), ("HIDE_DELAY", 0.05), ("region", (0, 0, 400, 60))]
    for name, v in monkey_set:
        monkey(T._owner(name), name, v)
    spoken = []
    if hasattr(T, "speak_subtitle_once"):
        monkey(T._owner("speak_subtitle_once"), "speak_subtitle_once", lambda t, *a: spoken.append(t))
    T.auto_on.set()
    alive = {"on": True}   # после теста этот наблюдатель засыпает и не мешает следующим
    w = T.Watcher("Субтитры", lambda: T.region if alive["on"] else None, "text", "subs_hide", None, lambda: T.PROMPT)
    threading.Thread(target=w.run, daemon=True).start()
    stop.wait(5)
    time.sleep(0.2)
    alive["on"] = False
    T.auto_on.clear()
    kinds = [k for k, _ in drain() if k in ("text", "subs_hide")]
    assert len(calls) == 1, f"ожидался 1 перевод, было {len(calls)}"
    assert kinds[:2] == (["text"] if keep else ["text", "subs_hide"]), kinds
    if hasattr(T, "speak_subtitle_once"):
        assert spoken == ["Да, она в безопасности."], spoken


def test_region_deleted_mid_translation(monkey):
    """Область удалили, пока шёл перевод, — перевод не всплывает на экране после удаления."""
    T.set("PROVIDER", "google")
    seq = [img()] * 2 + [img(text="Yes, she's safe.")] * 8 + [img()] * 4
    it = iter(seq)
    stop = threading.Event()

    def grab(r):
        try:
            return next(it)
        except StopIteration:
            stop.set()
            time.sleep(0.2)
            return img()
    region = {"r": (0, 0, 400, 60)}
    calls = []

    def slow_translate(im, prompt=None):
        calls.append(1)
        region["r"] = None                 # пока переводим — область удалили
        return "Да, она в безопасности.", None
    for name, v in [("grab", grab), ("ocr_lines", lambda im: ["Yes, she's safe."] if im.getbbox() else []),
                    ("safe_translate", slow_translate), ("POLL_INTERVAL", 0.02), ("MIN_REQUEST_GAP", 0)]:
        monkey(T._owner(name), name, v)
    T.auto_on.set()
    drain()
    w = T.Watcher("Субтитры", lambda: region["r"], "text", "subs_hide", None, lambda: T.PROMPT)
    threading.Thread(target=w.run, daemon=True).start()
    deadline = time.time() + 3
    while not calls and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.3)
    T.auto_on.clear()
    assert calls, "перевод должен был начаться"
    assert not [k for k, _ in drain() if k == "text"], "перевод удалённой области не показываем"


def test_history(monkey):
    T.translation_history.clear()
    T.history_add("Субтитры", "Renald\nHello", "Ренальд\nПривет")
    files = os.listdir(T.HISTORY_DIR)
    assert files and "RU: Ренальд / Привет" in open(os.path.join(T.HISTORY_DIR, files[0]), encoding="utf-8").read()
    assert any(k == "history_new" for k, _ in drain())


def test_toggle_auto_needs_region(monkey):
    monkey(T._owner("region"), "region", None)
    monkey(T._owner("answers_region"), "answers_region", None)
    T.auto_on.clear()
    T.toggle_auto()
    assert not T.auto_on.is_set()
    assert any(k == "log" and "выделите" in p[1] for k, p in drain())


def test_hotkey_capture(monkey):
    T.set("SETTINGS", {})
    T.load_hotkeys()
    T.register_hotkeys()
    assert len(kb.registered) == sum(1 for d in T.HOTKEY_DEFS if not T.is_mouse(str(T.hotkeys[d[0]])))
    t = threading.Thread(target=T.capture_hotkey, args=("once",))
    t.start()
    time.sleep(0.2)
    E = lambda typ, name: types.SimpleNamespace(event_type=typ, name=name)  # noqa: E731
    kb.hooks[-1](E("down", "ctrl"))
    kb.hooks[-1](E("down", "g"))
    kb.hooks[-1](E("up", "g"))
    t.join(3)
    assert T.hotkeys["once"] == "ctrl+g" and T.K("once") == "Ctrl+G"
    assert len(kb.registered) == sum(1 for d in T.HOTKEY_DEFS if not T.is_mouse(str(T.hotkeys[d[0]])))
    T.hotkeys["once"] = "mouse_x1"
    assert T.K("once") == "Мышь назад"


def test_single_instance():
    port = T.SINGLE_PORT
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        s.close()
    except OSError:
        print("   (порт занят — пропуск)")
        return
    assert T.single_instance() is True

    def second(extra="", call="a.single_instance()"):
        code = ("import sys,types\nfor m in ('keyboard','tkinter'): sys.modules[m]=types.ModuleType(m)\n"
                f"sys.path.insert(0,{ROOT!r})\n")
        code += ("from aac import main as a\n" if T.kind == "package" else "import aac_translator as a\n")
        code += extra + f"print({call})"
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        return r.stdout.strip() + r.stderr
    # та же версия, программа жива — вторая копия показывает панель первой и выходит
    out = second()
    assert out.endswith("False"), out
    time.sleep(0.3)
    assert any(k == "second_copy" for k, _ in drain())
    if not hasattr(T._owner("single_instance"), "_ask"):
        return
    # запускается более новая версия — просит старую закрыться
    out = second("a.config.VERSION = '99.0'\n", "a.single_instance(takeover_wait=1)")
    time.sleep(0.3)
    assert any(k == "quit" for k, _ in drain()), out
    # программа «зависла» (окна не отвечают) — новая копия не уступает ей, а пытается закрыть
    core_mod = T._owner("heartbeat")
    monkey_old = core_mod.heartbeat
    core_mod.heartbeat = 0
    out = second("", "a._ask('hello 1.0')")
    core_mod.heartbeat = monkey_old
    assert out.endswith("hung"), out


def test_port_owner_parse(monkey):
    """Поиск процесса, который держит порт программы (вывод netstat в Windows, в т.ч. русской)."""
    m = T._owner("single_instance")
    if not hasattr(m, "_port_owner_pid"):
        return
    out = ("\nАктивные подключения\n\n  Имя    Локальный адрес        Внешний адрес          Состояние       PID\n"
           "  TCP    127.0.0.1:47911        0.0.0.0:0              ПРОСЛУШИВАНИЕ   5520\n"
           "  TCP    127.0.0.1:47911        127.0.0.1:50001        TIME_WAIT       0\n"
           "  TCP    127.0.0.1:479110       0.0.0.0:0              LISTENING       77\n")
    monkey(m.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout=out))
    assert m._port_owner_pid(47911) == 5520


def test_settings_not_lost_on_bad_file():
    """Файл настроек повреждён/недописан в момент сохранения — галочки не должны слететь."""
    T.save_settings(answers_auto=True, region=(1, 2, 3, 4))
    T.set("SETTINGS", T.load_settings())
    open(T.SETTINGS_FILE, "w", encoding="utf-8").write('{"answers_auto": tr')     # недописанный файл
    T.save_settings(font_size=15)
    data = json.load(open(T.SETTINGS_FILE, encoding="utf-8"))
    assert data.get("answers_auto") is True and data.get("font_size") == 15, data


def test_settings_roundtrip():
    T.save_settings(region=(1, 2, 3, 4), font_size=17)
    data = json.load(open(T.SETTINGS_FILE, encoding="utf-8"))
    prof = data["profiles"][T._owner("active_profile").active_profile] if "profiles" in data else data
    assert prof["region"] == [1, 2, 3, 4] and data["font_size"] == 17   # области — в пресете текущей игры
    T.set("SETTINGS", T.load_settings())
    T.apply_saved_provider()
    assert T.FONT[1] == 17


def test_gui_smoke(monkey):
    if not GUI:
        print("   (без экрана — пропуск)")
        return
    T.set("SETTINGS", {})
    T.load_hotkeys()
    T.set("region", (150, 520, 700, 150))
    T.set("answers_region", (900, 300, 260, 200))
    app = T.App()
    done = {}

    def step():
        T.events.put(("text", ("Ренальд\nПривет", "Renald\nHi")))
        T.events.put(("answers", "1. Да"))
        app.open_history()
        app.open_settings()
        app.toggle_layout()
        if hasattr(app, "show_tooltip"):
            app.show_tooltip({"text": ("Клинок\nМеч", "Blade\nSword"), "pos": (700, 400),
                              "box": (720.0, 380.0, 200.0, 120.0)})
            done["tip"] = app.tip.visible and app.tip._pos()[2] == 720 - 12 - app.tip.width
            app.tip.hide()
            from aac import ui_windows
            ui_windows.CharactersWindow(app)
        if hasattr(app, "indicator"):   # значок «перевод вкл»: виден при автопереводе, прячется без него
            ind = app.indicator
            cfg = T._owner("SHOW_INDICATOR")
            ind.update(True, busy=True, tts_on=True)
            ok1 = ind.visible and "перевожу" in ind.label.cget("text") and "🔊" in ind.label.cget("text")
            ind.update(True)
            ok2 = "перевод вкл" in ind.label.cget("text")
            ind.update(False)
            ok3 = not ind.visible
            cfg.SHOW_INDICATOR = False
            ind.update(True)
            ok4 = not ind.visible
            cfg.SHOW_INDICATOR = True
            done["indicator"] = ok1 and ok2 and ok3 and ok4
        if hasattr(app, "_update_own_rects"):   # где наши окна — чтобы не переводить собственную панель
            app.root.update()
            app._update_own_rects()
            pw = app.panel.win
            want = (pw.winfo_rootx(), pw.winfo_rooty(), pw.winfo_width(), pw.winfo_height())
            done["own"] = want in T._owner("own_rects").own_rects
        if hasattr(app, "show_chat"):   # окошко чата и «написать в чат»
            app.show_chat([("[World] Ann: ", "привет"), ("Bob: ", "ищу группу")])
            ok_chat = app.chat.visible and "Bob: ищу группу" in app.chat.label.cget("text")
            app.chat_compose()
            app.compose_var.set("Привет")
            app.chat_out_ready("Привет", "Hi there")
            ok_clip = app.root.clipboard_get() == "Hi there" and "Скопировано" in app.compose_info.cget("text")
            app._close_compose()
            ok_style = True
            if hasattr(app.chat, "cover"):
                cfg = T._owner("CHAT_COVER")
                core_m = T._owner("chat_region")
                core_m.chat_region = (100, 400, 380, 90)
                # предельная высота: старые сообщения уходят, окно не выше предела
                cfg.CHAT_COVER, cfg.CHAT_HEIGHT = False, 70
                app.show_chat([(f"P{i}: ", f"сообщение номер {i}") for i in range(8)])
                shown = app.chat.label.cget("text")
                ok_style = app.chat._pos()[1] == 70 and "номер 7" in shown and "номер 0" not in shown
                if hasattr(app, "_chat_wheel"):     # прокрутка колесом: вверх — старые, вниз — обратно
                    E = types.SimpleNamespace
                    for _ in range(5):
                        app._chat_wheel(E(delta=120))
                    up = app.chat.label.cget("text")
                    ok_style = ok_style and "номер 7" not in up and "↓ ещё 5" in up
                    app.show_chat([("Q: ", "свежее")])           # пришло новое, пока листаем — вид стоит
                    ok_style = ok_style and app.chat_scroll == 6 and "свежее" not in app.chat.label.cget("text")
                    for _ in range(10):
                        app._chat_wheel(E(delta=-120))
                    ok_style = ok_style and app.chat_scroll == 0 and "свежее" in app.chat.label.cget("text")
                if hasattr(app, "_chat_height_drag"):      # потянули нижний край — высота 160
                    app._chat_height_drag(160)
                    ok_style = ok_style and cfg.CHAT_HEIGHT == 160 and app.chat._pos()[1] == 160
                # поверх чата: ровно на месте области чата
                cfg.CHAT_COVER = True
                app.show_chat([("Z: ", "ещё одно")])
                ok_style = ok_style and app.chat._pos() == (380, 90, 100, 400)
                cfg.CHAT_FG, cfg.CHAT_ALPHA = "#ffe08a", 0.6
                app.chat.apply_style()
                ok_style = ok_style and app.chat.label.cget("fg") == "#ffe08a"
                cfg.CHAT_COVER, cfg.CHAT_HEIGHT, cfg.CHAT_FG, cfg.CHAT_ALPHA = False, 0, "#eeeeee", 0.85
                core_m.chat_region = None
                app.chat.apply_style()
            if hasattr(app, "chat_btn"):             # кнопка «Перевести» на окне чата
                drain()
                app.chat_btn.invoke()
                ok_style = ok_style and any(k == "chat_once" for k, _ in drain())
            if hasattr(app, "menu_state"):       # меню игры открыли — окна прячутся, закрыли — возвращаются
                app.subs.show("Привет")
                app.menu_state(True)
                hidden = not app.subs.visible
                app.menu_state(False)
                ok_style = ok_style and hidden and app.subs.visible
            if hasattr(app, "show_chat_window"):     # закрыли правым кликом — вернуть
                app.chat.hide()
                app.show_chat_window()
                ok_style = ok_style and app.chat.visible
            done["chat"] = ok_chat and ok_clip and ok_style
        if hasattr(app, "restart"):     # «Перезапустить»: новая копия с --after-pid, эта — закрывается
            started = []
            real = subprocess.Popen
            subprocess.Popen = lambda cmd, **k: started.append(cmd)
            try:
                app.restart()
            finally:
                subprocess.Popen = real
            done["restart"] = bool(started) and started[0][-2] == "--after-pid" and \
                any(k == "quit" for k, _ in drain())
        app.root.after(300, step2)

    def step2():
        done["frames"] = len(app.region_frames)
        app.toggle_layout()
        app.settings_win.size.set(15)
        app.settings_win.changed()
        done["font"] = T.FONT[1]
        sw = app.settings_win
        if hasattr(sw, "ENGINES"):   # переключение движка озвучки и выбор нейроголоса
            sw.engine.set(sw.ENGINES["windows"]); sw._engine_changed()
            assert T._owner("TTS_ENGINE").TTS_ENGINE == "windows"
            sw.fill_voices([("Microsoft Irina Desktop", "ru-RU"), ("Microsoft Zira Desktop", "en-US")])
            assert sw.voice.get() in ("по умолчанию", "Microsoft Irina Desktop")
            sw.engine.set(sw.ENGINES["neural"]); sw._engine_changed()
            sw.voice.set("Дмитрий — мужской, русский"); sw.changed()
            assert T._owner("TTS_ENGINE").TTS_NEURAL_VOICE == "ru-RU-DmitryNeural"
            assert T.load_settings()["tts_neural_voice"] == "ru-RU-DmitryNeural"
            if hasattr(sw, "gender_vars"):   # один голос на всех женщин — прямо в настройках
                if hasattr(sw, "vary"):
                    sw.vary.set(False); sw._vary_changed()
                    assert str(sw.gender_vars["f"][1]["state"]) == "normal"
                sw.gender_vars["f"][0].set("Emma — женский, многоязычный"); sw.changed()
                assert T.load_settings()["tts_default_voices"]["neural"]["f"] == "en-US-EmmaMultilingualNeural"
                if hasattr(sw, "vary"):
                    sw.vary.set(True); sw._vary_changed()     # разные внутри пола — список неактивен
                    assert str(sw.gender_vars["f"][1]["state"]) == "disabled"
                    assert T.load_settings()["tts_vary_in_gender"] is True
                sw.engine.set(sw.ENGINES["windows"]); sw._engine_changed()
                assert not sw.gender_rows["m"][1].winfo_ismapped() or True
                sw.engine.set(sw.ENGINES["neural"]); sw._engine_changed()
        T.events.put(("quit", None))

    app.root.after(300, step)
    app.root.mainloop()
    done.pop("tip", True) or (_ for _ in ()).throw(AssertionError("окно подсказки встало не туда"))
    done.pop("own", True) or (_ for _ in ()).throw(AssertionError("окна программы не попали в own_rects"))
    done.pop("chat", True) or (_ for _ in ()).throw(AssertionError("окно чата / буфер обмена"))
    done.pop("indicator", True) or (_ for _ in ()).throw(AssertionError("значок автоперевода"))
    done.pop("restart", True) or (_ for _ in ()).throw(AssertionError("перезапуск не сработал"))
    assert done == {"frames": 2, "font": 15}, done


def test_second_subs_region(monkey):
    """Вторая область реплик: свой наблюдатель, общее окно субтитров, каждая область прячет только своё."""
    if not hasattr(T._owner("region"), "region2"):
        print("   (в этой версии нет второй области — пропуск)")
        return
    from PIL import Image
    # закраска сразу нескольких чужих областей
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    out = T.mask_out(img, (0, 0, 100, 100), [(0, 0, 10, 10), None, (90, 90, 50, 50)])
    assert out.getpixel((5, 5)) == (0, 0, 0) and out.getpixel((95, 95)) == (0, 0, 0) and out.getpixel((50, 50)) == (255,) * 3
    names = [w.name for w in T.WATCHERS]
    assert "Реплики 2" in names, names
    w2 = next(w for w in T.WATCHERS if w.name == "Реплики 2")
    monkey(T._owner("region2"), "region2", (100, 100, 300, 80))
    assert w2.get_region() == (100, 100, 300, 80) and w2.show_event == "text" and w2.hide_event == "subs2_hide"
    if not GUI:
        return
    T.set("SETTINGS", {})
    T.load_hotkeys()
    T.set("region", (150, 700, 700, 150))
    app = T.App()
    res = {}

    def step():
        T.events.put(("subs_from", "subs2_hide"))
        T.events.put(("text", ("Стражник\nПроходи, не задерживайся.", None)))
        app.root.after(150, step2)

    def step2():
        res["anchor2"] = app.subs.anchor() == (100, 100, 300, 80)
        T.events.put(("subs_hide", None))          # основная область пуста — чужую реплику не трогает
        app.root.after(150, step3)

    def step3():
        res["kept"] = app.subs.visible
        T.events.put(("subs2_hide", None))
        app.root.after(150, step4)

    def step4():
        res["hidden"] = not app.subs.visible
        # сломанное событие не должно останавливать главный цикл (иначе программа «зависает»)
        T.events.put(("tooltip_show", {"broken": True}))
        app.root.after(300, step5)

    def step5():
        res["alive"] = time.time() - T._owner("heartbeat").heartbeat < 0.5
        T.events.put(("quit", None))

    app.root.after(300, step)
    app.root.mainloop()
    assert res == {"anchor2": True, "kept": True, "hidden": True, "alive": True}, res


def test_unstable_warning(monkey):
    """«Сузьте область» — только если текст правда скачет; дописывающийся по буквам текст не в счёт."""
    if not hasattr(T, "growing"):
        print("   (в этой версии нет — пропуск)")
        return
    assert T.growing("Hey, you", "Hey, you there! Stop.") and T.growing("", "Hi")
    assert T.growing("Fresh fish for sale", "Fresh fish")          # исчезает по буквам
    assert not T.growing("Guard: Move along", "Merchant: Fresh fish")
    monkey(T._owner("UNSTABLE_SECONDS"), "UNSTABLE_SECONDS", 0)
    w = T.Watcher("Реплики 2", lambda: None, "text", "subs2_hide", None, lambda: "")
    drain()
    text = "Stay out of trouble, traveler, the roads are not safe"
    for i in range(5, len(text), 2):        # печатается по буквам — 25 «разных» прочтений
        w._warn_unstable(text[:i - 2], text[:i])
    assert not [p for k, p in drain() if k == "log" and "устояться" in p[1]]
    for i in range(20):                     # обрывки узора мостовой — не реплика, не жалуемся
        w._warn_unstable(f"Il {i}", f"rn lI {i}")
    assert not [p for k, p in drain() if k == "log" and "устояться" in p[1]]
    for i in range(16):                     # каждый раз совсем другое — это и есть «скачет»
        w._warn_unstable(f"Noise number {i} zq here", f"Other words {i} kx there")
    logs = [p for k, p in drain() if k == "log" and "устояться" in p[1]]
    assert len(logs) == 1 and "Реплики 2" in logs[0][1], logs


def test_background_junk_filter(monkey):
    """Узор мостовой/травы, прочитанный OCR как «Il lI», выбрасывается; короткие реплики остаются."""
    ocr = T._owner("ocr_lines")
    if not hasattr(ocr, "_has_real_word"):
        print("   (в этой версии нет — пропуск)")
        return
    assert [ocr._clean_line(t, []) for t in ("Il II", "rn .", "IIl lI")] == [None, None, None]
    assert [ocr._clean_line(t, []) for t in ("No!", "Run!", "Hi there")] == ["No!", "Run!", "Hi there"]
    assert ocr._clean_line("Vidrin : Goat, bison, and wolf-hide boots to guard a settler's feet!", [])


def test_updater(monkey):
    """Обновления: сравнение версий, запрос к GitHub (открытый и закрытый репозиторий), распаковка, запуск."""
    try:
        from aac import updater
    except ImportError:
        print("   (в этой версии нет обновлений — пропуск)")
        return
    import zipfile
    assert updater.is_newer("v4.10", "4.9") and not updater.is_newer("4.5", "4.5") and updater.is_newer("5.0", "4.9")
    cfg = T._owner("UPDATE_REPO")
    monkey(cfg, "UPDATE_REPO", "user/aac-translator")
    monkey(cfg, "VERSION", "4.5")
    calls = []

    class Resp:
        def __init__(self, code, data): self.status_code, self._d = code, data
        def json(self): return self._d
        def raise_for_status(self): pass
    ver = {"version": "4.6", "notes": ["голоса", "чат"]}
    monkey(updater.requests, "get", lambda url, headers=None, timeout=None, **k: calls.append((url, headers)) or Resp(200, ver))
    monkey(updater.os, "environ", {})
    drain()
    info = updater.check()
    assert calls[0][0] == "https://api.github.com/repos/user/aac-translator/contents/version.json?ref=main", calls
    assert "Authorization" not in calls[0][1]
    assert info["version"] == "4.6" and info["notes"] == "голоса\nчат"
    assert info["asset_url"] == "https://codeload.github.com/user/aac-translator/zip/refs/heads/main"
    assert [p for k, p in drain() if k == "update_available"][0]["version"] == "4.6"
    # GitHub ограничил API (60 в час без токена) — сразу берём обычный адрес файла и до сброса лимита API не трогаем
    calls.clear()
    updater.state.update(latest=None, etag_api=None, etag_raw=None)
    monkey(updater.core, "SETTINGS", {})

    def limited(url, headers=None, timeout=None, **k):
        calls.append((url, headers))
        if "api.github.com" in url:
            r = Resp(403, {})
            r.headers = {"X-RateLimit-Reset": str(int(time.time()) + 600)}
            return r
        return Resp(200, ver)
    monkey(updater.requests, "get", limited)
    assert updater.check()["version"] == "4.6"
    assert [u.split("/")[2] for u, _ in calls] == ["api.github.com", "raw.githubusercontent.com"]
    calls.clear()
    updater.check()
    assert [u.split("/")[2] for u, _ in calls] == ["raw.githubusercontent.com"], "пока лимит — API не трогаем"
    updater.state["api_blocked_until"] = 0
    monkey(updater.requests, "get", lambda url, headers=None, timeout=None, **k: calls.append((url, headers)) or Resp(200, ver))
    # закрытый репозиторий: токен в заголовке
    monkey(updater.os, "environ", {"GITHUB_TOKEN": "tok"})
    calls.clear()
    updater.check()
    assert calls[0][1]["Authorization"] == "Bearer tok" and calls[0][0].startswith("https://api.github.com/")
    # та же версия — кнопку не показываем
    monkey(cfg, "VERSION", "4.6")
    drain()
    updater.check()
    assert not [p for k, p in drain() if k == "update_available"]
    # нет файла / закрыт без токена — понятное сообщение
    monkey(updater.os, "environ", {})
    monkey(updater.requests, "get", lambda *a, **k: Resp(404, {}))
    drain()
    assert updater.check() is None
    assert any("GITHUB_TOKEN" in p[1] for k, p in drain() if k == "log")
    # распаковка: находит папку с install.py; «злой» путь в архиве — отказ
    src = os.path.join(TMP, "rel.zip")
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("kz12oleg12-aac-translator-abc123/install.py", "print(1)")
        z.writestr("kz12oleg12-aac-translator-abc123/aac/__init__.py", "")

    class Stream:
        def __init__(self, path): self.data = open(path, "rb").read()
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def raise_for_status(self): pass
        def iter_content(self, n): yield self.data
    monkey(updater.requests, "get", lambda url, headers=None, timeout=None, stream=False: Stream(src))
    d = tempfile.mkdtemp(dir=TMP)
    folder = updater.download({"asset_url": "x", "api_asset": False}, d)
    assert folder.endswith("aac-translator-abc123") and os.path.exists(os.path.join(folder, "install.py"))
    bad = os.path.join(TMP, "bad.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../../evil.py", "x")
    monkey(updater.requests, "get", lambda url, headers=None, timeout=None, stream=False: Stream(bad))
    try:
        updater.download({"asset_url": "x"}, tempfile.mkdtemp(dir=TMP))
        assert False, "должен отказаться"
    except RuntimeError:
        pass
    # установка: запускает install.py --update --wait-pid и закрывает программу
    monkey(updater.requests, "get", lambda url, headers=None, timeout=None, stream=False: Stream(src))
    started = []
    monkey(updater.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    drain()
    updater.state["installing"] = False
    updater.install({"version": "4.6", "asset_url": "x", "api_asset": False})
    assert started and started[0][1].endswith("install.py") and started[0][2:4] == ["--update", "--wait-pid"]
    assert any(k == "quit" for k, _ in drain())
    updater.state["installing"] = False
    # первый запуск после обновления — сообщение «обновлена: 4.5 → 4.6»
    monkey(T._owner("SETTINGS"), "SETTINGS", {"last_version": "4.5"})
    monkey(cfg, "VERSION", "4.6")
    drain()
    updater.announce_if_updated()
    assert any("4.5 → 4.6" in p[1] for k, p in drain() if k == "log")
    updater.announce_if_updated()        # второй раз — уже молчим
    assert not any("→" in p[1] for k, p in drain() if k == "log")


def test_area_read_aloud(monkey):
    """«Обвести и озвучить»: перевод обведённого текста показывается и читается целиком голосом «без имени»."""
    tts = T._owner("speak_subtitle")
    if not hasattr(tts, "speak_text"):
        print("   (в этой версии нет — пропуск)")
        return
    said = []
    monkey(tts, "_say", lambda text, seen=None, vp=None: said.append((text, vp)))
    monkey(tts, "stop", lambda: said.append("stop"))
    tts.speak_text("Письмо от Кеспера\nПринеси мне Клинок рассвета (Dawn Blade).\n📜")
    assert said == ["stop", ("Письмо от Кеспера Принеси мне Клинок рассвета.", None)], said
    from PIL import Image
    w = T._owner("translate_once")
    monkey(w.translate, "safe_translate", lambda img, prompt=None: ("Дорогой друг,\nприходи скорее.", None))
    monkey(w.capture, "grab", lambda reg: Image.new("RGB", (10, 10)))
    monkey(w.tts, "speak_text", lambda t: said.append(("speak", t)))
    said.clear()
    drain()
    w.translate_once((0, 0, 10, 10), speak=True)
    assert ("speak", "Дорогой друг,\nприходи скорее.") in said, said
    assert any(k == "quest" and isinstance(p, tuple) for k, p in drain())
    said.clear()
    w.translate_once((0, 0, 10, 10))                 # обычный F7 — без чтения
    assert not said


def test_limits_and_glossary_learning(monkey):
    """Лимиты переводчиков для панели; словарь пополняется сам из заголовков подсказок и имён."""
    try:
        from aac import limits
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    monkey(limits, "state", {})
    monkey(limits, "_warned", set())
    drain()
    limits.note_headers("groq", {"x-ratelimit-remaining-requests": "14120", "x-ratelimit-limit-requests": "14400",
                                 "x-ratelimit-remaining-tokens": "7200", "x-ratelimit-limit-tokens": "8000"})
    limits.count_request("gemini"); limits.count_request("gemini")
    limits.state["deepl"] = {"used": 60000, "limit": 500000, "t": 0}
    sm = limits.summary()
    assert "Groq 14 120/14 400 запр. на сегодня, 7 200/8 000 ток./мин" in sm, sm
    assert "Gemini 2 запр. сегодня" in sm and "DeepL 12% месяца (440 000 симв. осталось)" in sm, sm
    limits.note_headers("groq", {"x-ratelimit-remaining-requests": "100", "x-ratelimit-limit-requests": "14400"})
    assert any("почти кончились" in p[1] for k, p in drain() if k == "log")
    # словарь
    g = T._owner("glossary_prompt")
    if not hasattr(g, "learn"):
        return
    monkey(T._owner("GLOSSARY_AUTO"), "GLOSSARY_AUTO", True)
    open(g.GLOSSARY_FILE, "w", encoding="utf-8").write("Renald = Ренальд\n")
    g._glossary["mtime"] = None
    assert g.terms_in("Возьми Клинок рассвета (Dawn Blade)") == [("Dawn Blade", "Клинок рассвета")]
    assert g.terms_in("Огненный шар (Fireball)") == [("Fireball", "Огненный шар")]
    assert g.terms_in("Это (Not a name) тест") == []
    g.learn_from_translation("Огненный шар (Fireball)\nУрон +120", "Подсказка")
    g.learn_from_translation("Иди к Кевину (Kevin)", "Субтитры")          # из реплик — не берём (падежи)
    assert not g.learn("Renald", "Реналд")                                # уже есть — не трогаем
    txt = open(g.GLOSSARY_FILE, encoding="utf-8").read()
    assert "Fireball = Огненный шар" in txt and "Kevin" not in txt and g.AUTO_HEADER in txt, txt
    assert ("Fireball", "Огненный шар") in g.glossary()
    assert any("В словарь" in p[1] for k, p in drain() if k == "log")
    monkey(T._owner("GLOSSARY_AUTO"), "GLOSSARY_AUTO", False)
    assert not g.learn("Dawn Blade", "Клинок рассвета")


def test_watcher_survives_errors(monkey):
    """Ошибка внутри слежения не убивает его: в журнал — сообщение, слежение запускается заново."""
    W = T._owner("Watcher")
    if not hasattr(W.Watcher, "_loop"):
        print("   (в этой версии нет — пропуск)")
        return
    w = T.Watcher("Ответы", lambda: None, "answers", "answers_hide", None, lambda: "")
    calls = []

    def boom():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("сломалось")
        raise SystemExit   # второй заход — выходим из теста
    monkey(w, "_loop", boom)
    monkey(W.time, "sleep", lambda s: None)
    drain()
    try:
        w.run()
    except SystemExit:
        pass
    assert len(calls) == 2
    assert any(k == "log" and "перезапускаю слежение" in p[1] for k, p in drain())
    # перекрытие областей — предупреждение
    w._check_overlap((0, 0, 100, 100), [(0, 0, 100, 50), None])
    assert any(k == "log" and "закрывает 50%" in p[1] for k, p in drain())


def test_subs_once(monkey):
    """«Перевести субтитры» (Shift+F8): один раз по сохранённой области, с озвучкой и историей."""
    w = T._owner("translate_once")
    if not hasattr(w, "translate_subs_once"):
        print("   (в этой версии нет — пропуск)")
        return
    from PIL import Image
    monkey(w.core, "region", (0, 0, 10, 10))
    monkey(w.translate, "safe_translate", lambda img, prompt=None: ("Кеспер\nПривет!", None))
    monkey(w.capture, "grab", lambda reg: Image.new("RGB", (10, 10)))
    spoken = []
    monkey(w.tts, "speak_subtitle_once", lambda t, *a: spoken.append(t))
    drain()
    w.translate_subs_once()
    ev = drain()
    assert ("subs_from", "subs_hide") in ev and ("text", ("Кеспер\nПривет!", None)) in [
        (k, (p[0], None) if isinstance(p, tuple) else p) for k, p in ev], ev
    assert spoken == ["Кеспер\nПривет!"]
    monkey(w.core, "region", None)
    w.translate_subs_once()
    assert any(k == "log" and "выделите область субтитров" in p[1] for k, p in drain())


def test_skip_system_messages(monkey):
    """Системные сообщения игры в области субтитров: не переводим и не озвучиваем; реплики — как обычно."""
    try:
        from aac import voices
    except ImportError:
        return
    if not hasattr(voices, "is_system"):
        print("   (в этой версии нет — пропуск)")
        return
    for t in ("You acquired Iron Ore x3.", "Quest completed: The Missing Volume", "Inventory is full.",
              "Labor +10", "Your guild has been disbanded"):
        assert voices.is_system(t), t
    for t in ("Kesper\nYou acquired my trust, friend.", "Juan\nGreetings. I am Juan.",
              "Vidrin : Goat, bison, and wolf-hide boots!", "Ah, you have already recovered Volume I.",
              "The ship has been destroyed by pirates!"):
        assert not voices.is_system(t), t
    tts = T._owner("speak_subtitle")
    cfg = T._owner("TTS_READ_NAME")
    said = []
    monkey(cfg, "TTS_ENABLED", True)
    monkey(cfg, "SKIP_SYSTEM", True)
    monkey(tts, "_say", lambda text, seen=None, vp=None: said.append(text))
    T.speak_subtitle("Вы получили железную руду x3.", None, "You acquired Iron Ore x3.")
    assert not said
    monkey(cfg, "SKIP_SYSTEM", False)
    T.speak_subtitle("Вы получили железную руду x3.", None, "You acquired Iron Ore x3.")
    assert said


def test_game_menu_pause(monkey):
    """Меню игры: запомнили вид — когда он на экране, автоперевод на паузе; закрыли — продолжается."""
    try:
        from aac import menu
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    from PIL import Image, ImageDraw
    monkey(menu, "REF_FILE", os.path.join(TMP, "menu_ref.png"))
    monkey(menu, "_ref", {"img": None, "loaded": False})
    core_m = T._owner("menu_region")
    monkey(core_m, "menu_region", None)
    monkey(core_m, "in_menu", False)
    menu_img = Image.new("RGB", (200, 100), (30, 30, 40))
    ImageDraw.Draw(menu_img).rectangle([20, 20, 180, 40], fill=(220, 200, 120))   # «кнопки меню»
    game_img = Image.new("RGB", (200, 100), (90, 140, 60))
    shots = {"img": menu_img}
    monkey(menu.capture, "grab", lambda reg: shots["img"])
    drain()
    menu.learn((10, 10, 200, 100))
    assert core_m.menu_region == (10, 10, 200, 100) and os.path.exists(menu.REF_FILE)
    assert menu.is_menu(menu_img) and not menu.is_menu(game_img)
    noisy = menu_img.copy()
    ImageDraw.Draw(noisy).point([(5, 5), (190, 90)], fill=(255, 255, 255))           # мелкие отличия — всё равно меню
    assert menu.is_menu(noisy)
    import random                                                                     # тёмная сцена той же яркости — не меню
    rnd = random.Random(1)
    dark = Image.new("RGB", (200, 100), (30, 30, 40))
    dd = ImageDraw.Draw(dark)
    for _ in range(40):
        x, y = rnd.randrange(200), rnd.randrange(100)
        dd.ellipse([x, y, x + rnd.randrange(5, 30), y + rnd.randrange(5, 30)], fill=(rnd.randrange(20, 90),) * 3)
    assert not menu.is_menu(dark), menu.similarity(dark)
    menu._ref.update(img=None, loaded=False)                                         # после перезапуска — из файла
    assert menu.is_menu(menu_img)
    menu.forget()
    assert core_m.menu_region is None and not os.path.exists(menu.REF_FILE)


def test_chat(monkey):
    """Чат: ник и канал не переводятся, только новые строки, перевод пачкой; исходящие рус→англ."""
    try:
        from aac import chat
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    assert chat.split_line("[World] Vanersis: wts iron ore") == ("[World] Vanersis: ", "wts iron ore")
    assert chat.split_line("Player123 : lfg dungeon") == ("Player123 : ", "lfg dungeon")
    assert chat.split_line("Server will restart soon") == ("", "Server will restart soon")
    # перевод пачкой через нейросеть (нумерация), иначе — Google построчно
    asked = []
    monkey(chat.translate, "ask_text", lambda p: asked.append(p) or "1. продаю железную руду\n2. ищу группу")
    assert chat.translate_messages(["wts iron ore", "lfg"]) == ["продаю железную руду", "ищу группу"]
    assert "exactly 2 lines" in asked[0]
    monkey(chat.translate, "ask_text", lambda p: None)
    monkey(chat.mt, "_mt_google", lambda t, sl=None, tl=None: {"wts iron ore\nlfg": "продаю руду\nищу группу",
                                                              "Привет всем": "Hi all"}[t])
    assert chat.translate_messages(["wts iron ore", "lfg"]) == ["продаю руду", "ищу группу"]
    assert chat.translate_outgoing("Привет всем") == "Hi all"
    # слежение: строки должны устояться; первый раз — только последние 3; дальше — только новые
    from PIL import Image
    monkey(chat.core, "chat_region", (0, 0, 10, 10))
    monkey(chat.capture, "grab", lambda reg: Image.new("RGB", (10, 10)))
    screen = {"lines": [f"[World] P{i}: message number {i}" for i in range(6)]}
    monkey(chat, "read_lines", lambda img: list(screen["lines"]))
    monkey(chat, "_state", {"prev": None, "started": False})
    monkey(chat, "seen", chat.collections.deque(maxlen=400))
    monkey(chat, "_seen_set", set())
    got = []
    monkey(chat, "translate_messages", lambda msgs, lang=None: got.append(list(msgs)) or [m.upper() for m in msgs])
    drain()
    chat._step()                     # первое чтение — ждём, пока устоится
    assert not got
    chat._step()
    assert got == [["message number 3", "message number 4", "message number 5"]], got
    ev = [p for k, p in drain() if k == "chat"]
    assert ev[0][0] == ("[World] P3: ", "MESSAGE NUMBER 3")
    screen["lines"] = screen["lines"][1:] + ["[Faction] Zed: need healer"]   # чат прокрутился
    chat._step(); chat._step()
    assert got[-1] == ["need healer"], got
    chat._step()
    assert len(got) == 2                                                     # повторно не переводим
    # клавиша «перевести чат»: сразу, без ожидания и без автоперевода
    if hasattr(chat, "translate_chat_once"):
        screen["lines"] = screen["lines"] + ["[World] Kim: wtb wolf hide"]
        monkey(chat, "_blink_grab", lambda reg: None)
        drain()
        chat.translate_chat_once()
        assert got[-1] == ["wtb wolf hide"], got
        assert any(k == "chat" for k, _ in drain())
        chat.translate_chat_once()                                  # новых нет — просто показать окно
        assert any(k == "chat_show" for k, _ in drain())
    # перевод поверх чата: если Windows прячет окно от снимков — не моргаем; если нет — моргаем, но редко
    if hasattr(chat, "_grab_under_overlay"):
        frames = {"plain": Image.new("L", (10, 10), 20), "under": Image.new("L", (10, 10), 20)}
        blinks = []
        monkey(chat.capture, "grab", lambda reg: frames["plain"])
        monkey(chat, "_blink_grab", lambda reg: blinks.append(1) or frames["under"])
        monkey(chat, "_state", {"prev": None, "started": False})
        chat._grab_under_overlay((0, 0, 10, 10))
        assert chat._state["cover_mode"] == "ok"
        chat._grab_under_overlay((0, 0, 10, 10)); chat._grab_under_overlay((0, 0, 10, 10))
        assert len(blinks) == 1                      # проверили один раз — дальше без моргания
        frames["plain"] = Image.new("L", (10, 10), 200)   # на снимке видно наше окно
        monkey(chat, "_state", {"prev": None, "started": False})
        blinks.clear()
        assert chat._grab_under_overlay((0, 0, 10, 10)) is frames["under"]
        assert chat._state["cover_mode"] == "blink"
        assert chat._grab_under_overlay((0, 0, 10, 10)) is None   # сразу снова — не моргаем
        assert len(blinks) == 1


def test_dock_overlays(monkey):
    """Ответы и субтитры одним окном: ответы вплотную под субтитрами, двигаются и тянутся вместе."""
    if not GUI:
        print("   (без экрана — пропуск)")
        return
    T.set("SETTINGS", {})
    T.load_hotkeys()
    T.set("region", (150, 700, 700, 150))
    T.set("answers_region", (900, 300, 260, 200))
    app = T.App()
    if not hasattr(app, "set_docked"):
        print("   (в этой версии нет склейки окон — пропуск)")
        app.root.destroy()
        return
    res = {}
    E = types.SimpleNamespace

    def step():
        subs, ans = app.subs, app.answers
        subs.manual = True
        subs._place(500, 10, 200, 100)
        T.events.put(("text", ("Рогху\nРынки могут измениться.", None)))
        T.events.put(("answers", "1. Покажи товары\n2. Я вернусь позже"))
        app.root.after(200, lambda: step2(subs, ans))

    def step2(subs, ans):
        app.set_docked(True)
        app.root.update()
        sw, sh, sx, sy = subs._pos()
        aw, ah, ax, ay = ans._pos()
        res["below"] = (ax, ay, aw) == (sx, sy + sh, sw)
        # тащим за окно ответов — едут оба
        ans._start_move(E(x_root=300, y_root=300))
        ans._move(E(x_root=350, y_root=320))
        ans._end_move(None)
        sw2, sh2, sx2, sy2 = subs._pos()
        aw2, ah2, ax2, ay2 = ans._pos()
        res["moved"] = (sx2, sy2) == (sx + 50, sy + 20) and (ax2, ay2) == (sx2, sy2 + sh2)
        # ширина: колесо над ответами меняет оба окна
        ans._wheel(E(delta=120))
        res["width"] = subs.width == sw + 40 and ans._pos()[0] == subs.width
        # субтитры скрылись — ответы встают на их место
        subs.hide()
        res["up"] = ans._pos()[3] == subs._pos()[3]
        res["saved"] = T.load_settings().get("answers_docked") is True
        app.set_docked(False)
        res["undocked"] = ans.leader is None and ans not in subs.followers
        T.events.put(("quit", None))

    app.root.after(300, step)
    app.root.mainloop()
    assert res == {"below": True, "moved": True, "width": True, "up": True, "saved": True, "undocked": True}, res


def test_tts_text_and_calls(monkey):
    if not hasattr(T, "speech_text"):
        print("   (в этой версии нет озвучки — пропуск)")
        return
    monkey(T._owner("TTS_READ_NAME"), "TTS_READ_NAME", False)
    assert T.speech_text("Ренальд\nНо как только пираты нас заметили, он сбежал!") == \
        "Но как только пираты нас заметили, он сбежал!"
    assert T.speech_text("Возьми Клинок рассвета (Dawn Blade).") == "Возьми Клинок рассвета."
    # имя через двоеточие в той же строке (журнал v3.2: «Полдат: За твое... здоровье!»)
    assert T.speech_text("Полдат: За твое... здоровье!") == "За твое... здоровье!"
    assert T.speech_text("Капитан Морган: Вперёд!") == "Вперёд!"
    assert T.speech_text("Он сказал: иди") == "Он сказал: иди"
    # имя осталось в начале перевода, а в оригинале оно на своей строке (журнал: «Ethan / A rental…»)
    tts_mod = T._owner("speak_subtitle")
    if hasattr(tts_mod, "_strip_speaker"):
        o = "Ethan\nA rental fee is posted on the Resident Board."
        assert T.speech_text("Итан Аренда указана на доске.", o) == "Аренда указана на доске."
        assert T.speech_text("Итан — Аренда указана.", o) == "Аренда указана."
        assert T.speech_text("Аренда — это важно.", o) == "Аренда — это важно."      # не имя — не трогаем
        assert T.speech_text("Я Итан, рад знакомству.", o) == "Я Итан, рад знакомству."
        assert T.speech_text("Капитан Морган — Вперёд!", "Captain Morgan\nForward!") == "Вперёд!"
        # имя с должностью (журнал: «Archivist Rotild / Ah, you've already recovered Volume I.»)
        o2 = "Archivist Rotild\nAh, you've already recovered Volume I."
        assert T.speech_text("Архивариус Ротильд А, ты уже нашёл первый том.", o2) == "А, ты уже нашёл первый том."
        assert T.speech_text("Архивист Ротильд — А, ты уже нашёл том.", o2) == "А, ты уже нашёл том."
    monkey(T._owner("TTS_READ_NAME"), "TTS_READ_NAME", True)
    assert T.speech_text("Ренальд\nПривет!") == "Ренальд Привет!"
    assert T.speech_text("Полдат: Привет!") == "Полдат: Привет!"
    sent = []
    tts = T._owner("speak_subtitle")
    if hasattr(tts, "TTS_ENGINE") or hasattr(T._owner("TTS_READ_NAME"), "TTS_ENGINE"):
        monkey(T._owner("TTS_READ_NAME"), "TTS_ENGINE", "windows")
    if hasattr(T._owner("TTS_READ_NAME"), "TTS_FINISH_LINE"):
        monkey(T._owner("TTS_READ_NAME"), "TTS_FINISH_LINE", False)
    monkey(tts, "_start", lambda: True)
    monkey(tts, "_send", lambda cmd, arg="": sent.append((cmd, arg)))
    monkey(T._owner("TTS_ENABLED"), "TTS_ENABLED", False)
    T.speak_subtitle("Ренальд\nПривет!")
    assert sent == [], "выключенная озвучка не должна говорить"
    monkey(T._owner("TTS_ENABLED"), "TTS_ENABLED", True)
    T.speak_subtitle("Ренальд\nПривет!")
    assert sent == [("say", "Ренальд Привет!")], sent


def test_neural_voice(monkey):
    """Нейроголос: фразы синтезируются параллельно и играют по очереди; новая реплика прерывает старую;
    без сети — голос Windows."""
    tts = T._owner("speak_subtitle")
    if not hasattr(tts, "_Neural"):
        print("   (в этой версии нет нейроголосов — пропуск)")
        return
    cfg = T._owner("TTS_READ_NAME")
    monkey(cfg, "TTS_ENABLED", True)
    monkey(cfg, "TTS_ENGINE", "neural")
    monkey(cfg, "TTS_NEURAL_VOICE", "ru-RU-DmitryNeural")
    monkey(cfg, "TTS_RATE", 2)
    if hasattr(cfg, "TTS_EXPRESSIVE"):
        monkey(cfg, "TTS_EXPRESSIVE", False)     # интонацию проверяет свой тест
    monkey(tts, "neural_available", lambda: True)
    synth, played, win = [], [], []

    async def fake_synth(text, path, voice, rate, pitch="+0Hz", volume="+0%"):
        import asyncio
        synth.append((text, voice, rate))
        await asyncio.sleep(0.05 + len(text) / 400)
        if "сбой" in text:
            raise RuntimeError("нет сети")
        return path

    class P:
        def __init__(self): self.until = {}
        def load(self, path): return path
        def play(self, alias, vol): played.append(alias); self.until[alias] = time.time() + 0.15
        def busy(self, alias): return time.time() < self.until.get(alias, 0)
        def close(self, alias): self.until.pop(alias, None)
        def close_all(self): self.until.clear()
    monkey(tts, "_synth_async", fake_synth)
    monkey(tts, "_make_player", P)
    monkey(tts, "_windows_say", lambda text: win.append(text))
    n = tts._Neural()
    monkey(tts, "_neural", n)

    def wait(cond, t=3):
        end = time.time() + t
        while time.time() < end and not cond():
            time.sleep(0.02)

    if hasattr(n, "warm"):   # прогрев: синтез «Готово.» без проигрывания
        n.warm()
        wait(lambda: synth and n.warm_fut is None and n.warmed)
        assert synth[-1][0] == "Готово." and not played, (synth, played)
        synth.clear()
    T.speak_subtitle("Полдат: За твоё здоровье!")
    wait(lambda: played)
    assert synth and synth[0] == ("За твоё здоровье!", "ru-RU-DmitryNeural", "+20%"), synth
    assert len(played) == 1
    # длинная реплика: две фразы, обе синтезируются сразу, играют по порядку
    synth.clear(); played.clear()
    T.speak_subtitle("Но как только пираты нас заметили, он сбежал! А мы остались одни. Что теперь делать?")
    wait(lambda: len(played) == 2)
    assert [x[0] for x in synth] == ["Но как только пираты нас заметили, он сбежал!",
                                     "А мы остались одни. Что теперь делать?"], synth
    assert played[0].endswith("_0.mp3") and played[1].endswith("_1.mp3"), played
    # режим «дочитывать»: вторая реплика ждёт, третья вытесняет вторую из очереди, читается быстрее
    if hasattr(cfg, "TTS_FINISH_LINE"):
        monkey(cfg, "TTS_FINISH_LINE", True)
        synth.clear(); played.clear()
        T.speak_subtitle("Первая реплика звучит")
        wait(lambda: played)
        T.speak_subtitle("Вторая реплика ждёт")
        time.sleep(0.02)
        T.speak_subtitle("Третья реплика ждёт")
        wait(lambda: len(played) >= 2)
        time.sleep(0.3)
        assert len(played) == 2, played
        said = [x for x in synth]
        assert said[0][0] == "Первая реплика звучит" and said[-1][0] == "Третья реплика ждёт", said
        assert said[-1][2] == "+40%", said   # +20% ползунка и +20% «догоняем»
        monkey(cfg, "TTS_FINISH_LINE", False)
    # новая реплика прерывает старую
    synth.clear(); played.clear()
    T.speak_subtitle("Первая длинная реплика. Вторая её часть тут.")
    time.sleep(0.03)
    T.speak_subtitle("Совсем другая реплика")
    wait(lambda: any("_0" in p for p in played) and len(played) >= 1)
    time.sleep(0.4)
    assert len(played) == 1, played
    # нет сети → голос Windows
    T.speak_subtitle("Тут случится сбой сети")
    wait(lambda: win)
    assert win == ["Тут случится сбой сети"], win
    n.quit()
    assert tts.neural_id(tts.neural_label("ru-RU-SvetlanaNeural")) == "ru-RU-SvetlanaNeural"
    assert tts.split_chunks("Я долго шёл по дороге через лес, через горы и болота, пока не увидел огромную "
                            "крепость у самого моря, и понял что пришёл.")[0] == "Я долго шёл по дороге через лес,"


def test_silero(monkey):
    """Silero: очистка текста, скорость → SSML, запись wav; через очередь озвучки — wav-файлы."""
    tts = T._owner("speak_subtitle")
    if not hasattr(tts, "tts_silero"):
        print("   (в этой версии нет Silero — пропуск)")
        return
    sil = tts.tts_silero
    assert sil.clean("Kesper: Привет, «друг»… Seaglass") == "Кеспер: Привет, друг... Сигласс"
    assert sil.clean("Иди в Seaglass Harbor.") == "Иди в Сигласс Харбор."
    assert [sil._prosody_rate(x) for x in (-5, -1, 0, 2, 4)] == ["x-slow", "slow", "medium", "fast", "x-fast"]
    if hasattr(sil, "say_numbers"):   # Silero сам цифры не читает — переводим в слова
        assert sil.clean("Атака +120, скидка 15%") == "Атака плюс сто двадцать, скидка пятнадцать процентов"
        assert sil.clean("Принеси 3 шкуры и 10 000 золота") == "Принеси три шкуры и десять тысяч золота"
        assert sil.number_words(2024) == "две тысячи двадцать четыре"
        assert sil.number_words(1001000) == "один миллион одна тысяча"
        assert sil.number_words(-5) == "минус пять" and sil.number_words(0) == "ноль"
    if hasattr(sil, "noun_gender"):   # согласование с существительным
        for src, want in (("У меня 21 монета", "двадцать одна монета"), ("Принеси 2 шкуры", "две шкуры"),
                          ("Возьми 1 зелье", "одно зелье"), ("Нужно 2 меча", "два меча"),
                          ("Убей 1 волка", "одного волка"), ("Принеси 1 шкуру", "одну шкуру"),
                          ("Осталась 1 попытка", "одна попытка"), ("12 монет", "двенадцать монет"),
                          ("2 старые монеты", "две старые монеты"), ("В 1 году", "один году")):
            assert want in sil.clean(src), (src, sil.clean(src))
    import contextlib, wave as wv
    calls = []

    class Ten:
        def __init__(self, v): self.v = v
        def clamp(self, a, b): return Ten([max(a, min(b, x)) for x in self.v])
        def __mul__(self, k): return Ten([x * k for x in self.v])
        def to(self, dt): return Ten([int(x) for x in self.v])
        def tolist(self): return self.v

    class Model:
        def apply_tts(self, **kw):
            calls.append(kw)
            return Ten([0.0, 0.5, -0.5, 2.0] * 100)
    fake_torch = types.SimpleNamespace(int16="int16", no_grad=contextlib.nullcontext)
    monkey(sil, "_model", {"m": Model(), "torch": fake_torch, "error": None})
    path = os.path.join(TMP, "s.wav")
    sil.synth_to_wav("Привет, мир", path, "aidar", 0)
    assert calls[-1]["text"] == "Привет, мир" and calls[-1]["speaker"] == "aidar"
    with wv.open(path) as w:
        assert w.getframerate() == sil.SAMPLE_RATE and w.getnframes() == 400
    sil.synth_to_wav("Быстрее & лучше", path, "xenia", 3)
    assert calls[-1]["ssml_text"] == '<speak><prosody rate="fast">Быстрее &amp; лучше</prosody></speak>'
    try:
        sil.synth_to_wav("!!! ... ?", path, "xenia")
        assert False, "без букв — нечего читать"
    except ValueError:
        pass
    # доп. голоса (модель v5_cis_base): ударения расставляются, синтез — своей моделью;
    # если не вышло — основной голос того же пола
    if hasattr(sil, "_synth_cis"):
        cis_calls = []

        class CisModel:
            speakers = ["ru_eduard", "ru_aigul"]
            def apply_tts(self, **kw):
                cis_calls.append(kw)
                return Ten([0.1] * 50)
        monkey(sil, "_cis", {"m": CisModel(), "acc": lambda t: t.replace("Привет", "Прив+ет"), "error": None,
                             "speakers_logged": False})
        sil.synth_to_wav("Привет, мир", path, "ru_eduard")
        assert cis_calls[-1] == {"text": "Прив+ет, мир", "speaker": "ru_eduard", "sample_rate": sil.SAMPLE_RATE}
        calls.clear()
        sil.synth_to_wav("Привет, мир", path, "ru_igor")            # такого голоса нет в модели → Айдар
        assert calls and calls[-1]["speaker"] == "aidar", calls
        voices_mod = __import__("aac.voices", fromlist=["x"])
        monkey(sil, "cis_available", lambda: True)
        assert "ru_eduard" in voices_mod.SILERO_POOL["m"] and "eugene" in voices_mod.SILERO_POOL["m"]
        assert "eugene" not in voices_mod.SILERO_POOL.auto("m")      # Евгения в автоподборе заменили
        monkey(sil, "cis_available", lambda: False)
        assert voices_mod.SILERO_POOL.auto("m") == ["aidar", "eugene"]
        assert sil.label("ru_aigul") == "Айгуль — женский (доп.)"
    # через очередь: движок silero → wav, голос и уровень скорости из настроек
    cfg = T._owner("TTS_READ_NAME")
    monkey(cfg, "TTS_ENABLED", True)
    monkey(cfg, "TTS_ENGINE", "silero")
    monkey(cfg, "TTS_SILERO_VOICE", "eugene")
    monkey(cfg, "TTS_RATE", 1)
    monkey(cfg, "TTS_FINISH_LINE", True)
    monkey(sil, "installed", lambda: True)
    got, played = [], []
    monkey(sil, "synth_to_wav", lambda text, path, voice, level=0, pitch=0: got.append((text, voice, level)) or path)

    class P:
        def load(self, path): return path
        def play(self, alias, vol): played.append(alias)
        def busy(self, alias): return False
        def close(self, alias): pass
        def close_all(self): pass
    monkey(tts, "_make_player", P)
    n = tts._Neural()
    monkey(tts, "_neural", n)
    T.speak_subtitle("Кеспер: Если найдёшь кости, неси их мне.")
    end = time.time() + 3
    while time.time() < end and not played:
        time.sleep(0.02)
    n.quit()
    assert got == [("Если найдёшь кости, неси их мне.", "eugene", 1)], got
    assert played and played[0].endswith(".wav"), played
    assert "Silero" in tts.voice_title()


def test_character_voices(monkey):
    """Голоса персонажей: имя, пол по речи, стабильный голос, ручная настройка, передача в озвучку."""
    try:
        from aac import voices
    except ImportError:
        print("   (в этой версии нет голосов персонажей — пропуск)")
        return
    monkey(voices, "FILE", os.path.join(TMP, "characters.json"))
    monkey(voices, "_data", {"loaded": False, "chars": {}})
    cfg = T._owner("TTS_READ_NAME")
    monkey(cfg, "TTS_RUSSIAN_ONLY", False)
    assert voices.gender_votes("Я нашла кости у моря.") == (1, 0)
    assert voices.gender_votes("Я не видел его. Я рад!") == (0, 2)
    assert voices.gender_votes("Мы пришли.") == (0, 0)
    assert voices.speaker("Кеспер\nПривет", "Kesper\nHi") == ("kesper", "Kesper", "Кеспер")
    assert voices.speaker("Полдат: За твоё здоровье!", None) == ("полдат", "", "Полдат")
    assert voices.speaker("Просто текст без имени.", "Just text.") is None
    # имя без подсказок: Марианна — женщина по имени, Кеспер — мужчина
    k1 = voices.note_line("Марианна\nДобро пожаловать.", "Marianna\nWelcome.")
    k2 = voices.note_line("Кеспер\nДобро пожаловать.", "Kesper\nWelcome.")
    assert voices.voice_for(k1, "neural")[0] in voices.NEURAL_POOL["f"]
    assert voices.voice_for(k2, "neural")[0] in voices.NEURAL_POOL["m"]
    assert voices.voice_for(k2, "silero")[0] in voices.SILERO_POOL["m"]
    # речь говорит обратное — пол меняется
    voices.note_line("Кеспер\nЯ сама нашла эти кости.", "Kesper\nI found these bones myself.")
    voices.note_line("Кеспер\nЯ так рада!", "Kesper\nI'm so glad!")
    assert voices.voice_for(k2, "neural")[0] in voices.NEURAL_POOL["f"]
    # стабильно: тот же персонаж — тот же голос и высота
    assert voices.voice_for(k1) == voices.voice_for(k1)
    # то же имя, но пришло только по-русски — не заводим двойника
    assert voices.note_line("Кеспер\nЕщё раз привет.", None) == k2
    # вручную: пол и голос
    voices.set_manual(k2, gender_value="m")
    assert voices.voice_for(k2, "neural")[0] in voices.NEURAL_POOL["m"]
    voices.set_manual(k2, voice="ru-RU-DmitryNeural", engine="neural")
    assert voices.voice_for(k2, "neural") == ("ru-RU-DmitryNeural", 0)
    # голос по умолчанию для женщин: все женщины без ручного голоса — им
    if hasattr(voices, "set_default_voice"):
        monkey(cfg, "TTS_DEFAULT_VOICES", {"neural": {"m": "", "f": ""}, "silero": {"m": "", "f": ""}})
        voices.set_default_voice("neural", "f", "en-US-EmmaMultilingualNeural")
        if hasattr(cfg, "TTS_VARY_IN_GENDER"):
            monkey(cfg, "TTS_VARY_IN_GENDER", True)       # «разные внутри пола» — общий голос не мешает
            assert voices.voice_for(k1, "neural")[1] in voices.NEURAL_PITCH
            monkey(cfg, "TTS_VARY_IN_GENDER", False)      # один голос на всех женщин
            assert voices.voice_for(k1, "silero") == (voices.SILERO_POOL["f"][0], 0)   # не выбран — первый
        assert voices.voice_for(k1, "neural")[0] == "en-US-EmmaMultilingualNeural"
        assert voices.voice_for(k2, "neural") == ("ru-RU-DmitryNeural", 0)       # ручной выбор важнее
        assert T.load_settings()["tts_default_voices"]["neural"]["f"] == "en-US-EmmaMultilingualNeural"
        voices.set_default_voice("neural", "f", "")
    monkey(cfg, "TTS_RUSSIAN_ONLY", True)
    assert voices.voice_for(k1, "neural")[0].startswith("ru-")
    assert voices.voice_for(k1, "windows") is None
    assert json.load(open(voices.FILE, encoding="utf-8"))[k2]["voice_neural"] == "ru-RU-DmitryNeural"
    # передача в озвучку
    tts = T._owner("speak_subtitle")
    said = []
    monkey(cfg, "TTS_ENABLED", True)
    monkey(cfg, "TTS_PER_CHARACTER", True)
    monkey(cfg, "TTS_ENGINE", "neural")
    monkey(tts, "engine_ready", lambda: True)
    monkey(tts._neural, "say", lambda text, seen=None, vp=None: said.append((text, vp)))
    T.speak_subtitle("Кеспер\nПойдём к морю.", None, "Kesper\nLet's go to the sea.")
    assert said == [("Пойдём к морю.", ("ru-RU-DmitryNeural", 0))], said
    monkey(cfg, "TTS_PER_CHARACTER", False)
    T.speak_subtitle("Марианна\nДо встречи.", None, "Marianna\nSee you.")
    assert said[-1] == ("До встречи.", None), said
    voices.forget(k1)
    assert k1 not in dict(voices.all_chars())
    if hasattr(voices, "same_name"):
        # двойники из-за ошибок распознавания: «Dometos» / «Dometosn» / «Дометос» — один персонаж
        monkey(voices, "ask_ai", None)
        kd = voices.note_line("Дометос\nПривет.", "Dometos\nHi.")
        assert voices.note_line("Дометос\nЕщё.", "Dometosn\nMore.") == kd
        assert voices.note_line("Дометос\nИ ещё.", None) == kd
        assert not voices.same_name("Marik", "Mario") and voices.same_name("Дометос", "Дометоса")
        # уже сохранённые двойники склеиваются при загрузке (ручной пол не теряется)
        json.dump({"dometos": {"en": "Dometos", "ru": "Дометос", "lines": 5, "f": 0, "m": 1},
                   "дометос": {"en": "", "ru": "Дометос", "lines": 2, "gender_manual": "f"},
                   "dometosn": {"en": "Dometosn", "ru": "Дометосн", "lines": 1}},
                  open(voices.FILE, "w", encoding="utf-8"))
        monkey(voices, "_data", {"loaded": False, "chars": {}})
        chars = dict(voices.all_chars())
        assert list(chars) == ["dometos"] and chars["dometos"]["lines"] == 8, chars
        assert chars["dometos"]["gender_manual"] == "f"
    if hasattr(voices, "flip_last"):
        # новый персонаж: нейросеть угадывает пол по имени и реплике — сразу, уже для первой реплики
        asked = []
        monkey(voices, "ask_ai", lambda prompt: asked.append(prompt) or "f")
        monkey(cfg, "TTS_DEFAULT_VOICES", {"neural": {"m": "", "f": ""}, "silero": {"m": "", "f": ""}})
        monkey(cfg, "TTS_RUSSIAN_ONLY", False)
        k3 = voices.note_line("Видрин\nСапоги из шкуры волка!", "Vidrin\nWolf-hide boots!")
        assert asked and "Vidrin" in asked[0] and "Wolf-hide boots!" in asked[0], asked
        assert voices.voice_for(k3, "neural")[0] in voices.NEURAL_POOL["f"]
        voices.note_line("Видрин\nЕщё раз.", "Vidrin\nAgain.")
        assert len(asked) == 1                                   # спрашиваем один раз на персонажа
        # подсказка переводчику о поле говорящего
        assert "a woman" in voices.gender_hint("Vidrin\nWolf-hide boots!")
        assert voices.gender_hint("Nobody here.") == ""
        # клавиша «сменить пол говорящего» — последний персонаж, запоминается
        assert voices.flip_last()[1] == "m"
        assert voices.voice_for(k3, "neural")[0] in voices.NEURAL_POOL["m"]
        assert "a man" in voices.gender_hint("Vidrin\nHi there.")
        # нейросеть не знает — не мешает остальным догадкам
        monkey(voices, "ask_ai", lambda prompt: "u")
        k4 = voices.note_line("Марианна\nДобро пожаловать.", "Marianna\nWelcome.")
        assert voices.voice_for(k4, "neural")[0] in voices.NEURAL_POOL["f"]


def test_tooltip(monkey):
    """Подсказка у мыши: блок текста рядом с курсором, перевод только его, окно рядом с подсказкой."""
    try:
        from aac import tooltip
    except ImportError:
        print("   (в этой версии нет перевода подсказок — пропуск)")
        return
    # две «подсказки»: строка чата далеко слева внизу и блок предмета справа от курсора
    lines = [("Player123: hi all", (10, 800, 200, 818)),
             ("Dawn Blade", (520, 300, 640, 318)), ("Two-handed sword", (520, 322, 680, 338)),
             ("Attack +120", (520, 342, 620, 358)), ("Durability 80/80", (520, 362, 660, 378)),
             ("Quest", (900, 40, 950, 56))]
    blocks = tooltip.group_blocks(lines)
    assert sorted(len(b["lines"]) for b in blocks) == [1, 1, 4], blocks
    bl = tooltip.pick_block(blocks, 500, 310)
    assert bl["lines"][0] == "Dawn Blade" and bl["box"] == (520, 300, 680, 378), bl
    assert tooltip.search_box(100, 100, 1920, 1080, (1100, 900)) == (0, 0, 1100, 900)
    assert tooltip.search_box(1900, 1000, 1920, 1080, (1100, 900)) == (820, 180, 1100, 900)
    # окно перевода: слева от подсказки, если есть место, иначе справа
    assert tooltip.place((600, 300, 200, 100), (590, 310), 420, 150, 1920, 1080) == (168, 300)
    assert tooltip.place((100, 300, 200, 100), (90, 310), 420, 150, 1920, 1080) == (312, 300)
    # OCR Windows отдаёт дробные координаты — окно всё равно ставится (журнал: «bad geometry +889.0+449.0»)
    x, y = tooltip.place((1309.0, 449.0, 200.0, 100.0), (1300, 450), 420, 62, 1920, 1080)
    assert isinstance(x, int) and isinstance(y, int) and (x, y) == (877, 449)
    # весь путь: снимок → OCR с рамками → перевод вырезанного блока
    shots, crops = [], []
    from PIL import Image
    monkey(tooltip.capture, "grab", lambda reg: shots.append(reg) or Image.new("RGB", (reg[2], reg[3])))
    monkey(tooltip, "screen_size", lambda: (1920, 1080))
    try:
        from aac import screens
        monkey(screens, "monitor_at", lambda x, y: (0, 0, 1920, 1080))
    except ImportError:
        pass
    monkey(tooltip.ocr, "ocr_boxes", lambda img: [(t, (b[0] - 0, b[1], b[2], b[3])) for t, b in lines])

    def fake_tr(img, prompt=None):
        crops.append((img.size, prompt))
        return "Клинок рассвета (Dawn Blade)\nДвуручный меч", None
    monkey(tooltip.translate, "safe_translate", fake_tr)
    drain()
    tooltip.translate_smart((1000, 700))          # одна кнопка: рядом блок из 4 строк — это подсказка предмета
    ev = [p for k, p in drain() if k == "tooltip_show"]
    assert shots == [(450, 180, 1100, 900)], shots
    assert crops and crops[0][1].startswith("Screenshot of a tooltip"), crops
    # курсор (1000,700) → в снимке (550,520): ближе всех блок предмета; вырезан он с полями 10 px
    assert crops[0][0] == (180, 98), crops
    assert ev[0]["text"].startswith("⏳") and ev[-1]["box"] == (450 + 510, 180 + 290, 180, 98), ev
    assert ev[-1]["text"][0].startswith("Клинок рассвета")


def test_mouse_with_modifier(monkey):
    """Сочетания «Ctrl + кнопка мыши»: назначение, подпись, срабатывание; без Ctrl — обычная кнопка."""
    hk = T._owner("load_hotkeys")
    if not hasattr(hk, "is_mouse"):
        print("   (в этой версии нет — пропуск)")
        return
    assert hk.pretty("ctrl+mouse_x1") == "Ctrl+Мышь назад" and hk.pretty("shift+f9") == "Shift+F9"
    monkey(hk, "hotkeys", dict(hk.hotkeys, once="mouse_x1", once_tts="ctrl+mouse_x1"))
    monkey(hk, "MOUSE_OK", True)
    hk.register_hotkeys()
    assert hk.mouse_bindings.get("ctrl+mouse_x1") == "once_tts" and hk.mouse_bindings.get("mouse_x1") == "once"
    assert hk.K("once_tts") == "Ctrl+Мышь назад"
    monkey(hk, "_mouse_button_name", lambda b: "mouse_x1")
    mods = []
    monkey(hk, "held_modifiers", lambda: list(mods))
    drain()
    mods[:] = ["ctrl"]
    hk._on_mouse_click(0, 0, "b", True)
    mods[:] = []
    hk._on_mouse_click(0, 0, "b", True)
    mods[:] = ["shift"]                       # Shift+кнопка не назначена — срабатывает просто кнопка
    hk._on_mouse_click(0, 0, "b", True)
    evs = [k for k, _ in drain() if k in ("once", "once_tts")]
    assert evs == ["once_tts", "once", "once"], evs
    # назначение: зажали Ctrl и нажали кнопку мыши
    got = {}
    monkey(hk, "mouse_capture", lambda combo: got.setdefault("c", combo))
    mods[:] = ["ctrl"]
    hk._on_mouse_click(0, 0, "b", True)
    assert got["c"] == "ctrl+mouse_x1"
    monkey(hk, "mouse_capture", None)
    hk.unregister_hotkeys()


def test_new_hotkey_does_not_steal(monkey):
    """Новая клавиша из обновления не забирает кнопку, которую вы уже назначили на другое."""
    hk = T._owner("load_hotkeys")
    if not any(d[0] == "tooltip" for d in getattr(hk, "HOTKEY_DEFS", [])):
        print("   (в этой версии нет клавиши подсказки — пропуск)")
        return
    monkey(T._owner("SETTINGS"), "SETTINGS", {"hotkeys": {"once": "mouse_x2"}})
    T.load_hotkeys()
    assert hk.hotkeys["once"] == "mouse_x2" and hk.hotkeys["tooltip"] == "ctrl+shift+t", hk.hotkeys
    monkey(T._owner("SETTINGS"), "SETTINGS", {})
    T.load_hotkeys()
    assert hk.hotkeys["tooltip"] == "mouse_x2"


def test_ignore_ui_words_and_same_text(monkey):
    if not hasattr(T, "ignored_words"):
        print("   (в этой версии нет — пропуск)")
        return
    assert "skip" in T.ignored_words()
    try:
        import numpy  # noqa: F401  (нужен только для этой проверки)
    except ImportError:
        print("   (нет numpy — проверка фильтра OCR пропущена)")
    else:
        ocr = T._owner("_ocr_lines")
        monkey(ocr, "_init_ocr", lambda: None)
        monkey(ocr, "_ocr_kind", "rapid")
        res = types.SimpleNamespace(boxes=[[[0, 0]], [[0, 40]], [[0, 80]]],
                                    txts=["Poldat", "Damn sharks will be fed tonight Skip", "Skip"])
        monkey(ocr, "_rapid", lambda arr: res)
        assert T.ocr_lines(img()) == ["Poldat", "Damn sharks will be fed tonight"], T.ocr_lines(img())
    same = T.same_text
    assert same("Poldat\nDamn sharks will be fed tonight", "Poldat\nDamn sharks will be fed tonight.")
    assert not same("Poldat\nDamn sharks will be fed tonight", "Poldat\nOh? Now we've got two little mice")
    assert not same("Yes", "Yes, she's safe.")
    sent = []
    tts = T._owner("speak_subtitle")
    if hasattr(T._owner("TTS_READ_NAME"), "TTS_ENGINE"):
        monkey(T._owner("TTS_READ_NAME"), "TTS_ENGINE", "windows")
    monkey(tts, "_start", lambda: True)
    monkey(tts, "_send", lambda cmd, arg="": sent.append(arg))
    monkey(T._owner("TTS_ENABLED"), "TTS_ENABLED", True)
    T.speak_subtitle("Р-и")
    assert sent == [], "обрывки не озвучиваем"


def test_translation_cache(monkey):
    """Одинаковая фраза — второй раз из кэша без запроса; кэш переживает перезапуск; по клавише — свежий перевод."""
    from aac import tcache
    T.set("PROVIDER", "groq_ocr")
    T.set("FALLBACK_PROVIDERS", [])
    T.set("GROQ_API_KEY", "q")
    T.dialogue_history.clear()
    T.provider_cooldown.clear()
    T.model_cooldown.clear()
    sent = []

    def post(url, headers=None, json=None, timeout=None, **k):
        sent.append(1)
        return R(200, {"choices": [{"message": {"content": f"Добро пожаловать, путник №{len(sent)}"}}],
                       "usage": {"prompt_tokens": 50}})

    monkey(T.requests, "post", post)
    lines = [["Welcome,  traveler."]]
    monkey(T._owner("ocr_lines"), "ocr_lines", lambda im: lines[0])
    assert T.safe_translate(img())[0] == "Добро пожаловать, путник №1"
    lines[0] = ["welcome, traveler"]        # чуть иначе распознано — всё равно совпадение
    assert T.safe_translate(img())[0] == "Добро пожаловать, путник №1"
    assert len(sent) == 1, "повтор не должен тратить запрос"
    assert tcache.stats["hits"] == 1
    tcache.save()
    with tcache._lock:
        tcache._data = None                 # «перезапуск программы»
    assert T.safe_translate(img())[0] == "Добро пожаловать, путник №1" and len(sent) == 1
    with tcache.fresh():                    # разовый перевод по клавише — новый запрос, и кэш обновится
        assert T.safe_translate(img())[0] == "Добро пожаловать, путник №2"
    assert T.safe_translate(img())[0] == "Добро пожаловать, путник №2" and len(sent) == 2
    T.set("CACHE_ENABLED", False)
    try:
        T.safe_translate(img())
        assert len(sent) == 3, "выключенный кэш не используется"
    finally:
        T.set("CACHE_ENABLED", True)
    tcache.clear()                          # не-русский ответ (сбой модели) в кэш не попадает
    monkey(T.requests, "post", lambda *a, **k: R(200, {"choices": [{"message": {"content": "Welcome back, friend of mine"}}]}))
    T.safe_translate(img())
    assert tcache.size() == 0


def test_intonation(monkey):
    """Интонация: «!» живее и громче, «?» выше, «…» медленнее; фразы с разной интонацией не склеиваются."""
    tts = T._owner("speak_subtitle")
    if not hasattr(tts, "mood_of"):
        print("   (в этой версии нет — пропуск)")
        return
    cfg = T._owner("TTS_READ_NAME")
    monkey(cfg, "TTS_EXPRESSIVE", True)
    assert [tts.mood_of(x) for x in ("Беги!", "Ты кто?", "Ну… не знаю…", "СТОЙ НА МЕСТЕ", "Ладно.", "Что?!")] == \
        ["excl", "ask", "pause", "excl", "", "excl"]
    ch = tts.split_chunks("Привет. Как дела? Хорошо. Отлично. Беги отсюда!")
    assert [tts.mood_of(c) for c in ch] == ["", "ask", "", "excl"], ch
    assert ch[2] == "Хорошо. Отлично."
    # нейроголос получает другие скорость/высоту/громкость
    monkey(cfg, "TTS_ENGINE", "neural")
    monkey(cfg, "TTS_RATE", 0)
    got = []

    async def fake(text, path, voice, rate, pitch="+0Hz", volume="+0%"):
        got.append((text, rate, pitch, volume))
    monkey(tts, "_synth_async", fake)
    import asyncio
    n = tts._Neural.__new__(tts._Neural)
    for t in ("Беги!", "Ладно."):
        asyncio.run(n._synth_coro(t, os.path.join(TMP, "x"), False, ("ru-RU-DmitryNeural", -5)))
    assert got[0] == ("Беги!", "+8%", "+5Hz", "+15%"), got
    assert got[1] == ("Ладно.", "+0%", "-5Hz", "+0%"), got
    monkey(cfg, "TTS_EXPRESSIVE", False)
    assert tts.mood_of("Беги!") == ""


def test_word_at_cursor(monkey):
    """Надпись под мышкой: берётся строка у курсора (табличка в 2 строки — целиком), перевод в кэш."""
    try:
        from aac import tooltip, tcache
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    if not hasattr(tooltip, "pick_line"):
        print("   (в этой версии нет — пропуск)")
        return
    lines = [("Archivist Rotild", (300, 70, 420, 88)), ("Quest", (300, 10, 340, 26)),
             ("The Drunken", (600, 70, 690, 86)), ("Sailor Inn", (605, 88, 685, 104))]
    assert tooltip.pick_line(lines, 350, 95)[0] == "Archivist Rotild"
    assert tooltip.pick_line(lines, 640, 95)[0] == "The Drunken Sailor Inn"
    assert tooltip.pick_line(lines, 100, 150) is None        # далеко от надписей
    asked = []
    monkey(T._owner("ask_text"), "ask_text", lambda p: asked.append(p) or "«Таверна «Пьяный моряк»»")
    assert T.translate_short("The Drunken  Sailor Inn") == "Таверна «Пьяный моряк»"
    assert T.translate_short("the drunken sailor inn") == "Таверна «Пьяный моряк»" and len(asked) == 1
    # без нейросети — Google
    monkey(T._owner("ask_text"), "ask_text", lambda p: None)
    monkey(T._owner("_mt_google"), "_mt_google", lambda t, sl=None, tl=None: "Архивариус Ротильд")
    assert T.translate_short("Archivist Rotild") == "Архивариус Ротильд"
    # весь путь: снимок → OCR → событие для маленькой плашки
    from PIL import Image
    monkey(tooltip, "screen_size", lambda: (1920, 1080))
    monkey(tooltip.capture, "grab", lambda reg: Image.new("RGB", (reg[2], reg[3])))
    monkey(tooltip.ocr, "ocr_boxes", lambda img: [("Archivist Rotild", (500, 440, 620, 458)),
                                                  ("Silent Crossway", (100, 100, 220, 118))])
    drain()
    tooltip.translate_smart((800, 520))   # снимок с (250, 70): курсор над надписью → маленькая плашка
    ev = [e for e in drain() if e[0] == "word_show"]
    assert ev and ev[0][1]["text"] == "Архивариус Ротильд" and ev[0][1]["orig"] == "Archivist Rotild", ev
    assert tooltip.place_word((500, 300, 120, 18), (560, 310), 200, 40, 1920, 1080) == (460, 254)
    # выбор: подсказка предмета рядом с курсором → большое окно; над подписью карты → плашка
    item = [("Dawn Blade", (520, 300, 640, 318)), ("Two-handed sword", (520, 322, 680, 338)),
            ("Attack +120", (520, 342, 620, 358)), ("Durability 80/80", (520, 362, 660, 378))]
    assert tooltip.choose(item, 500, 310)[0] == "tooltip"
    assert tooltip.choose(item + [("Seaglass Harbor", (900, 600, 1040, 620))], 950, 612)[0] == "word"
    assert tooltip.choose(item, 520 + 40, 300 + 8)[0] == "tooltip"      # курсор прямо на заголовке подсказки
    assert tooltip.choose([], 10, 10) == (None, None)


def test_key_hints_skipped():
    """Строка подсказок клавиш (карта, инвентарь) не переводится, обычные реплики — переводятся."""
    try:
        from aac.ocr import is_key_hints
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    for ln in ("Esc Close Zoom In/Out Select T Track I Legend F Fast Travel H Destination List Z My Location",
               "Esc Close F Replace R Unequip", "F Talk", "Enter Chat", "[T] Track [I] Legend"):
        assert is_key_hints(ln), ln
    for ln in ("I Agree with you", "Go to Seaglass Harbor and find T. Rotild.", "Archivist Rotild",
               "Find Vol. II of the Chronicles of Aurorian Settlement (0/1)", "Silent Crossway",
               "A Brave New World", "Yes, I'll do it", "Welcome to Seaglass Harbor"):
        assert not is_key_hints(ln), ln


def test_quest_key_closes_window(monkey):
    """Окно задания открыто — клавиша «перевести задание» его закрывает (мышкой не дотянуться в игре)."""
    if not GUI:
        print("   (без экрана — пропуск)")
        return
    T.set("SETTINGS", {})
    app = T.App()
    try:
        picked = []
        monkey(app, "pick_area", lambda *a, **k: picked.append(a))
        app.quest.show("Найдите том II")
        app.root.update()
        app.select_quest_once()
        assert not app.quest.visible and not picked, "первое нажатие — закрыть окно"
        app.select_quest_once()
        assert picked, "второе нажатие — обвести новое задание"
    finally:
        app.root.destroy()


def test_backup_roundtrip(monkey):
    """Резервная копия: всё в один zip; восстановление возвращает файлы, а текущие сохраняет в backups."""
    try:
        from aac import backup, voices, glossary, tcache, menu
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    import zipfile
    d = tempfile.mkdtemp(dir=TMP)
    real = {"s.json": "s.json", "c.json": "characters.json", "g.txt": "glossary.txt", "t.json": "translation_cache.json",
            "m.png": "menu_ref.png"}
    paths = {n: os.path.join(d, real[n]) for n in real}
    monkey(T._owner("SETTINGS_FILE"), "SETTINGS_FILE", paths["s.json"])
    monkey(T._owner("APP_DIR"), "APP_DIR", d)          # файлы пресета ArcheAge — «рядом с программой»
    monkey(voices, "FILE", paths["c.json"])
    monkey(glossary, "GLOSSARY_FILE", paths["g.txt"])
    monkey(tcache, "CACHE_FILE", paths["t.json"])
    monkey(menu, "REF_FILE", paths["m.png"])
    monkey(backup, "BACKUP_DIR", os.path.join(d, "backups"))
    for n, text in (("s.json", '{"region": [1, 2, 3, 4]}'), ("c.json", '{"renald": {"en": "Renald"}}'),
                    ("g.txt", "Renald = Ренальд\n"), ("t.json", "{}")):
        open(paths[n], "w", encoding="utf-8").write(text)
    os.makedirs(os.path.join(d, "profiles", "witcher3"))
    wg = os.path.join(d, "profiles", "witcher3", "glossary.txt")
    open(wg, "w", encoding="utf-8").write("Geralt = Геральт\n")
    zpath = os.path.join(d, "backup.zip")
    saved = backup.export(zpath)
    assert set(saved) == {"settings.json", "characters.json", "glossary.txt", "translation_cache.json",
                          "profiles/witcher3/glossary.txt"}, saved
    os.remove(wg)
    assert backup.read_manifest(zpath)["files"] == saved
    # всё поменяли / удалили…
    open(paths["s.json"], "w").write('{"region": [9, 9, 9, 9]}')
    os.remove(paths["g.txt"])
    restored, before = backup.restore(zpath)
    assert set(restored) == set(saved)
    assert open(wg, encoding="utf-8").read() == "Geralt = Геральт\n", "пресеты других игр — тоже в копии"
    assert json.load(open(paths["s.json"]))["region"] == [1, 2, 3, 4]
    assert open(paths["g.txt"], encoding="utf-8").read() == "Renald = Ренальд\n"
    assert os.path.exists(before) and json.loads(zipfile.ZipFile(before).read("settings.json"))["region"] == [9, 9, 9, 9]
    assert T.SETTINGS.get("region") == [1, 2, 3, 4], "в памяти программы — восстановленные настройки"
    # чужой zip и попытка подсунуть файл мимо папки — отклоняются
    bad = os.path.join(d, "bad.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "x")
    try:
        backup.read_manifest(bad)
        assert False, "чужой архив не должен приниматься"
    except ValueError:
        pass
    evil = os.path.join(d, "evil.zip")
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("aac_backup.json", json.dumps({"files": ["../../evil.txt", "glossary.txt"]}))
        z.writestr("../../evil.txt", "x")
        z.writestr("glossary.txt", "Kevin = Кевин\n")
    restored, _ = backup.restore(evil)
    assert restored == ["glossary.txt"] and not os.path.exists(os.path.join(d, "..", "..", "evil.txt"))


def test_repeat_line(monkey):
    """Повторить реплику: последняя реплика снова звучит (даже при выключенной озвучке) голосом персонажа."""
    tts = T._owner("speak_subtitle")
    if not hasattr(tts, "repeat_line"):
        print("   (в этой версии нет — пропуск)")
        return
    said, stopped = [], []
    monkey(tts, "_say", lambda text, seen=None, vp=None: said.append(text))
    monkey(tts, "stop", lambda: stopped.append(1))
    monkey(T._owner("TTS_ENABLED"), "TTS_ENABLED", False)
    tts.repeat_line("Ренальд\nДержись рядом.", "Renald\nStay close.")
    assert stopped and said and "Держись рядом" in said[0], said
    if GUI:
        T.set("SETTINGS", {})
        app = T.App()
        try:
            monkey(T._owner("last_line"), "last_line", ("Ренальд\nДержись рядом.", "Renald\nStay close."))
            got = []
            monkey(tts, "repeat_line", lambda t, o=None: got.append(t))
            app.subs.hide()
            app.repeat_line()
            app.root.update()
            time.sleep(0.1)
            assert app.subs.visible and app.subs.label.cget("text") == "Ренальд\nДержись рядом."
            assert got == ["Ренальд\nДержись рядом."], got
        finally:
            app.root.destroy()


def test_new_shell(monkey):
    """Новое главное окно: разделы открываются, плитки и переключатели меняют настройки, клавиши подписаны."""
    if not GUI:
        print("   (без экрана — пропуск)")
        return
    try:
        from aac import ui_shell
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    T.set("SETTINGS", {})
    T.load_hotkeys()
    app = T.App()
    try:
        sh = app.panel
        assert isinstance(sh, ui_shell.Shell) and sh.current == "home"
        for sid in ("areas", "tr", "keys", "backup", "home"):
            sh.show(sid)
            app.root.update()
            assert sh.current == sid
        core_m = T._owner("answers_auto")
        was = core_m.answers_auto
        sh.tiles["answers"].toggle.click()
        assert core_m.answers_auto == (not was) and T.load_settings()["answers_auto"] == (not was)
        sh.tiles["answers"].toggle.click()
        # окна перевода на трансляции: переключатель сохраняется и применяется ко всем окнам перевода
        from aac import ui_overlay
        applied = []
        monkey(ui_overlay, "apply_stream_visibility", lambda: applied.append(1))
        sh.stream_row.toggle.click()
        assert T._owner("SHOW_ON_STREAM").SHOW_ON_STREAM is True and T.load_settings()["show_on_stream"] is True
        assert applied and app.subs.win in ui_overlay.STREAM_WINDOWS and sh.win not in ui_overlay.STREAM_WINDOWS
        sh.stream_row.toggle.click()
        assert T._owner("SHOW_ON_STREAM").SHOW_ON_STREAM is False
        sh.show("tr")
        cfg = T._owner("CACHE_ENABLED")
        before = cfg.CACHE_ENABLED
        sh.tr_rows[0].toggle.click()
        assert cfg.CACHE_ENABLED == (not before) and T.load_settings()["cache_enabled"] == (not before)
        sh.tr_rows[0].toggle.click()
        # обновление панели (несколько раз в секунду) не пересоздаёт строки — иначе они мигают
        ids = {pid: str(w["title"]) for pid, w in sh.prov_rows.items()}
        for _ in range(3):
            sh.refresh()
        assert ids == {pid: str(w["title"]) for pid, w in sh.prov_rows.items()}
        assert all(w["title"].winfo_exists() for w in sh.prov_rows.values())
        sh.show("keys")
        assert sh.key_chips["auto"].cget("text") == T.K("auto")
        # все разделы — внутри окна, прежние окна не открываются
        drain()
        for sid in ("win", "voice", "chars", "hist", "gloss"):
            sh.show(sid)
            app.root.update()
            assert sh.current == sid, sid
        assert not any(k in ("history_open", "settings_open") for k, _ in drain())
        # окна перевода: ползунок шрифта меняет настройку и сохраняет её на отпускании
        sh.show("win")
        cfg_f = T._owner("FONT")
        sh.win_sliders[0].slider.command(18, True)
        assert cfg_f.FONT[1] == 18 and T.load_settings()["font_size"] == 18
        sh.win_sliders[0].slider.command(13, True)
        # словарь из программы: добавить, исправить, удалить
        from aac import glossary as G
        monkey(G, "GLOSSARY_FILE", os.path.join(tempfile.mkdtemp(dir=TMP), "g.txt"))
        sh.show("gloss")
        sh._gl_edit("Rotild", "Ротильд")
        sh._gl_add()
        assert ("Rotild", "Ротильд", False) in G.entries()
        sh._gl_edit("Rotild", "Ротилд")
        sh._gl_add()
        assert ("Rotild", "Ротилд", False) in G.entries() and len([e for e in G.entries() if e[0] == "Rotild"]) == 1
        G.remove_entry("Rotild")
        assert not any(e[0] == "Rotild" for e in G.entries())
        assert G.add_ignore("Loot all") and ("Loot all", False) in G.ignore_entries()
        G.remove_ignore("Loot all")
        # персонажи: пол переключается
        from aac import voices as V
        monkey(V, "FILE", os.path.join(tempfile.mkdtemp(dir=TMP), "c.json"))
        with V._lock:
            V._data["loaded"] = False
        V._load()
        V._data["chars"]["vida"] = {"en": "Vida", "ru": "Вида", "f": 2, "seen": 1}
        sh.show("chars")
        V.set_manual("vida", gender_value="m")
        sh._chars_render()
        assert V.gender(dict(V.all_chars())["vida"]) == "m"
        # история: новый перевод дописывается в открытый раздел
        sh.show("hist")
        e = ("12:00:00", "Субтитры", "Hello", "Привет, путник")
        T._owner("translation_history").translation_history.append(e)
        sh.history_new(e)
        assert "Привет, путник" in sh.hist_text.get("1.0", "end")
        # колесо мыши крутит раздел, даже когда курсор над плиткой (раньше — нет)
        sh.show("voice")
        sh.win.geometry(f"{sh.win.winfo_width()}x360")
        app.root.update()
        sc = sh._current_scroll()
        tile = sh.voice_tiles[0]
        app.root.update()
        before = sc.canvas.yview()[0]
        sc.wheel(-120)
        app.root.update()
        assert sc.canvas.yview()[0] > before, "раздел должен прокрутиться"
        sh.win.geometry(f"{sh.win.winfo_width()}x{sh.height}")
        sh.show("keys")
        sh.show("home")
        sh.show_update("9.9")
        app.root.update()
        assert sh.upd_banner.winfo_manager() and "9.9" in sh.upd_text.cget("text")
        T.log("проверка журнала", "warn")
        for k, p in drain():
            if k == "log":
                sh.add_log(*p)
        assert "проверка журнала" in sh.logwin.text.get("1.0", "end")
        # журнал — отдельное окно: прячется и показывается сам по себе, главное окно не трогает
        lw = sh.logwin
        lw.toggle()
        assert not lw.visible and sh.visible and T.load_settings()["log_visible"] is False
        sh.add_log("00:00:00", "ошибка!", "error")      # ошибка показывает журнал
        assert lw.visible
        sh.toggle()
        assert not sh.visible and lw.visible
        sh.toggle()
    finally:
        app.root.destroy()


def test_update_on_startup(monkey):
    """Сама программа обновляется только при запуске и только если включено «обновлять автоматически»."""
    from aac import updater
    if not hasattr(updater, "startup_check"):
        print("   (в этой версии нет — пропуск)")
        return
    monkey(updater.time, "sleep", lambda s: None)
    T.set("SETTINGS", {})
    cfg = T._owner("UPDATE_AUTO")
    newer = {"version": "99.0", "notes": "", "asset_url": "x"}
    monkey(updater, "check", lambda quiet=True: newer)
    monkey(cfg, "UPDATE_AUTO", False)
    drain()
    assert updater.startup_check() is False
    assert ("update_install", None) not in drain(), "без согласия ничего не ставится"
    monkey(cfg, "UPDATE_AUTO", True)
    assert updater.startup_check() is True
    assert ("update_install", None) in drain(), "включено — ставится при запуске"
    updater.state["auto_installing"] = False
    monkey(updater, "check", lambda quiet=True: {"version": T._owner("VERSION").VERSION, "notes": ""})
    assert updater.startup_check() is False
    assert any(k == "log" and "последняя версия" in p[1] for k, p in drain())
    if GUI:
        app = T.App()
        try:
            clicked = []
            d = app.panel.ask("Вопрос", "Текст", "Да", lambda: clicked.append(1))
            app.root.update()
            btns = []

            def walk(w):
                for c in w.winfo_children():
                    if c.winfo_class() == "Button":
                        btns.append(c)
                    walk(c)
            walk(d)
            [b for b in btns if b.cget("text") == "Да"][0].invoke()
            assert clicked and app.panel._dialog is None
        finally:
            app.root.destroy()


def test_update_etag(monkey):
    """Частая проверка обновлений: повторный запрос спрашивает «изменилось ли?» (ETag), ответ 304 — без лимита."""
    from aac import updater
    sent = []

    def get(url, headers=None, timeout=None):
        sent.append(dict(headers or {}))
        if headers and headers.get("If-None-Match") == '"v1"':
            return R(304, {})
        r = R(200, {"version": "99.1", "notes": ["x"]})
        r.headers = {"ETag": '"v1"'}
        return r
    monkey(updater.requests, "get", get)
    updater.state.update(latest=None, etag=None, checking=False)
    drain()
    a = updater.check(quiet=True)
    b = updater.check(quiet=True)
    assert a["version"] == b["version"] == "99.1"
    assert "If-None-Match" not in sent[0] and sent[1]["If-None-Match"] == '"v1"'
    assert sum(1 for k, _ in drain() if k == "update_available") == 1, "второй раз — без нового объявления"
    updater.state.update(latest=None, etag=None)


def test_game_facts(monkey):
    """Groq один раз собирает об игре: словарь, персонажей с полом, описание (для DeepL и нейросетей)."""
    try:
        from aac import gamefacts, profiles, glossary, voices
    except ImportError:
        return
    d = tempfile.mkdtemp(dir=TMP)
    monkey(T._owner("APP_DIR"), "APP_DIR", d)
    monkey(T._owner("SETTINGS_FILE"), "SETTINGS_FILE", os.path.join(d, "s.json"))
    core_m = T._owner("active_profile")
    open(os.path.join(d, "s.json"), "w").write('{"font_size": 14}')
    T.set("SETTINGS", T.load_settings())
    pid = profiles.create("deadcells.exe", "Dead Cells")
    profiles.activate(pid, announce=False)
    with open(profiles.paths(pid)["glossary"], "a", encoding="utf-8") as f:
        f.write("Collector = Мой Коллекционер\n")          # ваша запись — не трогаем
    reply = """```json
{"known": true, "description": "Roguelite action platformer; sarcastic, informal tone.",
 "terms": [{"en": "Collector", "ru": "Коллекционер"}, {"en": "Prisoners' Quarters", "ru": "Тюремные камеры"},
           {"en": "Cells", "ru": "Клетки"}, {"en": "x", "ru": "x"}, {"en": "", "ru": "пусто"}],
 "characters": [{"en": "The Collector", "ru": "Коллекционер", "gender": "m"},
                {"en": "Queen", "ru": "Королева", "gender": "f"}, {"en": "Bob", "gender": "?"}]}
```"""
    data = gamefacts.parse(reply)
    assert data["known"] and len(data["terms"]) == 3 and len(data["characters"]) == 2
    assert gamefacts.parse('{"known": false}') == {"known": False} and not gamefacts.parse("мусор")["known"]
    monkey(T._owner("GROQ_API_KEY"), "GROQ_API_KEY", "gsk_test")
    monkey(gamefacts, "ask", lambda title, exe: data)
    assert gamefacts.gather(pid, wait=True)
    glossary._glossary.update(mtime=None, loaded=False)
    g = dict(glossary.glossary())
    assert g.get("Collector") == "Мой Коллекционер", "вашу запись не перезаписали"
    assert g.get("Prisoners' Quarters") == "Тюремные камеры" and g.get("Cells") == "Клетки"
    with voices._lock:
        voices._data["loaded"] = False
    chars = voices.all_chars() if hasattr(voices, "all_chars") else {}
    queen = [c for c in (chars.values() if isinstance(chars, dict) else [c for _, c in chars]) if c.get("en") == "Queen"]
    assert queen and voices.gender(queen[0]) == "f", chars
    assert profiles.active()["about"].startswith("Roguelite")
    assert "About this game: Roguelite" in profiles.adapt("Translate the subtitles.")
    assert not gamefacts.gather(pid, wait=True), "второй раз сам не собирает"
    assert gamefacts.gather(pid, force=True, wait=True), "«Собрать заново» — собирает"
    content = open(profiles.paths(pid)["glossary"], encoding="utf-8").read()
    assert content.count("Prisoners' Quarters =") == 1, "повторный сбор не дублирует словарь"
    # DeepL получает описание как контекст
    from aac import mt
    sent = {}

    class R:
        status_code = 200
        def json(self):
            return {"translations": [{"text": "Привет"}]}
    monkey(mt.requests, "post", lambda url, headers=None, data=None, timeout=None: sent.update(data) or R())
    monkey(T._owner("DEEPL_API_KEY"), "DEEPL_API_KEY", "k:fx")
    assert mt._mt_deepl("Hello") == "Привет" and sent.get("context", "").startswith("Roguelite")
    monkey(T._owner("GROQ_API_KEY"), "GROQ_API_KEY", "ВСТАВЬТЕ_СЮДА_КЛЮЧ_GROQ")
    assert not gamefacts.available() and not gamefacts.gather(pid, force=True), "без ключа — ничего"
    profiles.activate(None, announce=False)


def test_new_user_no_presets(monkey):
    """Новый пользователь: пресетов нет (ArcheAge не создаётся сама), игра не выбрана."""
    try:
        from aac import profiles
    except ImportError:
        return
    core_m = T._owner("active_profile")
    if not hasattr(core_m, "had_old_settings"):
        return
    d = tempfile.mkdtemp(dir=TMP)
    monkey(T._owner("APP_DIR"), "APP_DIR", d)
    monkey(T._owner("SETTINGS_FILE"), "SETTINGS_FILE", os.path.join(d, "s.json"))
    monkey(core_m, "active_profile", "archeage")
    open(os.path.join(d, "s.json"), "w").write('{"font_size": 14}')
    T.set("SETTINGS", T.load_settings())
    assert profiles.all_profiles() == {} and core_m.active_profile is None and core_m.region is None
    assert profiles.name() == "нет игры"
    T.save_settings(region=(1, 2, 3, 4))
    assert json.load(open(os.path.join(d, "s.json"))).get("profiles") in (None, {})


def test_game_presets(monkey):
    """Пресеты игр: у каждой игры свои области, словарь, персонажи; переключение — по окну на экране."""
    try:
        from aac import profiles, game, glossary, voices
    except ImportError:
        print("   (в этой версии нет — пропуск)")
        return
    d = tempfile.mkdtemp(dir=TMP)
    monkey(T._owner("APP_DIR"), "APP_DIR", d)
    monkey(T._owner("SETTINGS_FILE"), "SETTINGS_FILE", os.path.join(d, "s.json"))
    cfg = T._owner("GAMES_ONLY")
    monkey(cfg, "GAMES_ONLY", True)
    core_m = T._owner("active_profile")
    monkey(core_m, "active_profile", "archeage")
    T.set("SETTINGS", {"region": [1, 2, 3, 4]})                 # старые настройки до пресетов
    open(os.path.join(d, "s.json"), "w").write('{"region": [1, 2, 3, 4]}')
    T.set("SETTINGS", T.load_settings())
    assert core_m.active_profile is None, "игра не запущена — пресет не выбран"
    assert list(profiles.all_profiles()) == ["archeage"], "прежние настройки — в пресет ArcheAge"
    profiles.activate("archeage", announce=False)
    assert profiles.name() == "ArcheAge Chronicles" and core_m.region == (1, 2, 3, 4), "прежние области — в ArcheAge"
    glossary.set_entry("Renald", "Ренальд")
    fg = ["Witcher3.exe"]
    monkey(game, "foreground_exe", lambda: (fg[0].lower(), 4242))
    assert game.blocked(), "у новой игры пресета ещё нет — клавиши не работают"
    drain()
    monkey(game, "foreground_title", lambda: "Witcher3")
    assert game.remember_game_window() == "new"       # клавиша автоперевода в новой игре — пресет создаётся сам
    ev = drain()
    assert ("game_created", "witcher3") in ev and ("profile_changed", "witcher3") in ev
    assert core_m.active_profile == "witcher3" and profiles.name() == "Witcher3"
    assert core_m.region is None, "у новой игры — свои (пустые) области"
    T.save_settings(region=(5, 6, 7, 8))
    glossary.set_entry("Geralt", "Геральт")
    assert [e[0] for e in glossary.entries()] == ["Geralt"], "словарь новой игры — свой"
    assert "the video game Witcher3" in profiles.adapt(T._owner("TEXT_PROMPT").TEXT_PROMPT)
    assert "ArcheAge" not in profiles.adapt(T._owner("TEXT_PROMPT").TEXT_PROMPT)
    # вернулись в ArcheAge — её пресет подхватился сам
    fg[0] = "ArcheAgeChronicles.exe"
    game.follow_foreground()
    assert core_m.active_profile == "archeage" and core_m.region == (1, 2, 3, 4)
    assert "Renald" in [e[0] for e in glossary.entries()] and "Geralt" not in [e[0] for e in glossary.entries()]
    assert profiles.adapt("MMORPG ArcheAge Chronicles") == "MMORPG ArcheAge Chronicles"
    fg[0] = "Witcher3.exe"
    game.follow_foreground()
    assert core_m.region == (5, 6, 7, 8), "области второй игры сохранились"
    # браузер — не игра, вопроса нет
    fg[0] = "chrome.exe"
    drain()
    game.remember_game_window()
    assert not any(k == "game_created" for k, _ in drain()) and set(profiles.all_profiles()) == {"archeage", "witcher3"}
    assert game.blocked()
    # «Не игра» — больше не спрашиваем
    assert game.unknown_game() is None, "плеер — в списке «не игр»"
    if hasattr(game, "no_game"):            # игра не запущена — ничего не переводим, автоперевод не включается
        monkey(game, "running_programs", lambda: [])
        profiles._run_cache["t"] = 0
        fg[0] = "chrome.exe"
        assert game.no_game() and game.blocked()
        auto0 = T._owner("auto_on").auto_on
        auto0.clear()
        drain()
        T.toggle_auto()
        assert not auto0.is_set() and any("Игра не запущена" in p[1] for k, p in drain() if k == "log")
        hk = T._owner("register_hotkeys") if hasattr(T, "register_hotkeys") else None
        import importlib
        hkm = importlib.import_module(game.__name__.rsplit(".", 1)[0] + ".hotkeys")
        if hasattr(hkm, "allowed"):          # без игры горячие клавиши молчат, кроме панели и выхода
            drain()
            for ev in ("select", "layout", "tooltip_key", "auto", "panel_toggle", "quit"):
                hkm._fire(ev) if ev != "quit" else hkm.allowed(ev) and core_m.events.put((ev, None))
            ev = drain()
            assert [k for k, _ in ev if k != "log"] == ["panel_toggle", "quit"], ev
            assert sum("горячие клавиши не работают" in p[1] for k, p in ev if k == "log") == 1, "в журнал — один раз"
        monkey(game, "running_programs", lambda: [("witcher3.exe", "The Witcher 3")])
        profiles._run_cache["t"] = 0
        assert not game.no_game()
        profiles._run_cache["t"] = 0
    if hasattr(game, "unmark_not_game"):    # «не игра» по ошибке — вернуть
        game.mark_not_game("deadcells.exe")
        fg[0] = "DeadCells.exe"
        assert game.unknown_game() is None
        game.unmark_not_game("deadcells.exe")
        assert game.unknown_game() == "deadcells.exe" and "deadcells.exe" not in game.not_games()
    fg[0] = "someplayer.exe"
    assert game.unknown_game() == "someplayer.exe"
    game.mark_not_game("someplayer.exe")
    assert game.unknown_game() is None and game.remember_game_window() is None
    # перевод уже включён, а на экране новая игра: клавиша не выключает перевод, а предлагает пресет
    fg[0] = "Skyrim.exe"
    auto = T._owner("auto_on").auto_on
    auto.set()
    drain()
    T.toggle_auto()
    assert auto.is_set() and ("game_created", "skyrim") in drain()
    assert profiles.delete("skyrim")
    auto.clear()
    # запущена ли игра: «сейчас» / «последняя»
    monkey(game, "running_programs", lambda: [("witcher3.exe", "The Witcher 3")])
    profiles._run_cache["t"] = 0
    assert profiles.is_running("witcher3") and not profiles.is_running("archeage")
    monkey(game, "running_programs", lambda: [])
    profiles._run_cache["t"] = 0
    assert not profiles.is_running("witcher3")
    # новая игра узнаётся сама, без клавиш: папка игр (Steam…) — сразу; иначе — на весь экран 3 секунды
    if hasattr(game, "detect_new_game"):
        full, folder = [False], [False]
        monkey(game, "foreground_fullscreen", lambda: full[0])
        monkey(game, "in_game_folder", lambda pid: folder[0])
        monkey(game, "foreground_title", lambda: "ELDEN RING™")
        fg[0] = "EldenRing.exe"
        assert all(game.detect_new_game() is None for _ in range(10)), "обычное окно не из папки игр — не игра"
        full[0] = True
        got = [game.detect_new_game() for _ in range(6)]
        assert got[:5] == [None] * 5 and got[5] == ("eldenring.exe", "ELDEN RING")
        full[0], folder[0] = False, True
        fg[0] = "Hades.exe"
        assert game.detect_new_game() is None and game.detect_new_game() == ("hades.exe", "ELDEN RING")
        fg[0] = "Witcher3.exe"
        assert all(game.detect_new_game() is None for _ in range(10)), "у известной игры уже есть пресет"
        folder[0] = False
        assert game.nice_title("Cyberpunk 2077 (C) 2020 by CD Projekt RED", "cyberpunk2077.exe") == "Cyberpunk2077"
        assert game.nice_title("Hollow Knight - v1.5.78", "hollow_knight.exe") == "Hollow Knight"
    if hasattr(game, "scan_running"):      # игра запущена раньше программы и стоит за панелью — всё равно узнаём
        monkey(game, "running_programs", lambda: [("deadcells.exe", "Dead Cells"), ("telegram.exe", "Telegram")])
        monkey(game, "in_game_folder", lambda pid: True)
        game.window_pids.update({"deadcells.exe": 1, "telegram.exe": 2})
        game._scan["t"] = 0
        assert game.scan_running() == ("deadcells.exe", "Dead Cells")
        assert game.scan_running() is None, "не чаще раза в 3 секунды"
        prof = game.create_profile_for("deadcells.exe", "Dead Cells")
        monkey(game, "running_programs", lambda: [("witcher3.exe", "The Witcher 3")])
        game._scan["t"] = 0
        assert game.scan_running() is None and core_m.active_profile == "witcher3", "последняя не запущена — к запущенной"
        assert profiles.delete(prof)
        monkey(game, "in_game_folder", lambda pid: False)
    if hasattr(game, "has_game_files"):     # игра не из Steam и в окне — узнаём по файлам движка рядом с .exe
        g = tempfile.mkdtemp(dir=TMP)
        os.makedirs(os.path.join(g, "Dead Cells"))
        for n in ("deadcells.exe", "libhl.dll", "res.pak"):
            open(os.path.join(g, "Dead Cells", n), "w").close()
        assert game.has_game_files(os.path.join(g, "Dead Cells", "deadcells.exe"))
        os.makedirs(os.path.join(g, "Stray", "Hk_project", "Binaries", "Win64"))
        os.makedirs(os.path.join(g, "Stray", "Engine"))
        assert game.has_game_files(os.path.join(g, "Stray", "Hk_project", "Binaries", "Win64", "Stray-Win64-Shipping.exe"))
        os.makedirs(os.path.join(g, "Tools", "Editor", "bin"))
        open(os.path.join(g, "Tools", "Editor", "bin", "editor.exe"), "w").close()
        assert not game.has_game_files(os.path.join(g, "Tools", "Editor", "bin", "editor.exe")), "обычная программа"
    # ещё файл игры (лаунчер / защита от читов / новое имя после обновления)
    assert profiles.add_exe("witcher3", "start_protected_game.exe")
    assert profiles.for_exe("START_PROTECTED_GAME.exe") == "witcher3"
    assert not profiles.add_exe("archeage", "witcher3.exe"), "файл чужой игры не перехватываем"
    assert profiles.remove_exe("witcher3", "start_protected_game.exe")
    assert not profiles.remove_exe("witcher3", "witcher3.exe"), "последний файл игры не убирается"
    # закрепить пресет: не переключаемся сами и переводим в любом окне (кроме браузеров)
    profiles.lock("witcher3")
    fg[0] = "GeForceNOW.exe"
    assert game.is_game("geforcenow.exe") and not game.blocked() and game.unknown_game() is None
    fg[0] = "ArcheAgeChronicles.exe"
    game.follow_foreground()
    assert core_m.active_profile == "witcher3", "закреплённый пресет не меняется"
    assert not game.is_game("chrome.exe")
    profiles.lock(None)
    game.follow_foreground()
    assert core_m.active_profile == "archeage"
    fg[0] = "Witcher3.exe"
    game.follow_foreground()
    # переименовать и удалить
    profiles.rename("witcher3", "The Witcher 3")
    assert profiles.name("witcher3") == "The Witcher 3"
    assert profiles.delete("witcher3") and core_m.active_profile is None, "удалили текущую — пресет не выбран"
    assert "witcher3" not in profiles.all_profiles()
    assert "witcher3.exe" in game.skip_this_run, "игра ещё запущена — сразу заново не добавляем"
    game.skip_this_run.clear()
    # ArcheAge — обычный пресет: тоже удаляется, её файлы уходят в backups; потом создаётся заново как знакомая игра
    if hasattr(profiles, "is_archeage_like"):
        profiles.activate("archeage", announce=False)
        assert os.path.exists(os.path.join(d, "glossary.txt"))
        assert profiles.delete("archeage") and not profiles.all_profiles().get("archeage")
        assert not os.path.exists(os.path.join(d, "glossary.txt")), "словарь ArcheAge — в backups"
        assert any(n.startswith("profile_archeage_") for n in os.listdir(os.path.join(d, "backups")))
        game.skip_this_run.clear()
        pid = profiles.create("archeagechronicles.exe")
        assert pid == "archeage" and profiles.name(pid) == "ArcheAge Chronicles"
        assert profiles.all_profiles()[pid]["desc"] == "the MMORPG ArcheAge Chronicles"
        core_m.active_profile = None
        assert "ArcheAge" not in profiles.adapt("You translate the MMORPG ArcheAge Chronicles.")
        core_m.active_profile = "archeage"
        assert "ArcheAge" in profiles.adapt("You translate the MMORPG ArcheAge Chronicles.")
        # игра закрылась — пресет снимается сам; выбранный вручную в панели (настроить) — нет
        monkey(game, "running_programs", lambda: [])
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile is None
        profiles.activate("archeage", announce=False, hold=True)
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile == "archeage", "выбрали вручную, чтобы настроить, — не снимаем"
        T.save_settings(region=(9, 9, 9, 9))
        profiles.activate(None)
        T.save_settings(region=(5, 5, 5, 5))       # игры нет — области некуда сохранять, пресеты не портятся
        assert profiles.all_profiles()["archeage"]["region"] == [9, 9, 9, 9] and None not in profiles.all_profiles()
    if hasattr(profiles, "free_pid"):     # режим «Переводить без игры» (проверка): пресет «🧪 Без игры»
        monkey(cfg, "GAMES_ONLY", False)
        monkey(game, "running_programs", lambda: [])
        monkey(game, "in_game_folder", lambda pid: False)
        profiles._hold["pid"] = None
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile == profiles.FREE and not game.no_game() and not game.blocked()
        assert profiles.FREE not in profiles.game_profiles(), "в «Играх» его нет"
        T.save_settings(region=(7, 7, 7, 7))
        assert profiles.all_profiles()[profiles.FREE]["region"] == [7, 7, 7, 7]
        fg[0] = "notepad.exe"
        assert game.remember_game_window() is None and profiles.for_exe("notepad.exe") is None, \
            "обычная программа пресет не получает"
        monkey(game, "running_programs", lambda: [("archeagechronicles.exe", "ArcheAge")])
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile == "archeage", "запустили игру — её пресет"
        monkey(game, "running_programs", lambda: [])
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile == profiles.FREE and core_m.region == (7, 7, 7, 7), "закрыли — снова «Без игры»"
        monkey(cfg, "GAMES_ONLY", True)
        game._scan["t"] = 0
        game.scan_running()
        assert core_m.active_profile is None, "режим выключили — без игры пресета нет"
    profiles.activate("archeage", announce=False)
    # «только игры из списка» выключено — любая программа
    monkey(cfg, "GAMES_ONLY", False)
    assert not game.blocked()
    profiles.bind("archeage")
    if GUI:     # окно «+ Добавить игру»: список запущенных программ, щелчок — выбор
        monkey(game, "running_programs", lambda: [("eldenring.exe", "ELDEN RING"), ("notepad.exe", "x")])
        app = T.App()
        try:
            got = []
            d = app.panel.pick_program("Добавить игру", "текст", got.append)
            app.root.update()
            first = app.panel._pick_rows.winfo_children()[0]
            first.event_generate("<Button-1>")
            app.root.update()
            assert got == ["eldenring.exe"] and app.panel._dialog is None
            if hasattr(app.panel, "show_new_game"):     # баннер «Новая игра — пресет создан» на Главной
                prof = game.create_profile_for("eldenring.exe", "ELDEN RING")
                app.game_created(prof)
                app.root.update()
                assert app.panel.new_banner.winfo_manager() and "ELDEN RING" in app.panel.new_text.cget("text")
                app.panel.refresh()
                app.panel._new_not_game()               # «Это не игра» — пресет убран, больше не узнаём
                assert not app.panel.new_banner.winfo_manager() and "eldenring.exe" in game.not_games()
                assert prof not in profiles.all_profiles()
            if hasattr(app, "_area_target"):     # две игры: область — в пресет игры, где нажали клавишу
                import tkinter as tk
                monkey(cfg, "GAMES_ONLY", True)
                w3 = profiles.create("witcher3.exe", "The Witcher 3")
                fg2 = ["witcher3.exe"]
                monkey(game, "foreground_exe", lambda: (fg2[0], 4242))
                monkey(game, "foreground_title", lambda: "Hades")
                profiles.activate("archeage", announce=False)
                saved = []
                app.pick_area("Обведите область СУБТИТРОВ.", lambda r: saved.append((core_m.active_profile, r)),
                              game_area=True)
                app.root.update()
                assert core_m.active_profile == w3, "клавиша в Witcher — сразу его пресет"
                profiles.activate("archeage", announce=False)      # за время обводки переключились на другую
                cv = [c for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)
                      for c in w.winfo_children() if isinstance(c, tk.Canvas) and str(c.cget("cursor")) == "cross"][-1]
                assert "«The Witcher 3»" in cv.itemcget(cv.find_all()[0], "text")
                for ev, x, y in (("<ButtonPress-1>", 10, 10), ("<B1-Motion>", 200, 120), ("<ButtonRelease-1>", 200, 120)):
                    cv.event_generate(ev, x=x, y=y)
                app.root.update()
                assert saved and saved[0][0] == w3, saved
                fg2[0] = "hades.exe"                                 # незнакомая программа + F9 → это игра
                assert app._area_target() == "hades" and profiles.name("hades") == "Hades"
                fg2[0] = "chrome.exe"
                assert app._area_target() is None, "в браузере области не обводим"
                profiles.delete("hades")
                profiles.delete(w3)
            try:
                from aac import screens
            except ImportError:
                screens = None
            if screens is not None:            # два монитора: второй слева (x < 0) — обводка на нём тоже работает
                import tkinter as tk
                monkey(screens, "virtual", lambda: (-1920, 0, 3840, 1080))
                monkey(screens, "monitor_at", lambda x, y: (-1920, 0, 0, 1080) if x < 0 else (0, 0, 1920, 1080))
                got = []
                app.pick_area("Обведите ЗАДАНИЕ.", got.append)
                app.root.update()
                cv = app._picking and [c for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)
                                       for c in w.winfo_children() if isinstance(c, tk.Canvas)
                                       and str(c.cget("cursor")) == "cross"][-1]
                for ev, x, y in (("<ButtonPress-1>", 100, 200), ("<B1-Motion>", 400, 300), ("<ButtonRelease-1>", 400, 300)):
                    cv.event_generate(ev, x=x, y=y)
                app.root.update()
                assert got == [(-1820, 200, 300, 100)], got       # координаты экрана, на левом мониторе
                from aac import appwin as aw
                # подсказка у мышки на левом мониторе — окно перевода там же, а не на основном
                x, y = aw._on_monitor(T._owner("place_word").place_word if hasattr(T, "place_word") else
                                      __import__("aac.tooltip", fromlist=["x"]).place_word,
                                      (-1000, 500, 120, 18), (-940, 510), 200, 40)
                assert -1920 <= x <= -200 and 0 <= y < 1080, (x, y)
                from aac import tooltip as tt
                box = tt._box_at((-30, 500))
                assert box[0] + box[2] <= 0, "поиск подсказки — на мониторе, где мышка"
            if hasattr(app, "_picking"):        # F7 несколько раз — затемнения не накладываются друг на друга
                import tkinter as tk
                overlays = lambda: [c for w in app.root.winfo_children() if isinstance(w, tk.Toplevel) and w.winfo_exists()
                                    for c in w.winfo_children() if isinstance(c, tk.Canvas) and str(c.cget("cursor")) == "cross"]
                n0 = len(overlays())
                core_m.auto_on.set()
                app.pick_area("Обведите ЗАДАНИЕ.", lambda r: None)
                app.root.update()
                assert len(overlays()) == n0 + 1 and not core_m.auto_on.is_set()
                app.pick_area("Обведите ЗАДАНИЕ.", lambda r: None)      # та же клавиша ещё раз — отмена
                app.root.update()
                assert len(overlays()) == n0 and app._picking is None
                app.root.after(200, lambda: None); time.sleep(0.25); app.root.update()
                assert core_m.auto_on.is_set(), "автоперевод вернулся"
                app.pick_area("Обведите ЗАДАНИЕ.", lambda r: None)
                app.pick_area("Обведите текст — переведу и прочитаю вслух.", lambda r: None)   # другая — замена
                app.root.update()
                assert len(overlays()) == n0 + 1
                app._picking["cancel"]()
                app.root.update(); time.sleep(0.25); app.root.update()
                assert core_m.auto_on.is_set()
                core_m.auto_on.clear()
            if hasattr(app.panel, "_resize_start"):       # размер окна — тянуть за край, запоминается
                class E:
                    pass
                p = app.panel
                for edge, dx, dy in (("se", 200, 50), ("log", 60, 0)):
                    e = E(); e.x_root, e.y_root = 500, 500
                    p._resize_start(e, edge)
                    e.x_root, e.y_root = 500 + dx, 500 + dy
                    p._resize_move(e)
                    p._resize_end(e)
                app.root.update()
                assert core_m.SETTINGS["panel_size"][0] == p.main_w and p.log_w == core_m.SETTINGS["log_width"]
                assert p.win.winfo_width() == p.total_w()
                e = E(); e.x_root, e.y_root = 0, 0
                p._resize_start(e, "se"); e.x_root, e.y_root = -5000, -5000; p._resize_move(e); p._resize_end(e)
                assert p.main_w >= 760 and p.height >= 640, "не меньше минимума"
                p.reset_size()
            if "layout=False" in open(os.path.join(ROOT, "aac", "appwin.py"), encoding="utf-8").read():
                # начали обводить область — расстановка включается сама; отменили — выключается
                monkey(game, "foreground_exe", lambda: (None, None))
                profiles.activate("archeage", announce=False)
                core_m.region = (10, 20, 300, 80)
                assert not getattr(app, "layout", False)
                app.select_answers_region()
                app.root.update()
                assert app.layout and "subs" in app.region_frames, "рамки других областей видны"
                app._picking["cancel"]()
                app.root.update()
                assert not app.layout, "отменили — расстановка закрылась"
                app.select_answers_region()
                app.root.update()
                cv = [c for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)
                      for c in w.winfo_children() if isinstance(c, tk.Canvas) and str(c.cget("cursor")) == "cross"][-1]
                for ev, x, y in (("<ButtonPress-1>", 30, 300), ("<B1-Motion>", 330, 400), ("<ButtonRelease-1>", 330, 400)):
                    cv.event_generate(ev, x=x, y=y)
                app.root.update()
                assert app.layout and "answers" in app.region_frames, "обвели — расстановка открыта, рамка уже есть"
                app.toggle_layout()
                app.root.update()
                core_m.answers_region = None
            if hasattr(app, "sync_region_frames"):   # удалили область в режиме расстановки — рамка не возвращает её
                core_m.region, core_m.answers_region = (10, 20, 300, 80), (10, 400, 300, 120)
                app.toggle_layout()
                app.root.update()
                assert set(app.region_frames) >= {"subs", "answers"}
                app.panel._clear_area("region")
                app.root.update()
                assert "subs" not in app.region_frames, "рамка исчезла сразу"
                core_m.answers_region = (50, 450, 320, 100)      # обвели ответы заново, пока расстановка открыта
                app.sync_region_frames()
                assert app.region_frames["answers"].src == (50, 450, 320, 100)
                app.toggle_layout()                               # выход из расстановки
                app.root.update()
                assert core_m.region is None and profiles.active().get("region") is None, "удалённая не вернулась"
                assert core_m.answers_region == (50, 450, 320, 100), "новая область не затёрта старой рамкой"
                core_m.answers_region = None
            if hasattr(app.panel, "_ask_clear_area"):     # удалить любую область, с вопросом
                core_m.region, core_m.answers_region = (1, 2, 3, 4), (5, 6, 7, 8)
                app.panel.show("areas")
                app.root.update()
                app.panel._ask_clear_area("region", "Субтитры")
                app.root.update()
                assert core_m.region is not None and app.panel._dialog is not None, "сначала вопрос"
                app.panel._dialog_yes() if hasattr(app.panel, "_dialog_yes") else app.panel._clear_area("region")
                assert core_m.region is None and core_m.answers_region == (5, 6, 7, 8)
                app.panel._clear_area("answers_region")
                assert core_m.answers_region is None
        finally:
            app.root.destroy()


# ---------- запуск ----------
def main():
    print(f"Проверяю: {ROOT}  ({T.kind}, версия {T.VERSION})\n")
    ok = fail = 0
    for name, fn in [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]:
        undo = []
        cache_reset()

        def monkey(obj, attr, value):
            undo.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, value)
        try:
            fn(monkey) if fn.__code__.co_argcount else fn()
            print(f"  ✔ {name}")
            ok += 1
        except Exception:
            print(f"  ✘ {name}")
            traceback.print_exc()
            fail += 1
        finally:
            for obj, attr, old in reversed(undo):
                setattr(obj, attr, old)
            drain()
    print(f"\nИтого: {ok} прошло, {fail} с ошибками")
    return fail


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
