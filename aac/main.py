"""Запуск: одна копия программы, загрузка настроек, старт всех частей."""

import ctypes


import threading


from . import updater, tts, appwin, config, core, game, hotkeys, translate, tray, watcher


def apply_view_settings():
    """Настройки внешнего вида из файла настроек (меняются в окне «Настройки»)."""
    size = int(core.SETTINGS.get("font_size", config.FONT[1]))
    config.FONT = ("Segoe UI", size)
    config.HISTORY_FONT = ("Segoe UI", max(8, size - 2))
    config.OVERLAY_ALPHA = float(core.SETTINGS.get("overlay_alpha", config.OVERLAY_ALPHA))
    config.SHOW_ORIGINAL = bool(core.SETTINGS.get("show_original", config.SHOW_ORIGINAL))
    config.SAVE_HISTORY = bool(core.SETTINGS.get("save_history", config.SAVE_HISTORY))
    config.SHOW_OCR_IN_LOG = bool(core.SETTINGS.get("show_ocr_in_log", config.SHOW_OCR_IN_LOG))
    config.HIDE_DELAY = float(core.SETTINGS.get("hide_delay", config.HIDE_DELAY))
    config.KEEP_UNTIL_NEXT = bool(core.SETTINGS.get("keep_until_next", config.KEEP_UNTIL_NEXT))
    config.SUBS_HISTORY = int(core.SETTINGS.get("subs_history", config.SUBS_HISTORY))
    config.TTS_ENABLED = bool(core.SETTINGS.get("tts_enabled", config.TTS_ENABLED))
    config.TTS_VOICE = str(core.SETTINGS.get("tts_voice", config.TTS_VOICE))
    config.TTS_FINISH_LINE = bool(core.SETTINGS.get("tts_finish_line", config.TTS_FINISH_LINE))
    config.TTS_SILERO_VOICE = str(core.SETTINGS.get("tts_silero_voice", config.TTS_SILERO_VOICE))
    config.TTS_PER_CHARACTER = bool(core.SETTINGS.get("tts_per_character", config.TTS_PER_CHARACTER))
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
    config.ANSWERS_DOCKED = bool(core.SETTINGS.get("answers_docked", config.ANSWERS_DOCKED))
    core.answers_auto = bool(core.SETTINGS.get("answers_auto", False))
    game.game_exe = core.SETTINGS.get("game_exe")
    config.PAUSE_OUTSIDE_GAME = bool(core.SETTINGS.get("pause_outside_game", True))
    apply_view_settings()


def single_instance():
    """True — мы первая копия. Если программа уже запущена — просим её показать панель и выходим."""
    import socket
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", config.SINGLE_PORT))
    except OSError:
        try:
            with socket.create_connection(("127.0.0.1", config.SINGLE_PORT), timeout=2) as c:
                c.sendall(b"show")
        except OSError:
            pass
        return False
    srv.listen(5)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    if conn.recv(16).startswith(b"show"):
                        core.events.put(("second_copy", None))
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    return True


def main():
    if not single_instance():
        print("Переводчик уже запущен — показал его панель.")
        return
    core.SETTINGS = core.load_settings()
    apply_saved_provider()
    if not translate.provider_chain():
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "Нет ни одного ключа переводчика и не выбран Google/Microsoft.\n"
                   "Откройте файл aac/config.py и выберите PROVIDER = \"google\" "
                   "или сохраните ключ (например: setx GROQ_API_KEY \"ключ\").", "AAC Translator", 0x30)
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
