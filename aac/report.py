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


def make():
    """Собрать архив. Возвращает путь к нему."""
    folder = os.path.join(config.APP_DIR, "reports")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"aac_report_{time.strftime('%Y-%m-%d_%H-%M-%S')}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", _info())
        z.writestr("log.txt", "\n".join(f"{t} [{lvl}] {msg}" for t, lvl, msg in core.log_lines))
        z.writestr("errors.txt", "\n\n".join(core.error_traces) or "ошибок программы не было")
        try:
            with open(config.SETTINGS_FILE, encoding="utf-8") as f:
                z.writestr("settings.json", json.dumps(_clean_settings(json.load(f)), ensure_ascii=False, indent=1))
        except Exception as e:
            z.writestr("settings.json", f"не удалось прочитать: {e}")
        upd = os.path.join(config.APP_DIR, "update.log")
        if os.path.exists(upd):
            z.write(upd, "update.log")
    return path


def show_in_folder(path):
    """Открыть Проводник с выделенным архивом."""
    try:
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        pass
