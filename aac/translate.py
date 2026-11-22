"""Выбор переводчика, цепочка запасных, режим «OCR + ИИ», очистка перевода."""


import re

import threading
import time


import requests


from . import capture, config, core, glossary, history, llm, mt, ocr, voices


def provider_has_key(name):
    name = OCR_AI.get(name, name)
    keys = {"gemini": config.API_KEY, "claude": config.CLAUDE_API_KEY, "mistral": config.MISTRAL_API_KEY, "groq": config.GROQ_API_KEY,
            "deepl": config.DEEPL_API_KEY}
    return name in ("ollama", "google", "microsoft") or "ВСТАВЬТЕ" not in keys.get(name, "ВСТАВЬТЕ")


def provider_chain():
    chain = []
    for p in [config.PROVIDER] + list(config.FALLBACK_PROVIDERS):
        if p not in chain and provider_has_key(p):
            chain.append(p)
    return chain


def provider_ready_in(name):
    """Через сколько секунд переводчик снова сможет принять запрос (0 — уже может)."""
    now = time.time()
    wait = llm.provider_cooldown.get(name, 0) - now
    name = OCR_AI.get(name, name)
    models = (config.MODELS if name == "gemini" else
              llm.OPENAI_COMPAT[name][2]() if name in llm.OPENAI_COMPAT else None)
    if models:
        alive = [m for m in models if m not in llm.dead_models]
        if not alive:
            return 10 ** 9
        wait = max(wait, min(llm.model_cooldown.get(m, 0) - now for m in alive))
    return max(0.0, wait)


def chain_ready_in():
    """Через сколько секунд хоть один переводчик из цепочки освободится."""
    chain = provider_chain()
    return min((provider_ready_in(p) for p in chain), default=0)


OCR_AI = {  # режим «OCR + ИИ»: текст распознаётся на ПК, нейросеть получает только текст (в разы меньше токенов)
    "groq_ocr": "groq", "gemini_ocr": "gemini", "claude_ocr": "claude", "mistral_ocr": "mistral",
}
OCR_BASED = ("google", "microsoft", "deepl") + tuple(OCR_AI)  # переводчики, которые сначала распознают текст на ПК
dialogue_history = []                     # [(оригинал, перевод)] последних реплик субтитров
_ai_cache = {}


def _history_context():
    if not dialogue_history:
        return ""
    lines = "\n".join(f"EN: {src.replace(chr(10), ' / ')}\nRU: {tr.replace(chr(10), ' / ')}"
                      for src, tr in dialogue_history[-config.HISTORY_LINES:])
    return "Previous lines of this conversation (context only, do NOT translate them again):\n" + lines


def ask_ocr_ai(name, img, prompt):
    """OCR на ПК + перевод нейросетью по тексту."""
    base = OCR_AI[name]
    t0 = time.time()
    lines = ocr.ocr_lines(img)
    t_ocr = time.time() - t0
    if not lines:
        return "НЕТ_ТЕКСТА"
    src = "\n".join(lines)
    history._last_src[threading.get_ident()] = src
    is_answers = prompt is not None and prompt.startswith("Screenshot of the player's dialogue reply options")
    is_tooltip = prompt is not None and prompt.startswith("Screenshot of a tooltip")
    if config.SHOW_OCR_IN_LOG:
        core.log(f"OCR прочитал: {src.replace(chr(10), ' / ')[:150]}")
    key = (base, "tip" if is_tooltip else is_answers, src)
    if key in _ai_cache:
        return _ai_cache[key]
    hint = "" if (is_tooltip or is_answers) else voices.gender_hint(src)
    if is_tooltip:   # подсказка — без истории диалога
        text_prompt = config.TEXT_TOOLTIP_PROMPT.replace("{context}", glossary.glossary_prompt(src)).replace("{text}", src)
    else:
        tpl = config.TEXT_ANSWERS_PROMPT if is_answers else config.TEXT_PROMPT
        text_prompt = tpl.replace("{context}", _history_context() + glossary.glossary_prompt(src) + hint).replace("{text}", src)
    if base == "claude":
        out = llm.ask_claude(None, text_prompt)
    elif base in llm.OPENAI_COMPAT:
        out = llm.ask_openai_compat(base, None, text_prompt)
    else:
        out = llm.ask_gemini(None, text_prompt)
    out = (out or "").strip()
    if out and "НЕТ_ТЕКСТА" not in out:
        _ai_cache[key] = out
        if len(_ai_cache) > 300:
            _ai_cache.pop(next(iter(_ai_cache)))
        if not is_answers and not is_tooltip:
            dialogue_history.append((src, out))
            del dialogue_history[:-config.HISTORY_LINES]
    core.stats["last"] = f"OCR {t_ocr:.2f} с + " + core.stats["last"]
    core.events.put(("panel", None))
    return out


