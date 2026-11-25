"""Запуск: одна копия программы, загрузка настроек, старт всех частей."""

import ctypes


import threading
import os
import time
import subprocess


from . import chat, limits, menu, profiles, updater, tts, appwin, config, core, game, hotkeys, translate, tray, watcher


def apply_view_settings():
    """Настройки внешнего вида из файла настроек (меняются в окне «Настройки»)."""
    size = int(core.SETTINGS.get("font_size", config.FONT[1]))
    config.FONT = ("Segoe UI", size)
    config.HISTORY_FONT = ("Segoe UI", max(8, size - 2))
    config.OVERLAY_ALPHA = float(core.SETTINGS.get("overlay_alpha", config.OVERLAY_ALPHA))
    config.SHOW_ORIGINAL = bool(core.SETTINGS.get("show_original", config.SHOW_ORIGINAL))
    config.SAVE_HISTORY = bool(core.SETTINGS.get("save_history", config.SAVE_HISTORY))
    config.GLOSSARY_AUTO = bool(core.SETTINGS.get("glossary_auto", config.GLOSSARY_AUTO))
    config.GAMES_ONLY = bool(core.SETTINGS.get("games_only", core.SETTINGS.get("only_archeage", config.GAMES_ONLY)))
    config.UPDATE_AUTO = bool(core.SETTINGS.get("update_auto", config.UPDATE_AUTO))
    config.HOTKEY_SUPPRESS = bool(core.SETTINGS.get("hotkey_suppress", config.HOTKEY_SUPPRESS))
    config.EDITOR = str(core.SETTINGS.get("editor") or config.EDITOR)
    config.EDITOR_SCENE_IMAGE = bool(core.SETTINGS.get("editor_scene_image", config.EDITOR_SCENE_IMAGE))
    config.EDITOR2 = str(core.SETTINGS.get("editor2") or "")
    config.EDITOR_ON = bool(core.SETTINGS.get("editor_on", config.EDITOR_ON))
    config.SHOW_ON_STREAM = bool(core.SETTINGS.get("show_on_stream", config.SHOW_ON_STREAM))
    config.CACHE_ENABLED = bool(core.SETTINGS.get("cache_enabled", config.CACHE_ENABLED))
    config.SKIP_SYSTEM = bool(core.SETTINGS.get("skip_system", config.SKIP_SYSTEM))
    config.CHAT_HISTORY = int(core.SETTINGS.get("chat_history", config.CHAT_HISTORY))
    config.CHAT_COVER = bool(core.SETTINGS.get("chat_cover", config.CHAT_COVER))
    config.CHAT_HEIGHT = int(core.SETTINGS.get("chat_height", config.CHAT_HEIGHT))
    config.CHAT_ALPHA = float(core.SETTINGS.get("chat_alpha", config.CHAT_ALPHA))
    config.CHAT_FG = str(core.SETTINGS.get("chat_fg", config.CHAT_FG))
    config.SHOW_INDICATOR = bool(core.SETTINGS.get("show_indicator", config.SHOW_INDICATOR))
    config.SHOW_OCR_IN_LOG = bool(core.SETTINGS.get("show_ocr_in_log", config.SHOW_OCR_IN_LOG))
    config.HIDE_DELAY = float(core.SETTINGS.get("hide_delay", config.HIDE_DELAY))
    config.KEEP_UNTIL_NEXT = bool(core.SETTINGS.get("keep_until_next", config.KEEP_UNTIL_NEXT))
    config.SUBS_HISTORY = int(core.SETTINGS.get("subs_history", config.SUBS_HISTORY))
    config.TTS_ENABLED = bool(core.SETTINGS.get("tts_enabled", config.TTS_ENABLED))
    config.TTS_VOICE = str(core.SETTINGS.get("tts_voice", config.TTS_VOICE))
    config.TTS_DUCK = bool(core.SETTINGS.get("tts_duck", config.TTS_DUCK))
    config.TTS_CACHE = bool(core.SETTINGS.get("tts_cache", config.TTS_CACHE))
    config.TTS_NO_WAIT = bool(core.SETTINGS.get("tts_no_wait", config.TTS_NO_WAIT))
    config.TTS_SKIP_FAST = bool(core.SETTINGS.get("tts_skip_fast", config.TTS_SKIP_FAST))
    config.TTS_FINISH_LINE = bool(core.SETTINGS.get("tts_finish_line", config.TTS_FINISH_LINE))
    config.TTS_SILERO_VOICE = str(core.SETTINGS.get("tts_silero_voice", config.TTS_SILERO_VOICE))
    config.TTS_PER_CHARACTER = bool(core.SETTINGS.get("tts_per_character", config.TTS_PER_CHARACTER))
    saved = core.SETTINGS.get("tts_default_voices") or {}
    for eng in config.TTS_DEFAULT_VOICES:
        config.TTS_DEFAULT_VOICES[eng].update({g: v for g, v in (saved.get(eng) or {}).items() if g in ("m", "f")})
    any_default = any(v for eng in config.TTS_DEFAULT_VOICES.values() for v in eng.values())
    # раньше «один голос на пол» включался выбором голоса в списке — сохраняем это поведение
    config.TTS_EXPRESSIVE = bool(core.SETTINGS.get("tts_expressive", config.TTS_EXPRESSIVE))
    config.TTS_VARY_IN_GENDER = bool(core.SETTINGS.get("tts_vary_in_gender", not any_default))
    config.TTS_RUSSIAN_ONLY = bool(core.SETTINGS.get("tts_russian_only", config.TTS_RUSSIAN_ONLY))
    config.TTS_ENGINE = str(core.SETTINGS.get("tts_engine", config.TTS_ENGINE))
    config.TTS_NEURAL_VOICE = str(core.SETTINGS.get("tts_neural_voice", config.TTS_NEURAL_VOICE))
    config.TTS_RATE = int(core.SETTINGS.get("tts_rate", config.TTS_RATE))
    config.TTS_VOLUME = int(core.SETTINGS.get("tts_volume", config.TTS_VOLUME))
    config.TTS_READ_NAME = bool(core.SETTINGS.get("tts_read_name", config.TTS_READ_NAME))


