"""Ключи переводчиков: ввод прямо в программе. Ключ сохраняется в переменные среды Windows
(HKCU\\Environment — то же, что делает «setx»), а не в настройки программы: он не попадает ни в файл
настроек, ни в резервные копии, ни на GitHub. Подхватывается сразу, без перезапуска. Ключ нигде не печатается."""
import os

import requests

from . import config, core

# переводчик → (переменная Windows, поле в config, название, где взять ключ)
KEYS = {
    "groq": ("GROQ_API_KEY", "GROQ_API_KEY", "Groq", "console.groq.com → API Keys → Create API Key"),
    "gemini": ("GEMINI_API_KEY", "API_KEY", "Gemini", "aistudio.google.com → Get API key"),
    "mistral": ("MISTRAL_API_KEY", "MISTRAL_API_KEY", "Mistral", "console.mistral.ai → API Keys"),
    "deepl": ("DEEPL_API_KEY", "DEEPL_API_KEY", "DeepL", "deepl.com → Аккаунт → API-ключи (план DeepL API Free)"),
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "Claude", "console.anthropic.com → API Keys (платно)"),
}
ALIASES = {"groq_ocr": "groq", "gemini_ocr": "gemini", "mistral_ocr": "mistral", "claude_ocr": "claude"}


def load_from_windows():
    """Перечитать сохранённые ключи (и адрес для отчётов) прямо из Windows (HKCU\\Environment).
    Нужно, когда программу перезапустили из неё самой: новая копия получает старые переменные, без тех,
    что сохранили после её запуска (setx или кнопкой «Ключ» в другой копии). Возвращает, что подхватили."""
    try:
        import winreg
    except ImportError:
        return []
    got = []
    names = [env for env, _, _, _ in KEYS.values()] + ["AAC_REPORT_WEBHOOK"]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in names:
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                value = str(value or "").strip()
                if value and os.environ.get(name) != value:
                    os.environ[name] = value
                    got.append(name)
    except OSError:
        return got
    for k, (env, attr, _, _) in KEYS.items():       # ключи — сразу в настройки программы
        v = os.environ.get(env, "").strip()
        if v:
            setattr(config, attr, v)
    return got


def kind(pid):
    """id из списка переводчиков → чей это ключ (или None — ключ не нужен)."""
    pid = ALIASES.get(pid, pid)
    return pid if pid in KEYS else None


def has(pid):
    k = kind(pid)
    if not k:
        return True
    v = (getattr(config, KEYS[k][1], "") or "").strip()
    return bool(v) and "ВСТАВЬТЕ" not in v


def masked(pid):
    """Для показа: «gsk_…a1b2» — без самого ключа."""
    k = kind(pid)
    v = (getattr(config, KEYS[k][1], "") or "").strip() if k else ""
    if not v or "ВСТАВЬТЕ" in v:
        return ""
    return (v[:4] + "…" + v[-4:]) if len(v) > 12 else "…"


def _write_windows(name, value):
    """Записать (value=None — удалить) переменную пользователя Windows и сообщить об этом системе."""
    try:
        import winreg
    except ImportError:
        return False            # не Windows (проверки) — только в памяти программы
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    try:        # другие программы (и следующий запуск) увидят новое значение без перезахода в Windows
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, None)
    except Exception:
        pass
    return True


def save(pid, value):
    """Сохранить ключ: Windows + сразу в программу. Возвращает текст ошибки или None."""
    k = kind(pid)
    if not k:
        return "этому переводчику ключ не нужен"
    value = (value or "").strip().strip('"').strip("'").strip()
    if not value or len(value) < 8 or any(c.isspace() for c in value):
        return "это не похоже на ключ: вставьте его целиком, без пробелов"
    env, attr, _, _ = KEYS[k]
    try:
        _write_windows(env, value)
    except OSError as e:
        return f"не удалось сохранить в Windows: {e}"
    os.environ[env] = value
    setattr(config, attr, value)
    return None


def remove(pid):
    k = kind(pid)
    if not k:
        return
    env, attr, name, _ = KEYS[k]
    try:
        _write_windows(env, None)
    except OSError:
        pass
    os.environ.pop(env, None)
    setattr(config, attr, "")
    core.log(f"Ключ {name} удалён из Windows", "ok")


def check(pid):
    """Проверить ключ лёгким запросом (список моделей / остаток лимита). (ok, сообщение)."""
    k = kind(pid)
    if not k or not has(pid):
        return False, "ключа нет"
    v = getattr(config, KEYS[k][1]).strip()
    try:
        if k == "groq":
            r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {v}"},
                             timeout=15)
        elif k == "mistral":
            r = requests.get("https://api.mistral.ai/v1/models", headers={"Authorization": f"Bearer {v}"},
                             timeout=15)
        elif k == "gemini":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             headers={"x-goog-api-key": v}, timeout=15)
        elif k == "deepl":
            host = "api-free.deepl.com" if v.endswith(":fx") else "api.deepl.com"
            r = requests.get(f"https://{host}/v2/usage", headers={"Authorization": f"DeepL-Auth-Key {v}"},
                             timeout=15)
        else:
            r = requests.get("https://api.anthropic.com/v1/models",
                             headers={"x-api-key": v, "anthropic-version": "2023-06-01"}, timeout=15)
    except requests.exceptions.RequestException as e:
        return False, f"нет связи с сервером ({e.__class__.__name__}) — ключ сохранён, проверю при переводе"
    if r.status_code == 200:
        return True, "ключ рабочий"
    if r.status_code in (401, 403):
        return False, "сервер не принял ключ — проверьте, что скопировали его целиком"
    if r.status_code == 429:
        return True, "ключ рабочий (сейчас лимит запросов)"
    return False, f"ответ сервера {r.status_code} — ключ сохранён, проверю при переводе"
