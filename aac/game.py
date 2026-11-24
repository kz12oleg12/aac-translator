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


# файлы, которые лежат рядом с .exe только у игр: магазины (Steam, GOG, Epic) и игровые движки
GAME_FILES = ("steam_api.dll", "steam_api64.dll", "steam_appid.txt", "galaxy.dll", "galaxy64.dll",
              "eossdk-win64-shipping.dll", "eossdk-win32-shipping.dll", "unityplayer.dll", "gameassembly.dll",
              "libhl.dll", "data.win", "fmod.dll", "fmod64.dll", "fmodstudio.dll", "fmodstudio64.dll",
              "fmodex.dll", "fmodex64.dll", "bink2w64.dll", "binkw32.dll", "binkw64.dll",
              "physx3_x64.dll", "physxcommon_64.dll", "renpy.exe", "uplay_r1_loader64.dll", "mono-2.0-bdwgc.dll")
_files_cache = {}


def has_game_files(path):
    """Рядом с .exe (или на 2 папки выше — у Unreal он в Binaries/Win64) лежат файлы движка или магазина?"""
    if not path:
        return False
    if path in _files_cache:
        return _files_cache[path]
    name = os.path.basename(path).lower()
    found = name.endswith("-shipping.exe")
    d = os.path.dirname(path)
    for _ in range(3):
        if found or not d:
            break
        try:
            names = {n.lower() for n in os.listdir(d)}
        except OSError:
            break
        found = any(f in names for f in GAME_FILES) or ("engine" in names and any(n.endswith(".uproject") or
                                                                                   n == "binaries" for n in names))
        parent = os.path.dirname(d)
        d = parent if parent != d else None
    _files_cache[path] = found
    return found


def windows_games():
    """Пути .exe, которые Windows (Xbox Game Bar) сама считает играми — из реестра GameConfigStore."""
    out = set()
    try:
        import winreg
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore\Children")
    except Exception:
        return out
    try:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, sub) as k:
                    v, _ = winreg.QueryValueEx(k, "MatchedExeFullPath")
                    if v:
                        out.add(str(v).lower())
            except OSError:
                pass
    finally:
        winreg.CloseKey(root)
    return out


_wg_cache = {"t": 0.0, "set": set()}


def in_game_folder(pid):
    """Похоже на игру по файлам: папка игр (Steam, Epic, GOG…), файлы движка рядом или Windows знает её как игру."""
    p = _path_of(pid) if pid else None
    if not p:
        return False
    if any(d in p for d in GAME_DIRS) or has_game_files(p):
        return True
    import time
    if time.time() - _wg_cache["t"] > 30:
        _wg_cache.update(t=time.time(), set=windows_games())
    return p in _wg_cache["set"]


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


def explain(exe, pid):
    """Почему программа не считается игрой — строка для журнала."""
    p = _path_of(pid) if pid else None
    if not p:
        return f"{exe}: не удалось узнать путь к файлу (программа запущена от администратора?)"
    folder = any(d in p for d in GAME_DIRS)
    files = has_game_files(p)
    win = p in windows_games()
    full = foreground_fullscreen()
    yn = lambda v: "да" if v else "нет"
    return (f"{exe} ({p}): папка игр — {yn(folder)}, файлы движка — {yn(files)}, в списке игр Windows — {yn(win)}, "
            f"на весь экран — {yn(full)}")


_explained = set()


def detect_new_game(checks_needed=6):
    """Вызывается 2 раза в секунду, без всяких клавиш. Программа без пресета — игра, если она из папки игр
    (Steam, Epic, GOG…) или 3 секунды подряд открыта на весь экран. Возвращает (exe, название) — пора создать пресет."""
    exe = unknown_game()
    if not exe or exe in skip_this_run:
        _seen_new.update(exe=None, n=0)
        return None
    _, pid = foreground_exe()
    need = 2 if in_game_folder(pid) else (checks_needed if foreground_fullscreen() else None)
    if need is None:
        _seen_new.update(exe=None, n=0)
        if _seen_new.get("why") != exe:
            _seen_new.update(why=exe, wn=0)
        _seen_new["wn"] += 1
        if _seen_new["wn"] == checks_needed * 2 and exe not in _explained:     # 6 с на экране, а не узнали
            _explained.add(exe)
            core.log("Не похоже на игру — " + explain(exe, pid) + ". Если это игра: «Игры» → «+ Добавить игру».")
        return None
    if _seen_new["exe"] != exe:
        _seen_new.update(exe=exe, n=0)
    _seen_new["n"] += 1
    if _seen_new["n"] < need:
        return None
    _seen_new.update(exe=None, n=0)
    return exe, nice_title(foreground_title(), exe)


