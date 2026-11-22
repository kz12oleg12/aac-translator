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

REF_FILE = os.path.join(config.APP_DIR, "menu_ref.png")
MAX_W = 240                     # образец храним уменьшенным (по ширине), сравниваем в том же размере
_ref = {"img": None, "loaded": False}


def _ref_size(w, h):
    k = min(1.0, MAX_W / max(1, w))
    return max(8, int(w * k)), max(8, int(h * k))


def _prep(img, size=None):
    g = img.convert("L")
    return g.resize(size or _ref_size(*g.size))


def _load_ref():
    if not _ref["loaded"]:
        _ref["loaded"] = True
        try:
            if os.path.exists(REF_FILE):
                _ref["img"] = Image.open(REF_FILE).convert("L")
        except Exception:
            _ref["img"] = None
    return _ref["img"]


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


def learn(reg):
    """Запомнить, как выглядит меню в области reg (меню сейчас открыто)."""
    img = _prep(capture.grab(reg))
    if detail(img) < 4:
        core.log("Меню: в обведённом месте почти нет надписей и рамок — по нему меню не узнать. "
                 "Обведите строку вкладок или кнопки с текстом.", "warn")
    try:
        img.save(REF_FILE)
    except Exception as e:
        core.log(f"Меню: не удалось сохранить образец: {e}", "error")
    _ref.update(img=img, loaded=True)
    core.menu_region = tuple(reg)
    core.save_settings(menu_region=list(reg))
    core.log("Меню игры запомнено. Пока оно открыто, автоперевод на паузе и окна перевода скрыты.", "ok")


def forget():
    core.menu_region = None
    core.save_settings(menu_region=None)
    _ref.update(img=None, loaded=True)
    try:
        os.remove(REF_FILE)
    except OSError:
        pass
    if core.in_menu:
        core.in_menu = False
        core.events.put(("menu_state", False))
    core.log("Пауза в меню игры выключена")


def similarity(img):
    """(похожесть очертаний 0..1, разница яркости 0..255) текущего вида и запомненного меню."""
    ref = _load_ref()
    if ref is None:
        return 0.0, 255.0
    cur = _prep(img, ref.size)
    bright = ImageStat.Stat(ImageChops.difference(cur, ref)).mean[0]
    return _corr(_edges(cur), _edges(ref)), bright


def difference(img):   # для совместимости: 0 — один в один
    c, b = similarity(img)
    return b if c >= config.MENU_CORR else 255.0


def is_menu(img):
    c, b = similarity(img)
    return c >= config.MENU_CORR and b < config.MENU_MATCH


def run():
    streak = 0                  # меняем состояние, только если 2 проверки подряд (1 с) говорят одно и то же
    while True:
        try:
            if core.menu_region and core.auto_on.is_set() and _load_ref() is not None:
                shot = capture.mask_out(capture.grab(core.menu_region), core.menu_region, list(core.own_rects))
                now = is_menu(shot)
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
