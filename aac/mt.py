"""Машинный перевод: Google, Microsoft, DeepL."""


import re

import threading
import time


import requests


from . import config, core, glossary, history, ocr, tcache, ui_panel





def _mt_google(text, sl=None, tl=None):
    """Бесплатные адреса Google Переводчика по очереди: если один ограничен — пробуем другой."""
    errors = []
    attempts = (
        ("https://translate.googleapis.com/translate_a/single",
         {"client": "gtx", "sl": sl or config.SOURCE_LANG, "tl": tl or config.TARGET_LANG_CODE, "dt": "t", "q": text},
         "single"),
        ("https://clients5.google.com/translate_a/t",
         {"client": "dict-chrome-ex", "sl": sl or config.SOURCE_LANG, "tl": tl or config.TARGET_LANG_CODE, "q": text},
         "t"),
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
    for url, params, kind in attempts:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            errors.append(f"{url.split('/')[2]}: {e.__class__.__name__}")
            continue
        if r.status_code != 200:
            print(f"  {url.split('/')[2]} -> {r.status_code}: {r.text[:200]!r}")
            errors.append(f"{url.split('/')[2]}: код {r.status_code}")
            continue
        try:
            data = r.json()
            if kind == "single":
                return "".join(part[0] for part in data[0] if part and part[0])
            # формат dict-chrome-ex: ["перевод"] или [["перевод", "en"]]
            first = data[0] if isinstance(data, list) else data
            return first[0] if isinstance(first, list) else str(first)
        except Exception as e:
            errors.append(f"{url.split('/')[2]}: непонятный ответ ({e.__class__.__name__})")
    if all("429" in e for e in errors):
        raise core.RateLimited("Google ограничил бесплатные запросы: " + "; ".join(errors))
    raise core.ApiError("Google Переводчик не ответил: " + "; ".join(errors))


_ms_token = (None, 0.0)
_bing = {"exp": 0.0}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/130.0 Safari/537.36 Edg/130.0")


def _mt_microsoft_edge(text, sl=None, tl=None):
    """Способ 1: доступ, которым пользуется встроенный переводчик Edge."""
    global _ms_token
    token, exp = _ms_token
    if not token or time.time() > exp:
        r = requests.get("https://edge.microsoft.com/translate/auth", timeout=config.REQUEST_TIMEOUT,
                         headers={"User-Agent": _UA})
        if r.status_code != 200 or not r.text.strip():
            if r.status_code == 404:
                _bing["edge_dead"] = True  # этот способ Microsoft убрал — больше не пробуем
            raise core.ApiError(f"доступ Edge: код {r.status_code}")
        token, exp = r.text.strip(), time.time() + 8 * 60
        _ms_token = (token, exp)
    r = requests.post("https://api.cognitive.microsofttranslator.com/translate",
                      params={"api-version": "3.0", "from": sl or config.SOURCE_LANG,
                              "to": tl or config.TARGET_LANG_CODE},
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      json=[{"Text": text}], timeout=config.REQUEST_TIMEOUT)
    if r.status_code == 401:
        _ms_token = (None, 0.0)
    if r.status_code == 429:
        raise core.RateLimited("Microsoft ограничил запросы")
    if r.status_code != 200:
        raise core.ApiError(f"Edge-перевод: код {r.status_code}")
    return r.json()[0]["translations"][0]["text"]


def _mt_microsoft_bing(text, sl=None, tl=None):
    """Способ 2: как переводит страница bing.com/translator."""
    if time.time() > _bing["exp"]:
        sess = requests.Session()
        sess.headers["User-Agent"] = _UA
        r = sess.get("https://www.bing.com/translator", timeout=config.REQUEST_TIMEOUT)
        html = r.text
        ig = re.search(r'IG:"([A-Za-z0-9]+)"', html)
        iid = re.search(r'data-iid="([^"]+)"', html)
        aph = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)",(\d+)', html)
        if not (ig and aph):
            raise core.ApiError(f"страница Bing: не нашёл ключи (код {r.status_code})")
        _bing.update(sess=sess, ig=ig.group(1), iid=(iid.group(1) if iid else "translator.5028"),
                     key=aph.group(1), token=aph.group(2),
                     exp=time.time() + min(int(aph.group(3)) / 1000, 3000) - 60)
    r = _bing["sess"].post("https://www.bing.com/ttranslatev3",
                           params={"isVertical": "1", "IG": _bing["ig"], "IID": _bing["iid"] + ".1"},
                           data={"fromLang": sl or config.SOURCE_LANG, "to": tl or config.TARGET_LANG_CODE, "text": text,
                                 "token": _bing["token"], "key": _bing["key"]},
                           timeout=config.REQUEST_TIMEOUT)
    if r.status_code == 429:
        raise core.RateLimited("Bing ограничил запросы")
    try:
        data = r.json()
        return data[0]["translations"][0]["text"]
    except Exception:
        _bing["exp"] = 0.0  # ключи устарели — в следующий раз получим новые
        raise core.ApiError(f"Bing-перевод: код {r.status_code}, ответ {r.text[:120]!r}")


