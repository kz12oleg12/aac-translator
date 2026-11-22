"""Общее состояние программы: очередь событий, области, настройки на диске, журнал, ошибки."""


import json

import queue


import threading
import time


from . import config


events = queue.Queue()
auto_on = threading.Event()
region = None  # область субтитров (left, top, width, height)
answers_region = None  # область вариантов ответа
region2 = None  # вторая область реплик (НПС говорят мимоходом в другом месте экрана)
answers_auto = False   # следить за ответами автоматически (вкл/выкл в системной панели)
last_subtitle = ""     # последняя переведённая реплика — контекст для перевода ответов
SETTINGS = {}


# ---------- настройки (запоминаем область) ----------
def load_settings():
    global region, answers_region, region2
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("region"):
            region = tuple(data["region"])
        if data.get("answers_region"):
            answers_region = tuple(data["answers_region"])
        if data.get("region2"):
            region2 = tuple(data["region2"])
        return data
    except Exception:
        return {}


def save_settings(**kw):
    data = {}
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        pass
    data.update(kw)
    try:
        with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print("Не удалось сохранить настройки:", e)


# ---------- журнал для системной панели ----------
stats = {"requests": 0, "errors": 0, "last": "—", "tok_in": 0, "tok_out": 0, "cost": 0.0}


def log(msg, level="info"):
    """level: info / ok / warn / error — сообщение уходит в системную панель и в консоль."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
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
