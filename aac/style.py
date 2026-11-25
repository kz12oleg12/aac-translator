"""Вид перевода поверх игры — свой у каждой игры: шрифт, размер, цвет, «плашка» или «обводка букв»,
непрозрачность. Нет игры (или у игры свой вид не задан) — вид по умолчанию из общих настроек."""
from . import config, core

FONTS = ["Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Georgia", "Consolas", "Impact"]
COLORS = ["#eeeeee", "#ffffff", "#fff3b0", "#ffd166", "#bfe3ff", "#c8f7c5"]
MODES = [("box", "Плашка", "тёмная подложка под текстом"),
         ("outline", "Обводка букв", "без подложки, контур вокруг букв")]
DEFAULTS = {"font_family": "Segoe UI", "font_size": 13, "text_color": "#eeeeee", "text_mode": "box",
            "overlay_alpha": 0.88}
KEYS = tuple(DEFAULTS)


def _global():
    s = core.SETTINGS if isinstance(core.SETTINGS, dict) else {}
    return {k: s.get(k, DEFAULTS[k]) for k in KEYS}


def current():
    """Вид для текущей игры: её собственный поверх общего."""
    from . import profiles
    st = _global()
    st.update({k: v for k, v in (profiles.active().get("style") or {}).items() if k in KEYS})
    if st["text_mode"] not in ("box", "outline"):
        st["text_mode"] = "box"
    return st


def apply():
    """Перенести вид текущей игры в настройки окон перевода (их перерисует apply_style окон)."""
    st = current()
    size = int(st["font_size"])
    config.FONT = (st["font_family"], size)
    config.HISTORY_FONT = (st["font_family"], max(8, size - 2))
    config.OVERLAY_ALPHA = float(st["overlay_alpha"])
    config.TEXT_COLOR = st["text_color"]
    config.TEXT_MODE = st["text_mode"]
    return st


def save(**kw):
    """Сохранить вид: в пресет текущей игры (или общий, если игры нет) — и сразу применить."""
    from . import profiles
    kw = {k: v for k, v in kw.items() if k in KEYS}
    pid = core.active_profile
    profs = profiles.all_profiles()
    if pid and pid in profs:
        profs[pid].setdefault("style", {}).update(kw)
        core.save_settings(profiles=profs)
    else:
        core.save_settings(**kw)
    return apply()


def save_default(**kw):
    """Вид для новых игр (и когда игра не выбрана): общие настройки. Свой вид игр не трогается."""
    kw = {k: v for k, v in kw.items() if k in KEYS}
    core.save_settings(**kw)
    if isinstance(core.SETTINGS, dict):
        core.SETTINGS.update(kw)
    return apply()


def default():
    return _global()


def owner():
    """Для подписи в панели: чей вид сейчас настраиваете."""
    from . import profiles
    return profiles.name() if core.active_profile else None