def apply_saved_provider():
    """Выбор переводчика из системной панели (сохранён в настройках) важнее значений в aac/config.py."""
    if core.SETTINGS.get("provider"):
        config.PROVIDER = core.SETTINGS["provider"]
    if "fallback" in core.SETTINGS:
        config.FALLBACK_PROVIDERS = list(core.SETTINGS["fallback"])
    from .ui_panel import BY_IMAGE
    chain = [config.PROVIDER] + list(config.FALLBACK_PROVIDERS)
    if any(p in BY_IMAGE for p in chain):       # режима «нейросеть по картинке» больше нет
        new = [BY_IMAGE.get(p, p) for p in chain]
        new = [p for i, p in enumerate(new) if p not in new[:i]]
        config.PROVIDER, config.FALLBACK_PROVIDERS = new[0], new[1:2]
        core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
        core.log("Переводчики: режим «нейросеть по картинке» убран — теперь текст читает программа, "
                 f"а переводит {' → '.join(new[:2])}", "ok")
    config.ANSWERS_DOCKED = bool(core.SETTINGS.get("answers_docked", config.ANSWERS_DOCKED))
    core.answers_auto = bool(core.SETTINGS.get("answers_auto", False))
    core.chat_auto = bool(core.SETTINGS.get("chat_auto", True))
    game.game_exe = core.SETTINGS.get("game_exe")
    config.PAUSE_OUTSIDE_GAME = bool(core.SETTINGS.get("pause_outside_game", True))
    apply_view_settings()


NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _port_owner_pid(port):
    """Номер процесса, который держит порт (Windows, через netstat). None — не нашли."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
        for ln in out.splitlines():
            parts = ln.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[-1].isdigit() \
                    and parts[2] in ("0.0.0.0:0", "*:*", "[::]:0"):
                return int(parts[-1])
    except Exception:
        pass
    return None


def _kill(pid):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10, creationflags=NO_WINDOW)
    except Exception:
        pass


def _ask(msg, timeout=2.0):
    """Отправить сообщение запущенной копии; ответ (строка, может быть пустой) или None — не подключились."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", config.SINGLE_PORT), timeout=timeout) as c:
            c.settimeout(timeout)
            c.sendall(msg.encode())
            try:
                return c.recv(64).decode(errors="ignore").strip()
            except OSError:
                return ""          # подключились, но не ответила: старая версия или зависла
    except OSError:
        return None


