"""ИИ-редактор: работает в связке с основным переводчиком (Microsoft / Google / DeepL).
Основной переводит быстро и надёжно, редактор правит черновик с учётом контекста:
падежи и род, имена по словарю, тон и «ты»/«вы» по описанию игры, связь с предыдущими репликами,
короткая «память сцены». Ждём его до EDITOR_WAIT секунд; не успел / лимит / нет сети — показываем
перевод основного переводчика (хуже, чем без редактора, не бывает), а поздний ответ тихо подменяет текст.
"""
import threading
import time

from . import config, core, glossary, tcache, voices

# кто может быть редактором: id → (название, переводчик в цепочке, чей ключ нужен)
EDITORS = {
    "groq": ("Groq — бесплатно, быстро", "groq"),
    "gemini": ("Gemini — бесплатный уровень", "gemini"),
    "mistral": ("Mistral — бесплатный уровень", "mistral"),
    "claude": ("Claude — платно, лучшее качество", "claude"),
}

PROMPT = """You are a professional video game localization editor (English → Russian) for {game}.
{about}A machine translator produced a Russian draft. Your job has two parts.

1) TEXT — the subtitle the player reads. Edit the draft into natural, correct Russian game dialogue:
- fix grammar, noun cases and gender agreement: figure out who speaks and to whom (gender hints below, the
  speaker's name, the scene) and make verbs/adjectives match («я пришла» for a woman, «я готов» for a man);
- use the glossary spellings for names and terms, declined correctly;
- keep the meaning, keep the same number of lines and the numbering of reply options;
- keep the tone of the game; use the same "ты"/"вы" as the previous lines;
- if the draft is already good, keep it unchanged.

2) VOICE — the same line prepared for a Russian text-to-speech voice (it reads letters literally):
- never include the speaker's name (not as a prefix, not on its own line); no brackets, no markup, no emoji;
- write numbers, fractions, percents, "x2", "HP", "lvl", "3/5" etc. as Russian words, correctly declined;
- write any remaining Latin words in Russian letters the way they are pronounced;
- put "+" right before the stressed vowel in names, invented/fantasy words, rare words and homographs
  (з+амок / зам+ок, вс+ё); do not mark ordinary unambiguous words;
- use punctuation for natural pauses and intonation (commas, «—», «…», «!», «?»);
- if the line is longer than about {maxlen} characters, condense VOICE to the essential meaning.
{voice_only}
Also guess who is speaking (if a name is visible or obvious from context), their gender, the mood,
what kind of voice suits them and how they address the player. List proper names / game terms from this line
(not common words) with their Russian form in the nominative case.
{glossary}{gender}{stress}{scene}{history}
Original English:
{src}

Draft translation:
{draft}

(In the history above " / " only marks a line break. In your answer use real line breaks, never " / ".)
Answer strictly in this format, nothing else:
TEXT:
<final Russian subtitle>
VOICE:
<text for speech>
SPEAKER: <speaker's name in English as in the original, or ->
GENDER: <m, f or ->
MOOD: <calm, shout, whisper, question, sad or ->
TYPE: <young, adult, old, child, monster, noble or -> (judge by name/title, the scene and speech manner:
      elder, grandma, old archivist → old; beast, demon, undead, golem → monster; baron, queen, lord → noble;
      kid, boy, girl → child; youthful recruit, apprentice → young)
ADDRESS: <ты, вы or ->
TERMS: <English = Русский; English = Русский … or ->"""

SCENE_PROMPT = """Here are the latest dialogue lines from {game} (English original → Russian):
{lines}
{old}{shot}Write 1-2 short sentences in English: who is talking to whom and what is going on now. No intro."""

SHOT_NOTE = """The attached screenshot is the current game screen. Use it: say who is visible (man/woman/child/old/creature,
by name if the dialogue reveals it) and who is likely speaking.
"""

_state = {"scene": "", "since_scene": 0, "history": []}
_speech = {}            # показанный текст → {"voice", "speaker", "gender", "mood"} — для озвучки
_SPEECH_MAX = 200
_lock = threading.Lock()
stats = {"edited": 0, "same": 0, "late": 0, "failed": 0, "voice_up": 0, "skipped": 0}


def _usable(e):
    from . import llm, translate
    return bool(e) and e in EDITORS and llm.provider_cooldown.get(e, 0) <= time.time() and translate.provider_has_key(e)


