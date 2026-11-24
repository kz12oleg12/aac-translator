"""«Сообщить о проблеме»: один архив со всем, что нужно, чтобы разобраться, — без ключей и личных файлов.
В архиве: журнал этого запуска, ошибки программы, версия, Windows, мониторы, переводчики, пресеты игр
и их области, какие программы открыты, журнал обновлений и настройки (ключей в настройках нет и не бывает)."""
import json
import os
import platform
import sys
import time
import zipfile

from . import config, core

SECRET_WORDS = ("key", "token", "secret", "password", "ключ")


def _clean_settings(data):
    """Настройки без всего, что похоже на ключ (на всякий случай: ключей там быть не должно)."""
    if isinstance(data, dict):
        return {k: ("<скрыто>" if any(w in str(k).lower() for w in SECRET_WORDS) else _clean_settings(v))
                for k, v in data.items()}
    if isinstance(data, list):
        return [_clean_settings(v) for v in data]
    return data


def _monitors():
    out = []
    try:
        import ctypes
        from . import screens
        u = ctypes.windll.user32
        proto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(screens._RECT),
                                   ctypes.c_double)

        def each(hmon, hdc, rect, data):
            r = rect.contents
            dpi = "?"
            try:
                x, y = ctypes.c_uint(), ctypes.c_uint()
                ctypes.windll.shcore.GetDpiForMonitor(ctypes.c_void_p(hmon), 0, ctypes.byref(x), ctypes.byref(y))
                dpi = f"{round(x.value / 96 * 100)}%"
            except Exception:
                pass
            out.append(f"{r.r - r.l}×{r.b - r.t} в ({r.l}, {r.t}), масштаб {dpi}")
            return 1
        u.EnumDisplayMonitors(None, None, proto(each), 0)
    except Exception as e:
        out.append(f"не удалось узнать: {e}")
    return out


def _info():
    from . import editor, game, keys, profiles, screens, translate
    lines = [f"AAC Translator {config.VERSION}",
             f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Windows: {platform.platform()}",
             f"Python: {sys.version.split()[0]} ({'exe' if getattr(sys, 'frozen', False) else 'python'})",
             f"Папка программы: {config.APP_DIR}",
             "", "Мониторы:"]
    lines += ["  " + m for m in _monitors()]
    lines += [f"  весь экран: {screens.virtual()}", "",
              f"Переводчики: {' → '.join(translate.provider_chain()) or 'нет'}",
              f"ИИ-редактор: {config.EDITOR if config.EDITOR_ON else 'выключен'}"
              + (" (ключа нет)" if config.EDITOR_ON and not editor.ready() else ""),
              "Ключи (только есть/нет): " + ", ".join(f"{n} — {'есть' if keys.has(k) else 'нет'}"
                                                      for k, (_, _, n, _) in keys.KEYS.items()),
              f"Только игры (без «Переводить без игры»): {config.GAMES_ONLY}",
              f"Автоперевод: {'вкл' if core.auto_on.is_set() else 'выкл'}, игра на экране: {game.game_active.is_set()}",
              "", f"Текущий пресет: {core.active_profile} ({profiles.name()})",
              f"Закреплён: {core.SETTINGS.get('profile_lock')}",
              "Области сейчас: " + ", ".join(f"{n}={getattr(core, a)}" for n, a in (
                  ("субтитры", "region"), ("реплики2", "region2"), ("ответы", "answers_region"),
                  ("чат", "chat_region"), ("меню", "menu_region"))),
              "", "Пресеты:"]
    for pid, p in profiles.all_profiles().items():
        lines.append(f"  {pid}: {p.get('name')} · файлы {p.get('exes')} · запущена: {profiles.is_running(pid)}")
    try:
        progs = game.running_programs()
        lines += ["", "Открытые программы (окна): " + ", ".join(sorted({e for e, _ in progs}))]
        exe, pid = game.foreground_exe()
        lines.append(f"Окно на экране: {exe}")
    except Exception as e:
        lines.append(f"Открытые программы: не удалось ({e})")
    lines.append(f"«Не игры»: {sorted(game.not_games())}")
    return "\n".join(lines)


def anonymize(text):
    """Убрать то, что указывает на человека: имя пользователя Windows и путь к его папке (в т.ч. OneDrive)."""
    import re
    home = os.path.expanduser("~")
    user = os.path.basename(home)
    for p in sorted({home, home.replace("\\", "/"), os.environ.get("OneDrive", ""), os.environ.get("USERPROFILE", "")},
                    key=len, reverse=True):
        if p and len(p) > 3:
            text = text.replace(p, "%USERPROFILE%")
    text = re.sub(r"(?i)[A-Z]:\\Users\\[^\\/\n\"']+", "%USERPROFILE%", text)
    if user and len(user) > 2:
        text = re.sub(re.escape(user), "<user>", text, flags=re.I)
    return text


