"""Пауза, пока открыто меню игры (Esc и т.п.).

Один раз «запоминаем» меню: открываете меню игры, жмёте клавишу «запомнить меню игры» и обводите кусочек,
который всегда одинаковый, когда меню открыто (например, заголовок или кнопки меню). Дальше программа
дважды в секунду сравнивает это место экрана с запомненным: совпало — меню открыто, весь автоперевод на паузе
и окна перевода спрятаны; меню закрыли — всё возвращается.
"""
import math
import os
import threading
import time

from PIL import Image, ImageChops, ImageFilter, ImageStat

from . import capture, config, core

REF_FILE = os.path.join(config.APP_DIR, "menu_ref.png")   # указывает на папку пресета (меняет profiles.bind)
MAX_W = 240                     # образец храним уменьшенным (по ширине), сравниваем в том же размере
_ref = {"img": None, "loaded": False, "screens": []}     # screens: [{"id","name","region","img"}]
replace_next = {"id": None}     # «Заменить» в панели: следующее запоминание заменит этот экран


def _dir():
    return os.path.dirname(REF_FILE)


def _list_file():
    return os.path.join(_dir(), "screens.json")


def _img_file(sid):
    return os.path.join(_dir(), f"screen_{sid}.png")


def preview_file(sid):
    return os.path.join(_dir(), f"screen_{sid}_view.jpg")


def _ref_size(w, h):
    k = min(1.0, MAX_W / max(1, w))
    return max(8, int(w * k)), max(8, int(h * k))


def _prep(img, size=None):
    g = img.convert("L")
    return g.resize(size or _ref_size(*g.size))


def screens():
    """Запомненные экраны текущей игры (загружаются один раз; старое «одно меню» переносится сюда само)."""
    import json
    if _ref["loaded"]:
        return _ref["screens"]
    _ref["loaded"] = True
    out = []
    try:
        if os.path.exists(_list_file()):
            with open(_list_file(), encoding="utf-8") as f:
                out = json.load(f)
        elif core.menu_region and os.path.exists(REF_FILE):      # было одно «меню» — делаем его первым экраном
            out = [{"id": "m1", "name": "Меню", "region": list(core.menu_region)}]
            Image.open(REF_FILE).save(_img_file("m1"))
            _save_list(out)
    except Exception as e:
        print("screens:", e)
        out = []
    for sc in out:
        try:
            sc["img"] = Image.open(_img_file(sc["id"])).convert("L")
        except Exception:
            sc["img"] = None
    _ref["screens"] = [sc for sc in out if sc.get("img") is not None and sc.get("region")]
    _ref["img"] = _ref["screens"][0]["img"] if _ref["screens"] else None
    return _ref["screens"]


def _save_list(items):
    import json
    os.makedirs(_dir(), exist_ok=True)
    with open(_list_file(), "w", encoding="utf-8") as f:
        json.dump([{"id": x["id"], "name": x["name"], "region": list(x["region"])} for x in items], f,
                  ensure_ascii=False, indent=1)


def _sync_core():
    """core.menu_region — «есть ли хоть один экран» для старых частей программы."""
    sc = _ref["screens"]
    core.menu_region = tuple(sc[0]["region"]) if sc else None
    core.save_settings(menu_region=list(core.menu_region) if core.menu_region else None)


def _load_ref():
    sc = screens()
    return sc[0]["img"] if sc else None


def _edges(g):
    """Очертания (буквы, рамки, кнопки) — по ним меню отличается от тёмной сцены той же яркости."""
    return g.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1))


def _corr(a, b):
    """Похожесть рисунка очертаний: 1 — одинаковые, около 0 — ничего общего."""
    x, y = list(a.getdata()), list(b.getdata())
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sxx = syy = 0.0
    for p, q in zip(x, y):
        dp, dq = p - mx, q - my
        sxy += dp * dq
        sxx += dp * dp
        syy += dq * dq
    if sxx < 1e-6 or syy < 1e-6:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def detail(img):
    """Сколько в картинке очертаний (мало — однотонный кусок, по нему меню не узнать)."""
    return ImageStat.Stat(_edges(img.convert("L"))).stddev[0]