def candidates():
    """Основной редактор, потом запасной."""
    if not config.EDITOR_ON:
        return []
    out = [config.EDITOR] if config.EDITOR in EDITORS else []
    if config.EDITOR2 in EDITORS and config.EDITOR2 not in out:
        out.append(config.EDITOR2)
    return out


def name():
    """Нейросеть, которая сейчас редактирует (основной, а если он на паузе — запасной), иначе ""."""
    c = candidates()
    return next((e for e in c if _usable(e)), c[0] if c else "")


def ready():
    """Редактор включён и хотя бы у одной из его нейросетей есть ключ и нет паузы."""
    from . import bench
    if bench.active():          # на стенде редактор вызывается отдельно, чтобы показать его работу
        return False
    return any(_usable(e) for e in candidates())


def reset():
    """Сменилась игра — память сцены и прошлые реплики больше не нужны."""
    with _lock:
        _state.update(scene="", since_scene=0, history=[], last_speaker=None, last_line_at=0, scene_at=0)


def _game():
    from . import profiles
    p = profiles.active()
    return p.get("name") or "a video game", p.get("about", "")


def _ask_one(e, prompt):
    from . import llm
    if e == "claude":
        return llm.ask_claude(None, prompt)
    if e in llm.OPENAI_COMPAT:
        return llm.ask_openai_compat(e, None, prompt)
    return llm.ask_gemini(None, prompt)


def _ask_with_shot(prompt):
    """Заметка о сцене по скриншоту игры: видно, кто в кадре — точнее говорящий и его пол."""
    from . import capture, llm
    img = capture.grab(None)
    for e in candidates():
        if not _usable(e) or is_custom_id(e):
            continue                       # свои ИИ могут не понимать картинки — для них заметка только по тексту
        try:
            if e == "claude":
                return llm.ask_claude(capture.encode(img, 1024), prompt)
            if e in llm.OPENAI_COMPAT:
                return llm.ask_openai_compat(e, img, prompt)
            return llm.ask_gemini(capture.encode(img, 1024), prompt)
        except core.RateLimited:
            llm.provider_cooldown[e] = time.time() + config.PROVIDER_COOLDOWN.get(e, 60)
        except Exception as ex:
            if not _state.get("shot_warned"):
                _state["shot_warned"] = True
                core.log(f"🖼 ИИ-редактор не смог посмотреть на экран ({name_of(e)}): {str(ex)[:120]} — "
                         "заметка о сцене будет только по тексту", "warn")
    return None


def name_of(e):
    try:
        return EDITORS[e][0].split(" —")[0]
    except Exception:
        return str(e)


def is_custom_id(e):
    return str(e).startswith("c_")


def _ask(prompt):
    """Спросить основной редактор; лимит или сбой — запасной."""
    from . import llm
    err = None
    for e in candidates():
        if not _usable(e):
            continue
        try:
            return _ask_one(e, prompt)
        except core.RateLimited as ex:
            llm.provider_cooldown[e] = time.time() + config.PROVIDER_COOLDOWN.get(e, 60)
            err = ex
        except Exception as ex:
            err = ex
    if err:
        raise err
    raise core.ApiError("нет доступного редактора")


def build_prompt(src, draft, kind):
    game, about = _game()
    gl = glossary.glossary_prompt(src)
    gender = "" if kind != "subs" else voices.gender_hint(src)
    with _lock:
        scene = _state["scene"]
        hist = list(_state["history"][-config.HISTORY_LINES:])
    st = stress_prompt(src + "\n" + draft)
    mem = voices.memory_hint(src)
    bad = bad_hint()
    if mem:
        st = (st + "\n" if st else "") + mem
    if bad:
        st = (st + "\n" if st else "") + bad
    return PROMPT.format(
        game=game, about=(f"About the game: {about}\n" if about else ""),
        maxlen=config.EDITOR_VOICE_MAX,
        voice_only=("These are reply options of a dialogue menu: in VOICE keep them as separate lines without numbers.\n"
                    if kind == "answers" else ""),
        stress=(st + "\n" if st else ""),
        glossary=(gl + "\n" if gl else ""), gender=(gender + "\n" if gender else ""),
        scene=(f"What is happening now: {scene}\n" if scene else ""),
        history=("Previous lines (context only):\n" + "\n".join(f"EN: {a}\nRU: {b}" for a, b in hist) + "\n"
                 if hist and kind == "subs" else ""),
        src=src, draft=draft)


