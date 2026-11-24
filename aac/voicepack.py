"""Офлайн-голоса Silero одной кнопкой.

Собранной программе (.exe) нельзя «доставить» PyTorch через pip — поэтому он лежит отдельным пакетом
в «Релизах» GitHub (около 250 МБ в архиве, собирается и проверяется там же автоматически). Кнопка в разделе
«Голос и интонация» скачивает его один раз в папку программы (voices_pack) и подключает — без Python и
без перезапуска. Обновления программы пакет не трогают.
Обычной версии (с Python) кнопка запускает install_silero.py — он ставит PyTorch через pip.
"""
import importlib
import os
import subprocess
import sys
import threading
import zipfile

import requests

from . import config, core

PACK_TAG = "voices-1"                       # меняется, только если пакет нужно пересобрать (новый PyTorch)
PACK_ZIP = "AAC_Voices_Silero_win64.zip"
URL = "https://github.com/{repo}/releases/download/{tag}/{zip}"
state = {"busy": False, "progress": ""}


def folder():
    return os.path.join(config.APP_DIR, "voices_pack")


def activate():
    """Подключить скачанный пакет (если он есть): его библиотеки — в пути поиска модулей и DLL."""
    d = folder()
    site = os.path.join(d, "site")
    if not os.path.isdir(site):
        return False
    if site not in sys.path:
        sys.path.insert(0, site)                       # torch, silero-stress, scipy…
    for extra in ("stdlib", "dlls"):                   # модули Python, которых нет в самой программе
        p = os.path.join(d, extra)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    _complete_packages(os.path.join(d, "stdlib"))
    for dll_dir in (os.path.join(site, "torch", "lib"), os.path.join(d, "dlls")):
        if os.path.isdir(dll_dir) and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(dll_dir)
            except OSError:
                pass
    importlib.invalidate_caches()
    return True


def _complete_packages(stdlib):
    """В программе пакеты Python бывают урезаны (например, unittest без unittest.mock — PyTorch он нужен).
    Такому пакету добавляем путь к полной копии из пакета голосов: недостающие части найдутся там."""
    if not config.FROZEN or not os.path.isdir(stdlib):
        return
    import importlib.util
    for name in os.listdir(stdlib):
        full = os.path.join(stdlib, name)
        if not os.path.isfile(os.path.join(full, "__init__.py")):
            continue
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            continue
        locs = list(getattr(spec, "submodule_search_locations", None) or []) if spec else []
        if not spec or not locs or any(os.path.normcase(l).startswith(os.path.normcase(stdlib)) for l in locs):
            continue                                    # нет в программе — найдётся сам; или уже полный
        try:
            pkg = importlib.import_module(name)
            if full not in pkg.__path__:
                pkg.__path__.append(full)
        except Exception:
            pass


def installed():
    from . import tts_silero
    return tts_silero.installed()


def install():
    """Скачать и подключить пакет (в фоне). Ход — в журнал и в state["progress"]."""
    if state["busy"]:
        return
    if not config.FROZEN:
        # обычная версия: ставим PyTorch тем же Python, что запускает программу (откроется окно установки)
        script = os.path.join(config.APP_DIR, "install_silero.py")
        flags = 0x00000010 if os.name == "nt" else 0          # CREATE_NEW_CONSOLE — видно ход установки
        subprocess.Popen([sys.executable, script], cwd=config.APP_DIR, creationflags=flags)
        core.log("Открыл установку офлайн-голосов (PyTorch, ~1 ГБ на диске). Когда она закончится — "
                 "перезапустите программу.", "ok")
        return
    state["busy"] = True
    threading.Thread(target=_install, daemon=True).start()


def _install():
    d = folder()
    tmp_zip = d + ".download.zip"
    tmp_dir = d + ".new"
    url = URL.format(repo=config.UPDATE_REPO, tag=PACK_TAG, zip=PACK_ZIP)
    try:
        core.log("Скачиваю офлайн-голоса Silero (~250 МБ, один раз)…")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            got, shown = 0, -1
            with open(tmp_zip, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = got * 100 // total
                        state["progress"] = f"{pct}%"
                        if pct // 20 != shown:
                            shown = pct // 20
                            core.log(f"Офлайн-голоса: скачано {pct}% ({got // 1048576} из {total // 1048576} МБ)")
                        core.events.put(("panel", None))
        state["progress"] = "распаковываю…"
        core.events.put(("panel", None))
        import shutil
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        with zipfile.ZipFile(tmp_zip) as z:
            root = os.path.realpath(tmp_dir)
            for name in z.namelist():           # защита: файлы только внутри папки распаковки
                if not os.path.realpath(os.path.join(tmp_dir, name)).startswith(root + os.sep):
                    raise RuntimeError("подозрительный путь в архиве")
            z.extractall(tmp_dir)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.replace(tmp_dir, d)
        os.remove(tmp_zip)
        activate()
        import torch  # noqa: F401  — проверка, что подключилось
        core.log("✓ Офлайн-голоса установлены. Выберите «Silero» в разделе «Голос и интонация» — в первый раз "
                 "скачается модель голосов (~100 МБ).", "ok")
    except Exception as e:
        core.log(f"Офлайн-голоса не установились: {e}. Если пакет скачался, но не подключился — перезапустите "
                 "программу.", "error")
    finally:
        state.update(busy=False, progress="")
        for p in (tmp_zip,):
            try:
                os.remove(p)
            except OSError:
                pass
        core.events.put(("panel", None))