def learn(reg, sid=None):
    """Запомнить экран, где переводить не нужно, по области reg (экран сейчас открыт).
    sid — заменить этот экран; иначе добавить новый."""
    sid = sid or replace_next["id"]
    replace_next["id"] = None
    full = capture.grab(None)
    img = _prep(capture.grab(reg))
    if detail(img) < 4:
        core.log("Экран: в обведённом месте почти нет надписей и рамок — по нему экран не узнать. "
                 "Обведите строку вкладок или кнопки с текстом.", "warn")
    items = list(screens())
    old = next((x for x in items if x["id"] == sid), None)
    if old is None:
        n = 1
        while any(x["id"] == f"s{n}" for x in items):
            n += 1
        sid = f"s{n}"
        old = {"id": sid, "name": "Меню" if not items else f"Экран {len(items) + 1}"}
        items.append(old)
    old.update(region=list(reg), img=img)
    try:
        img.save(_img_file(sid))
        view = full.convert("RGB")
        view.thumbnail((320, 180))
        view.save(preview_file(sid), quality=82)
        _save_list(items)
    except Exception as e:
        core.log(f"Экран: не удалось сохранить образец: {e}", "error")
    _ref["screens"] = items
    _ref["img"] = items[0]["img"]
    _sync_core()
    core.log(f"Экран «{old['name']}» запомнен. Пока он на экране, автоперевод на паузе и окна перевода скрыты. "
             f"Всего экранов: {len(items)}.", "ok")
    core.events.put(("panel", None))


def rename(sid, name):
    items = screens()
    for x in items:
        if x["id"] == sid and name.strip():
            x["name"] = name.strip()[:40]
    _save_list(items)


def forget(sid=None):
    """Забыть экран sid (без sid — все)."""
    items = screens()
    gone = [x for x in items if sid is None or x["id"] == sid]
    for x in gone:
        for f in (_img_file(x["id"]), preview_file(x["id"])):
            try:
                os.remove(f)
            except OSError:
                pass
    items = [x for x in items if x not in gone]
    _ref["screens"] = items
    _ref["img"] = items[0]["img"] if items else None
    try:
        _save_list(items)
        if sid is None and os.path.exists(REF_FILE):
            os.remove(REF_FILE)
    except OSError:
        pass
    _sync_core()
    if core.in_menu and not items:
        core.in_menu = False
        core.events.put(("menu_state", False))
    core.log("Экран забыт" if sid else "Пауза на экранах игры выключена")


def _match(img, ref):
    cur = _prep(img, ref.size)
    bright = ImageStat.Stat(ImageChops.difference(cur, ref)).mean[0]
    return _corr(_edges(cur), _edges(ref)), bright


def similarity(img):
    """(похожесть очертаний 0..1, разница яркости 0..255) с первым запомненным экраном."""
    ref = _load_ref()
    if ref is None:
        return 0.0, 255.0
    return _match(img, ref)


def difference(img):   # для совместимости: 0 — один в один
    c, b = similarity(img)
    return b if c >= config.MENU_CORR else 255.0


def is_menu(img, ref=None):
    ref = ref or _load_ref()
    if ref is None:
        return False
    c, b = _match(img, ref)
    return c >= config.MENU_CORR and b < config.MENU_MATCH


def any_screen():
    """Открыт ли сейчас хоть один из запомненных экранов."""
    for sc in screens():
        reg = tuple(sc["region"])
        shot = capture.mask_out(capture.grab(reg), reg, list(core.own_rects))
        if is_menu(shot, sc["img"]):
            return True
    return False


def run():
    streak = 0                  # меняем состояние, только если 2 проверки подряд (1 с) говорят одно и то же
    while True:
        try:
            if core.auto_on.is_set() and screens():
                now = any_screen()
                streak = streak + 1 if now != core.in_menu else 0
                if streak >= 2:
                    streak = 0
                    core.in_menu = now
                    core.events.put(("menu_state", now))
            else:
                streak = 0
                if core.in_menu:
                    core.in_menu = False
                    core.events.put(("menu_state", False))
        except Exception as e:
            print("menu:", e)
        time.sleep(0.5)


def start():
    threading.Thread(target=run, daemon=True, name="menu").start()
