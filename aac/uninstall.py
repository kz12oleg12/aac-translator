"""Удаление программы одной кнопкой.

Удаляются ТОЛЬКО файлы и папки программы (по списку), а не вся папка целиком: если программу распаковали
прямо в «Загрузки» или на рабочий стол, чужие файлы там не пострадают. Сама папка удаляется, только если
после этого она пустая. Файлы удаляются после закрытия программы (пока она работает, они заняты).
"""
import os
import subprocess
import sys
import tempfile
import time

from . import config, core

# что принадлежит программе (в папке программы)
OWN_FILES = ["AAC Translator.exe", "aac_translator.py", "aac_translator_settings.json",
             "aac_translator_settings.json.tmp", "install.py", "install.bat", "install_silero.py",
             "install_silero.bat", "start_with_console.bat", "README.txt", "version.json", "logo.svg", "icon.ico",
             "icon_22.png", "icon_32.png", "glossary.txt", "characters.json", "characters.json.tmp",
             "translation_cache.json", "translation_cache.json.tmp", "menu_ref.png", "translator.log",
             "translator.log.old", "crash.log", "update.log", "selftest.txt", "selftest_voice.wav",
             "voices_pack.download.zip"]
OWN_DIRS = ["aac", "_internal", "tests", "history", "profiles", "backups", "reports", "models", "voices_pack",
            "voices_pack.new", "update_ready", "__pycache__"]
ENV_VARS = ["GROQ_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY", "DEEPL_API_KEY", "ANTHROPIC_API_KEY",
            "AAC_REPORT_WEBHOOK"]


def is_our_folder(d):
    """Это правда папка программы (а не диск, домашняя папка, Windows)?"""
    d = os.path.normpath(os.path.abspath(d))
    bad = {os.path.normpath(p) for p in (os.path.expanduser("~"), os.environ.get("SystemRoot", "C:\\Windows"),
                                         os.environ.get("ProgramFiles", ""), os.path.splitdrive(d)[0] + os.sep)
           if p}
    if d in bad or len(d) <= 3:
        return False
    return (os.path.exists(os.path.join(d, "AAC Translator.exe"))
            or (os.path.exists(os.path.join(d, "aac_translator.py")) and os.path.isdir(os.path.join(d, "aac"))))


def _shell_folder(csidl):
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            return buf.value
    except Exception:
        pass
    return None


def desktop():
    return _shell_folder(0x10) or os.path.join(os.path.expanduser("~"), "Desktop")   # CSIDL_DESKTOPDIRECTORY


def shortcuts():
    """Ярлыки «AAC Translator» на рабочем столе и в меню «Пуск»."""
    out = []
    for folder in (desktop(), _shell_folder(0x02)):          # CSIDL_PROGRAMS
        if folder:
            p = os.path.join(folder, "AAC Translator.lnk")
            if os.path.exists(p):
                out.append(p)
    return out


def remove_keys():
    """Убрать сохранённые ключи из переменных Windows (сами ключи на сайтах остаются рабочими)."""
    from . import keys
    n = 0
    for name in ENV_VARS:
        try:
            keys._write_windows(name, None)
            n += name in os.environ
            os.environ.pop(name, None)
        except OSError:
            pass
    return n


def save_backup():
    """Резервная копия на рабочий стол перед удалением. Возвращает путь."""
    from . import backup
    path = os.path.join(desktop(), f"AAC Translator — копия {time.strftime('%Y-%m-%d %H-%M')}.zip")
    backup.export(path)
    return path


def script(app_dir, pid):
    """bat-файл: дождаться закрытия программы, удалить её файлы и папки, затем саму папку — если пустая."""
    lines = ["@echo off", "chcp 65001 >nul", ":wait",
             f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto wait)',
             "timeout /t 1 /nobreak >nul"]
    for f in OWN_FILES:
        lines.append(f'del /f /q "{os.path.join(app_dir, f)}" 2>nul')
    for d in OWN_DIRS:
        lines.append(f'rmdir /s /q "{os.path.join(app_dir, d)}" 2>nul')
    lines.append(f'rmdir "{app_dir}" 2>nul')            # без /s — только если папка опустела
    lines.append('del "%~f0"')                          # и сам этот файл
    return "\r\n".join(lines) + "\r\n"


def run(backup_first=True, keys_too=True):
    """Удалить программу. Возвращает (ok, сообщение). При ok программа должна закрыться (событие quit)."""
    d = config.APP_DIR
    if not is_our_folder(d):
        return False, f"папка {d} не похожа на папку программы — ничего не удаляю"
    copy = None
    if backup_first:
        try:
            copy = save_backup()
        except Exception as e:
            return False, f"не удалось сохранить резервную копию ({e}) — ничего не удалено"
    if keys_too:
        remove_keys()
    for lnk in shortcuts():
        try:
            os.remove(lnk)
        except OSError:
            pass
    bat = os.path.join(tempfile.gettempdir(), f"aac_uninstall_{os.getpid()}.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write(script(d, os.getpid()))
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x00000008 | 0x00000200 | 0x08000000, close_fds=True)
    core.log("Программа удаляется — закрываюсь" + (f". Резервная копия: {copy}" if copy else ""), "ok")
    return True, copy or ""
