"""Определение окна игры и пауза, когда игра не на экране."""

import ctypes


import os


import threading


from . import config, core


game_exe = None                # имя .exe игры — запоминается, когда вы включаете автоперевод из игры
game_active = threading.Event()
game_active.set()
NOT_GAME_EXE = {"python.exe", "pythonw.exe", "explorer.exe", "py.exe", "pyw.exe", "cmd.exe",
                "windowsterminal.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe"}


def foreground_exe():
    """(имя .exe активного окна, pid) или (None, None)."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None, pid.value
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower(), pid.value
        finally:
            kernel32.CloseHandle(h)
        return None, pid.value
    except Exception:
        return None, None


def is_archeage(exe):
    return bool(exe) and "archeage" in exe.lower()


def is_game(exe):
    """Это окно игры? В режиме «только ArcheAge» — только ArcheAge Chronicles, иначе — запомненная игра."""
    if config.ONLY_ARCHEAGE:
        return is_archeage(exe)
    return exe == game_exe


_blocked_logged = {"exe": None}


def blocked():
    """Ручной перевод по клавише в чужом окне? True — не переводим (в журнал — один раз на программу)."""
    if not config.ONLY_ARCHEAGE:
        return False
    exe, pid = foreground_exe()
    if exe is None or pid == os.getpid() or is_archeage(exe):
        return False
    if _blocked_logged["exe"] != exe:
        _blocked_logged["exe"] = exe
        core.log(f"Сейчас на экране {exe}, а не ArcheAge — переводчик работает только в ArcheAge Chronicles "
                 "(выключить можно на Главной: «Только ArcheAge Chronicles»).", "warn")
    return True


def remember_game_window():
    """Вызывается при включении автоперевода: активное сейчас окно — это игра."""
    global game_exe
    exe, pid = foreground_exe()
    if not exe or pid == os.getpid() or exe in NOT_GAME_EXE:
        return
    if config.ONLY_ARCHEAGE and not is_archeage(exe):
        core.log(f"Сейчас на экране {exe}, а не ArcheAge — автоперевод включится, когда вы вернётесь "
                 "в ArcheAge Chronicles.", "warn")
        return
    if exe != game_exe:
        game_exe = exe
        core.save_settings(game_exe=exe)
        core.log(f"Запомнил окно игры: {exe}", "ok")
