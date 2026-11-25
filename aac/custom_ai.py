"""Свои ИИ-переводчики: любой сервис с адресом, совместимым с OpenAI (OpenRouter, DeepSeek, Qwen, Together,
LM Studio на этом ПК…). Описание (название, адрес, модель) — в настройках; ключ — в Windows, как у остальных
(переменная AAC_KEY_<ID>), не в файле настроек и не в резервных копиях.

Свой переводчик работает в режиме «OCR + ИИ»: текст читается на ПК, нейросеть получает только текст —
поэтому модели не нужно уметь смотреть на картинки."""
import os
import re

import requests

from . import config, core

PREFIX = "c_"


def items():
    v = core.SETTINGS.get("custom_ai") if isinstance(core.SETTINGS, dict) else None
    return [x for x in (v or []) if isinstance(x, dict) and str(x.get("id", "")).startswith(PREFIX)]


def get(cid):
    return next((x for x in items() if x["id"] == cid), None)


def is_custom(pid):
    return str(pid or "").startswith(PREFIX)


def env_name(cid):
    return "AAC_KEY_" + re.sub(r"[^A-Z0-9]", "_", cid.upper())


def key(cid):
    return (os.environ.get(env_name(cid)) or "").strip()


def is_local(url):
    return bool(re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])", str(url or "").strip(), re.I))


def ready(cid):
    x = get(cid)
    return bool(x) and (bool(key(cid)) or is_local(x.get("url")))


def chat_url(url):
    u = str(url or "").strip().rstrip("/")
    return u if u.endswith("/chat/completions") else u + "/chat/completions"


def masked(cid):
    v = key(cid)
    return (v[:4] + "…" + v[-4:]) if len(v) > 12 else ("…" if v else "")


def register():
    """Подключить свои переводчики к остальной программе (вызывается при запуске и после изменений)."""
    from . import editor, llm, translate
    for k in [k for k in llm.OPENAI_COMPAT if is_custom(k)]:
        llm.OPENAI_COMPAT.pop(k, None)
    for k in [k for k in translate.OCR_AI if is_custom(k)]:
        translate.OCR_AI.pop(k, None)
    for k in [k for k in editor.EDITORS if is_custom(k)]:
        editor.EDITORS.pop(k, None)
    for x in items():
        cid = x["id"]
        llm.OPENAI_COMPAT[cid] = (chat_url(x["url"]), lambda c=cid: key(c) or "none",
                                  lambda m=x["model"]: [m])
        translate.OCR_AI[cid] = cid
        editor.EDITORS[cid] = (f"{x['name']} — свой", cid)


def _save(lst):
    core.save_settings(custom_ai=lst)
    if isinstance(core.SETTINGS, dict):
        core.SETTINGS["custom_ai"] = lst
    register()


def add_or_update(cid, name, url, model, api_key=None):
    """Добавить (cid=None) или изменить. Возвращает (id, None) или (None, текст ошибки)."""
    name, url, model = str(name or "").strip()[:40], str(url or "").strip(), str(model or "").strip()[:120]
    if not name or not url or not model:
        return None, "заполните название, адрес и модель"
    if not re.match(r"https?://", url, re.I):
        return None, "адрес должен начинаться с http:// или https://"
    lst = items()
    if not cid:
        base = PREFIX + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "ai")[:20]
        cid, n = base, 2
        while any(x["id"] == cid for x in lst):
            cid, n = f"{base}{n}", n + 1
        lst.append({"id": cid, "name": name, "url": url, "model": model})
    else:
        x = next((x for x in lst if x["id"] == cid), None)
        if not x:
            return None, "нет такого переводчика"
        x.update(name=name, url=url, model=model)
    if api_key:
        from . import keys
        api_key = api_key.strip().strip('"').strip("'")
        try:
            keys._write_windows(env_name(cid), api_key)
        except OSError as e:
            return None, f"не удалось сохранить ключ в Windows: {e}"
        os.environ[env_name(cid)] = api_key
    _save(lst)
    return cid, None


def remove(cid):
    lst = [x for x in items() if x["id"] != cid]
    try:
        from . import keys
        keys._write_windows(env_name(cid), None)
    except OSError:
        pass
    os.environ.pop(env_name(cid), None)
    if config.PROVIDER == cid:
        config.PROVIDER = "google"
    config.FALLBACK_PROVIDERS = [p for p in config.FALLBACK_PROVIDERS if p != cid]
    if config.EDITOR == cid:
        config.EDITOR = "groq"
    core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS, editor=config.EDITOR)
    _save(lst)


def test(name, url, model, api_key=None, cid=None):
    """Перевести тестовую фразу. (ok, текст)."""
    k = (api_key or "").strip() or (key(cid) if cid else "") or "none"
    try:
        r = requests.post(chat_url(url), headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                          json={"model": model, "max_tokens": 60, "temperature": 0.2, "messages": [
                              {"role": "user", "content": "Translate into Russian, reply with the translation only: "
                                                          "Stay close! Did you hear that?"}]}, timeout=30)
    except requests.RequestException as e:
        return False, f"нет ответа: {e.__class__.__name__}"
    if r.status_code == 401:
        return False, "неверный ключ"
    if r.status_code == 404:
        return False, "адрес или модель не найдены"
    if r.status_code != 200:
        return False, f"ошибка {r.status_code}: {core._short_error(r.text)}"
    try:
        out = r.json()["choices"][0]["message"].get("content") or ""
        if isinstance(out, list):
            out = "".join(c.get("text", "") for c in out if isinstance(c, dict))
        out = out.split("</think>", 1)[-1].strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return False, "ответ не похож на перевод"
    return bool(out), out[:120] or "пустой ответ"


def load_keys_from_windows():
    try:
        import winreg
    except ImportError:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            for x in items():
                try:
                    v, _ = winreg.QueryValueEx(k, env_name(x["id"]))
                    if str(v).strip():
                        os.environ[env_name(x["id"])] = str(v).strip()
                except FileNotFoundError:
                    pass
    except OSError:
        pass
