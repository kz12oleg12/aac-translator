"""Определение окна игры и пауза, когда игра не на экране."""

import ctypes


import os


import threading


from . import config, core


game_exe = None                # имя .exe игры — запоминается, когда вы включаете автоперевод из игры
game_active = threading.Event()
game_active.set()
NOT_GAME_EXE = {"python.exe", "pythonw.exe", "explorer.exe", "py.exe", "pyw.exe", "cmd.exe",
                "windowsterminal.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
                # браузеры, мессенджеры, лаунчеры — не игры (для них пресет не создаётся)
                "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe", "vivaldi.exe",
                "discord.exe", "telegram.exe", "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe",
                "obs64.exe", "code.exe", "notepad.exe", "notepad++.exe", "claude.exe", "taskmgr.exe",
                "applicationframehost.exe", "lockapp.exe", "textinputhost.exe"}


def _exe_of(pid):
    kernel32 = ctypes.windll.kernel32
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return None


def foreground_exe():
    """(имя .exe активного окна, pid) или (None, None)."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return _exe_of(pid.value), pid.value
    except Exception:
        return None, None


def running_programs():
    """[(exe, заголовок окна)] — программы с видимыми окнами (кроме этой и «не игр»), для «+ Добавить игру»."""
    out = {}
    try:
        user32 = ctypes.windll.user32
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def each(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):   # 4 = GW_OWNER: всплывашки
                    return True
                n = user32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid():
                    return True
                exe = _exe_of(pid.value)
                if exe and exe not in NOT_GAME_EXE and exe not in out:
                    out[exe] = buf.value
            except Exception:
                pass
            return True
        user32.EnumWindows(proto(each), 0)
    except Exception:
        return []
    return sorted(out.items(), key=lambda kv: kv[1].lower())


def is_archeage(exe):
    return bool(exe) and "archeage" in exe.lower()


def locked():
    """Пресет закреплён: программа не переключается сама и считает игрой любое окно (стриминг, эмулятор)."""
    from . import core as _c
    return bool(_c.SETTINGS.get("profile_lock"))


def is_game(exe):
    """Это окно игры? Режим «только игры из списка» — игра, для которой есть пресет; иначе — запомненная."""
    from . import profiles
    if locked():
        return bool(exe) and exe not in NOT_GAME_EXE and exe not in not_games()
    if config.GAMES_ONLY:
        return profiles.for_exe(exe) is not None
    return exe == game_exe


_blocked_logged = {"exe": None}


def blocked():
    """Ручной перевод по клавише в окне без пресета? True — не переводим (в журнал — один раз на программу)."""
    from . import profiles
    if not config.GAMES_ONLY:
        return False
    exe, pid = foreground_exe()
    if exe is None or pid == os.getpid() or profiles.for_exe(exe):
        return False
    if locked() and exe not in NOT_GAME_EXE and exe not in not_games():
        return False
    if _blocked_logged["exe"] != exe:
        _blocked_logged["exe"] = exe
        core.log(f"Для {exe} нет пресета — переводчик работает только в играх из списка. Чтобы добавить эту "
                 "игру, нажмите в ней клавишу автоперевода — программа предложит создать пресет.", "warn")
    return True


def follow_foreground():
    """Игра из списка на экране — переключиться на её пресет (области, словарь, персонажи, кэш)."""
    from . import profiles
    if locked():
        return
    exe, pid = foreground_exe()
    if not exe or pid == os.getpid():
        return
    prof = profiles.for_exe(exe)
    if prof and prof != core.active_profile:
        profiles.activate(prof)


def not_games():
    """Программы, про которые вы сказали «не игра» (в окне «Новая игра»)."""
    return set(core.SETTINGS.get("not_games", []))


def mark_not_game(exe):
    ng = sorted(not_games() | {exe.lower()})
    core.save_settings(not_games=ng)
    core.log(f"{exe} — не игра, больше не спрошу", "ok")


def unknown_game(exe=None, pid=None):
    """На экране программа, похожая на игру, но без пресета? Возвращает её exe или None."""
    from . import profiles
    if exe is None:
        exe, pid = foreground_exe()
    if locked() or not exe or pid == os.getpid() or exe in NOT_GAME_EXE or exe in not_games():
        return None
    return None if profiles.for_exe(exe) else exe


def remember_game_window():
    """Вызывается при включении автоперевода: активное сейчас окно — это игра.
    Игра из списка — включаем её пресет. Новая игра — спрашиваем, создать ли пресет (окно «Новая игра»).
    Возвращает "new", если показан вопрос про новую игру."""
    global game_exe
    from . import profiles
    exe, pid = foreground_exe()
    if not exe or pid == os.getpid():
        return None
    if exe in NOT_GAME_EXE or exe in not_games():
        if config.GAMES_ONLY:
            core.log(f"{exe} — не игра. Включите автоперевод, когда на экране игра.", "warn")
        return None
    if locked():
        return None                              # пресет закреплён — ничего не переключаем и не спрашиваем
    prof = profiles.for_exe(exe)
    if prof is None:
        core.events.put(("game_new", exe))      # окно: «Новая игра … — создать пресет?»
        return "new"
    if prof != core.active_profile:
        profiles.activate(prof)
    if exe != game_exe:
        game_exe = exe
        core.save_settings(game_exe=exe)
    return None


def create_profile_for(exe, title=None):
    """Ответ «Создать» в окне «Новая игра»."""
    global game_exe
    from . import profiles
    prof = profiles.for_exe(exe) or profiles.create(exe, title)
    profiles.activate(prof, announce=False)
    game_exe = exe
    core.save_settings(game_exe=exe)
    core.log(f"🎮 Новая игра: «{profiles.name(prof)}» — пресет создан. У неё свои области, словарь и персонажи: "
             "обведите субтитры (F9) и ответы.", "ok")
    return prof
