"""Сколько осталось бесплатных лимитов у переводчиков (строка «Лимиты» в панели).

- Groq: из заголовков каждого ответа (x-ratelimit-*): запросы на сегодня и токены на эту минуту.
- Gemini: заголовков нет — считаем свои запросы за сегодня.
- DeepL: раз в 10 минут спрашиваем /v2/usage — сколько символов потрачено за месяц.
Когда лимит почти кончился — один раз пишем предупреждение в журнал.
"""
import threading
import time

import requests

from . import config, core

state = {}            # имя -> dict
_warned = set()
_lock = threading.Lock()


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def note_headers(name, headers):
    """Запомнить лимиты из заголовков ответа (Groq и другие OpenAI-совместимые сервисы)."""
    req_left, req_limit = _int(headers.get("x-ratelimit-remaining-requests")), _int(headers.get("x-ratelimit-limit-requests"))
    tok_left, tok_limit = _int(headers.get("x-ratelimit-remaining-tokens")), _int(headers.get("x-ratelimit-limit-tokens"))
    if req_left is None and tok_left is None:
        return
    with _lock:
        state[name] = {"req_left": req_left, "req_limit": req_limit, "tok_left": tok_left, "tok_limit": tok_limit,
                       "t": time.time()}
    if req_left is not None and req_limit and req_left < req_limit * 0.05:
        _warn(name, f"{name}: почти кончились запросы на сегодня — осталось {req_left} из {req_limit}. "
                    "Дальше будет работать запасной переводчик.")


def count_request(name):
    """Свой счётчик запросов за сегодня (для сервисов без заголовков лимитов, например Gemini)."""
    today = time.strftime("%Y-%m-%d")
    with _lock:
        s = state.setdefault(f"{name}_count", {"day": today, "n": 0})
        if s["day"] != today:
            s.update(day=today, n=0)
        s["n"] += 1


def _warn(key, msg):
    if key not in _warned:
        _warned.add(key)
        core.log(msg, "warn")


def deepl_usage():
    """Сколько символов DeepL потрачено за месяц (запрос к /v2/usage)."""
    key = config.DEEPL_API_KEY
    if not key or "ВСТАВЬТЕ" in key:
        return None
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    try:
        r = requests.get(f"https://{host}/v2/usage", headers={"Authorization": f"DeepL-Auth-Key {key}"}, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        used, limit = int(d.get("character_count", 0)), int(d.get("character_limit", 0))
    except Exception:
        return None
    with _lock:
        state["deepl"] = {"used": used, "limit": limit, "t": time.time()}
    if limit and used > limit * 0.9:
        _warn("deepl", f"DeepL: потрачено {used:,} из {limit:,} символов за месяц — лимит почти кончился."
              .replace(",", " "))
    return used, limit


def start_deepl_checks():
    def loop():
        while True:
            deepl_usage()
            time.sleep(600)
    threading.Thread(target=loop, daemon=True, name="deepl-usage").start()


def _fmt(n):
    return f"{n:,}".replace(",", " ")


def summary():
    """Короткая строка для панели: «Groq 14 120/14 400 запр. · DeepL 12% месяца»."""
    parts = []
    with _lock:
        snap = {k: dict(v) for k, v in state.items()}
    for name in ("groq", "mistral"):
        s = snap.get(name)
        if not s:
            continue
        txt = name.capitalize()
        if s.get("req_left") is not None and s.get("req_limit"):
            txt += f" {_fmt(s['req_left'])}/{_fmt(s['req_limit'])} запр. на сегодня"
        if s.get("tok_left") is not None and s.get("tok_limit"):
            txt += f", {_fmt(s['tok_left'])}/{_fmt(s['tok_limit'])} ток./мин"
        parts.append(txt)
    g = snap.get("gemini_count")
    if g and g.get("day") == time.strftime("%Y-%m-%d"):
        parts.append(f"Gemini {g['n']} запр. сегодня")
    d = snap.get("deepl")
    if d and d.get("limit"):
        parts.append(f"DeepL {d['used'] * 100 // d['limit']}% месяца ({_fmt(d['limit'] - d['used'])} симв. осталось)")
    return " · ".join(parts) or "—"
