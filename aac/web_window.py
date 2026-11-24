"""Окно новой панели: WebView2 (Edge) через pywebview. Отдельный процесс — см. web_api.py.

Крестик прячет окно (программа работает дальше, как и раньше). Показать снова — F6 или значок в трее.
"""
import os
import sys

TITLE = "AAC Translator"


class Api:
    """Вызывается из страницы: window.pywebview.api.…"""

    def __init__(self):
        self.window = None
        self.quitting = False

    def toggle(self):
        w = self.window
        if w is None:
            return
        if getattr(self, "hidden", False):
            w.show()
            w.restore()
            self.hidden = False
        else:
            w.hide()
            self.hidden = True

    def show(self):
        if self.window is not None:
            self.window.show()
            self.window.restore()
            self.hidden = False

    def quit(self):
        self.quitting = True
        if self.window is not None:
            self.window.destroy()


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


def run(url, parent=None):
    if parent:
        _follow_parent(parent)
    import webview
    api = Api()
    here = os.path.dirname(os.path.abspath(__file__))
    icon = os.path.join(os.path.dirname(here), "icon.ico")
    w = webview.create_window(TITLE, url, js_api=api, width=1320, height=900, min_size=(980, 640),
                              background_color="#262624", text_select=True)
    api.window = w

    def closing():
        if api.quitting:
            return True
        w.hide()                 # крестик — спрятать, не закрывать
        api.hidden = True
        return False
    w.events.closing += closing
    kw = {"gui": "edgechromium"} if sys.platform == "win32" else {}
    try:
        webview.start(debug=False, icon=icon if os.path.exists(icon) else None, **kw)
    except TypeError:            # старые pywebview без icon=
        webview.start(debug=False, **kw)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
