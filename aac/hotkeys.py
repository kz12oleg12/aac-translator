"""Горячие клавиши и кнопки мыши: назначение, переназначение, перехват."""


import threading


import keyboard


from . import config, core


# ---------- горячие клавиши (переназначаются кнопками «изменить» в системной панели) ----------
HOTKEY_DEFS = [  # (id, что делает, клавиша по умолчанию, событие)
    ("once", "перевести задание", config.HOTKEY_ONCE, "once"),
    ("subs_once", "перевести субтитры", config.HOTKEY_SUBS_ONCE, "subs_once"),
    ("answers_once", "перевести ответы", config.HOTKEY_ANSWERS_ONCE, "answers_once"),
    ("once_tts", "обвести и озвучить", config.HOTKEY_ONCE_TTS, "once_tts"),
    ("tooltip", "подсказка у мыши", config.HOTKEY_TOOLTIP, "tooltip_key"),
    ("auto", "автоперевод вкл/выкл", config.HOTKEY_AUTO, "auto"),
    ("select", "область субтитров", config.HOTKEY_SELECT, "select"),
    ("select_answers", "область ответов", config.HOTKEY_SELECT_ANSWERS, "select_answers"),
    ("select_subs2", "область реплик 2", config.HOTKEY_SELECT_SUBS2, "select_subs2"),
    ("toggle", "скрыть/показать переводы", config.HOTKEY_TOGGLE, "toggle"),
    ("layout", "окна и области", config.HOTKEY_LAYOUT, "layout"),
    ("reset", "окна на место", config.HOTKEY_RESET, "reset"),
    ("panel", "скрыть эту панель", config.HOTKEY_PANEL, "panel_toggle"),
    ("tts", "озвучка вкл/выкл", config.HOTKEY_TTS, "tts_toggle"),
    ("flip_gender", "сменить пол говорящего", config.HOTKEY_FLIP_GENDER, "flip_gender"),
    ("select_chat", "область чата", config.HOTKEY_SELECT_CHAT, "select_chat"),
    ("chat_once", "перевести чат", config.HOTKEY_CHAT_ONCE, "chat_once"),
    ("chat_compose", "написать в чат (рус→англ)", config.HOTKEY_CHAT_COMPOSE, "chat_compose"),
    ("quit", "выход", config.HOTKEY_QUIT, "quit"),
]
hotkeys = {hid: default for hid, _, default, _ in HOTKEY_DEFS}  # текущие назначения
_hotkey_handles = []
capturing = None  # id клавиши, которую сейчас переназначают


MOUSE_NAMES = {  # кнопки мыши, которые можно назначать (левую и правую нельзя — ими играют)
    "mouse_x1": "Мышь назад",     # нижняя боковая кнопка
    "mouse_x2": "Мышь вперёд",    # верхняя боковая кнопка
    "mouse_middle": "Колесо мыши",
}
mouse_bindings = {}   # "mouse_x1" -> событие
mouse_capture = None  # функция, которая ловит нажатие мыши при переназначении


MODIFIERS = ("ctrl", "shift", "alt")


def is_mouse(combo):
    """Сочетание с кнопкой мыши: «mouse_x1», «ctrl+mouse_x1»…"""
    return bool(combo) and combo.split("+")[-1] in MOUSE_NAMES


def held_modifiers():
    """Какие из Ctrl/Shift/Alt сейчас зажаты (для сочетаний «Ctrl + кнопка мыши»)."""
    out = []
    for m in MODIFIERS:
        try:
            if keyboard.is_pressed(m):
                out.append(m)
        except Exception:
            pass
    return out


def pretty(combo):
    """shift+f9 -> Shift+F9, ctrl+mouse_x1 -> Ctrl+Мышь назад."""
    parts = (combo or "?").split("+")
    return "+".join(MOUSE_NAMES.get(p) or (p.upper() if (p[:1] == "f" and p[1:].isdigit()) or len(p) == 1
                                           else p.capitalize()) for p in parts)


def K(hid):
    """Красивое имя сочетания для подсказок: shift+f9 -> Shift+F9, mouse_x1 -> Мышь назад."""
    combo = hotkeys.get(hid, "?")
    if is_mouse(combo):
        return pretty(combo)
    parts = combo.split("+")
    return "+".join(p.upper() if (p[:1] == "f" and p[1:].isdigit()) or len(p) == 1 else p.capitalize()
                    for p in parts)


def load_hotkeys():
    saved = core.SETTINGS.get("hotkeys", {})
    for hid, _, default, _ in HOTKEY_DEFS:
        hotkeys[hid] = saved.get(hid, default)
    # новая клавиша из обновления не должна отнять сочетание, которое вы уже назначили на другое
    for hid, _, default, _ in HOTKEY_DEFS:
        if hid not in saved and any(hotkeys[o] == hotkeys[hid] for o in hotkeys if o != hid):
            hotkeys[hid] = next(c for c in SPARE_KEYS if c not in hotkeys.values())


