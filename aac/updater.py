"""Проверка и установка обновлений с GitHub.

Новые версии лежат в ветке main репозитория config.UPDATE_REPO; номер версии и что нового —
в файле version.json в корне. При запуске (и раз в несколько часов) программа читает этот файл.
Если версия новее — пишет в журнал и показывает кнопку «⬇ Обновить». По нажатию: скачивает
архив ветки, распаковывает во временную папку и запускает оттуда install.py --update, а сама закрывается.
Установщик обновляет файлы (ключи, настройки, словарь, история, голоса персонажей не трогаются)
и снова запускает программу.

Закрытый (Private) репозиторий: нужен токен только на чтение — setx GITHUB_TOKEN "..." .
"""
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import requests

from . import config, core

VERSION_URL = "https://api.github.com/repos/{repo}/contents/version.json?ref={branch}"
ZIP_URL = "https://api.github.com/repos/{repo}/zipball/{branch}"
state = {"latest": None, "checking": False, "installing": False, "error": None}


def parse_version(v):
    """«v4.10» / «4.10» → (4, 10) — сравниваем числами, чтобы 4.10 было новее 4.9."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest, current=None):
    return parse_version(latest) > parse_version(current or config.VERSION)


def _headers(raw=False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
         "User-Agent": f"AAC-Translator/{config.VERSION}"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def check(quiet=True):
    """Узнать последнюю версию. Возвращает dict(version, notes, asset_url, size) или None."""
    if not config.UPDATE_REPO or state["checking"]:
        return None
    state["checking"] = True
    try:
        url = VERSION_URL.format(repo=config.UPDATE_REPO, branch=config.UPDATE_BRANCH)
        headers = _headers(raw=True)
        if state.get("etag") and state.get("latest"):
            headers["If-None-Match"] = state["etag"]   # «изменилось ли?» — ответ «нет» не тратит лимит GitHub
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 304:                      # version.json не менялся с прошлой проверки
            info = state["latest"]
            if not quiet:
                core.log(f"Обновлений нет: у вас последняя версия {config.VERSION}"
                         if not is_newer(info["version"]) else f"Доступна версия {info['version']}", "ok")
            return info
        if r.status_code == 404:
            msg = ("Обновления: репозиторий не найден или закрыт. Если он Private — сохраните токен "
                   "только на чтение: setx GITHUB_TOKEN \"...\" и перезапустите программу.")
            raise RuntimeError(msg)
        if r.status_code == 401:
            raise RuntimeError("Обновления: токен GITHUB_TOKEN не подходит или истёк — сделайте новый.")
        if r.status_code == 403:
            raise RuntimeError("Обновления: GitHub временно ограничил запросы — проверю позже.")
        r.raise_for_status()
        state["etag"] = (getattr(r, "headers", None) or {}).get("ETag")
        data = r.json()
        info = {"version": str(data.get("version", "")).lstrip("vV"),
                "notes": "\n".join(data.get("notes", [])) if isinstance(data.get("notes"), list)
                else str(data.get("notes", "")).strip(),
                "asset_url": ZIP_URL.format(repo=config.UPDATE_REPO, branch=config.UPDATE_BRANCH),
                "api_asset": False}
        if not info["version"]:
            raise RuntimeError("Обновления: в version.json нет номера версии.")
        state["latest"], state["error"] = info, None
        if is_newer(info["version"]):
            core.events.put(("update_available", info))
        elif not quiet:
            core.log(f"Обновлений нет: у вас последняя версия {config.VERSION}", "ok")
        return info
    except Exception as e:
        state["error"] = str(e)
        if not quiet or "репозиторий не найден" in str(e) or "токен" in str(e):
            core.log(str(e) if str(e).startswith("Обновления") else f"Обновления: не удалось проверить ({e})",
                     "warn")
        return None
    finally:
        state["checking"] = False


def check_async(quiet=True):
    if not quiet:
        core.log("Проверяю обновления…")
    threading.Thread(target=check, args=(quiet,), daemon=True).start()


def startup_check():
    """Проверка при запуске. Сама ничего не ставит: новая версия → спросить (или скачать в фоне и спросить)."""
    st = staged()
    if st:                    # скачано раньше, а перезапуск отложили — спросить снова
        core.events.put(("update_ready", st))
        return False
    info = check(quiet=True)
    if info and is_newer(info["version"]):
        return False          # check() уже отправил update_available — дальше решает окно программы
    if info:
        core.log(f"Обновления проверены: у вас последняя версия {config.VERSION}")
    elif state.get("error"):
        core.log("Обновления: не удалось проверить при запуске — попробую позже", "warn")
    return False


def start_periodic():
    """Проверка сразу при запуске и потом раз в минуту (config.UPDATE_EVERY_SECONDS).
    При запуске (вы ещё не в игре) новая версия ставится сама, если включено «обновляться сам»."""
    if not config.UPDATE_CHECK or not config.UPDATE_REPO:
        return

    def loop():
        time.sleep(3)
        startup_check()
        while True:
            time.sleep(max(30, config.UPDATE_EVERY_SECONDS))
            check(quiet=True)
            if "ограничил" in str(state.get("error") or ""):
                time.sleep(15 * 60)                    # GitHub попросил подождать — не настаиваем
    threading.Thread(target=loop, daemon=True).start()


def download(info, dest_dir):
    """Скачать zip релиза и распаковать. Возвращает папку, где лежит install.py."""
    zpath = os.path.join(dest_dir, "update.zip")
    with requests.get(info["asset_url"], headers=_headers(), timeout=60, stream=True) as r:
        r.raise_for_status()
        with open(zpath, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():   # защита: файлы только внутри папки распаковки
            target = os.path.realpath(os.path.join(dest_dir, name))
            if not target.startswith(os.path.realpath(dest_dir) + os.sep):
                raise RuntimeError("подозрительный путь в архиве обновления")
        z.extractall(dest_dir)
    for root, dirs, files in os.walk(dest_dir):
        if "install.py" in files and "aac" in dirs:
            return root
    raise RuntimeError("в архиве обновления нет install.py")


def install(info):
    """Скачать и запустить установщик; программа после этого должна закрыться (событие quit)."""
    if state["installing"]:
        return
    state["installing"] = True
    try:
        core.log(f"Скачиваю версию {info['version']}…")
        folder = download(info, tempfile.mkdtemp(prefix="aac_update_"))
        py = sys.executable   # тот же Python, которым запущена программа
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # отдельно от программы
        subprocess.Popen([py, os.path.join(folder, "install.py"), "--update", "--wait-pid", str(os.getpid())],
                         cwd=folder, creationflags=flags, close_fds=True)
        core.log(f"Устанавливаю версию {info['version']} — программа перезапустится сама через полминуты.", "ok")
        core.events.put(("quit", None))
    except Exception as e:
        state["installing"] = False
        core.log(f"Обновление не удалось: {e}. Можно обновиться вручную: github.com/{config.UPDATE_REPO} → "
                 f"Code → Download ZIP, распаковать и запустить install.bat", "error")


def install_async(info):
    threading.Thread(target=install, args=(info,), daemon=True).start()


# ---------- «обновлять автоматически»: скачать заранее, поставить при перезапуске ----------
STAGE_DIR = os.path.join(config.APP_DIR, "update_ready")


def staged():
    """Скачанное заранее обновление {"version", "folder"} или None."""
    st = core.SETTINGS.get("staged_update")
    if not st or not is_newer(str(st.get("version", ""))):
        return None
    if not os.path.exists(os.path.join(st.get("folder", ""), "install.py")):
        return None
    return st


def prepare(info):
    """Скачать новую версию в фоне (ничего не меняя в программе) и спросить про перезапуск."""
    if state.get("preparing") or state["installing"]:
        return
    st = staged()
    if st and st["version"] == info["version"]:
        core.events.put(("update_ready", st))
        return
    state["preparing"] = True
    try:
        import shutil
        shutil.rmtree(STAGE_DIR, ignore_errors=True)
        os.makedirs(STAGE_DIR, exist_ok=True)
        core.log(f"Скачиваю версию {info['version']} в фоне…")
        folder = download(info, STAGE_DIR)
        st = {"version": info["version"], "folder": folder}
        core.save_settings(staged_update=st)
        core.SETTINGS["staged_update"] = st
        core.log(f"Версия {info['version']} скачана — установится при перезапуске программы.", "ok")
        core.events.put(("update_ready", st))
    except Exception as e:
        core.log(f"Не удалось скачать обновление: {e} — попробую позже", "warn")
    finally:
        state["preparing"] = False


def prepare_async(info):
    threading.Thread(target=prepare, args=(info,), daemon=True).start()


def apply_staged():
    """Поставить скачанное обновление: запустить установщик и закрыть программу (он запустит её снова)."""
    st = staged()
    if not st:
        return False
    state["installing"] = True
    py = sys.executable
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
    subprocess.Popen([py, os.path.join(st["folder"], "install.py"), "--update", "--wait-pid", str(os.getpid())],
                     cwd=st["folder"], creationflags=flags, close_fds=True)
    core.save_settings(staged_update=None)
    core.log(f"Устанавливаю версию {st['version']} — программа перезапустится сама.", "ok")
    core.events.put(("quit", None))
    return True


def announce_if_updated():
    """Первый запуск после обновления: пишем в журнал, с какой версии обновились и что нового."""
    prev = core.SETTINGS.get("last_version")
    if prev != config.VERSION:
        core.save_settings(last_version=config.VERSION)
        core.SETTINGS["last_version"] = config.VERSION
    log = os.path.join(config.APP_DIR, "update.log")
    just_updated = os.path.exists(log) and time.time() - os.path.getmtime(log) < 900
    if prev and not is_newer(config.VERSION, prev):
        return
    if not prev and not just_updated:
        return            # первая установка, а не обновление
    notes = []
    try:
        import json
        with open(os.path.join(config.APP_DIR, "version.json"), encoding="utf-8") as f:
            data = json.load(f)
        notes = data.get("notes", []) if isinstance(data.get("notes"), list) else [str(data.get("notes", ""))]
    except Exception:
        pass
    core.log(f"✅ Программа обновлена: {prev + ' → ' if prev else 'до версии '}{config.VERSION}" + (". Что нового: " + "; ".join(notes) if notes else ""),
             "ok")