def trivial(draft):
    """Короткая реплика без имён и цифр («Да.», «Хм…», «Спасибо!») — редактору нечего править, бережём лимит."""
    import re
    words = re.findall(r"[А-Яа-яЁёA-Za-z]+", draft or "")
    if len(words) > 2 or sum(map(len, words)) > 12 or re.search(r"\d|[A-Za-z]", draft or ""):
        return False
    return not any(w[:1].isupper() for w in words[1:])


def _norm(t):
    import re
    return re.sub(r"[^\wё]", "", (t or "").lower())


def parse(out):
    """Ответ редактора → {"text", "voice", "speaker", "gender", "mood"}. Старый формат (просто текст) тоже понимаем."""
    import re
    out = (out or "").strip().strip("`").strip()
    m = re.search(r"TEXT:\s*(.*?)\s*VOICE:\s*(.*?)\s*(?=SPEAKER:|GENDER:|MOOD:|$)", out, re.S)
    if not m:
        return {"text": out}
    unslash = lambda t: re.sub(r"\s+/\s+", "\n", t)     # «Имя / Реплика» — это перенос строки, не знак
    res = {"text": unslash(m.group(1).strip()), "voice": unslash(m.group(2).strip())}
    for k in ("speaker", "gender", "mood"):
        mm = re.search(k.upper() + r":\s*([^\n]*)", out)
        v = (mm.group(1).strip().strip("<>\"' ") if mm else "")
        res[k] = "" if v in ("-", "—", "none", "unknown", "u") else v
    for k in ("type", "address", "terms"):
        mm = re.search(k.upper() + r":\s*([^\n]*)", out)
        v = (mm.group(1).strip().strip("<>\"' ") if mm else "")
        res[k] = "" if v in ("-", "—", "none") else v
    res["type"] = res["type"].lower() if res["type"].lower() in ("young", "old", "child", "monster", "noble") else ""
    res["address"] = res["address"].lower() if res["address"].lower() in ("ты", "вы") else ""
    terms = []
    for part in res["terms"].split(";"):
        if "=" in part:
            a, b = (x.strip(" .\"'«»") for x in part.split("=", 1))
            if a and b and len(a) <= 40 and len(b) <= 50:
                terms.append((a, b))
    res["terms"] = terms[:6]
    res["gender"] = res["gender"][:1].lower() if res["gender"][:1].lower() in ("m", "f") else ""
    res["mood"] = res["mood"].lower() if res["mood"].lower() in ("shout", "whisper", "question", "sad") else ""
    if len(res["speaker"]) > 30:
        res["speaker"] = ""
    return res


def _note_traits(info, shown=None):
    """Пол и характер говорящего — сразу в карточку персонажа (даже если ответ редактора опоздал к озвучке)."""
    if not (info.get("gender") or info.get("type") or info.get("address")):
        return
    try:
        key = None
        try:
            from . import tts
            key = tts.char_of_line(shown)          # кого озвучка уже узнала в этой реплике
        except Exception:
            pass
        sp = info.get("speaker")
        if not key and sp:
            found = voices.speaker("", f"{sp}\nHello there.")
            key = found[0] if found else None
        if key:
            voices.set_ai_gender(key, info.get("gender"))
            voices.set_traits(key, info.get("type"), info.get("address"))
    except Exception:
        pass


def _keep_speech(shown, info):
    if not shown or not info.get("voice"):
        return
    if _norm(shown) not in _speech:
        _note_traits(info, shown)
    with _lock:
        _speech[_norm(shown)] = info
        while len(_speech) > _SPEECH_MAX:
            _speech.pop(next(iter(_speech)))
    _learn_stress(info["voice"])
    for en, ru in info.get("terms") or []:
        try:
            if glossary.learn(en, ru, "ИИ-редактор"):
                pass
        except Exception:
            pass


# ---------- «плохой перевод» по горячей клавише: редактор учитывает такие примеры ----------
def _bad():
    return core.SETTINGS.setdefault("bad_lines", [])


def mark_bad(src, shown):
    """Игрок отметил последнюю реплику как плохо переведённую."""
    if not shown:
        return False
    b = _bad()
    b.append({"en": (src or "")[:300], "ru": shown[:300], "t": int(time.time())})
    del b[:-30]
    core.save_settings()
    tcache_keys = [k for k in list(_speech) if k == _norm(shown)]
    for k in tcache_keys:
        _speech.pop(k, None)
    return True


