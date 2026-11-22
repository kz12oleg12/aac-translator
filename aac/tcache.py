"""Кэш переводов: одна и та же фраза переводится один раз, дальше — мгновенно и без запросов.

Хранится в файле translation_cache.json рядом с программой и переживает перезапуск.
Разовый перевод по клавише (Shift+F8, F7, ответы) кэш не читает, а перезаписывает —
так можно исправить неудачный перевод.
"""


import contextlib
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict


from . import config


CACHE_FILE = os.path.join(config.APP_DIR, "translation_cache.json")
_lock = threading.Lock()
_data = None                 # OrderedDict: ключ -> {"t": перевод, "q": "ai"/"mt"}
_dirty = False
_saver = None
_local = threading.local()
stats = {"hits": 0, "misses": 0}


def normalize(src):
    """Мелкие отличия распознавания (пробелы, кавычки, регистр) не должны мешать совпадению."""
    s = src.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .…")


def make_key(kind, src, extra=""):
    raw = f"{kind}\x00{extra}\x00{normalize(src)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _load():
    global _data
    if _data is not None:
        return
    _data = OrderedDict()
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                if isinstance(v, dict) and v.get("t"):
                    _data[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        print("кэш переводов повреждён, начинаю заново:", e)


@contextlib.contextmanager
def fresh():
    """Внутри — кэш не читается (разовый перевод по клавише), но новый перевод запоминается."""
    old = getattr(_local, "fresh", False)
    _local.fresh = True
    try:
        yield
    finally:
        _local.fresh = old


def get(key, allow_mt=True):
    if not config.CACHE_ENABLED or getattr(_local, "fresh", False):
        return None
    with _lock:
        _load()
        v = _data.get(key)
        if v is None or (v.get("q") == "mt" and not allow_mt):
            stats["misses"] += 1
            return None
        _data.move_to_end(key)
        stats["hits"] += 1
        return v["t"]


def put(key, text, quality="ai"):
    global _dirty
    if not config.CACHE_ENABLED or not text or "НЕТ_ТЕКСТА" in text:
        return
    with _lock:
        _load()
        old = _data.get(key)
        if old and old.get("q") == "ai" and quality == "mt" and not getattr(_local, "fresh", False):
            return           # перевод нейросети лучше машинного — не затираем
        _data[key] = {"t": text, "q": quality}
        _data.move_to_end(key)
        while len(_data) > max(100, config.CACHE_MAX):
            _data.popitem(last=False)
        _dirty = True
    _schedule_save()


def _schedule_save():
    global _saver
    if _saver is not None and _saver.is_alive():
        return
    _saver = threading.Thread(target=_delayed_save, daemon=True)
    _saver.start()


def _delayed_save():
    time.sleep(10)
    save()


def save():
    global _dirty
    with _lock:
        if not _dirty or _data is None:
            return
        snapshot = dict(_data)
        _dirty = False
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        print("не удалось сохранить кэш переводов:", e)


def clear():
    global _dirty
    with _lock:
        _load()
        _data.clear()
        _dirty = True
        stats["hits"] = stats["misses"] = 0
    save()


def size():
    with _lock:
        _load()
        return len(_data)


def summary():
    if not config.CACHE_ENABLED:
        return "выкл"
    total = stats["hits"] + stats["misses"]
    part = f", из кэша {stats['hits']} из {total} ({100 * stats['hits'] // total}%)" if total else ""
    return f"{size()} фраз{part}"
