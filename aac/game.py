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
                "applicationframehost.exe", "lockapp.exe", "textinputhost.exe",
                # лаунчеры, плееры и прочее, что бывает на весь экран, но не игра
                "galaxyclient.exe", "battle.net.exe", "eadesktop.exe", "upc.exe", "ubisoftconnect.exe",
                "riotclientservices.exe", "riotclientux.exe", "vkplay.exe", "gamecenter.exe", "msedgewebview2.exe",
                "vlc.exe", "mpv.exe", "mpc-hc.exe", "mpc-hc64.exe", "mpc-be.exe", "mpc-be64.exe", "potplayer.exe",
                "potplayermini.exe", "potplayermini64.exe", "wmplayer.exe", "video.ui.exe", "spotify.exe",
                "powerpnt.exe", "winword.exe", "excel.exe", "acrord32.exe", "acrobat.exe", "zoom.exe", "teams.exe",
                "ms-teams.exe", "slack.exe", "obs32.exe", "streamlabs obs.exe", "nvidia overlay.exe", "gamebar.exe",
                "snippingtool.exe", "screenclippinghost.exe", "photos.exe", "microsoft.photos.exe"}
# папки, куда ставят игры лаунчеры: программа оттуда — игра, даже в окне
GAME_DIRS = ("\\steamapps\\common\\", "\\epic games\\", "\\gog galaxy\\games\\", "\\gog games\\",
             "\\xboxgames\\", "\\riot games\\", "\\ubisoft game launcher\\games\\", "\\ea games\\",
             "\\vk play\\", "\\games\\", "\\игры\\")


def _path_of(pid):
    """Полный путь к .exe процесса (в нижнем регистре) или None."""
    try:
        kernel32 = ctypes.windll.kernel32
    except Exception:
        return None
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.lower()
    finally:
        kernel32.CloseHandle(h)
    return None


def _exe_of(pid):
    p = _path_of(pid)
    return os.path.basename(p) if p else None


def in_game_folder(pid):
    """Программа установлена в папку игр (Steam, Epic, GOG, Xbox, Riot…)?"""
    p = _path_of(pid) if pid else None
    return bool(p) and any(d in p for d in GAME_DIRS)


def foreground_title():
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value.strip()
    except Exception:
        return ""


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


class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class _MONINFO(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("mon", _RECT), ("work", _RECT), ("flags", ctypes.c_ulong)]


def foreground_fullscreen():
    """Активное окно закрывает весь монитор (полный экран или окно без рамки) — так выглядят игры."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):     # рабочий стол и панель задач
            return False
        r = _RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        mi = _MONINFO()
        mi.cb = ctypes.sizeof(_MONINFO)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
        m = mi.mon
        return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b
    except Exception:
        return False


_seen_new = {"exe": None, "n": 0}


def nice_title(title, exe):
    """Название игры из заголовка окна («ELDEN RING™» → «ELDEN RING»); пустой или странный — из имени файла."""
    from . import profiles
    import re
    t = re.sub(r"[™®©]", "", title or "").strip()
    t = re.split(r"\s+[-–—|]\s+(?:v?\d|build|direct|vulkan|opengl|dx\d)", t, flags=re.I)[0].strip()
    return t if 2 <= len(t) <= 40 else profiles._pretty(exe)


def detect_new_game(checks_needed=6):
    """Вызывается 2 раза в секунду, без всяких клавиш. Программа без пресета — игра, если она из папки игр
    (Steam, Epic, GOG…) или 3 секунды подряд открыта на весь экран. Возвращает (exe, название) — пора создать пресет."""
    exe = unknown_game()
    if not exe:
        _seen_new.update(exe=None, n=0)
        return None
    _, pid = foreground_exe()
    need = 2 if in_game_folder(pid) else (checks_needed if foreground_fullscreen() else None)
    if need is None:
        _seen_new.update(exe=None, n=0)
        return None
    if _seen_new["exe"] != exe:
        _seen_new.update(exe=exe, n=0)
    _seen_new["n"] += 1
    if _seen_new["n"] < need:
        return None
    _seen_new.update(exe=None, n=0)
    return exe, nice_title(foreground_title(), exe)


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
        core.log(f"{exe} — не игра (или программа её не узнала), здесь не перевожу. Если это игра: "
                 "раздел «Игры» → «+ Добавить игру» или клавиша автоперевода в самой игре.", "warn")
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
    if prof is None:                             # новая игра — пресет создаётся сам, без вопросов
        prof = create_profile_for(exe, nice_title(foreground_title(), exe))
        core.events.put(("game_created", prof))
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
    from . import hotkeys
    core.log(f"🎮 Новая игра: «{profiles.name(prof)}» — пресет создан. У неё свои области, словарь и персонажи: "
             f"обведите субтитры ({hotkeys.K('select')}) и ответы.", "ok")
    return prof