def bad_hint():
    b = _bad()[-4:]
    if not b:
        return ""
    return ("The player marked these earlier translations as bad — avoid the same mistakes:\n"
            + "\n".join(f"EN: {x['en']} → RU (bad): {x['ru']}" for x in b))


def speech_for(shown):
    """Подготовленный редактором текст для озвучки показанной реплики (или None)."""
    with _lock:
        return _speech.get(_norm(shown))


# ---------- ударения: редактор отметил «+» в имени или редком слове — запоминаем для всех следующих реплик ----------
def _stress_map():
    return core.SETTINGS.setdefault("stress", {})


def _learn_stress(voice):
    import re
    d = _stress_map()
    changed = False
    for w in re.findall(r"[А-Яа-яЁё+]+", voice):
        if w.count("+") != 1 or len(w) < 4:
            continue
        plain = w.replace("+", "")
        if not (plain[:1].isupper() or len(plain) >= 9):     # имена, термины и длинные редкие слова
            continue
        k = plain.lower()
        if d.get(k) != w.lower():
            d[k] = w.lower()
            changed = True
    if changed:
        while len(d) > 600:
            d.pop(next(iter(d)))
        try:
            core.save_settings()
        except Exception:
            pass


def stress_prompt(text):
    d = _stress_map()
    low = (text or "").lower()
    hits = [v for k, v in d.items() if k[:-2] and k[:-2] in low][:15]
    return ("Known stresses (keep them): " + ", ".join(hits)) if hits else ""


def apply_stress(text):
    """Подставить запомненные ударения (для озвучки без редактора или если он не отметил)."""
    import re
    d = _stress_map()
    if not d:
        return text

    def rep(m):
        w = m.group(0)
        v = d.get(w.lower())
        if not v or "+" in w:
            return w
        i = v.index("+")
        return w[:i] + "+" + w[i:]
    return re.sub(r"(?<![+\w])[А-Яа-яЁё]{4,}(?![+\w])", rep, text)


def _clean(out, draft):
    """Ответ редактора → текст. Пусто, не по-русски, сильно длиннее черновика — значит, что-то пошло не так."""
    from . import translate
    out = (out or "").strip().strip("`").strip()
    if out.lower().startswith(("final", "here", "вот", "итог")) and "\n" in out:
        out = out.split("\n", 1)[1].strip()
    if not out or "НЕТ_ТЕКСТА" in out:
        return None
    try:
        out = translate.clean_translation(out)
    except core.ApiError:
        return None
    if len(out) > 2.2 * len(draft) + 40:
        return None
    return out


def _remember(src, final, kind):
    if kind != "subs":
        return
    with _lock:
        _state["history"].append((src.replace("\n", " / "), final.replace("\n", " / ")))
        del _state["history"][:-config.HISTORY_LINES]
        _state["since_scene"] += 1
        now = time.time()
        try:
            sp = voices.speaker(final, src)
            who = sp[0] if sp else None
        except Exception:
            who = None
        new_talk = now - _state.get("last_line_at", 0) > 20          # долго было тихо — новый разговор
        new_npc = bool(who) and who != _state.get("last_speaker")   # заговорил другой персонаж
        _state["last_line_at"] = now
        if who:
            _state["last_speaker"] = who
        need = (_state["since_scene"] >= config.EDITOR_SCENE_EVERY or new_talk or new_npc) \
            and now - _state.get("scene_at", 0) > 8                  # но не чаще раза в 8 с
        if need:
            _state["since_scene"] = 0
            _state["scene_at"] = now
    if need:
        threading.Thread(target=_update_scene, daemon=True).start()


