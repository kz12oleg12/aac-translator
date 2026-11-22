"""Проверка и установка обновлений с GitHub.

Новые версии выкладываются как «релизы» в репозиторий config.UPDATE_REPO (zip-файл программы).
При запуске (и раз в несколько часов) программа спрашивает GitHub, какая версия последняя.
Если новее — пишет в журнал и показывает кнопку «⬇ Обновить». По нажатию: скачивает zip,
распаковывает во временную папку и запускает оттуда install.py --update, а сама закрывается.
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

API = "https://api.github.com/repos/{repo}/releases/latest"
state = {"latest": None, "checking": False, "installing": False, "error": None}


def parse_version(v):
    """«v4.10» / «4.10» → (4, 10) — сравниваем числами, чтобы 4.10 было новее 4.9."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest, current=None):
    return parse_version(latest) > parse_version(current or config.VERSION)


def _headers(raw=False):
    h = {"Accept": "application/octet-stream" if raw else "application/vnd.github+json",
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
        r = requests.get(API.format(repo=config.UPDATE_REPO), headers=_headers(), timeout=15)
        if r.status_code == 404:
            msg = ("Обновления: репозиторий не найден или закрыт. Если он Private — сохраните токен "
                   "только на чтение: setx GITHUB_TOKEN \"...\" и перезапустите программу.")
            if not os.environ.get("GITHUB_TOKEN"):
                msg += " (Или в репозитории ещё нет ни одного релиза.)"
            raise RuntimeError(msg)
        if r.status_code == 401:
            raise RuntimeError("Обновления: токен GITHUB_TOKEN не подходит или истёк — сделайте новый.")
        if r.status_code == 403:
            raise RuntimeError("Обновления: GitHub временно ограничил запросы — проверю позже.")
        r.raise_for_status()
        data = r.json()
        asset = next((a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".zip")), None)
        if asset is None:
            raise RuntimeError("Обновления: в последнем релизе нет zip-файла.")
        info = {"version": (data.get("tag_name") or data.get("name") or "").lstrip("vV"),
                "notes": (data.get("body") or "").strip(),
                # закрытый репозиторий: качаем через API (с токеном), открытый — по прямой ссылке
                "asset_url": asset["url"] if os.environ.get("GITHUB_TOKEN") else asset["browser_download_url"],
                "api_asset": bool(os.environ.get("GITHUB_TOKEN")),
                "size": asset.get("size", 0)}
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
    threading.Thread(target=check, args=(quiet,), daemon=True).start()


def start_periodic():
    """Проверка при запуске (через несколько секунд) и раз в config.UPDATE_EVERY_HOURS часов."""
    if not config.UPDATE_CHECK or not config.UPDATE_REPO:
        return

    def loop():
        time.sleep(8)
        while True:
            check(quiet=True)
            time.sleep(config.UPDATE_EVERY_HOURS * 3600)
    threading.Thread(target=loop, daemon=True).start()


def download(info, dest_dir):
    """Скачать zip релиза и распаковать. Возвращает папку, где лежит install.py."""
    zpath = os.path.join(dest_dir, "update.zip")
    with requests.get(info["asset_url"], headers=_headers(raw=info.get("api_asset")), timeout=60, stream=True) as r:
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
        core.log(f"Обновление не удалось: {e}. Можно обновиться вручную — скачать zip со страницы "
                 f"github.com/{config.UPDATE_REPO}/releases", "error")


def install_async(info):
    threading.Thread(target=install, args=(info,), daemon=True).start()
