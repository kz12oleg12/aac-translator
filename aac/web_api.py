"""Панель на HTML: программа отдаёт страницу и данные по адресу 127.0.0.1, окно WebView2 их показывает.

Окно панели — отдельный процесс (aac/web_window.py): tkinter и WebView2 оба хотят главный поток,
поэтому вместе в одном процессе им тесно. Связь только с этого компьютера и только с одноразовым ключом.
Если окно не отозвалось за WAIT секунд — показывается прежняя панель на tkinter.

Действия из панели выполняются в потоке tkinter: кладём в core.events ("web_call", функция).
"""
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, core

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DIR = os.path.join(HERE, "webpanel")
WAIT = 12                    # сколько ждать, пока окно панели отзовётся

_state = {"server": None, "token": None, "port": None, "proc": None, "app": None,
          "connected": False, "clients": [], "lock": threading.Lock()}

PROVIDER_NAMES = {"gemini": "Gemini", "claude": "Claude", "ollama": "Ollama", "mistral": "Mistral", "groq": "Groq",
                  "google": "Google", "deepl": "DeepL", "microsoft": "Microsoft", "groq_ocr": "Groq",
                  "gemini_ocr": "Gemini", "claude_ocr": "Claude", "mistral_ocr": "Mistral"}

# пункты меню панели → разделы прежнего окна (пока экран не перенесён на HTML)
OLD_SECTIONS = {"games": "games", "tr": "tr", "voice": "voice", "hist": "hist", "keys": "keys",
                "settings": "backup"}


def connected():
    return _state["connected"]


# ---------- события в панель (журнал, «показать/спрятать») ----------
def push(kind, data=None):
    msg = f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
    with _state["lock"]:
        for q in list(_state["clients"]):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


def push_log(t, msg, level):
    push("log", {"t": t, "msg": msg, "level": level})


