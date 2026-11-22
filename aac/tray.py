"""Значок в трее."""


import os


import threading


from PIL import Image

from . import config, core, glossary


# ---------- значок в трее (возле часов) ----------
_tray = None


def start_tray():
    """Значок программы в области уведомлений с меню. Нужна библиотека pystray."""
    global _tray
    try:
        import pystray
    except ImportError:
        core.log("Значок в трее недоступен — установите: py -m pip install pystray", "warn")
        return
    here = config.APP_DIR
    try:
        img = Image.open(os.path.join(here, "icon.ico")).convert("RGBA").resize((64, 64), Image.LANCZOS)
    except Exception:
        img = Image.new("RGBA", (64, 64), (47, 107, 255, 255))

    def put(ev):
        return lambda icon, item: core.events.put((ev, None))

    menu = pystray.Menu(
        pystray.MenuItem(f"AAC Translator v{config.VERSION}", None, enabled=False),
        pystray.MenuItem(lambda item: f"⬇ Обновить до версии {_update_version()}", put("update_install"),
                         visible=lambda item: bool(_update_version())),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Автоперевод", put("auto"), checked=lambda item: core.auto_on.is_set()),
        pystray.MenuItem("Озвучка субтитров", put("tts_toggle"), checked=lambda item: config.TTS_ENABLED),
        pystray.MenuItem("Ответы и субтитры одним окном", put("dock_toggle"),
                         checked=lambda item: config.ANSWERS_DOCKED),
        pystray.MenuItem("Системная панель", put("panel_toggle"), default=True),
        pystray.MenuItem("Скрыть / показать переводы", put("toggle")),
        pystray.MenuItem("Окна и области", put("layout")),
        pystray.MenuItem("Окна на место", put("reset")),
        pystray.MenuItem("История переводов", put("history_open")),
        pystray.MenuItem("Настройки", put("settings_open")),
        pystray.MenuItem("Словарь имён", lambda icon, item: glossary.open_glossary()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Проверить обновления", put("update_check")),
        pystray.MenuItem("Открыть папку программы", lambda icon, item: os.startfile(here)),
        pystray.MenuItem("Выход", put("quit")),
    )
    _tray = pystray.Icon("AAC Translator", img, f"AAC Translator v{config.VERSION}", menu)

    def run():
        try:
            _tray.run()
        except Exception as e:
            core.log(f"Значок в трее не запустился: {e!r}", "warn")
    threading.Thread(target=run, daemon=True).start()  # в отдельном потоке — интерфейс не ждёт трей


def stop_tray():
    if _tray is not None:
        try:
            _tray.stop()
        except Exception:
            pass


def _update_version():
    from . import updater
    info = updater.state.get("latest")
    return info["version"] if info and updater.is_newer(info["version"]) else ""


def update():
    """Обновить галочки в меню значка."""
    if _tray is not None:
        try:
            _tray.update_menu()
        except Exception:
            pass
