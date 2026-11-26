"""Общее состояние программы: очередь событий, области, настройки на диске, журнал, ошибки."""


import json
import os

import queue


import threading
import time


from . import config


events = queue.Queue()
auto_on = threading.Event()
region = None  # область субтитров (left, top, width, height)
answers_region = None  # область вариантов ответа
own_rects = []   # где на экране сейчас окна самой программы (их закрашиваем на снимках — чтобы не переводить себя)
heartbeat = 0.0  # когда главный цикл окон последний раз «отметился» (для поиска зависшей копии)
chat_region = None  # область игрового чата
menu_region = None  # кусочек экрана, по которому узнаём открытое меню игры
in_menu = False     # меню игры сейчас открыто — автоперевод на паузе
last_line = None    # (перевод, оригинал) последней реплики субтитров — для «повторить реплику»
chat_auto = True    # переводить чат автоматически (галочка в панели)
region2 = None  # вторая область реплик (НПС говорят мимоходом в другом месте экрана)
answers_auto = False   # следить за ответами автоматически (вкл/выкл в системной панели)
last_subtitle = ""     # последняя переведённая реплика — контекст для перевода ответов
SETTINGS = {}


# ---------- настройки (запоминаем область) ----------
PROFILE_KEYS = ("region", "region2", "answers_region", "chat_region", "menu_region")   # у каждой игры свои
DEFAULT_PROFILE = "archeage"     # id пресета ArcheAge (его файлы — рядом с программой); не «главный», обычный
active_profile = None            # пресет игры, которая сейчас запущена; None — игры нет («ждёт игру»)


def had_old_settings(data):
    """Настройки из версий до пресетов (там всё было про ArcheAge)."""
    return any(data.get(k) for k in PROFILE_KEYS) or any(
        os.path.exists(os.path.join(config.APP_DIR, f)) for f in ("characters.json", "translation_cache.json"))


def default_profiles(data=None):
    """Переход со старых версий: всё прежнее — в пресет ArcheAge Chronicles (области из общих настроек)."""
    data = data or {}
    p = {"name": "ArcheAge Chronicles", "exes": ["archeagechronicles.exe"], "match": "archeage",
         "desc": "the MMORPG ArcheAge Chronicles"}
    for k in PROFILE_KEYS:
        if data.get(k):
            p[k] = data[k]
    return {DEFAULT_PROFILE: p}


test_scene = False       # открыта «Тестовая сцена»: пресет не переключается на запущенные игры


def apply_profile_regions(prof):
    global region, answers_region, region2, chat_region, menu_region
    region = tuple(prof["region"]) if prof.get("region") else None
    answers_region = tuple(prof["answers_region"]) if prof.get("answers_region") else None
    region2 = tuple(prof["region2"]) if prof.get("region2") else None
    chat_region = tuple(prof["chat_region"]) if prof.get("chat_region") else None
    menu_region = tuple(prof["menu_region"]) if prof.get("menu_region") else None


def load_settings():
    global active_profile
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data.get("profiles"), dict):
        # переход на пресеты: у прежнего пользователя всё было про ArcheAge — в её пресет; новый — без пресетов
        data["profiles"] = default_profiles(data) if had_old_settings(data) else {}
    active_profile = data.get("active_profile") if data.get("active_profile") in data["profiles"] else None
    apply_profile_regions(data["profiles"].get(active_profile) or {})
    return data


_settings_lock = threading.Lock()


def save_settings(**kw):
    """Дописать настройки в файл. Под замком и через временный файл: если два потока сохраняют одновременно
    или файл не прочитался, настройки не теряются (раньше так могли «слететь» галочки)."""
    with _settings_lock:
        data = None
        try:
            with open(config.SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except Exception:
            data = None
        if not isinstance(data, dict):
            # файл повреждён/недописан — берём то, что загружено в программу, а не пустоту
            data = dict(SETTINGS) if isinstance(SETTINGS, dict) else {}
        prof_kw = {k: kw.pop(k) for k in list(kw) if k in PROFILE_KEYS}
        if prof_kw and active_profile is not None:    # области — в пресет текущей игры (игры нет — некуда)
            profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else None
            if not profiles:
                profiles = (SETTINGS.get("profiles") if isinstance(SETTINGS, dict) else None) or {}
            prof = profiles.get(active_profile)
            if prof is not None:
                for k, v in prof_kw.items():
                    prof[k] = list(v) if isinstance(v, tuple) else v
                kw["profiles"] = profiles
        data.update(kw)
        if isinstance(SETTINGS, dict):
            SETTINGS.update(kw)
        try:
            tmp = config.SETTINGS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, config.SETTINGS_FILE)
        except Exception as e:
            print("Не удалось сохранить настройки:", e)


# ---------- журнал для системной панели ----------
stats = {"requests": 0, "errors": 0, "last": "—", "tok_in": 0, "tok_out": 0, "cost": 0.0}


import collections
log_lines = collections.deque(maxlen=3000)     # журнал за этот запуск — для «Сообщить о проблеме»
error_traces = collections.deque(maxlen=50)    # полные тексты ошибок программы


def log(msg, level="info"):
    """level: info / ok / warn / error — сообщение уходит в системную панель и в консоль."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    log_lines.append((time.strftime("%Y-%m-%d %H:%M:%S"), level, msg))
    events.put(("log", (time.strftime("%H:%M:%S"), msg, level)))


# ---------- Gemini ----------
class RateLimited(Exception):
    """Лимит запросов. detail — что ответил сервис (для журнала)."""
    def __init__(self, detail=""):
        super().__init__(detail)
        self.detail = detail


class ApiError(Exception):
    pass


def _short_error(text):
    """Достаём из ответа сервиса короткое сообщение об ошибке."""
    try:
        import json as _j
        d = _j.loads(text)
        msg = d.get("message") or (d.get("error") or {}).get("message") or d.get("detail") or text
        return str(msg)[:160]
    except Exception:
        return text[:160]
