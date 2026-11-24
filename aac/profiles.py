"""Пресеты игр: у каждой игры свои области, образец меню, словарь, персонажи с голосами, кэш переводов
и название игры в подсказке нейросети. Программа сама переключается, когда игра оказывается на экране.

Все пресеты равны: любой можно удалить; пока игра не запущена, пресет не выбран (core.active_profile = None).
Пресет ArcheAge (id «archeage») хранит файлы там же, где раньше (рядом с программой), остальные — в profiles/<id>/.
"""
import os
import re

from . import config, core

GENERIC_GLOSSARY = """# Словарь имён и терминов для этой игры (AAC Translator).
# Каждая строка:  Оригинал = Перевод
# Строка вида  - Слово  — не переводить это слово/фразу вообще (кнопки интерфейса и т.п.)
"""


def all_profiles():
    profs = core.SETTINGS.get("profiles") if isinstance(core.SETTINGS, dict) else None
    if not isinstance(profs, dict):
        profs = {}
        if isinstance(core.SETTINGS, dict):
            core.SETTINGS["profiles"] = profs
    return profs


def active():
    return all_profiles().get(core.active_profile) or {}


FREE = "_free"     # пресет «Без игры» — режим проверки: переводить в любом окне, когда игра не запущена


def free_pid():
    """Пресет «🧪 Без игры» (создаётся при первом включении режима). Свои области, словарь, персонажи."""
    profs = all_profiles()
    if FREE not in profs:
        profs[FREE] = {"name": "🧪 Без игры", "exes": [], "free": True, "desc": "a video game"}
        core.save_settings(profiles=profs)
    return FREE


def is_free(pid=None):
    return (pid or core.active_profile) == FREE


def idle_target():
    """Какой пресет выбран, когда ни одна игра не запущена: «Без игры» в режиме проверки, иначе никакой."""
    return None if config.GAMES_ONLY else free_pid()


def game_profiles():
    """Пресеты настоящих игр (без «Без игры») — для раздела «Игры»."""
    return {k: v for k, v in all_profiles().items() if not v.get("free")}


_hold = {"pid": None}     # пресет, выбранный вручную в панели (настроить области без игры) — не снимать сам


def is_archeage_like(p):
    return "archeage" in (p.get("match") or "") or any("archeage" in e for e in p.get("exes", []))


def name(pid=None):
    pid = pid or core.active_profile
    p = all_profiles().get(pid) or {}
    return p.get("name") or pid or "нет игры"


def folder(pid):
    """Где лежат файлы пресета (словарь, персонажи, кэш, образец меню)."""
    if pid == core.DEFAULT_PROFILE:
        return config.APP_DIR
    return os.path.join(config.APP_DIR, "profiles", pid or "_none")     # _none — пока игры нет (пусто)


def paths(pid):
    d = folder(pid)
    return {"glossary": os.path.join(d, "glossary.txt"), "characters": os.path.join(d, "characters.json"),
            "cache": os.path.join(d, "translation_cache.json"), "menu": os.path.join(d, "menu_ref.png")}


def for_exe(exe):
    """id пресета для программы exe или None."""
    if not exe:
        return None
    low = exe.lower()
    for pid, p in all_profiles().items():
        if low in [e.lower() for e in p.get("exes", [])]:
            return pid
        m = (p.get("match") or "").lower()
        if m and m in low:
            return pid
    return None


def _pretty(exe):
    stem = re.sub(r"\.exe$", "", exe, flags=re.I)
    stem = re.sub(r"[-_](win64|win32|shipping|x64|dx11|dx12|launcher)", "", stem, flags=re.I)
    stem = re.sub(r"[-_]+", " ", stem).strip()
    return stem[:1].upper() + stem[1:] if stem else exe


