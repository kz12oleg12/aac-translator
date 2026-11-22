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
T.set("GLOSSARY_FILE", os.path.join(TMP, "glossary.txt"))
T.set("HISTORY_DIR", os.path.join(TMP, "history"))
try:   # голоса персонажей — тоже во временную папку, и по умолчанию выключены (включает их свой тест)
    from aac import voices as _voices
    _voices.FILE = os.path.join(TMP, "characters.json")
    T._owner("TTS_READ_NAME").TTS_PER_CHARACTER = False
except ImportError:
    pass
T.set("SETTINGS", {})


class R:
    """Имитация ответа requests."""
    def __init__(self, code, js=None, text="", headers=None):
        self.status_code, self._js, self.text, self.headers = code, js, text, headers or {}

    def json(self):
        if self._js is None:
            raise ValueError("no json")
        return self._js


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
    T._mt_cache.clear()
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
    T._ai_cache.clear()
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
    assert len(kb.registered) == sum(1 for d in T.HOTKEY_DEFS if not str(T.hotkeys[d[0]]).startswith("mouse_"))
    t = threading.Thread(target=T.capture_hotkey, args=("once",))
    t.start()
    time.sleep(0.2)
    E = lambda typ, name: types.SimpleNamespace(event_type=typ, name=name)  # noqa: E731
    kb.hooks[-1](E("down", "ctrl"))
    kb.hooks[-1](E("down", "g"))
    kb.hooks[-1](E("up", "g"))
    t.join(3)
    assert T.hotkeys["once"] == "ctrl+g" and T.K("once") == "Ctrl+G"
    assert len(kb.registered) == sum(1 for d in T.HOTKEY_DEFS if not str(T.hotkeys[d[0]]).startswith("mouse_"))
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
    code = ("import sys,types\nfor m in ('keyboard','tkinter'): sys.modules[m]=types.ModuleType(m)\n"
            f"sys.path.insert(0,{ROOT!r})\n")
    code += ("from aac import main as a\n" if T.kind == "package" else "import aac_translator as a\n")
    code += "print(a.single_instance())"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.stdout.strip().endswith("False"), r.stdout + r.stderr
    time.sleep(0.3)
    assert any(k == "second_copy" for k, _ in drain())


def test_settings_roundtrip():
    T.save_settings(region=(1, 2, 3, 4), font_size=17)
    data = json.load(open(T.SETTINGS_FILE, encoding="utf-8"))
    assert data["region"] == [1, 2, 3, 4] and data["font_size"] == 17
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
            app.show_tooltip({"text": ("Клинок\nМеч", "Blade\nSword"), "pos": (700, 400), "box": (720, 380, 200, 120)})
            done["tip"] = app.tip.visible and app.tip._pos()[2] == 720 - 12 - app.tip.width
            app.tip.hide()
            from aac import ui_windows
            ui_windows.CharactersWindow(app)
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
        T.events.put(("quit", None))

    app.root.after(300, step)
    app.root.mainloop()
    done.pop("tip", True) or (_ for _ in ()).throw(AssertionError("окно подсказки встало не туда"))
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
        T.events.put(("quit", None))

    app.root.after(300, step)
    app.root.mainloop()
    assert res == {"anchor2": True, "kept": True, "hidden": True}, res


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
    assert info["asset_url"] == "https://api.github.com/repos/user/aac-translator/zipball/main"
    assert [p for k, p in drain() if k == "update_available"][0]["version"] == "4.6"
    # закрытый репозиторий: токен в заголовке
    monkey(updater.os, "environ", {"GITHUB_TOKEN": "tok"})
    calls.clear()
    updater.check()
    assert calls[0][1]["Authorization"] == "Bearer tok"
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
    monkey(tts, "neural_available", lambda: True)
    synth, played, win = [], [], []

    async def fake_synth(text, path, voice, rate, pitch="+0Hz"):
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
        sil.synth_to_wav("123 !!!", path, "xenia")
        assert False, "без букв — нечего читать"
    except ValueError:
        pass
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
    # весь путь: снимок → OCR с рамками → перевод вырезанного блока
    shots, crops = [], []
    from PIL import Image
    monkey(tooltip.capture, "grab", lambda reg: shots.append(reg) or Image.new("RGB", (reg[2], reg[3])))
    monkey(tooltip, "screen_size", lambda: (1920, 1080))
    monkey(tooltip.ocr, "ocr_boxes", lambda img: [(t, (b[0] - 0, b[1], b[2], b[3])) for t, b in lines])

    def fake_tr(img, prompt=None):
        crops.append((img.size, prompt))
        return "Клинок рассвета (Dawn Blade)\nДвуручный меч", None
    monkey(tooltip.translate, "safe_translate", fake_tr)
    drain()
    tooltip.translate_at_cursor((1000, 700))
    ev = [p for k, p in drain() if k == "tooltip_show"]
    assert shots == [(450, 180, 1100, 900)], shots
    assert crops and crops[0][1].startswith("Screenshot of a tooltip"), crops
    # курсор (1000,700) → в снимке (550,520): ближе всех блок предмета; вырезан он с полями 10 px
    assert crops[0][0] == (180, 98), crops
    assert ev[0]["text"].startswith("⏳") and ev[-1]["box"] == (450 + 510, 180 + 290, 180, 98), ev
    assert ev[-1]["text"][0].startswith("Клинок рассвета")


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


# ---------- запуск ----------
def main():
    print(f"Проверяю: {ROOT}  ({T.kind}, версия {T.VERSION})\n")
    ok = fail = 0
    for name, fn in [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]:
        undo = []

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