def make(description="", screenshot=None, anonymous=False):
    """Собрать архив. description — что случилось; screenshot — PIL-картинка; anonymous — для отправки:
    без имени пользователя и путей, без списка открытых программ (кроме игр). Возвращает путь к архиву."""
    folder = os.path.join(config.APP_DIR, "reports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"aac_report_{time.strftime('%Y-%m-%d_%H-%M-%S')}.zip")
    clean = anonymize if anonymous else (lambda s: s)
    info = _info()
    if anonymous:       # список открытых программ — только игры из пресетов
        from . import profiles
        lines = []
        for ln in info.splitlines():
            if ln.startswith("Открытые программы"):
                games = sorted({e for e in ln.split(":", 1)[1].replace(" ", "").split(",") if profiles.for_exe(e)})
                ln = "Открытые игры: " + (", ".join(games) or "нет")
            lines.append(ln)
        info = "\n".join(lines)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if description:
            z.writestr("описание.txt", description)
        z.writestr("info.txt", clean(info))
        z.writestr("log.txt", clean("\n".join(f"{t} [{lvl}] {msg}" for t, lvl, msg in core.log_lines)))
        z.writestr("errors.txt", clean("\n\n".join(core.error_traces) or "ошибок программы не было"))
        try:
            with open(config.SETTINGS_FILE, encoding="utf-8") as f:
                z.writestr("settings.json", clean(json.dumps(_clean_settings(json.load(f)), ensure_ascii=False,
                                                             indent=1)))
        except Exception as e:
            z.writestr("settings.json", f"не удалось прочитать: {e}")
        upd = os.path.join(config.APP_DIR, "update.log")
        if os.path.exists(upd):
            try:
                with open(upd, encoding="utf-8", errors="replace") as f:
                    z.writestr("update.log", clean(f.read()[-200000:]))
            except OSError:
                pass
        if screenshot is not None:
            import io
            buf = io.BytesIO()
            shot = screenshot.convert("RGB")
            shot.thumbnail((2560, 2560))
            shot.save(buf, "JPEG", quality=85)
            z.writestr("снимок_экрана.jpg", buf.getvalue())
    return path


# ---------- отправка автору (Discord) ----------
def webhook():
    """Куда отправлять отчёты: вшито при сборке .exe (секрет репозитория) или своё (переменная AAC_REPORT_WEBHOOK)."""
    url = os.environ.get("AAC_REPORT_WEBHOOK", "").strip()
    if not url:
        try:
            from . import _report_target
            url = (getattr(_report_target, "REPORT_WEBHOOK", "") or "").strip()
        except ImportError:
            url = ""
    return url if url.startswith("https://") and "/api/webhooks/" in url else ""


MAX_PER_HOUR = 3


def can_send():
    """(можно ли отправить сейчас, причина если нельзя)."""
    if not webhook():
        return False, "в этой версии отправка не настроена"
    now = time.time()
    sent = [t for t in core.SETTINGS.get("reports_sent", []) if now - t < 3600]
    if len(sent) >= MAX_PER_HOUR:
        return False, f"не больше {MAX_PER_HOUR} отчётов в час — попробуйте позже"
    return True, ""


def send(description, screenshot=None, contact=""):
    """Собрать обезличенный архив и отправить автору. Возвращает (ok, сообщение)."""
    import requests
    ok, why = can_send()
    if not ok:
        return False, why
    from . import profiles
    path = make(description, screenshot, anonymous=True)
    head = (f"**AAC Translator {config.VERSION}** · игра: {profiles.name() if core.active_profile else 'нет'}"
            + (f" · связь: {contact.strip()[:80]}" if contact.strip() else "") + "\n")
    text = head + (description.strip() or "(без описания)")
    if len(text) > 1900:
        text = text[:1900] + "…"
    errs = len(core.error_traces)
    if errs:
        text += f"\n⚠ ошибок программы в этом запуске: {errs}"
    payload = {"content": text, "username": "AAC Translator", "allowed_mentions": {"parse": []}}
    files = {"files[0]": (os.path.basename(path), open(path, "rb"), "application/zip")}
    try:
        r = requests.post(webhook() + "?wait=true", data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                          files=files, timeout=60)
    except requests.exceptions.RequestException as e:
        return False, f"нет связи ({e.__class__.__name__}) — архив сохранён: {path}"
    finally:
        files["files[0]"][1].close()
    if r.status_code in (200, 204):
        sent = [t for t in core.SETTINGS.get("reports_sent", []) if time.time() - t < 3600] + [time.time()]
        core.save_settings(reports_sent=sent)
        return True, "отправлено"
    if r.status_code == 413:
        return False, f"архив слишком большой для отправки — он сохранён: {path}"
    return False, f"сервер ответил {r.status_code} — архив сохранён: {path}"


def show_in_folder(path):
    """Открыть Проводник с выделенным архивом."""
    try:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        pass
