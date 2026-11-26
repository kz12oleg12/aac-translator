"""Окно новой панели: WebView2 (Edge) через pywebview. Отдельный процесс — см. web_api.py.

Крестик прячет окно (программа работает дальше, как и раньше). Показать снова — F6 или значок в трее.
"""
import os
import sys

TITLE = "AAC Translator"


class Api:
    """Вызывается из страницы: window.pywebview.api.…"""

    # Только поля с «_»: pywebview обходит открытые поля js_api, и объект окна там вешает окно («Не отвечает»).
    def __init__(self):
        self._window = None
        self._quitting = False
        self._hidden = False

    def toggle(self):
        w = self._window
        if w is None:
            return
        if self._hidden:
            w.show()
            w.restore()
            self._hidden = False
        else:
            w.hide()
            self._hidden = True

    def show(self):
        if self._window is not None:
            self._window.show()
            self._window.restore()
            self._hidden = False

    def hide(self):
        if self._window is not None:
            self._window.hide()
            self._hidden = True

    def save_file(self, name):
        """Окно Windows «Сохранить как» для резервной копии. Возвращает путь или пустую строку."""
        import webview
        r = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name,
                                            file_types=("Резервная копия AAC (*.zip)",))
        return (r[0] if isinstance(r, (list, tuple)) else r) or ""

    def open_file(self, kind=""):
        import webview
        types = (("Модель перевода (*.argosmodel;*.zip)", "Все файлы (*.*)") if kind == "model"
                 else ("Резервная копия AAC (*.zip)", "Все файлы (*.*)"))
        r = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=types)
        return (r[0] if r else "") or ""

    def quit(self):
        self._quitting = True
        if self._window is not None:
            self._window.destroy()


def _follow_parent(pid):
    """Программа закрылась (или её завершили) — окно панели тоже закрывается."""
    import threading

    def wait():
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x00100000, False, pid)       # SYNCHRONIZE
            if not h:
                return                                       # не удалось следить — окно живёт само
            k.WaitForSingleObject(h, 0xFFFFFFFF)
        except Exception:
            import time
            while True:                                      # не Windows: проверять раз в 2 с
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(2)
        os._exit(0)
    threading.Thread(target=wait, daemon=True).start()


def _unblock(root):
    """Файлы из скачанного архива Windows помечает «из интернета» — .NET тогда не грузит Python.Runtime.dll
    и WebView2 («Failed to resolve Python.Runtime.Loader.Initialize»). Снимаем пометку со своих .dll."""
    if sys.platform != "win32":
        return
    for d, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".dll", ".exe")):
                try:
                    os.remove(os.path.join(d, f) + ":Zone.Identifier")
                except OSError:
                    pass


def _log_path():
    try:
        from . import config
        return os.path.join(config.APP_DIR, "webpanel.log")
    except Exception:
        return None


def run(url, parent=None):
    """Открыть окно. Не вышло — причина в webpanel.log, процесс тихо завершается (программа покажет прежнюю панель)."""
    try:
        _run(url, parent)
    except Exception:
        import traceback
        p = _log_path()
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
            except OSError:
                pass
        os._exit(1)


def _run(url, parent=None):
    if parent:
        _follow_parent(parent)
    _unblock(getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable))
    import webview
    api = Api()
    here = os.path.dirname(os.path.abspath(__file__))
    icon = os.path.join(os.path.dirname(here), "icon.ico")
    w = webview.create_window(TITLE, url, js_api=api, width=1320, height=900, min_size=(980, 640),
                              background_color="#262624", text_select=True)
    api._window = w

    def closing():
        if api._quitting:
            return True
        w.hide()                 # крестик — спрятать, не закрывать
        api._hidden = True
        return False
    w.events.closing += closing
    kw = {"gui": "edgechromium"} if sys.platform == "win32" else {}
    try:
        webview.start(debug=False, icon=icon if os.path.exists(icon) else None, **kw)
    except TypeError:            # старые pywebview без icon=
        webview.start(debug=False, **kw)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