def _mt_microsoft(text, sl=None, tl=None):
    """Microsoft Переводчик: сначала способ Edge, если не вышло — способ bing.com."""
    errors = []
    for fn in (_mt_microsoft_edge, _mt_microsoft_bing):
        if fn is _mt_microsoft_edge and _bing.get("edge_dead"):
            continue
        try:
            return fn(text, sl, tl)
        except core.RateLimited:
            raise
        except (core.ApiError, requests.exceptions.RequestException, KeyError, IndexError, ValueError) as e:
            errors.append(str(e) or e.__class__.__name__)
            print(f"  microsoft: {errors[-1]}")
    raise core.ApiError("Microsoft Переводчик: " + "; ".join(errors))


def _mt_deepl(text):
    host = "api-free.deepl.com" if config.DEEPL_API_KEY.endswith(":fx") else "api.deepl.com"
    data = {"text": text, "source_lang": config.SOURCE_LANG.upper(), "target_lang": config.TARGET_LANG_CODE.upper(),
            "preserve_formatting": "1"}
    try:
        from . import gamefacts
        ctx = gamefacts.about()
    except Exception:
        ctx = ""
    if ctx:
        data["context"] = ctx      # описание игры: DeepL учитывает его (тон, «ты»/«вы»), но не переводит
    r = requests.post(f"https://{host}/v2/translate",
                      headers={"Authorization": f"DeepL-Auth-Key {config.DEEPL_API_KEY}"},
                      data=data, timeout=config.REQUEST_TIMEOUT)
    if r.status_code == 403:
        raise core.ApiError("Неверный ключ DeepL (DEEPL_API_KEY).")
    if r.status_code == 456:
        raise core.ApiError("У DeepL закончился лимит символов на этот месяц.")
    if r.status_code == 429:
        raise core.RateLimited("DeepL: слишком много запросов")
    if r.status_code != 200:
        raise core.ApiError(f"DeepL {r.status_code}: {r.text[:150]}")
    return "\n".join(t["text"] for t in r.json()["translations"])


def ask_ocr_mt(name, img, prompt):
    """Распознать текст на ПК и перевести машинным переводчиком."""
    t0 = time.time()
    lines = ocr.ocr_lines(img)
    t_ocr = time.time() - t0
    if not lines:
        return "НЕТ_ТЕКСТА"
    is_answers = prompt is not None and prompt.startswith("Screenshot of the player's dialogue reply options")
    history._last_src[threading.get_ident()] = "\n".join(lines)
    src = glossary.glossary_apply_source("\n".join(lines))
    key = tcache.make_key("mt-answers" if is_answers else "mt", src)
    # одинаковую фразу машинный переводчик тоже переводит один раз
    text = tcache.get(key)
    from_cache = text is not None
    if not from_cache:
        core.stats["requests"] += 1
        text = {"google": _mt_google, "microsoft": _mt_microsoft, "deepl": _mt_deepl}[name](src)
        tcache.put(key, text, "mt")
    out, seen = [], set()
    for ln in text.split("\n"):
        ln = ln.strip().strip("/").strip()
        key = re.sub(r"[^\w]", "", ln.lower())
        if ln and key and key not in seen:
            seen.add(key)
            out.append(ln)
    if is_answers:
        out = out[:8]  # вариантов ответа в игре не бывает больше
        out = [f"{i}. {ln.lstrip('0123456789.) ')}" for i, ln in enumerate(out, 1)]
    core.stats["last"] = (f"{time.strftime('%H:%M:%S')} · OCR {t_ocr:.2f} с + перевод "
                     f"{time.time() - t0 - t_ocr:.2f} с · " + ("из кэша (0 запросов)" if from_cache
                                                 else ui_panel.PROVIDER_NAMES.get(name, name)))
    core.events.put(("panel", None))
    print(f"  OCR: {src!r}")
    if config.SHOW_OCR_IN_LOG:
        core.log(f"OCR прочитал: {src.replace(chr(10), ' / ')[:150]}")
    draft = "\n".join(out)
    is_tooltip = prompt is not None and prompt.startswith("Screenshot of a tooltip")
    if not is_tooltip and draft:
        # ИИ-редактор правит черновик (падежи, род, имена, тон, контекст); не успел — показываем черновик
        from . import editor
        better = editor.improve("\n".join(lines), draft, "answers" if is_answers else "subs",
                                on_late=lambda txt, d=draft: core.events.put(("text_improve", (d, txt))))
        if better:
            return better
    return draft