skip_this_run = set()   # пресет удалили, пока игра запущена — до перезапуска программы сами её не добавляем
window_pids = {}      # exe → pid процесса с окном (заполняет running_programs)
_scan = {"t": 0.0}


def scan_running(every=3.0):
    """Раз в 3 с смотрим ВСЕ открытые окна, а не только активное: игра могла быть запущена раньше программы
    и сейчас стоять за её панелью. Новая игра (по папке/файлам/списку Windows) → (exe, название) для пресета.
    Если пресет на «последней» игре, а запущена другая знакомая игра — переключиться на неё."""
    import time
    from . import profiles
    now = time.time()
    if now - _scan["t"] < every or locked():
        return None
    _scan["t"] = now
    progs = running_programs()
    known = [profiles.for_exe(exe) for exe, _ in progs]
    act = core.active_profile
    if act not in known:
        others = [p for p in known if p]
        if others:
            profiles.activate(others[0])          # запущена другая знакомая игра — её пресет
        else:
            target = profiles.idle_target()       # игр нет: «Без игры» (режим проверки) или никакой
            if act != target and (act is None or profiles._hold["pid"] != act):
                was_game = act is not None and not profiles.is_free(act)
                profiles.activate(target, announce=False)
                if was_game:
                    core.log("Игра закрыта — " + ("перевожу без игры (режим проверки)" if target else "жду игру"))
    for exe, title in progs:
        if profiles.for_exe(exe) or exe in not_games() or exe in NOT_GAME_EXE or exe in skip_this_run:
            continue
        if in_game_folder(window_pids.get(exe)):
            return exe, nice_title(title, exe)
    return None


def running_programs():
    """[(exe, заголовок окна)] — программы с видимыми окнами (кроме этой и «не игр»), для «+ Добавить игру»."""
    out = {}
    try:
        user32 = ctypes.windll.user32
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def each(hwnd, _):
            try:
                hwnd = ctypes.c_void_p(hwnd)     # 64-битный адрес окна не влезает в int по умолчанию
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
                    window_pids[exe] = pid.value
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
    return True          # режим «Переводить без игры» — переводим в любом окне


_blocked_logged = {"exe": None}


def no_game():
    """Программа «ждёт игру»: ни одна игра из списка не запущена — значит, ничего не переводим.
    (Закреплённый пресет и выключенное «Только игры из списка» — исключения: там игра — любое окно.)"""
    from . import profiles
    return config.GAMES_ONLY and not locked() and not profiles.is_running()


def blocked():
    """Перевод по клавише сейчас нельзя? Нет запущенной игры или на экране не игра — не переводим
    (в журнал — один раз на причину)."""
    from . import profiles
    if not config.GAMES_ONLY:
        return False
    if no_game():
        if _blocked_logged["exe"] != "<no game>":
            _blocked_logged["exe"] = "<no game>"
            core.log("Игра не запущена — ничего не перевожу. Запустите игру, программа подхватит её сама.", "warn")
        return True
    exe, pid = foreground_exe()
    if exe is None or pid == os.getpid() or profiles.for_exe(exe):
        _blocked_logged["exe"] = None
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


def unmark_not_game(exe):
    ng = sorted(not_games() - {exe.lower()})
    core.save_settings(not_games=ng)
    _seen_new.update(exe=None, n=0)
    _scan["t"] = 0                       # сразу перепроверить открытые окна
    core.log(f"{exe} убрана из «не игр» — если это игра, программа узнает её через пару секунд", "ok")


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
    if prof is None and not config.GAMES_ONLY and not in_game_folder(pid):
        return None                              # режим без игры: обычная программа — пресет «Без игры»
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
