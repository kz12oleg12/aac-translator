"""Пауза, пока открыто меню игры (Esc и т.п.).

Один раз «запоминаем» меню: открываете меню игры, жмёте клавишу «запомнить меню игры» и обводите кусочек,
который всегда одинаковый, когда меню открыто (например, заголовок или кнопки меню). Дальше программа
дважды в секунду сравнивает это место экрана с запомненным: совпало — меню открыто, весь автоперевод на паузе
и окна перевода спрятаны; меню закрыли — всё возвращается.
"""
import os
import threading
import time

from PIL import Image, ImageChops, ImageStat

from . import capture, config, core

REF_FILE = os.path.join(config.APP_DIR, "menu_ref.png")
SIZE = (96, 48)                 # сравниваем уменьшенные серые картинки — быстро и устойчиво к мелочам
_ref = {"img": None, "loaded": False}


def _prep(img):
    return img.convert("L").resize(SIZE)


def _load_ref():
    if not _ref["loaded"]:
        _ref["loaded"] = True
        try:
            if os.path.exists(REF_FILE):
                _ref["img"] = Image.open(REF_FILE).convert("L").resize(SIZE)
        except Exception:
            _ref["img"] = None
    return _ref["img"]


def learn(reg):
    """Запомнить, как выглядит меню в области reg (меню сейчас открыто)."""
    img = _prep(capture.grab(reg))
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


def difference(img):
    """Насколько текущий вид отличается от запомненного меню (0 — один в один)."""
    ref = _load_ref()
    if ref is None:
        return 255.0
    return ImageStat.Stat(ImageChops.difference(_prep(img), ref)).mean[0]


def is_menu(img):
    return difference(img) < config.MENU_MATCH


def run():
    while True:
        try:
            if core.menu_region and core.auto_on.is_set() and _load_ref() is not None:
                shot = capture.mask_out(capture.grab(core.menu_region), core.menu_region, list(core.own_rects))
                now = is_menu(shot)
                if now != core.in_menu:
                    core.in_menu = now
                    core.events.put(("menu_state", now))
            elif core.in_menu:
                core.in_menu = False
                core.events.put(("menu_state", False))
        except Exception as e:
            print("menu:", e)
        time.sleep(0.5)


def start():
    threading.Thread(target=run, daemon=True, name="menu").start()
