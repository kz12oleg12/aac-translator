"""Резервная копия: все ваши настройки одним файлом (перенос на другой ПК, восстановление после переустановки).

В копию входят: настройки и области, голоса персонажей, словарь, кэш переводов, образец меню игры.
Ключи переводчиков (GROQ_API_KEY и т.п.) хранятся в Windows (setx) и в копию НЕ попадают.
"""
import json
import os
import time
import zipfile

from . import config, core, glossary, menu, tcache, voices

MANIFEST = "aac_backup.json"
BACKUP_DIR = os.path.join(config.APP_DIR, "backups")


def _files():
    """Имя в архиве -> путь на диске (пути берём в момент вызова — в тестах их подменяют)."""
    return {
        "settings.json": config.SETTINGS_FILE,
        "characters.json": voices.FILE,
        "glossary.txt": glossary.GLOSSARY_FILE,
        "translation_cache.json": tcache.CACHE_FILE,
        "menu_ref.png": menu.REF_FILE,
    }


def default_name():
    return time.strftime("AAC_backup_%Y-%m-%d.zip")


def export(path):
    """Сохранить всё в zip-файл. Возвращает список того, что сохранено."""
    tcache.save()
    saved = []
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in _files().items():
            if src and os.path.exists(src):
                z.write(src, arc)
                saved.append(arc)
        z.writestr(MANIFEST, json.dumps({"app": "AAC Translator", "version": config.VERSION,
                                         "created": time.strftime("%Y-%m-%d %H:%M:%S"), "files": saved},
                                        ensure_ascii=False, indent=1))
    os.replace(tmp, path)
    return saved


def read_manifest(path):
    with zipfile.ZipFile(path) as z:
        if MANIFEST not in z.namelist():
            raise ValueError("это не резервная копия AAC Translator")
        return json.loads(z.read(MANIFEST).decode("utf-8"))


def restore(path):
    """Восстановить из zip-файла. Текущие файлы сначала сохраняются в папку backups.
    Возвращает (что восстановлено, путь к копии «как было до»)."""
    info = read_manifest(path)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    before = os.path.join(BACKUP_DIR, time.strftime("before_restore_%Y-%m-%d_%H-%M-%S.zip"))
    export(before)
    targets = _files()
    restored = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for arc in info.get("files", []):
            dst = targets.get(arc)            # берём только известные файлы — ничего лишнего не распаковываем
            if not dst or arc not in names:
                continue
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(z.read(arc))
            os.replace(tmp, dst)
            restored.append(arc)
    _reload_memory()
    return restored, before


def _reload_memory():
    """Программа держит часть данных в памяти — сбрасываем, чтобы при выходе она не записала старое поверх."""
    with tcache._lock:
        tcache._data = None
        tcache._dirty = False
    with voices._lock:
        voices._data["loaded"] = False
    menu._ref.update(img=None, loaded=False)
    core.SETTINGS.clear()
    core.SETTINGS.update(core.load_settings())


TITLES = {"settings.json": "настройки и области", "characters.json": "голоса персонажей",
          "glossary.txt": "словарь", "translation_cache.json": "кэш переводов", "menu_ref.png": "образец меню"}


def describe(files):
    return ", ".join(TITLES.get(f, f) for f in files) or "ничего"