# ---------- состояние для панели ----------
def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def state():
    """Всё, что показывает главная: собирается заново при каждом запросе (раз в секунду)."""
    from . import game, hotkeys, limits, profiles, tcache, translate
    on = core.auto_on.is_set()
    in_menu = bool(getattr(core, "in_menu", False))
    paused = on and (in_menu or not game.game_active.is_set())
    if not on:
        sub = "Выключен"
    elif paused:
        sub = "На паузе · открыто меню игры" if in_menu else "На паузе · игра не на экране"
    else:
        sub = "Включён"
    last = (core.stats or {}).get("last")
    if on and not paused and last and last != "—":
        sub += f" · последний перевод — {last}"
    chain = _safe(translate.provider_chain, []) or []
    editor_name = ""
    try:
        from . import editor
        editor_name = editor.name() or ""
    except Exception:
        pass
    total = tcache.stats["hits"] + tcache.stats["misses"]
    run = _safe(lambda: set(profiles.running()), set())
    games = []
    for pid, p in _safe(profiles.all_profiles, {}).items():
        if profiles.is_free(pid):
            continue
        games.append({"id": pid, "name": p.get("name") or pid, "running": pid in run,
                      "active": pid == core.active_profile})
    games.sort(key=lambda g: (not g["running"], not g["active"]))
    keys = {hid: _safe(lambda h=hid: hotkeys.K(h), "") for hid, *_ in hotkeys.HOTKEY_DEFS}
    descs = {hid: d for hid, d, *_ in hotkeys.HOTKEY_DEFS}
    bars = [{"name": n, "frac": f, "text": t} for n, f, t in (_safe(limits.bars, []) or [])]
    app = _state["app"]
    return {
        "version": config.VERSION,
        "update": getattr(getattr(app, "panel", None), "update_version", None) if app else None,
        "auto": {"on": on, "paused": paused, "sub": sub},
        "game": {"name": profiles.name() if core.active_profile else None,
                 "running": _safe(profiles.is_running, False), "free": _safe(profiles.is_free, False)},
        "games": games[:6],
        "translator": {"chain": [PROVIDER_NAMES.get(p, p) for p in chain[:3]], "editor": editor_name,
                       "editor_on": bool(getattr(config, "EDITOR_ON", False))},
        "limits": bars,
        "cache": {"pct": (100 * tcache.stats["hits"] // total) if total else None,
                  "size": _safe(tcache.size, 0), "on": config.CACHE_ENABLED},
        "modes": {
            "subs": {"ready": bool(core.region)},
            "subs2": {"ready": bool(getattr(core, "region2", None))},
            "answers": {"on": bool(getattr(core, "answers_auto", False)),
                        "ready": bool(getattr(core, "answers_region", None))},
            "chat": {"on": bool(getattr(core, "chat_auto", False)), "ready": bool(getattr(core, "chat_region", None))},
            "tts": {"on": bool(config.TTS_ENABLED)},
        },
        "stream": bool(config.SHOW_ON_STREAM),
        "update_auto": bool(getattr(config, "UPDATE_AUTO", False)),
        "keys": keys, "key_desc": descs,
    }


# ---------- действия из панели ----------
def _set(attr_owner, attr, value, setting):
    setattr(attr_owner, attr, value)
    core.save_settings(**{setting: value})


def _do(name, arg):
    """Выполняется в потоке tkinter."""
    from . import game, profiles, ui_overlay
    app = _state["app"]
    simple = {"auto", "select", "select_answers", "select_subs2", "select_chat", "tts", "toggle", "layout",
              "reset", "update_install", "update_check", "restart", "menu_learn"}
    if name in simple:
        core.events.put((name, None))
    elif name == "answers":
        core.answers_auto = bool(arg)
        core.save_settings(answers_auto=core.answers_auto)
        if not arg:
            core.events.put(("answers_hide", None))
        core.log("Автоперевод ответов " + ("включён" if arg else "выключен"), "ok")
    elif name == "chat":
        core.chat_auto = bool(arg)
        core.save_settings(chat_auto=core.chat_auto)
        core.log("Автоперевод чата " + ("включён" if arg else "выключен"), "ok")
    elif name == "stream":
        from . import chat
        config.SHOW_ON_STREAM = bool(arg)
        core.save_settings(show_on_stream=config.SHOW_ON_STREAM)
        ui_overlay.apply_stream_visibility()
        chat._state["cover_mode"] = None
        core.log("Окна перевода " + ("видны на трансляции" if arg else "скрыты от трансляции"), "ok")
    elif name == "update_auto":
        config.UPDATE_AUTO = bool(arg)
        core.save_settings(update_auto=config.UPDATE_AUTO)
    elif name == "free":                 # «Без игры»
        config.GAMES_ONLY = False
        core.save_settings(games_only=False)
        game.game_active.set()
        profiles.activate(profiles.idle_target(), announce=False)
        core.log("Перевожу без игры — в любом окне, по пресету «Без игры»", "ok")
    elif name == "game" and arg in profiles.all_profiles():
        profiles.activate(arg, hold=True)
    elif name == "old" and app is not None:      # раздел, ещё не перенесённый на HTML
        sid = OLD_SECTIONS.get(arg, arg)
        p = app.panel
        p.win.deiconify()
        p.visible = True
        if sid == "report":
            p._report()
        else:
            p.show(sid)
    elif name == "quit":
        core.events.put(("quit", None))
    else:
        return False
    core.events.put(("panel", None))
    return True


def _call(name, arg):
    done = threading.Event()
    res = {"ok": False}

    def run():
        try:
            res["ok"] = _do(name, arg)
        except Exception as e:      # ошибка действия — в журнал, панель не падает
            core.log(f"Панель: «{name}» не выполнено: {e}", "error")
        finally:
            done.set()
    core.events.put(("web_call", run))
    done.wait(5)
    return res["ok"]


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "AAC"

    def log_message(self, *a):        # не шуметь в консоли
        pass

    def _ok_token(self):
        tok = self.headers.get("X-Token") or ""
        if "?" in self.path:
            from urllib.parse import parse_qs, urlparse
            tok = tok or (parse_qs(urlparse(self.path).query).get("t") or [""])[0]
        return secrets.compare_digest(tok, _state["token"] or "-")

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if not self._ok_token():
            return self._send(403, {"error": "forbidden"})
        if path in ("/", "/index.html"):
            with open(os.path.join(PAGE_DIR, "index.html"), encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", _state["token"])
            return self._send(200, html, "text/html; charset=utf-8")
        if path == "/api/state":
            return self._send(200, state())
        if path == "/api/log":
            tail = [{"t": t[-8:], "msg": m, "level": lv} for t, lv, m in list(core.log_lines)[-200:]]
            return self._send(200, tail)
        if path == "/api/events":
            _state["connected"] = True
            return self._events()
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok_token():
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})
        if self.path.split("?")[0] == "/api/action":
            ok = _call(str(data.get("name", "")), data.get("arg"))
            return self._send(200, {"ok": ok})
        if self.path.split("?")[0] == "/api/hello":
            _state["connected"] = True
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "not found"})

    def _events(self):
        q = queue.Queue(maxsize=500)
        with _state["lock"]:
            _state["clients"].append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b": hi\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                except queue.Empty:
                    msg = b": ping\n\n"
                self.wfile.write(msg)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _state["lock"]:
                if q in _state["clients"]:
                    _state["clients"].remove(q)