def _update_scene():
    """Память сцены: раз в несколько реплик — короткая заметка «что сейчас происходит»."""
    game, _ = _game()
    with _lock:
        lines = "\n".join(f"{a} → {b}" for a, b in _state["history"][-8:])
        old = _state["scene"]
    fmt = dict(game=game, lines=lines, old=(f"Previous note: {old}\n" if old else ""))
    out = None
    by_shot = False
    if config.EDITOR_SCENE_IMAGE:
        try:
            out = _ask_with_shot(SCENE_PROMPT.format(shot=SHOT_NOTE, **fmt))
            by_shot = bool(out)
        except Exception:
            out = None
    if not out:
        try:
            out = _ask(SCENE_PROMPT.format(shot="", **fmt))
        except Exception:
            return
    out = (out or "").strip()
    if out and len(out) < 400:
        with _lock:
            _state["scene"] = out
            _state["scene_shot"] = by_shot
            _state["scene_at_t"] = time.time()
        stats["scenes"] = stats.get("scenes", 0) + 1
        core.log(("🖼 ИИ-редактор посмотрел на экран: " if by_shot else "📝 Заметка о сцене (по тексту): ") + out[:160])


def improve(src, draft, kind, on_late=None):
    """Поправить черновик основного переводчика и подготовить текст для озвучки. kind: "subs" или "answers".
    Возвращает исправленный текст, если редактор успел за EDITOR_WAIT с, иначе None (показывайте черновик).
    on_late(текст) — вызовется, если ответ пришёл позже (подменить показанный черновик)."""
    import json
    if trivial(draft):
        stats["skipped"] = stats.get("skipped", 0) + 1
        _remember(src, draft, kind)
        return None
    src = src or "(original not available — the translator read it from a screenshot)"
    if not ready() or not draft:
        if draft:
            _remember(src, draft, kind)
        return None
    game, about = _game()
    key = tcache.make_key("ed2-" + kind, src, draft + "|" + name() + "|" + about + glossary.glossary_prompt(src)
                          + (voices.gender_hint(src) if kind == "subs" else ""))
    cached = tcache.get(key)
    if cached:
        try:
            info = json.loads(cached)
        except Exception:
            info = {"text": cached}
        _keep_speech(info["text"], info)
        _keep_speech(draft, info)
        _remember(src, info["text"], kind)
        return None if info["text"].strip() == draft.strip() else info["text"]
    box = {}
    done = threading.Event()
    st = {"phase": "waiting"}           # waiting → done (успел) | gave_up (не дождались — ответ «поздний»)
    lk = threading.Lock()
    prompt = build_prompt(src, draft, kind)

    def work():
        try:
            info = parse(_ask(prompt))
            txt = _clean(info.get("text"), draft)
            if txt:
                info["text"] = txt
                if info.get("voice"):
                    info["voice"] = info["voice"] if len(info["voice"]) <= 3 * len(draft) + 60 else ""
                box["info"] = info
        except Exception as e:
            box["err"] = e
        info = box.get("info")
        if info:
            tcache.put(key, json.dumps(info, ensure_ascii=False), "ai")
            _keep_speech(info["text"], info)
            _keep_speech(draft, info)
        with lk:
            gave_up = st["phase"] == "gave_up"
            st["phase"] = "done"
        done.set()
        if gave_up:
            stats["late"] += 1
            out = info and info["text"]
            if out and out.strip() != draft.strip() and on_late:
                on_late(out)
            if info and info.get("voice") and kind == "subs":
                try:      # реплика уже звучит черновиком — оставшиеся фразы дочитать вариантом редактора
                    from . import tts
                    tts.upgrade(draft, info, src)
                except Exception:
                    pass
            _remember(src, out or draft, kind)

    threading.Thread(target=work, daemon=True).start()
    voice_fast = config.TTS_NO_WAIT and config.TTS_ENABLED and kind == "subs"
    done.wait(min(config.EDITOR_WAIT, config.EDITOR_WAIT_VOICE) if voice_fast else config.EDITOR_WAIT)
    with lk:
        if st["phase"] != "done":
            st["phase"] = "gave_up"
            return None
    info = box.get("info")
    if "err" in box or not info:
        stats["failed"] += 1
        _remember(src, draft, kind)
        return None
    out = info["text"]
    _remember(src, out, kind)
    if config.EDITOR_LOG and info.get("voice"):
        core.log(f"🔊 Для озвучки: {info['voice'].replace(chr(10), ' / ')[:110]}"
                 + (f" · {info['speaker']}" if info.get("speaker") else "")
                 + (f" · {info['mood']}" if info.get("mood") else ""))
    if out.strip() == draft.strip():
        stats["same"] += 1
        return None
    stats["edited"] += 1
    if config.EDITOR_LOG:
        core.log(f"✏️ Редактор: {draft.replace(chr(10), ' / ')[:90]} → {out.replace(chr(10), ' / ')[:90]}")
    return out
