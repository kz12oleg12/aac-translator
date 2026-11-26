"""Groq один раз на игру собирает то, что знает о ней: словарь имён и терминов, персонажей с полом
и короткое описание мира и тона. Это помогает любому переводчику:
- словарь программа подставляет и Google, и Microsoft, и DeepL (имена переводятся всегда одинаково);
- пол персонажей — озвучке (голос) и роду в переводе («сказал»/«сказала»);
- описание уходит в «контекст» DeepL и в подсказку нейросетям-переводчикам.
Ничего вашего не перезаписывается: в словарь и персонажей добавляется только то, чего там ещё нет."""
import json
import os
import re
import threading
import time

from . import config, core

PROMPT = """You help translate the video game "{title}" (executable: {exe}) from English to Russian.
If you do not know this exact game well, reply with {{"known": false}}.
Otherwise reply with JSON only:
{{"known": true,
 "description": "2-3 sentences in English: genre, world/setting, tone of dialogue, whether characters address each other formally or informally",
 "terms": [{{"en": "Original", "ru": "Перевод"}}],
 "characters": [{{"en": "Name", "ru": "Имя", "gender": "m"}}]}}
terms: up to 60 proper names and recurring game terms (places, factions, items, skills, enemies, UI words).
Use the official Russian localization if the game has one; otherwise a natural Russian transliteration or translation.
characters: up to 30 named characters who speak in the game; gender is "m" or "f".
Do not invent anything you are not sure about."""

_running = set()
AI_HEADER = "# ---- собрано ИИ (Groq) для этой игры — можно исправить или удалить строку ----"


def available():
    key = (config.GROQ_API_KEY or "").strip()
    return bool(key) and "ВСТАВЬТЕ" not in key


def ask(title, exe):
    """Спросить Groq. Возвращает dict (может быть {"known": False}) или бросает core.ApiError."""
    from . import llm
    url = llm.OPENAI_COMPAT["groq"][0]
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}", "Content-Type": "application/json"}
    models = sorted(config.GROQ_TEXT_MODELS, key=lambda m: "120b" not in m)   # самая знающая — первой
    last = None
    for model in models:
        if model in llm.dead_models:
            continue
        body = {"model": model, "temperature": 0.2, "max_tokens": 3500,
                "messages": [{"role": "user", "content": PROMPT.format(title=title, exe=exe)}],
                "response_format": {"type": "json_object"}}
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"
        elif "qwen" in model:
            body["reasoning_effort"] = "none"
        r = llm._compat_request("groq", url, headers, body)
        if r.status_code == 400 and ("response_format" in r.text or "json" in r.text.lower()):
            body.pop("response_format", None)        # модель не умеет «только JSON» — просим словами, разберём сами
            r = llm._compat_request("groq", url, headers, body)
        if r.status_code == 401:
            raise core.ApiError("Неверный ключ Groq (GROQ_API_KEY).")
        if r.status_code != 200:
            last = f"Groq {r.status_code}: {core._short_error(r.text)}"
            continue
        text = r.json()["choices"][0]["message"].get("content") or ""
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        return parse(text)
    raise core.ApiError(last or "Groq: нет доступной модели")


