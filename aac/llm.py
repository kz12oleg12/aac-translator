"""Нейросети: Gemini, Claude, Ollama, Groq/Mistral (формат OpenAI); лимиты и паузы моделей."""


import re

import threading
import time


import requests


from . import capture, config, core


def call_model(model, img_b64, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{
            "parts": [{"text": prompt}] + (
                [{"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}] if img_b64 else [])
        }],
        # просим модель не «думать» долго — для перевода это не нужно
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "minimal"}},
    }
    print(f"[{time.strftime('%H:%M:%S')}] Запрос в {model}...")
    t0 = time.time()
    r = requests.post(url, params={"key": config.API_KEY}, json=body, timeout=config.REQUEST_TIMEOUT)
    if r.status_code == 400 and "thinking" in r.text.lower():
        body.pop("generationConfig")  # модель не поддерживает параметр — повторяем без него
        r = requests.post(url, params={"key": config.API_KEY}, json=body, timeout=config.REQUEST_TIMEOUT)
    print(f"  ответ {r.status_code} за {time.time() - t0:.1f} с")
    return r


# Состояние моделей Gemini за сессию: отключённые (404) пропускаем, перегруженные/упёршиеся в лимит
# отправляем «отдыхать» на время, чтобы не тратить запросы впустую.
dead_models = set()
model_cooldown = {}   # модель -> время, до которого её не трогаем


def models_status():
    """Короткая строка для системной панели: какие модели сейчас недоступны."""
    now = time.time()
    short = lambda m: m.replace("gemini-", "").split("/")[-1][:22]
    parts = [f"{short(m)}: {int(t - now)} с" for m, t in model_cooldown.items() if t > now]
    parts += [f"{short(m)}: недоступна" for m in dead_models]
    return ", ".join(parts) or "нет"


def ask_gemini(img_b64, prompt):
    t0 = time.time()
    core.stats["requests"] += 1
    seen = {}  # код ответа -> (модель, текст), чтобы в конце показать главную причину
    for model in config.MODELS:
        if model in dead_models or model_cooldown.get(model, 0) > time.time():
            continue
        r = call_model(model, img_b64, prompt)
        if r.status_code == 200:
            break
        print(r.text[:300])
        seen.setdefault(r.status_code, (model, r.text))
        if r.status_code == 404:
            dead_models.add(model)
            core.log(f"{model}: отключена Google — больше не использую", "warn")
        elif r.status_code == 429:
            model_cooldown[model] = time.time() + config.COOLDOWN_429
            core.log(f"{model}: лимит запросов, пауза {config.COOLDOWN_429} с — пробую следующую", "warn")
        elif r.status_code in (500, 503):
            model_cooldown[model] = time.time() + config.COOLDOWN_503
            core.log(f"{model}: перегружена, пауза {config.COOLDOWN_503} с — пробую следующую", "warn")
        else:
            break  # другая ошибка (ключ, запрос) — другие модели не помогут
        core.events.put(("panel", None))
    else:
        # ни одна модель не ответила (или все на паузе)
        core.events.put(("panel", None))
        if not seen:
            if all(m in dead_models for m in config.MODELS):
                raise core.ApiError("Все модели из списка MODELS отключены Google — обновите список MODELS в файле aac/config.py.")
            wait = int(min(t for m, t in model_cooldown.items() if m not in dead_models) - time.time()) + 1
            raise core.ApiError(f"Все модели Gemini на паузе (лимит/перегрузка). Ближайшая освободится через {wait} с.")
        if 429 in seen:
            raise core.RateLimited()
        if 503 in seen or 500 in seen:
            raise core.ApiError("Все модели Gemini сейчас перегружены. Подождите немного.")
        raise core.ApiError("Все модели из списка MODELS отключены Google — обновите список MODELS в файле aac/config.py.")

    if r.status_code != 200:
        if r.status_code in (400, 403) and "api key" in r.text.lower():
            raise core.ApiError("Неверный ключ Gemini (API_KEY).")
        raise core.ApiError(f"{model}: ошибка {r.status_code}: {r.text[:200]}")
    core.stats["last"] = f"{time.strftime('%H:%M:%S')} · {time.time() - t0:.1f} с · {model}"
    core.events.put(("panel", None))
    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    except (KeyError, IndexError):
        # чаще всего — ответ заблокирован фильтром или пустой
        raise core.ApiError(f"Странный ответ Gemini: {str(data)[:200]}")