def ask_text(prompt):
    """Короткий текстовый вопрос нейросети из вашей цепочки переводчиков (например, пол персонажа).
    None — в цепочке нет нейросетей (только Google/Microsoft) или все на паузе."""
    for name in provider_chain():
        base = OCR_AI.get(name, name)
        if base not in ("groq", "gemini", "claude", "mistral") or llm.provider_cooldown.get(name, 0) > time.time():
            continue
        try:
            if base == "claude":
                return llm.ask_claude(None, prompt)
            if base in llm.OPENAI_COMPAT:
                return llm.ask_openai_compat(base, None, prompt)
            return llm.ask_gemini(None, prompt)
        except Exception:
            continue
    return None


voices.ask_ai = ask_text


def _ask(name, img_b64, prompt):
    if name in OCR_AI:
        return ask_ocr_ai(name, img_b64, prompt)
    if name in ("google", "microsoft", "deepl"):
        return mt.ask_ocr_mt(name, img_b64, prompt)
    if name == "ollama":
        return llm.ask_ollama(img_b64, prompt)
    if name == "claude":
        return llm.ask_claude(img_b64, prompt)
    if name in llm.OPENAI_COMPAT:
        return llm.ask_openai_compat(name, img_b64, prompt)
    return llm.ask_gemini(img_b64, prompt)


MT_PROVIDERS = ("google", "microsoft", "deepl")


def clean_translation(text, strict=True):
    """Убираем водяной знак Windows и повторы; проверяем, что это действительно перевод."""
    lines, seen = [], set()
    for line in text.splitlines():
        low = line.strip().lower()
        if any(w in low for w in config.WATERMARK_WORDS):
            continue
        key = low.lstrip("0123456789.-) ")
        if key and key in seen:
            continue  # повтор строки — модель зациклилась
        if key:
            seen.add(key)
        lines.append(line.rstrip())
    text = "\n".join(lines).strip()
    # проверка: перевод на русский должен быть в основном кириллицей (имена в скобках — не в счёт)
    # (только для нейросетей: машинный переводчик честно оставляет имена и непереводимое латиницей)
    if strict and config.TARGET_LANG == "русский" and text and "НЕТ_ТЕКСТА" not in text:
        plain = re.sub(r"\([^)]*\)", "", text)
        cyr = sum(1 for ch in plain if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
        lat = sum(1 for ch in plain if "a" <= ch.lower() <= "z")
        if cyr + lat > 10 and cyr < 0.5 * (cyr + lat):
            raise core.ApiError("модель не перевела текст (ответ не на русском)")
    return text


def safe_translate(img, prompt=None):
    """Пробует основной переводчик, при лимите/сбое — запасные.
    Возвращает (текст или None если текста нет, сообщение об ошибке или None)."""
    history._last_src.pop(threading.get_ident(), None)
    img_b64 = capture.encode(img)
    prompt = prompt or config.PROMPT
    if prompt.startswith(("Screenshot from the MMORPG", "Screenshot of the player's", "Screenshot of a tooltip")):
        prompt = prompt + glossary.glossary_prompt()   # для перевода по картинке — весь словарь
    chain = provider_chain()
    if not chain:
        return None, "Нет ни одного ключа: впишите ключ хотя бы одного переводчика в файле aac/config.py или через setx."
    errors = []
    all_rate = True
    for name in chain:
        if llm.provider_cooldown.get(name, 0) > time.time():
            continue  # отдыхает после лимита
        try:
            text = _ask(name, img if (name in ("ollama",) + OCR_BASED or name in llm.OPENAI_COMPAT) else img_b64,
                        prompt)
            text = clean_translation(text, strict=name not in MT_PROVIDERS) if text else text
            if not text or "НЕТ_ТЕКСТА" in text:
                return None, None
            return text, None
        except core.RateLimited as e:
            pause = config.PROVIDER_COOLDOWN.get(name, 60)
            llm.provider_cooldown[name] = time.time() + pause
            err = f"лимит запросов, пауза {pause} с" + (f" [{e.detail}]" if e.detail else "")
        except core.ApiError as e:
            err, all_rate = str(e), False
        except requests.exceptions.Timeout:
            all_rate = False
            err = (f"Ollama не ответила за {config.OLLAMA_TIMEOUT} с — видеокарта не справляется" if name == "ollama"
                   else f"не ответил за {config.REQUEST_TIMEOUT} с")
        except requests.exceptions.ConnectionError as e:
            print(e)
            all_rate = False
            err = ("Ollama не запущена — запустите приложение Ollama" if name == "ollama"
                   else "нет соединения (интернет / VPN)")
        except Exception as e:
            all_rate = False
            err = f"ошибка: {e!r}"
        errors.append(f"{name}: {err}")
        if name != chain[-1]:
            core.log(f"{name}: {err} — пробую запасной переводчик", "warn")
    core.stats["errors"] += 1
    if not errors:
        active = [t for t in llm.provider_cooldown.values() if t > time.time()] or [time.time()]
        wait = int(min(active) - time.time()) + 1
        return None, f"Все переводчики на паузе после лимита. Ближайший освободится через {wait} с."
    if all_rate and len(errors) == 1:
        core.log(errors[0], "warn")  # покажем, что именно ответил сервис
        return None, "rate"
    return None, "; ".join(errors)
