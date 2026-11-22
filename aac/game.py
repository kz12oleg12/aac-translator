"""Определение окна игры и пауза, когда игра не на экране."""

import ctypes


import os


import threading


from . import core


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


def remember_game_window():
    """Вызывается при включении автоперевода: активное сейчас окно — это игра."""
    global game_exe
    exe, pid = foreground_exe()
    if exe and pid != os.getpid() and exe not in NOT_GAME_EXE and exe != game_exe:
        game_exe = exe
        core.save_settings(game_exe=exe)
        core.log(f"Запомнил окно игры: {exe}", "ok")
