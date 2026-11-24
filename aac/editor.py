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
    "": ("Выключен", None),
    "groq": ("Groq — бесплатно, быстро", "groq"),
    "gemini": ("Gemini — бесплатный уровень", "gemini"),
    "mistral": ("Mistral — бесплатный уровень", "mistral"),
    "claude": ("Claude — платно, лучшее качество", "claude"),
}

PROMPT = """You are a professional video game localization editor (English → Russian) for {game}.
{about}A machine translator produced a Russian draft. Edit it into natural, correct Russian game dialogue:
- fix grammar, noun cases and gender agreement (a speaker's gender is given below when known);
- use the glossary spellings for names and terms, declined correctly;
- keep the meaning, keep the same number of lines and the numbering of reply options;
- keep the tone of the game; use the same "ты"/"вы" as the previous lines;
- if the draft is already good, return it unchanged.
{glossary}{gender}{scene}{history}
Original English:
{src}

Draft translation:
{draft}

Return ONLY the final Russian text, nothing else."""

SCENE_PROMPT = """Here are the latest dialogue lines from {game} (English original → Russian):
{lines}
{old}Write 1-2 short sentences in English: who is talking to whom and what is going on now. No intro."""

_state = {"scene": "", "since_scene": 0, "history": []}
_lock = threading.Lock()
stats = {"edited": 0, "same": 0, "late": 0, "failed": 0}


def name():
    return config.EDITOR if config.EDITOR in EDITORS else ""


def ready():
    """Редактор выбран и у его нейросети есть ключ."""
    from . import llm, translate
    e = name()
    if not e:
        return False
    if llm.provider_cooldown.get(e, 0) > time.time():
        return False
    return translate.provider_has_key(e)


def reset():
    """Сменилась игра — память сцены и прошлые реплики больше не нужны."""
    with _lock:
        _state.update(scene="", since_scene=0, history=[])


def _game():
    from . import profiles
    p = profiles.active()
    return p.get("name") or "a video game", p.get("about", "")


def _ask(prompt):
    from . import llm
    e = name()
    if e == "claude":
        return llm.ask_claude(None, prompt)
    if e in llm.OPENAI_COMPAT:
        return llm.ask_openai_compat(e, None, prompt)
    return llm.ask_gemini(None, prompt)


def build_prompt(src, draft, kind):
    game, about = _game()
    gl = glossary.glossary_prompt(src)
    gender = "" if kind != "subs" else voices.gender_hint(src)
    with _lock:
        scene = _state["scene"]
        hist = list(_state["history"][-config.HISTORY_LINES:])
    return PROMPT.format(
        game=game, about=(f"About the game: {about}\n" if about else ""),
        glossary=(gl + "\n" if gl else ""), gender=(gender + "\n" if gender else ""),
        scene=(f"What is happening now: {scene}\n" if scene else ""),
        history=("Previous lines (context only):\n" + "\n".join(f"EN: {a}\nRU: {b}" for a, b in hist) + "\n"
                 if hist and kind == "subs" else ""),
        src=src, draft=draft)


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
        need = _state["since_scene"] >= config.EDITOR_SCENE_EVERY
        if need:
            _state["since_scene"] = 0
    if need:
        threading.Thread(target=_update_scene, daemon=True).start()


def _update_scene():
    """Память сцены: раз в несколько реплик — короткая заметка «что сейчас происходит»."""
    game, _ = _game()
    with _lock:
        lines = "\n".join(f"{a} → {b}" for a, b in _state["history"][-8:])
        old = _state["scene"]
    try:
        out = _ask(SCENE_PROMPT.format(game=game, lines=lines,
                                       old=(f"Previous note: {old}\n" if old else "")))
    except Exception:
        return
    out = (out or "").strip()
    if out and len(out) < 400:
        with _lock:
            _state["scene"] = out


def improve(src, draft, kind, on_late=None):
    """Поправить черновик основного переводчика. kind: "subs" или "answers".
    Возвращает исправленный текст, если редактор успел за EDITOR_WAIT с, иначе None (показывайте черновик).
    on_late(текст) — вызовется, если ответ пришёл позже (подменить показанный черновик)."""
    if not ready() or not src or not draft:
        if draft:
            _remember(src, draft, kind)
        return None
    game, about = _game()
    key = tcache.make_key("ed-" + kind, src, draft + "|" + name() + "|" + about + glossary.glossary_prompt(src)
                          + (voices.gender_hint(src) if kind == "subs" else ""))
    cached = tcache.get(key)
    if cached:
        _remember(src, cached, kind)
        return cached
    box = {}
    done = threading.Event()
    st = {"phase": "waiting"}           # waiting → done (успел) | gave_up (не дождались — ответ «поздний»)
    lk = threading.Lock()
    prompt = build_prompt(src, draft, kind)

    def work():
        try:
            box["out"] = _clean(_ask(prompt), draft)
        except Exception as e:
            box["err"] = e
        out = box.get("out")
        if out:
            tcache.put(key, out, "ai")
        with lk:
            gave_up = st["phase"] == "gave_up"
            st["phase"] = "done"
        done.set()
        if gave_up:
            stats["late"] += 1
            if out and out.strip() != draft.strip() and on_late:
                on_late(out)
            _remember(src, out or draft, kind)

    threading.Thread(target=work, daemon=True).start()
    done.wait(config.EDITOR_WAIT)
    with lk:
        if st["phase"] != "done":
            st["phase"] = "gave_up"
            return None
    out = box.get("out")
    if "err" in box or not out:
        stats["failed"] += 1
        _remember(src, draft, kind)
        return None
    _remember(src, out, kind)
    if out.strip() == draft.strip():
        stats["same"] += 1
        return None
    stats["edited"] += 1
    if config.EDITOR_LOG:
        core.log(f"✏️ Редактор: {draft.replace(chr(10), ' / ')[:90]} → {out.replace(chr(10), ' / ')[:90]}")
    return out