def single_instance(takeover_wait=8.0):
    """True — мы единственная копия. Если программа уже запущена:
    — та же или более новая версия и отвечает → просим её показать панель и выходим;
    — старая версия или зависла → закрываем её и запускаемся сами."""
    import socket
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", config.SINGLE_PORT))
    except OSError:
        reply = _ask(f"hello {config.VERSION}")
        if reply and reply.startswith("aac "):
            ver = (reply.split() + [""])[1]
            from . import updater
            if not updater.is_newer(config.VERSION, ver):
                _ask("show")
                return False
            print(f"Запущена старая версия {ver} — закрываю её")
            _ask("quit")
        else:
            print("Запущенная копия не отвечает (старая версия или зависла) — закрываю её")
        pid = _port_owner_pid(config.SINGLE_PORT)
        killed = False
        t0 = time.time()
        while True:
            time.sleep(0.5)
            try:
                srv.bind(("127.0.0.1", config.SINGLE_PORT))
                break
            except OSError:
                waited = time.time() - t0
                if not killed and (waited > 3 or not (reply or "").startswith("aac ")) and pid and pid != os.getpid():
                    _kill(pid)
                    killed = True
                if waited > takeover_wait:
                    return False
        core.log("Предыдущая копия программы (старая или зависшая) закрыта", "warn")
    srv.listen(5)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            try:
                with conn:
                    conn.settimeout(2)
                    msg = conn.recv(32)
                    if msg.startswith(b"hello"):
                        # окна программы живы? (главный цикл отмечается каждые 50 мс) — иначе мы «зависли»
                        alive = time.time() - core.heartbeat < 5
                        conn.sendall((f"aac {config.VERSION} {os.getpid()}" if alive else "hung").encode())
                    elif msg.startswith(b"quit"):
                        core.log("Запущена более новая версия — эта копия закрывается", "warn")
                        core.events.put(("quit", None))
                        conn.sendall(b"ok")
                    elif msg.startswith(b"show"):
                        core.events.put(("second_copy", None))
                        conn.sendall(b"ok")
                    # ждём, пока закроет собеседник: тогда «хвост» соединения остаётся у него,
                    # а порт программы сразу свободен для следующего запуска
                    conn.recv(1)
            except OSError:
                continue
    core.heartbeat = time.time()
    threading.Thread(target=serve, daemon=True).start()
    return True


def wait_pid(pid, timeout=30):
    """Подождать, пока процесс закроется (перезапуск: старая копия освобождает место новой)."""
    try:
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
        if h:
            k.WaitForSingleObject(h, int(timeout * 1000))
            k.CloseHandle(h)
        return            # Windows: процесса уже нет — ждать нечего
    except Exception:
        pass
    if os.name == "nt":
        return
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return
        time.sleep(0.2)


def _gui_state():
    """Что Windows думает о главном потоке окон: захват мыши, перетаскивание, меню (для hang.log)."""
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                        ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND),
                        ("hwndMenuOwner", wintypes.HWND), ("hwndMoveSize", wintypes.HWND),
                        ("hwndCaret", wintypes.HWND), ("rcCaret", RECT)]
        gi = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        ok = ctypes.windll.user32.GetGUIThreadInfo(threading.main_thread().native_id, ctypes.byref(gi))
        fg = ctypes.windll.user32.GetForegroundWindow()
        return (f"GUI: ok={ok} flags={gi.flags:#x} capture={gi.hwndCapture} active={gi.hwndActive} "
                f"focus={gi.hwndFocus} menu={gi.hwndMenuOwner} movesize={gi.hwndMoveSize} foreground={fg}")
    except Exception as e:
        return f"GUI: {e!r}"