def create(exe, title=None):
    """Новый пресет для игры exe. Возвращает его id."""
    profs = all_profiles()
    if "archeage" in exe.lower() and core.DEFAULT_PROFILE not in profs:
        # знакомая игра: её название и описание для нейросети; файлы — рядом с программой, как раньше
        pid = core.DEFAULT_PROFILE
        profs[pid] = {"name": "ArcheAge Chronicles", "exes": [exe.lower()], "match": "archeage",
                      "desc": "the MMORPG ArcheAge Chronicles"}
    else:
        base = re.sub(r"[^a-z0-9]+", "", re.sub(r"\.exe$", "", exe.lower())) or "game"
        pid, n = base, 2
        while pid in profs or pid == core.DEFAULT_PROFILE:
            pid, n = f"{base}{n}", n + 1
        title = title or _pretty(exe)
        profs[pid] = {"name": title, "exes": [exe.lower()], "desc": f"the video game {title}"}
    core.save_settings(profiles=profs)
    os.makedirs(folder(pid), exist_ok=True)
    g = paths(pid)["glossary"]
    if not os.path.exists(g):
        with open(g, "w", encoding="utf-8") as f:
            f.write(GENERIC_GLOSSARY)
    return pid


def add_exe(pid, exe):
    """Ещё один файл игры (лаунчер, защита от читов, новое имя после обновления)."""
    profs = all_profiles()
    exe = exe.lower()
    if pid not in profs:
        return False
    owner = for_exe(exe)
    if owner and owner != pid:
        core.log(f"{exe} уже относится к игре «{name(owner)}»", "warn")
        return False
    if exe not in profs[pid].setdefault("exes", []):
        profs[pid]["exes"].append(exe)
        core.save_settings(profiles=profs)
        core.log(f"🎮 «{name(pid)}»: добавлен файл {exe}", "ok")
    return True


def remove_exe(pid, exe):
    profs = all_profiles()
    p = profs.get(pid)
    if not p or exe not in p.get("exes", []) or (len(p["exes"]) < 2 and not p.get("match")):
        return False      # последний файл игры не убираем — иначе пресет не узнает игру
    p["exes"].remove(exe)
    core.save_settings(profiles=profs)
    return True


def lock(pid):
    """Закрепить пресет (None — открепить)."""
    if pid:
        activate(pid, announce=False)
        core.log(f"📌 Пресет «{name(pid)}» закреплён: программа не переключается сама и переводит в любом окне "
                 "(кроме браузеров и «не игр»).", "ok")
    else:
        core.log("Пресет откреплён — снова переключаюсь по игре на экране", "ok")
    core.save_settings(profile_lock=pid or None)
    core.events.put(("panel", None))


def rename(pid, title):
    title = title.strip()
    profs = all_profiles()
    if not title or pid not in profs:
        return
    profs[pid]["name"] = title
    if not is_archeage_like(profs[pid]):
        profs[pid]["desc"] = f"the video game {title}"
    core.save_settings(profiles=profs)
    core.events.put(("panel", None))