def ask_ollama(img, prompt):
    img_b64 = capture.encode(img, config.OLLAMA_IMAGE_SIDE)
    core.stats["requests"] += 1
    body = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [img_b64]}],
        "stream": False,
        "think": False,            # отключаем «размышления» — для перевода не нужны, только тормозят
        "keep_alive": "30m",       # держать модель в памяти, чтобы следующие запросы были быстрыми
        "options": {
            "temperature": 0.2,
            "num_ctx": config.OLLAMA_CTX,
            "num_predict": config.OLLAMA_MAX_TOKENS,
            "repeat_penalty": 1.2,   # штраф за повторы — против зацикливания
        },
    }
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Запрос в Ollama ({config.OLLAMA_MODEL})...")
    r = requests.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.OLLAMA_TIMEOUT)
    if r.status_code == 400 and "think" in r.text.lower():
        body.pop("think")  # модель/версия не поддерживает параметр
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", json=body, timeout=config.OLLAMA_TIMEOUT)
    print(f"  ответ {r.status_code} за {time.time() - t0:.1f} с")
    if r.status_code == 404:
        raise core.ApiError(f"Модель не скачана. Выполните в командной строке: ollama pull {config.OLLAMA_MODEL}")
    if r.status_code != 200:
        raise core.ApiError(f"Ollama {r.status_code}: {r.text[:200]}")
    core.stats["last"] = f"{time.strftime('%H:%M:%S')} · {time.time() - t0:.1f} с · {config.OLLAMA_MODEL}"
    core.events.put(("panel", None))
    text = r.json().get("message", {}).get("content", "")
    # на всякий случай убираем блок размышлений, если модель его всё же выдала
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def ask_claude(img_b64, prompt):
    core.stats["requests"] += 1
    body = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": ([{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                       "data": img_b64}}] if img_b64 else [])
                       + [{"type": "text", "text": prompt}],
        }],
    }
    headers = {
        "x-api-key": config.CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Запрос в {config.CLAUDE_MODEL}...")
    r = None
    for attempt in range(3):
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body,
                          timeout=config.REQUEST_TIMEOUT)
        if r.status_code not in (500, 529):  # 529 = серверы перегружены — пробуем ещё раз
            break
        core.log(f"Claude перегружен, повтор {attempt + 1}/2", "warn")
        time.sleep(2)
    print(f"  ответ {r.status_code} за {time.time() - t0:.1f} с")
    if r.status_code == 401:
        raise core.ApiError("Неверный ключ Claude (CLAUDE_API_KEY).")
    if r.status_code == 429:
        raise core.RateLimited()
    if r.status_code == 400 and "credit" in r.text.lower():
        raise core.ApiError("На балансе Claude закончились деньги — пополните на platform.claude.com.")
    if r.status_code == 529:
        raise core.ApiError("Серверы Claude перегружены. Подождите минуту.")
    if r.status_code != 200:
        raise core.ApiError(f"Claude {r.status_code}: {r.text[:200]}")
    core.stats["last"] = f"{time.strftime('%H:%M:%S')} · {time.time() - t0:.1f} с · {config.CLAUDE_MODEL}"
    core.events.put(("panel", None))
    data = r.json()
    # считаем реальные траты по ответу API (сколько токенов ушло на картинку, инструкцию и перевод)
    usage = data.get("usage", {})
    tin = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) \
        + usage.get("cache_creation_input_tokens", 0)
    tout = usage.get("output_tokens", 0)
    core.stats["tok_in"] += tin
    core.stats["tok_out"] += tout
    core.stats["cost"] += tin / 1e6 * config.CLAUDE_PRICE_IN + tout / 1e6 * config.CLAUDE_PRICE_OUT
    total = core.stats["cost"]
    print(f"  токены: {tin} вход / {tout} выход, всего потрачено за сессию ${total:.4f}")
    _save_spent(total)
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