SPARE_KEYS = ["ctrl+shift+t", "ctrl+shift+y", "ctrl+shift+u", "ctrl+shift+k", "ctrl+alt+t"]


def unregister_hotkeys():
    for h in _hotkey_handles:
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    _hotkey_handles.clear()
    mouse_bindings.clear()


def _fire(ev):
    import time
    if ev == "quit" and core.heartbeat and time.time() - core.heartbeat > 3:
        from . import tray
        tray.emergency("quit")      # окна зависли — выход сразу
    core.events.put((ev, None))


def register_hotkeys():
    unregister_hotkeys()
    for hid, _, _, ev in HOTKEY_DEFS:
        combo = hotkeys[hid]
        if is_mouse(combo):
            mouse_bindings[combo] = ev
            if not MOUSE_OK:
                core.log("Кнопки мыши не работают: установите pynput (py -m pip install pynput)", "error")
            continue
        try:
            _hotkey_handles.append(keyboard.add_hotkey(combo, lambda ev=ev: _fire(ev)))
        except Exception as e:
            core.log(f"Не удалось назначить «{combo}»: {e}", "error")


# --- мышь (боковые кнопки) через pynput ---
try:
    from pynput import mouse as pmouse
    MOUSE_OK = True
except Exception:
    pmouse = None
    MOUSE_OK = False


def _mouse_button_name(button):
    for name, attr in (("mouse_x1", "x1"), ("mouse_x2", "x2"), ("mouse_middle", "middle")):
        if getattr(pmouse.Button, attr, None) == button:
            return name
    return None


def _on_mouse_click(x, y, button, pressed):
    if not pressed:
        return
    name = _mouse_button_name(button)
    if not name:
        return
    combo = "+".join(held_modifiers() + [name])
    if mouse_capture:
        mouse_capture(combo)
    elif combo in mouse_bindings:
        core.events.put((mouse_bindings[combo], None))
    elif name in mouse_bindings:
        # Ctrl+кнопка не назначена отдельно — срабатывает просто кнопка (например, бежите с зажатым Shift)
        core.events.put((mouse_bindings[name], None))


def start_mouse_listener():
    if MOUSE_OK:
        pmouse.Listener(on_click=_on_mouse_click, daemon=True).start()


def capture_hotkey(hid):
    """Ждём, какую клавишу/сочетание или боковую кнопку мыши нажмёт пользователь. Работает в отдельном потоке."""
    global capturing, mouse_capture
    capturing = hid
    unregister_hotkeys()  # чтобы при нажатии не сработали старые действия
    core.events.put(("keys", None))
    desc = next(d for i, d, _, _ in HOTKEY_DEFS if i == hid)
    mouse_hint = (", боковую кнопку мыши или колесо (нажатием), можно с Ctrl/Shift/Alt" if MOUSE_OK else "")
    core.log(f"Нажмите клавишу/сочетание{mouse_hint} для «{desc}». Esc — отмена.")

    result = {}
    done = threading.Event()
    down = []

    def on_key(e):
        if done.is_set():
            return
        if e.event_type == "down":
            if e.name not in down:
                down.append(e.name)
        elif down:  # отпустили первую клавишу — сочетание готово
            result["combo"] = keyboard.get_hotkey_name(down).lower()
            done.set()

    def on_mouse(name):
        if not done.is_set():
            result["combo"] = name
            done.set()

    hook = keyboard.hook(on_key)
    mouse_capture = on_mouse
    done.wait(timeout=20)
    mouse_capture = None
    try:
        keyboard.unhook(hook)
    except Exception:
        pass

    combo = result.get("combo")
    parts = combo.split("+") if combo else []
    other = {hotkeys[i]: d for i, d, _, _ in HOTKEY_DEFS if i != hid}
    if not combo or combo == "esc":
        core.log("Назначение отменено")
    elif all(p in MODIFIERS or p in ("left ctrl", "right ctrl", "left shift", "right shift", "left alt",
                                     "right alt", "alt gr") for p in parts):
        core.log("Только Ctrl/Shift/Alt — мало: зажмите их и нажмите ещё клавишу или кнопку мыши.", "warn")
    elif len(parts) == 1 and len(parts[0]) == 1:
        core.log(f"Одна буква «{combo}» не подходит — будет срабатывать, когда пишете в чат. "
            "Возьмите F-клавишу, кнопку мыши или добавьте Ctrl/Shift/Alt.", "warn")
    elif combo in other:
        core.log(f"«{pretty(combo)}» уже занято: {other[combo]}. Выберите другое.", "warn")
    else:
        hotkeys[hid] = combo
        core.save_settings(hotkeys=dict(hotkeys))
        core.log(f"«{desc}» теперь на {K(hid)}", "ok")
    capturing = None
    register_hotkeys()
    core.events.put(("keys", None))