def delete(pid):
    """Убрать пресет (файлы пресета переносятся в папку backups, а не стираются)."""
    profs = all_profiles()
    if pid not in profs:
        return False
    title = profs[pid].get("name", pid)
    if pid == core.active_profile:
        activate(None, announce=False)
    if _hold["pid"] == pid:
        _hold["pid"] = None
    profs = all_profiles()
    gone = profs.pop(pid, None) or {}
    core.save_settings(profiles=profs)
    from . import game
    game.skip_this_run.update(e.lower() for e in gone.get("exes", []))   # не создавать заново сразу же
    if core.SETTINGS.get("profile_lock") == pid:
        core.save_settings(profile_lock=None)
    import shutil
    import time
    dst = os.path.join(config.APP_DIR, "backups", f"profile_{pid}_{time.strftime('%Y-%m-%d_%H-%M-%S')}")
    if pid != core.DEFAULT_PROFILE:
        src = folder(pid)
        if os.path.isdir(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
    else:                       # ArcheAge: её файлы лежат рядом с программой — переносим их по одному
        for f in paths(pid).values():
            if os.path.exists(f):
                os.makedirs(dst, exist_ok=True)
                shutil.move(f, os.path.join(dst, os.path.basename(f)))
    core.log(f"Пресет «{title}» удалён (его файлы — в папке backups)", "ok")
    return True


def bind(pid):
    """Подключить файлы пресета: словарь, персонажи, кэш, образец меню. Без событий — для запуска и проверок."""
    from . import glossary, menu, tcache, voices
    p = paths(pid)
    tcache.save()
    with tcache._lock:
        tcache.CACHE_FILE = p["cache"]
        tcache._data = None
        tcache._dirty = False
    with voices._lock:
        voices.FILE = p["characters"]
        voices._data["loaded"] = False
    glossary.GLOSSARY_FILE = p["glossary"]
    glossary._glossary.update(mtime=None, loaded=False)
    if not os.path.exists(p["glossary"]):
        os.makedirs(folder(pid), exist_ok=True)
        with open(p["glossary"], "w", encoding="utf-8") as f:
            f.write(GENERIC_GLOSSARY)
    menu.REF_FILE = p["menu"]
    menu._ref.update(img=None, loaded=False)


def activate(pid, announce=True, hold=False):
    """Переключиться на пресет игры pid. None — игры нет: никакой пресет не выбран.
    hold — выбрали вручную в панели (настроить игру, пока она не запущена): программа его сама не снимает."""
    _run_cache["t"] = 0               # список запущенных игр — перепроверить (новый пресет мог только что появиться)
    profs = all_profiles()
    if pid is not None and pid not in profs:
        return
    _hold["pid"] = pid if hold else None
    core.active_profile = pid
    core.save_settings(active_profile=pid)
    core.apply_profile_regions(profs.get(pid) or {})
    core.in_menu = False
    bind(pid)
    try:
        from . import translate
        translate.dialogue_history.clear()         # контекст диалога другой игры не нужен
    except Exception:
        pass
    core.last_line = None
    if announce and pid is not None:
        regs = [n for n, r in (("субтитры", core.region), ("реплики 2", core.region2),
                               ("ответы", core.answers_region), ("чат", core.chat_region)) if r]
        core.log(f"🎮 Игра: {profs[pid].get('name', pid)} — " +
                 (f"области: {', '.join(regs)}" if regs else "области ещё не обведены (F9 — субтитры)"), "ok")
    core.events.put(("profile_changed", pid))


def adapt(prompt):
    """Подставить в подсказку нейросети название текущей игры (подсказки написаны для ArcheAge)
    и добавить описание мира и тона, если его собрал Groq."""
    p = active()
    if prompt and p.get("about") and "About this game:" not in prompt:
        prompt = prompt.rstrip() + "\n\nAbout this game: " + p["about"]
    if not prompt or "ArcheAge" not in prompt or (p and is_archeage_like(p)):
        return prompt
    desc = p.get("desc") or (f"the video game {p['name']}" if p.get("name") else "a video game")
    title = p.get("name", "the game")
    for old in ("the fantasy MMORPG ArcheAge Chronicles", "the MMORPG ArcheAge Chronicles",
                "an English-language MMORPG (ArcheAge Chronicles)"):
        prompt = prompt.replace(old, desc)
    for old in ("fantasy MMORPG ArcheAge Chronicles", "MMORPG ArcheAge Chronicles"):
        prompt = prompt.replace(old, desc.replace("the ", "", 1))
    return prompt.replace("ArcheAge Chronicles", title)


def stats(pid):
    """(персонажей, записей в словаре) пресета — для раздела «Игры»."""
    import json
    p = paths(pid)
    chars = gl = 0
    try:
        with open(p["characters"], encoding="utf-8") as f:
            d = json.load(f)
        chars = len(d.get("chars", d)) if isinstance(d, dict) else 0
    except Exception:
        pass
    try:
        with open(p["glossary"], encoding="utf-8-sig") as f:
            gl = sum(1 for ln in f if "=" in ln and not ln.lstrip().startswith(("#", "-")))
    except Exception:
        pass
    return chars, gl


_run_cache = {"t": 0.0, "pids": set()}


def running():
    """Пресеты, чьи игры сейчас запущены (есть окно). Проверка раз в 3 с — это дёшево."""
    import time
    now = time.time()
    if now - _run_cache["t"] > 3:
        from . import game
        found = set()
        for exe, _ in game.running_programs():
            pid = for_exe(exe)
            if pid:
                found.add(pid)
        _run_cache.update(t=now, pids=found)
    return _run_cache["pids"]


def is_running(pid=None):
    return (pid or core.active_profile) in running()