_spent_before = None  # потрачено в прошлых запусках


def _save_spent(session_cost):
    global _spent_before
    if _spent_before is None:
        _spent_before = core.SETTINGS.get("claude_spent", 0.0)
    core.save_settings(claude_spent=_spent_before + session_cost)


def spent_total():
    base = _spent_before if _spent_before is not None else core.SETTINGS.get("claude_spent", 0.0)
    return base + core.stats["cost"]


# ---------- Mistral и Groq: оба понимают формат OpenAI ----------
OPENAI_COMPAT = {
    "mistral": ("https://api.mistral.ai/v1/chat/completions", lambda: config.MISTRAL_API_KEY, lambda: [config.MISTRAL_MODEL]),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", lambda: config.GROQ_API_KEY, lambda: config.GROQ_MODELS),
}
provider_cooldown = {}  # переводчик -> время, до которого он «отдыхает» после лимита
_provider_locks = {}
_provider_last = {}


def _wait_turn(name):
    """Не даёт отправить запросы к одному сервису чаще, чем он разрешает."""
    lock = _provider_locks.setdefault(name, threading.Lock())
    lock.acquire()
    gap = config.PROVIDER_MIN_GAP.get(name, 0) - (time.time() - _provider_last.get(name, 0))
    if gap > 0:
        time.sleep(gap)
    return lock


def _done_turn(name, lock):
    _provider_last[name] = time.time()
    lock.release()


token_budget = {}   # модель -> (сколько токенов осталось, когда лимит обновится)
LAST_REQUEST_TOKENS = {}  # модель -> сколько токенов занял прошлый запрос (оценка следующего)


def _parse_reset(v):
    """'16.184s' / '1m26.4s' / '250ms' -> секунды."""
    if not v:
        return 0.0
    total, num = 0.0, ""
    v = v.strip()
    i = 0
    while i < len(v):
        ch = v[i]
        if ch.isdigit() or ch == ".":
            num += ch
        elif v[i:i + 2] == "ms":
            total += float(num or 0) / 1000
            num = ""
            i += 1
        elif ch in "hms":
            total += float(num or 0) * {"h": 3600, "m": 60, "s": 1}[ch]
            num = ""
        i += 1
    return total + (float(num) if num else 0.0)


def _remember_budget(model, r):
    rem = r.headers.get("x-ratelimit-remaining-tokens")
    if rem is None:
        return
    try:
        token_budget[model] = (int(float(rem)), time.time() + _parse_reset(r.headers.get("x-ratelimit-reset-tokens")))
    except ValueError:
        pass


def _wait_for_budget(model):
    """Если по прошлому ответу видно, что токенов не хватит — ждём обновления лимита (до 20 с), а не ловим отказ."""
    info = token_budget.get(model)
    if not info:
        return
    remaining, reset_at = info
    need = LAST_REQUEST_TOKENS.get(model, 1500)
    wait = reset_at - time.time()
    if remaining < need and 0 < wait <= 20:
        print(f"  {model}: осталось {remaining} токенов, нужно ~{need} — жду {wait:.1f} с")
        time.sleep(wait + 0.2)