def serve():
    """Запустить сервер на свободном порту 127.0.0.1. Возвращает адрес страницы."""
    if _state["server"] is None:
        _state["token"] = secrets.token_urlsafe(24)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        srv.daemon_threads = True
        _state["server"], _state["port"] = srv, srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True, name="web-panel").start()
    return f"http://127.0.0.1:{_state['port']}/?t={_state['token']}"


def _window_cmd(url):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--webpanel", url, "--parent", str(os.getpid())]
    return [sys.executable, "-m", "aac.web_window", url, str(os.getpid())]


def start(app):
    """Открыть панель на HTML вместо окна tkinter. Не вышло — остаётся прежняя панель."""
    if not getattr(config, "WEB_PANEL", True):
        return False
    try:
        import webview  # noqa: F401  (pywebview) — без неё окно не откроется
    except Exception:
        core.log("Новая панель недоступна (нет pywebview) — открыта прежняя", "warn")
        return False
    _state["app"] = app
    url = serve()
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0   # без окна консоли
        _state["proc"] = subprocess.Popen(_window_cmd(url), cwd=config.APP_DIR, creationflags=flags)
    except Exception as e:
        core.log(f"Новая панель не запустилась ({e}) — открыта прежняя", "warn")
        return False
    _wrap_panel(app)
    app.panel.win.withdraw()
    app.panel.visible = False
    t0 = time.time()

    def check():
        p = _state["proc"]
        if _state["connected"]:
            return
        if (p is not None and p.poll() is not None) or time.time() - t0 > WAIT:
            fallback("окно новой панели не открылось")
            return
        app.root.after(300, check)
    app.root.after(300, check)
    return True


def fallback(why):
    app = _state["app"]
    _state["connected"] = False
    p = _state["proc"]
    if p is not None and p.poll() is None:
        try:
            p.terminate()
        except Exception:
            pass
    if app is not None:
        app.panel.win.deiconify()
        app.panel.visible = True
        app.panel.refresh()
    core.log(f"Новая панель: {why} — открыта прежняя", "warn")


def _wrap_panel(app):
    """Журнал и «показать/спрятать» прежней панели дублируются в новую."""
    p = app.panel
    old_log, old_toggle = p.add_log, p.toggle

    def add_log(t, msg, level):
        push_log(t, msg, level)
        old_log(t, msg, level)

    def toggle():
        if _state["connected"] and _state["proc"] is not None and _state["proc"].poll() is None:
            push("toggle")
        else:
            old_toggle()
    p.add_log, p.toggle = add_log, toggle


def shutdown():
    push("quit")
    p = _state["proc"]
    if p is not None:
        try:
            p.wait(2)
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
