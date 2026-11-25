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
    """Имя в архиве -> путь на диске. Файлы пресета ArcheAge — рядом с программой, остальных игр — profiles/…"""
    from . import profiles
    base = profiles.paths(core.DEFAULT_PROFILE)
    out = {
        "settings.json": config.SETTINGS_FILE,
        "characters.json": base["characters"],
        "glossary.txt": base["glossary"],
        "translation_cache.json": base["cache"],
        "menu_ref.png": base["menu"],
    }
    root = os.path.join(config.APP_DIR, "profiles")
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            arc = "profiles/" + os.path.relpath(full, root).replace(os.sep, "/")
            out[arc] = full
    return out


def _target(arc):
    """Куда восстановить файл из архива (только известные места — ничего лишнего)."""
    known = _files()
    if arc in known:
        return known[arc]
    if arc.startswith("profiles/") and ".." not in arc.split("/") and not arc.endswith("/"):
        return os.path.join(config.APP_DIR, *arc.split("/"))
    return None


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
    restored = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for arc in info.get("files", []):
            dst = _target(arc)                # берём только известные файлы — ничего лишнего не распаковываем
            if not dst or arc not in names:
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(z.read(arc))
            os.replace(tmp, dst)
            restored.append(arc)
    _reload_memory()
    return restored, before


def _reload_memory():
    """Программа держит часть данных в памяти — сбрасываем, чтобы при выходе она не записала старое поверх."""
    from . import profiles
    with tcache._lock:
        tcache._data = None
        tcache._dirty = False
    with voices._lock:
        voices._data["loaded"] = False
    menu._ref.update(img=None, loaded=False, screens=[])
    core.SETTINGS.clear()
    core.SETTINGS.update(core.load_settings())
    try:
        profiles.bind(core.active_profile)
    except Exception:
        pass


TITLES = {"settings.json": "настройки и области", "characters.json": "голоса персонажей",
          "glossary.txt": "словарь", "translation_cache.json": "кэш переводов", "menu_ref.png": "образец меню"}


def describe(files):
    main = [TITLES.get(f, f) for f in files if not f.startswith("profiles/")]
    games = {f.split("/")[1] for f in files if f.startswith("profiles/") and f.count("/") >= 2}
    if games:
        main.append(f"пресеты других игр ({len(games)})")
    return ", ".join(main) or "ничего"