def _compat_request(name, url, headers, body):
    """Один запрос с очередью и одним повтором при секундном лимите."""
    lock = _wait_turn(name)
    try:
        _wait_for_budget(body["model"])
        print(f"[{time.strftime('%H:%M:%S')}] Запрос в {name} ({body['model']})...")
        r = requests.post(url, headers=headers, json=body, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 400 and "reasoning" in r.text.lower():
            body.pop("reasoning_effort", None)  # модель не поддерживает параметр
            r = requests.post(url, headers=headers, json=body, timeout=config.REQUEST_TIMEOUT)
        if r.status_code == 429:
            retry = r.headers.get("Retry-After", "2")
            try:
                wait = float(retry)
            except ValueError:
                wait = 2
            if wait <= 12:  # короткая пауза — подождём и повторим; длинная — пусть берётся другая модель
                print(f"  429, жду {wait:.1f} с: {r.text[:200]}")
                time.sleep(max(wait, 1.0))
                r = requests.post(url, headers=headers, json=body, timeout=config.REQUEST_TIMEOUT)
        _remember_budget(body["model"], r)
        if r.status_code == 200:
            usage = (r.json() or {}).get("usage") or {}
            if usage.get("prompt_tokens"):
                LAST_REQUEST_TOKENS[body["model"]] = usage["prompt_tokens"] + body.get("max_tokens", 0)
    finally:
        _done_turn(name, lock)
    return r


def ask_openai_compat(name, img, prompt):
    img_b64 = capture.encode(img, config.COMPAT_IMAGE_SIDE) if img is not None else None
    url, key, models = OPENAI_COMPAT[name][0], OPENAI_COMPAT[name][1](), OPENAI_COMPAT[name][2]()
    if img_b64 is None and name == "groq":
        models = config.GROQ_TEXT_MODELS
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    core.stats["requests"] += 1
    t0 = time.time()
    rate_detail = None
    tried = 0
    for model in models:
        if model in dead_models or model_cooldown.get(model, 0) > time.time():
            continue
        tried += 1
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ] if img_b64 else prompt}],
            "max_tokens": config.COMPAT_MAX_TOKENS,
            "temperature": 0.2,
        }
        if name == "groq" and "qwen" in model:
            body["reasoning_effort"] = "none"  # без «размышлений» — быстрее
        r = _compat_request(name, url, headers, body)
        print(f"  ответ {r.status_code} за {time.time() - t0:.1f} с")
        if r.status_code == 401:
            raise core.ApiError(f"Неверный ключ {name.title()}.")
        if r.status_code == 429:
            rate_detail = core._short_error(r.text)
            m = re.search(r"try again in ([0-9.]+)(ms|s)", r.text)
            try:
                pause = int(float(r.headers.get("Retry-After", ""))) + 1
            except ValueError:
                pause = (int(float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)) + 1 if m
                         else config.PROVIDER_COOLDOWN.get(name, 60))
            model_cooldown[model] = time.time() + pause
            if len(models) > 1:
                core.log(f"{name}: {model} — лимит, пауза {pause} с, пробую следующую модель", "warn")
            continue
        if r.status_code in (404, 403) or (r.status_code == 400 and img_b64 and any(
                w in r.text.lower() for w in ("decommission", "does not exist", "not found",
                                               "image", "vision", "not supported", "must be a string"))) or (
                r.status_code == 400 and not img_b64 and any(
                w in r.text.lower() for w in ("decommission", "does not exist", "not found"))):
            dead_models.add(model)
            core.log(f"{name}: модель {model} недоступна ({core._short_error(r.text)}) — больше не использую", "warn")
            continue
        if r.status_code != 200:
            raise core.ApiError(f"{name.title()} {r.status_code}: {core._short_error(r.text)}")
        core.stats["last"] = f"{time.strftime('%H:%M:%S')} · {time.time() - t0:.1f} с · {name}: {model}"
        core.events.put(("panel", None))
        text = r.json()["choices"][0]["message"].get("content") or ""
        if isinstance(text, list):  # у некоторых моделей ответ — список кусков
            text = "".join(c.get("text", "") for c in text if isinstance(c, dict))
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        return text.strip()
    if rate_detail is not None or (tried == 0 and any(model_cooldown.get(m, 0) > time.time() for m in models)):
        raise core.RateLimited(rate_detail or "все модели на паузе")
    raise core.ApiError(f"{name.title()}: ни одна модель из списка не работает — запустите тест и обновите список.")