def _unstick_windows():
    """Окна не отвечают: шлём им WM_CANCELMODE — Windows отменяет зависший захват мыши / модальный режим."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        tid = threading.main_thread().native_id
        hwnds = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            lambda h, l: hwnds.append(h) or True)
        user32.EnumThreadWindows(tid, proc, 0)
        for h in hwnds:
            user32.PostMessageW(h, 0x001F, 0, 0)    # WM_CANCELMODE
        core.log(f"Окна не отвечали — отправил им сигнал «отменить зависший режим» ({len(hwnds)} окон)", "warn")
    except Exception:
        pass


def _watchdog():
    """Если окна программы перестали отвечать дольше 8 с — записываем, чем занят каждый поток, в hang.log.
    Когда отвиснет — пишем в журнал, сколько висела (файл помогает найти причину)."""
    import sys
    import traceback
    path = os.path.join(config.APP_DIR, "hang.log")
    dumped_at = None
    kicked = False
    while True:
        time.sleep(2)
        if not core.heartbeat:
            continue
        stale = time.time() - core.heartbeat
        if stale > 8 and dumped_at is None:
            dumped_at = time.time() - stale
            try:
                names = {t.ident: t.name for t in threading.enumerate()}
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} v{config.VERSION}: окна не отвечают "
                            f"{stale:.0f} с =====\n")
                    f.write(_gui_state() + "\n")
                    for ident, frame in sys._current_frames().items():
                        f.write(f"\n--- поток {names.get(ident, ident)} ---\n")
                        f.write("".join(traceback.format_stack(frame)))
            except Exception:
                pass
        if stale > 5 and not kicked:
            kicked = True
            _unstick_windows()            # попробовать «растолкать» окна (отменить зависший режим мыши)
        if stale < 2:
            kicked = False
        if stale < 2 and dumped_at is not None:
            core.log(f"Программа подвисала на {time.time() - dumped_at:.0f} с. Что она делала — записано в файл "
                     "hang.log в папке программы, пришлите его, пожалуйста.", "warn")
            dumped_at = None


def main():
    import sys
    if "--webpanel" in sys.argv:      # окно новой панели (отдельный процесс, см. web_api.py)
        from . import web_window
        a = sys.argv
        web_window.run(a[a.index("--webpanel") + 1], int(a[a.index("--parent") + 1]) if "--parent" in a else None)
        return
    try:
        from . import keys
        keys.load_from_windows()      # ключи и адрес для отчётов — из Windows, даже после «Перезапустить»
    except Exception:
        pass
    try:
        from . import voicepack
        voicepack.activate()          # скачанные офлайн-голоса (.exe) — подключить до первого голоса
    except Exception:
        pass
    try:   # если программа упадёт целиком — причина попадёт в crash.log
        import faulthandler
        faulthandler.enable(open(os.path.join(config.APP_DIR, "crash.log"), "a"))
    except Exception:
        pass
    threading.Thread(target=_watchdog, daemon=True, name="watchdog").start()
    if "--after-pid" in sys.argv:   # кнопка «Перезапустить»
        try:
            wait_pid(sys.argv[sys.argv.index("--after-pid") + 1])
        except (IndexError, ValueError):
            pass
    if not single_instance():
        print("Переводчик уже запущен — показал его панель.")
        return
    core.SETTINGS = core.load_settings()
    try:              # окно панели по ошибке приняли за игру — убираем такой пресет
        from . import profiles as _pr
        _pr.drop_self()
    except Exception:
        pass
    try:              # свои ИИ-переводчики: ключи из Windows и подключение к остальной программе
        from . import custom_ai
        custom_ai.load_keys_from_windows()
        custom_ai.register()
    except Exception as e:
        print(f"Свои переводчики не подключились: {e}")
    if "profiles" not in core.SETTINGS:
        core.save_settings(profiles=profiles.all_profiles())
    config.GAMES_ONLY = bool(core.SETTINGS.get("games_only", config.GAMES_ONLY))   # нужен до выбора пресета
    lock = core.SETTINGS.get("profile_lock")
    if lock in profiles.all_profiles():
        core.active_profile = lock                # закреплённый пресет — всегда он
        core.apply_profile_regions(profiles.all_profiles()[lock])
    elif not profiles.is_running(core.active_profile):
        # игра не запущена — пресет не выбран («ждёт игру») или «Без игры» в режиме проверки
        core.active_profile = profiles.idle_target()
        core.apply_profile_regions(profiles.all_profiles().get(core.active_profile) or {})
    core.save_settings(active_profile=core.active_profile)
    profiles.bind(core.active_profile)          # файлы пресета текущей игры: словарь, персонажи, кэш, меню
    apply_saved_provider()
    if not translate.provider_chain():
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "Нет ни одного ключа переводчика и не выбран Google/Microsoft.\n"
                   "Откройте в программе «Переводчики»: выберите Google Переводчик (без ключа) "
                   "или нажмите «Ключ» у нужной нейросети и вставьте ключ.", "AAC Translator", 0x30)
        except Exception:
            pass
        print("Нет ни одного ключа. Впишите ключ хотя бы одного переводчика в aac/config.py или сохраните через setx:")
        print("  Gemini  (бесплатно): https://aistudio.google.com/apikey  -> API_KEY / GEMINI_API_KEY")
        print("  Mistral (бесплатно): https://console.mistral.ai          -> MISTRAL_API_KEY")
        print("  Groq    (бесплатно): https://console.groq.com            -> GROQ_API_KEY")
        print("  Claude  (платно):    https://platform.claude.com         -> CLAUDE_API_KEY / ANTHROPIC_API_KEY")
        return
    if not translate.provider_has_key(config.PROVIDER):
        print(f"Внимание: у основного переводчика ({config.PROVIDER}) нет ключа — буду использовать: "
              f"{', '.join(translate.provider_chain())}")

    hotkeys.load_hotkeys()
    app = appwin.App()
    tts.warm()   # озвучка: прогрев соединения и звука в фоне
    updater.start_periodic()   # есть ли новая версия на GitHub
    limits.start_deepl_checks()
    chat.start()               # перевод игрового чата (если обведена его область)
    menu.start()               # пауза, пока открыто меню игры (если меню запомнено)   # сколько символов DeepL осталось (если есть ключ)
    for w in watcher.WATCHERS:
        threading.Thread(target=w.run, daemon=True).start()

    hotkeys.register_hotkeys()
    hotkeys.start_mouse_listener()
    tray.start_tray()
    if not hotkeys.MOUSE_OK:
        core.log("Боковые кнопки мыши недоступны — установите: py -m pip install pynput", "warn")
    print("Переводчик запущен. Клавиши:")
    for hid, desc, _, _ in hotkeys.HOTKEY_DEFS:
        print(f"  {hotkeys.K(hid):<14} {desc}")
    print("Клавиши можно переназначить в системной панели (кнопка «изменить»).")
    app.root.mainloop()