def parse(text):
    """JSON из ответа (бывает обёрнут в ```json … ```). Неверные записи выбрасываются."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict) or not data.get("known"):
        return {"known": False}
    ok = lambda s, n: isinstance(s, str) and 0 < len(s.strip()) <= n
    terms = [(t["en"].strip(), t["ru"].strip()) for t in data.get("terms") or []
             if isinstance(t, dict) and ok(t.get("en"), 40) and ok(t.get("ru"), 50)
             and re.match(r"^[A-Za-z0-9]", t["en"].strip()) and t["en"].strip().lower() != t["ru"].strip().lower()]
    chars = [(c["en"].strip(), (c.get("ru") or "").strip(), c.get("gender"))
             for c in data.get("characters") or []
             if isinstance(c, dict) and ok(c.get("en"), 40) and c.get("gender") in ("m", "f")]
    desc = data.get("description") if ok(data.get("description"), 600) else ""
    return {"known": True, "description": desc.strip(), "terms": terms[:60], "characters": chars[:30]}


def apply(pid, data):
    """Записать собранное в пресет pid: описание, словарь, персонажи. Возвращает (терминов, персонажей)."""
    from . import glossary, profiles, voices
    paths = profiles.paths(pid)
    profs = profiles.all_profiles()
    if pid not in profs:
        return 0, 0
    profs[pid]["facts_at"] = int(time.time())
    profs[pid]["facts_known"] = bool(data.get("known"))
    if data.get("description"):
        profs[pid]["about"] = data["description"]
    core.save_settings(profiles=profs)
    if not data.get("known"):
        return 0, 0
    # словарь: только новые записи, в конец файла под своим заголовком
    try:
        with open(paths["glossary"], encoding="utf-8-sig") as f:
            content = f.read()
    except OSError:
        content = ""
    have = {ln.split("=", 1)[0].strip().lower() for ln in content.splitlines() if "=" in ln and not ln.startswith("#")}
    have |= {ln[1:].strip().lower() for ln in content.splitlines() if ln.startswith("-")}
    add = [(en, ru) for en, ru in data["terms"] if en.lower() not in have]
    if add:
        os.makedirs(os.path.dirname(paths["glossary"]), exist_ok=True)
        with open(paths["glossary"], "a", encoding="utf-8") as f:
            f.write(("" if not content or content.endswith("\n") else "\n") + "\n" + AI_HEADER + "\n"
                    + "".join(f"{en} = {ru}\n" for en, ru in add))
        if pid == core.active_profile:
            glossary._glossary.update(mtime=None, loaded=False)
    # персонажи: новые — с полом от ИИ; у уже известных — пол от ИИ, если вы его не задали сами
    try:
        with open(paths["characters"], encoding="utf-8") as f:
            chars = json.load(f)
    except (OSError, ValueError):
        chars = {}
    n_chars = 0
    for en, ru, g in data["characters"]:
        found = next((k for k, c in chars.items() if voices._same_char({"en": en, "ru": ru}, c)), None)
        if found is None:
            chars[voices.key_of(en)] = {"en": en, "ru": ru, "ai": g, "guess": g, "f": 0, "m": 0, "from_ai": True}
            n_chars += 1
        elif chars[found].get("ai") not in ("m", "f") and not chars[found].get("gender_manual"):
            chars[found]["ai"] = g
    if n_chars or data["characters"]:
        tmp = paths["characters"] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(chars, f, ensure_ascii=False, indent=1)
        os.replace(tmp, paths["characters"])
        if pid == core.active_profile:
            with voices._lock:
                voices._data["loaded"] = False
    return len(add), n_chars


def gather(pid, force=False, wait=False):
    """Собрать данные об игре в фоне (один раз; force — заново). Без ключа Groq — ничего не делаем."""
    from . import profiles
    p = profiles.all_profiles().get(pid)
    if not p or p.get("free") or p.get("test") or pid in _running or not available():
        return False
    if p.get("facts_at") and not force:
        return False
    _running.add(pid)
    title = p.get("name", pid)
    exe = (p.get("exes") or [pid])[0]

    def run():
        try:
            core.log(f"🤖 Groq собирает данные об игре «{title}»: имена, термины, персонажи…")
            data = ask(title, exe)
            n_terms, n_chars = apply(pid, data)
            if data.get("known"):
                core.log(f"🤖 Для «{title}» собрано: терминов в словарь — {n_terms}, новых персонажей — {n_chars}"
                         + (", описание мира и тона — есть" if data.get("description") else ""), "ok")
            else:
                desc = steam_about(title)
                if desc:
                    profs = profiles.all_profiles()
                    if pid in profs and not profs[pid].get("about"):
                        profs[pid]["about"] = desc
                        core.save_settings(profiles=profs)
                    core.log(f"🤖 Groq пока не знает «{title}» (новая игра?) — взял описание из Steam, оно поможет "
                             "переводу. Имена и термины словарь соберёт по ходу игры.", "ok")
                else:
                    core.log(f"🤖 Groq не знает игру «{title}» — ничего страшного: словарь и персонажи соберутся по ходу "
                             "игры. Можно помочь — впишите пару строк в «Об игре» на странице игры.", "warn")
        except Exception as e:
            core.log(f"🤖 Не удалось собрать данные об игре «{title}»: {e}", "warn")
        finally:
            _running.discard(pid)
            core.events.put(("panel", None))
    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return True


def steam_about(title):
    """Короткое описание игры со страницы Steam (английское) или "" — для новых игр, которых ИИ ещё не знает."""
    import html
    import requests
    try:
        r = requests.get("https://store.steampowered.com/api/storesearch/",
                         params={"term": title, "l": "english", "cc": "US"}, timeout=8)
        items = (r.json() or {}).get("items") or []
        want = re.sub(r"[^a-z0-9]", "", title.lower())
        app = next((i for i in items if re.sub(r"[^a-z0-9]", "", i.get("name", "").lower()) == want), None) \
            or next((i for i in items if want and want in re.sub(r"[^a-z0-9]", "", i.get("name", "").lower())), None)
        if not app:
            return ""
        d = requests.get("https://store.steampowered.com/api/appdetails",
                         params={"appids": app["id"], "l": "english"}, timeout=8).json()
        info = (d.get(str(app["id"])) or {}).get("data") or {}
        text = html.unescape(re.sub(r"<[^>]+>", " ", info.get("short_description") or ""))
        text = re.sub(r"\s+", " ", text).strip()
        genres = ", ".join(g.get("description", "") for g in info.get("genres") or [])
        return (text + (f" Genres: {genres}." if genres else ""))[:600]
    except Exception:
        return ""


def about():
    """Описание текущей игры (для DeepL и нейросетей) или пустая строка."""
    from . import profiles
    return (profiles.active() or {}).get("about", "")
