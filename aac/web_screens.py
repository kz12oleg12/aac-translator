"""Данные и действия экранов новой панели (кроме главной — она в web_api.state).

screen(name) — что показать на экране; do(name, arg, app) — действие (в потоке tkinter).
"""
import os
import threading

from . import config, core

REGION_KEYS = [("region", "Субтитры"), ("region2", "Реплики 2"), ("answers_region", "Ответы"),
               ("chat_region", "Чат")]
REGION_EVENTS = {"region": "select", "region2": "select_subs2", "answers_region": "select_answers",
                 "chat_region": "select_chat"}
PROVIDERS = [  # (id, название, описание, группа)
    ("deepl", "DeepL", "Лучший из машинных · 500 000 символов в месяц", "mt"),
    ("microsoft", "Microsoft", "Как в браузере Edge · без ключа", "mt"),
    ("google", "Google", "Google Переводчик · без ключа", "mt"),
    ("groq_ocr", "Groq", "Очень быстро · бесплатно", "ai"),
    ("gemini_ocr", "Gemini", "Бесплатно, лимит в минуту и в день", "ai"),
    ("mistral_ocr", "Mistral", "Бесплатно, 1 запрос в секунду", "ai"),
    ("claude_ocr", "Claude", "Платно, но копейки · лучше всех по-русски", "ai"),
]
KEY_GROUPS = [
    ("Автоперевод", ["auto", "once", "repeat", "tooltip"]),
    ("Перевести по области", ["subs_once", "answers_once", "chat_once", "once_tts"]),
    ("Обвести область", ["select", "select_answers", "select_subs2", "select_chat"]),
    ("Окна и области", ["toggle", "layout", "reset", "panel"]),
    ("Озвучка и чат", ["tts", "flip_gender", "bad_line", "recent", "chat_compose", "menu_learn"]),
    ("Программа", ["quit"]),
]
FLAGS = {  # переключатели: имя → (атрибут config, ключ настроек, что сделать после)
    "cache": ("CACHE_ENABLED", "cache_enabled", None),
    "skip_system": ("SKIP_SYSTEM", "skip_system", None),
    "gloss_auto": ("GLOSSARY_AUTO", "glossary_auto", None),
    "save_history": ("SAVE_HISTORY", "save_history", None),
    "ocr_log": ("SHOW_OCR_IN_LOG", "show_ocr_in_log", None),
    "indicator": ("SHOW_INDICATOR", "show_indicator", None),
    "suppress": ("HOTKEY_SUPPRESS", "hotkey_suppress", "hotkeys"),
    "tts_per_character": ("TTS_PER_CHARACTER", "tts_per_character", "tts"),
    "tts_vary": ("TTS_VARY_IN_GENDER", "tts_vary_in_gender", "tts"),
    "tts_expressive": ("TTS_EXPRESSIVE", "tts_expressive", "tts"),
    "tts_finish": ("TTS_FINISH_LINE", "tts_finish_line", "tts"),
    "tts_skip": ("TTS_SKIP_FAST", "tts_skip_fast", "tts"),
    "tts_nowait": ("TTS_NO_WAIT", "tts_no_wait", "tts"),
    "tts_duck": ("TTS_DUCK", "tts_duck", "tts"),
    "tts_cache": ("TTS_CACHE", "tts_cache", "tts"),
    "ed_shot": ("EDITOR_SCENE_IMAGE", "editor_scene_image", None),
    "tts_read_name": ("TTS_READ_NAME", "tts_read_name", "tts"),
    "tts_russian_only": ("TTS_RUSSIAN_ONLY", "tts_russian_only", "tts"),
}
_win_voices = {"list": None}


def providers():
    """Встроенные переводчики и ваши свои."""
    from . import custom_ai
    return PROVIDERS + [(x["id"], x["name"], f"Свой · {x['model']}", "own") for x in custom_ai.items()]


def _clean(name):
    """«🧪 Без игры» → «Без игры»: значки из старых названий в новой панели не нужны."""
    s = str(name or "")
    while s and not (s[0].isalnum() or s[0] in "«\"'("):
        s = s[1:]
    return s.strip() or str(name or "")


def _size(r):
    try:
        return f"{int(r[2])}×{int(r[3])}"
    except (TypeError, ValueError, IndexError):
        return ""


# ---------- экраны ----------
def screen(name):
    fn = globals().get(f"_s_{name}")
    return fn() if fn else {}


def _s_games():
    from . import game, gamefacts, profiles
    run = set(profiles.running())
    lock = core.SETTINGS.get("profile_lock")
    out = []
    for pid, p in profiles.all_profiles().items():
        free = profiles.is_free(pid)
        chars, gl = profiles.stats(pid)
        regs = []
        for key, title in REGION_KEYS:
            r = p.get(key)
            regs.append({"key": key, "title": title, "has": bool(r), "size": _size(r) if r else ""})
        out.append({
            "id": pid, "name": _clean(p.get("name") or pid), "free": free, "running": pid in run,
            "active": pid == core.active_profile, "locked": lock == pid,
            "exes": list(p.get("exes", [])), "regions": regs, "menu": bool(p.get("menu_region")), "screens": _screens(pid),
            "icon": _icon(pid),
            "auto_start": bool(p.get("auto_start")), "about": p.get("about") or "",
            "facts_busy": pid in gamefacts._running, "facts_ok": gamefacts.available(),
            "chars": chars, "gloss": gl,
            "configured": bool(p.get("region") or p.get("answers_region") or p.get("region2")),
        })
    out.sort(key=lambda g: (not g["free"], not g["running"], not g["active"], g["name"].lower()))
    return {"games": out, "not_games": sorted(game.not_games()), "keys": _keys()}


def _keys():
    from . import hotkeys
    return {hid: hotkeys.K(hid) for hid, *_ in hotkeys.HOTKEY_DEFS}


def _s_tr():
    from . import editor, keys, limits, tcache, translate
    chain = translate.provider_chain()
    lim = {n.lower(): (f, t) for n, f, t in limits.bars()}
    provs = []
    from . import custom_ai
    for pid, name, desc, grp in providers():
        if grp == "own":
            x = custom_ai.get(pid)
            local = custom_ai.is_local(x["url"])
            provs.append({"id": pid, "name": name, "desc": desc, "group": grp, "need_key": not local,
                          "has": custom_ai.ready(pid), "masked": custom_ai.masked(pid), "frac": None, "limit": "",
                          "can_key": False, "own": True, "url": x["url"], "model": x["model"], "local": local})
            continue
        need = pid not in ("microsoft", "google")
        has = translate.provider_has_key(pid)
        f, t = lim.get(name.lower(), (None, ""))
        provs.append({"id": pid, "name": name, "desc": desc, "group": grp, "need_key": need, "has": has,
                      "masked": keys.masked(pid) if need and has else "", "frac": f, "limit": t,
                      "can_key": bool(keys.kind(pid))})
    eds = [{"id": e, "name": editor.EDITORS[e][0].split(" —")[0], "desc": editor.EDITORS[e][0].split("— ")[-1],
            "has": translate.provider_has_key(e)} for e in editor.EDITORS]
    s = editor.stats
    return {"main": config.PROVIDER, "fallback": list(config.FALLBACK_PROVIDERS),
            "chain": chain, "providers": provs, "editor_on": bool(config.EDITOR_ON), "editor": config.EDITOR,
            "editors": eds, "editor2": config.EDITOR2, "ed_shot": config.EDITOR_SCENE_IMAGE,
            "bad": [{"en": x.get("en", ""), "ru": x.get("ru", "")} for x in core.SETTINGS.get("bad_lines", [])],
            "editor_stats": {k: s.get(k, 0) for k in ("edited", "same", "late", "failed", "voice_up", "skipped")},
            "flags": {k: bool(getattr(config, FLAGS[k][0], False))
                      for k in ("cache", "skip_system", "gloss_auto", "save_history")},
            "cache_size": tcache.size(), "gloss_count": _gloss_count(), "default_style": _style_summary(),
            "ds": _s_win_default()}


def _style_summary():
    from . import style
    g = style.default()
    return f"{g['font_family']} {int(g['font_size'])} · {'обводка' if g['text_mode'] == 'outline' else 'плашка'}"


def _gloss_count():
    try:
        from . import glossary
        return len(glossary.entries())
    except Exception:
        return 0


def _voice_list(eng):
    from . import tts
    if eng == "neural":
        return [{"id": v, "name": lab} for v, lab in tts.NEURAL_VOICES]
    if eng == "silero":
        return [{"id": v, "name": lab} for v, lab in tts.tts_silero.VOICES]
    found = _win_voices["list"]
    if found is None:
        _win_voices["list"] = []

        def load():
            _win_voices["list"] = tts.list_voices()
        threading.Thread(target=load, daemon=True).start()
        return []
    return [{"id": "", "name": "по умолчанию"}] + [{"id": n, "name": n} for n, lang in
                                                    sorted(found, key=lambda v: (not v[1].startswith("ru"), v[0]))]


def _s_voice():
    from . import hotkeys, tts, voicepack, voices
    eng = config.TTS_ENGINE
    cur = {"neural": config.TTS_NEURAL_VOICE, "silero": config.TTS_SILERO_VOICE}.get(eng, config.TTS_VOICE)
    chars = []
    e2 = "silero" if eng == "silero" else "neural"
    pool = dict(tts.tts_silero.VOICES) if e2 == "silero" else dict(tts.NEURAL_VOICES)
    for key, c in voices.all_chars()[:300]:
        g = voices.gender(c)
        if c.get("gender_manual") in ("m", "f"):
            how = "вы указали"
        elif c.get("ai") in ("m", "f"):
            how = "нейросетью"
        elif c.get("f", 0) or c.get("m", 0):
            how = "по речи"
        else:
            how = "по имени"
        auto = voices.voice_for(key, e2, auto_only=True)
        manual = c.get(f"voice_{e2}", "")
        chars.append({"key": key, "name": c.get("ru") or c.get("en") or key, "en": c.get("en") or "", "g": g,
                      "how": how, "manual_g": c.get("gender_manual", ""), "voice": manual,
                      "auto": pool.get(auto[0], auto[0]).split(" — ")[0] if auto else "",
                      "type": voices.TYPE_NAMES.get(c.get("type", ""), ""), "addr": c.get("address", ""),
                      "type_id": c.get("type", ""), "type_manual": bool(c.get("type_manual"))})
    vpool = [{"id": v, "name": pool.get(v, v).split(" — ")[0], "g": g}
             for g in ("f", "m") for v in (voices.SILERO_POOL if e2 == "silero" else voices.NEURAL_POOL)[g]]
    gpool = {g: [{"id": v, "name": pool.get(v, v).split(" — ")[0]}
                 for v in (voices.SILERO_POOL if e2 == "silero" else voices.NEURAL_POOL)[g]] for g in ("m", "f")}
    gvoice = {g: (_safe(lambda g=g: voices.default_voice(e2, g)) or (gpool[g][0]["id"] if gpool[g] else ""))
              for g in ("m", "f")}
    mode = ("one" if not config.TTS_PER_CHARACTER else "each" if config.TTS_VARY_IN_GENDER else "gender")
    return {"on": bool(config.TTS_ENABLED), "key": hotkeys.K("tts"), "engine": eng, "voice": cur,
            "mode": mode, "gender_pool": gpool, "gender_voice": gvoice,
            "voices": _voice_list(eng), "rate": config.TTS_RATE, "volume": config.TTS_VOLUME,
            "pause": config.TTS_PARAGRAPH_PAUSE,
            "flags": {k: bool(getattr(config, FLAGS[k][0], False)) for k in FLAGS if k.startswith("tts_")},
            "silero_installed": bool(_safe(tts.tts_silero.installed)), "frozen": config.FROZEN,
            "voicepack": dict(voicepack.state) if hasattr(voicepack, "state") else {},
            "chars": chars, "char_voices": vpool,
            "type_voices": _type_voices(),
            "stress": [{"k": k, "v": v} for k, v in reversed(list(core.SETTINGS.get("stress", {}).items()))][:300], "game": _clean(_safe(lambda: __import__("aac.profiles",
                                                                                         fromlist=["x"]).name()))}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _s_hist():
    from . import history
    items = [{"t": t, "kind": k, "orig": o, "tr": r} for t, k, o, r in history.translation_history[-500:]]
    return {"items": items[::-1]}


def _icon(pid):
    try:
        from . import gameicon
        return gameicon.data_url(pid)
    except Exception:
        return ""


def _screens(pid):
    """Запомненные экраны без перевода у игры pid: имя и миниатюра."""
    import base64
    import json
    from . import menu, profiles
    d = profiles.folder(pid)
    out = []
    try:
        if pid == core.active_profile:
            items = [{"id": x["id"], "name": x["name"]} for x in menu.screens()]
        else:
            f = os.path.join(d, "screens.json")
            items = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else (
                [{"id": "m1", "name": "Меню"}] if profiles.all_profiles().get(pid, {}).get("menu_region") else [])
        for x in items:
            thumb = ""
            for f in (os.path.join(d, f"screen_{x['id']}_view.jpg"), os.path.join(d, f"screen_{x['id']}.png"),
                      os.path.join(d, "menu_ref.png")):
                if os.path.exists(f):
                    with open(f, "rb") as fh:
                        mime = "jpeg" if f.endswith(".jpg") else "png"
                        thumb = f"data:image/{mime};base64," + base64.b64encode(fh.read()).decode()
                    break
            out.append({"id": x["id"], "name": x["name"], "thumb": thumb})
    except Exception as e:
        print("screens:", e)
    return out


def _type_voices():
    from . import voices
    eng = "silero" if config.TTS_ENGINE == "silero" else "neural"
    d = dict(config.TTS_TYPE_VOICES.get(eng) or {})
    for g in ("m", "f"):
        d[f"{g}_adult"] = voices.default_voice(eng, g)
    return d


def _s_start():
    """Мастер первого запуска: шаги отмечаются сами."""
    from . import hotkeys, profiles, translate
    game_on = bool(core.active_profile) and _safe(profiles.is_running, False) and not _safe(profiles.is_free, True)
    chain = translate.provider_chain()
    from .ui_panel import PROVIDER_NAMES as names
    return {
        "tr": {"ok": bool(chain), "txt": " → ".join(names.get(p, p) for p in chain[:2]) or "выберите переводчик",
               "main": config.PROVIDER, "groq_key": bool(translate.provider_has_key("groq"))},
        "game": {"ok": game_on, "txt": _clean(profiles.name()) if game_on else "ждёт игру…"},
        "area": {"ok": bool(core.region), "txt": "обведено" if core.region else "ещё не обведено",
                 "key": hotkeys.K("select")},
        "auto": {"ok": core.auto_on.is_set(), "txt": "включён" if core.auto_on.is_set() else "выключен",
                 "key": hotkeys.K("auto")},
        "voice": {"ok": bool(config.TTS_ENABLED), "txt": "включена" if config.TTS_ENABLED else "выключена"},
    }


def _s_keys():
    from . import hotkeys
    desc = {hid: d for hid, d, *_ in hotkeys.HOTKEY_DEFS}
    known = {h for _, ids in KEY_GROUPS for h in ids}
    groups = [(g, [h for h in ids if h in desc]) for g, ids in KEY_GROUPS]
    rest = [h for h in desc if h not in known]
    if rest:
        groups.append(("Другое", rest))
    return {"groups": [{"title": g, "items": [{"id": h, "desc": desc[h][:1].upper() + desc[h][1:],
                                               "key": hotkeys.K(h),
                                               "risk": "" if config.HOTKEY_SUPPRESS else
                                               (hotkeys.risk(hotkeys.hotkeys.get(h)) or "")} for h in ids]}
                       for g, ids in groups],
            "capturing": hotkeys.capturing, "suppress": bool(config.HOTKEY_SUPPRESS)}


def _s_settings():
    from . import backup
    try:
        names = sorted((n for n in os.listdir(backup.BACKUP_DIR) if n.endswith(".zip")), reverse=True)[:5]
    except OSError:
        names = []
    return {"version": config.VERSION, "update_auto": bool(getattr(config, "UPDATE_AUTO", False)),
            "indicator": bool(getattr(config, "SHOW_INDICATOR", True)), "autobackups": names,
            "backup_name": backup.default_name(),
            "app_dir": config.APP_DIR}


def _s_win():
    from . import style
    return {"owner": _clean(style.owner() or "") or None, "font": config.FONT[0], "size": config.FONT[1],
            "fonts": list(style.FONTS), "color": str(config.TEXT_COLOR), "colors": list(style.COLORS),
            "mode": config.TEXT_MODE, "alpha": int(round(config.OVERLAY_ALPHA * 100)),
            "history": config.SUBS_HISTORY, "delay": config.HIDE_DELAY,
            "keep": bool(config.KEEP_UNTIL_NEXT), "orig": bool(config.SHOW_ORIGINAL),
            "docked": bool(getattr(config, "ANSWERS_DOCKED", False)),
            "chat_cover": bool(config.CHAT_COVER), "chat_height": config.CHAT_HEIGHT,
            "chat_history": config.CHAT_HISTORY, "chat_alpha": int(round(config.CHAT_ALPHA * 100)),
            "chat_fg": str(config.CHAT_FG), "chat_colors": ["#eeeeee", "#ffe08a", "#8cf0ff", "#9dff9d", "#ffb3e6"]}


def _s_win_default():
    from . import style
    g = style.default()
    d = _s_win()
    d.update({"default": True, "owner": None, "font": g["font_family"], "size": int(g["font_size"]),
              "color": str(g["text_color"]), "mode": g["text_mode"], "alpha": int(round(float(g["overlay_alpha"]) * 100))})
    return d


def _s_gloss():
    from . import glossary
    return {"auto": bool(config.GLOSSARY_AUTO), "game": _clean(_safe(lambda: __import__(
                "aac.profiles", fromlist=["x"]).name()) or ""),
            "items": [{"en": en, "ru": ru, "auto": bool(a)} for en, ru, a in glossary.entries()[:2000]],
            "ignore": [{"w": w, "builtin": bool(b)} for w, b in glossary.ignore_entries()]}


def _s_programs():
    from . import game, profiles
    return {"items": [{"exe": e, "title": (t or "")[:80], "known": bool(profiles.for_exe(e))}
                      for e, t in game.running_programs()][:30]}


def _s_report():
    from . import report
    can, why = report.can_send()
    return {"can": bool(can), "why": why or ""}


# ---------- действия ----------
def _flag(name, value):
    attr, key, after = FLAGS[name]
    setattr(config, attr, bool(value))
    core.save_settings(**{key: bool(value)})
    if after == "tts":
        from . import tts
        tts.apply_settings()
    elif after == "hotkeys":
        from . import hotkeys
        hotkeys.register_hotkeys()


def _save_tts():
    from . import tts
    core.save_settings(tts_enabled=config.TTS_ENABLED, tts_read_name=config.TTS_READ_NAME,
                       tts_voice=config.TTS_VOICE, tts_engine=config.TTS_ENGINE,
                       tts_finish_line=config.TTS_FINISH_LINE, tts_neural_voice=config.TTS_NEURAL_VOICE,
                       tts_silero_voice=config.TTS_SILERO_VOICE, tts_rate=config.TTS_RATE,
                       tts_volume=config.TTS_VOLUME, tts_per_character=config.TTS_PER_CHARACTER,
                       tts_russian_only=config.TTS_RUSSIAN_ONLY)
    tts.apply_settings()


def _bg(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


def do(name, arg, app):
    """Действие экрана. True — выполнено."""
    from . import profiles, translate
    a = arg if isinstance(arg, dict) else {"v": arg}
    p = app.panel if app is not None else None
    if name == "flag" and a.get("name") in FLAGS:
        _flag(a["name"], a.get("v"))
    # --- игры ---
    elif name == "game_select" and a.get("id") in profiles.all_profiles():
        if not core.SETTINGS.get("profile_lock"):
            profiles.activate(a["id"], hold=True)
    elif name == "game_rename" and a.get("id") in profiles.all_profiles():
        profiles.rename(a["id"], str(a.get("name", "")).strip()[:60])
    elif name == "game_delete" and a.get("id") in profiles.all_profiles():
        profiles.delete(a["id"])
    elif name == "game_lock":
        profiles.lock(a.get("id") or None)
    elif name == "game_auto_start" and a.get("id") in profiles.all_profiles():
        profs = profiles.all_profiles()
        profs[a["id"]]["auto_start"] = bool(a.get("v"))
        core.save_settings(profiles=profs)
    elif name == "game_facts":
        from . import gamefacts
        gamefacts.gather(a.get("id"), force=True)
    elif name == "game_add" and p is not None:
        p._game_add()
    elif name == "game_add_exe" and p is not None:
        p._game_add_exe(a.get("id"))
    elif name == "game_remove_exe":
        profiles.remove_exe(a.get("id"), a.get("exe"))
    elif name == "unmark_not_game":
        from . import game
        game.unmark_not_game(a.get("v"))
    elif name == "screen_del":
        from . import menu
        menu.forget(a.get("id"))
    elif name == "screen_rename":
        from . import menu
        menu.rename(a.get("id"), str(a.get("v") or ""))
    elif name == "screen_replace":
        from . import menu
        menu.replace_next["id"] = a.get("id")
        core.events.put(("menu_learn_panel", None))
    elif name == "screen_new":
        from . import menu
        menu.replace_next["id"] = None
        core.events.put(("menu_learn_panel", None))
    elif name == "area_draw" and a.get("key") in REGION_EVENTS:
        if a.get("id") and a["id"] != core.active_profile:
            profiles.activate(a["id"], hold=True)
        if app is not None:
            app.from_panel(REGION_EVENTS[a["key"]])
        else:
            core.events.put((REGION_EVENTS[a["key"]], None))
    elif name == "area_clear" and a.get("key") in REGION_EVENTS and p is not None:
        if a.get("id") in (None, core.active_profile):
            p._clear_area(a["key"])
    # --- переводчики ---
    elif name == "provider_main":
        config.PROVIDER = a.get("v") or config.PROVIDER
        config.FALLBACK_PROVIDERS = [f for f in config.FALLBACK_PROVIDERS if f != config.PROVIDER]
        _save_providers()
    elif name == "provider_fallbacks":
        fb = [f for f in (a.get("v") or []) if f in dict((x[0], 1) for x in providers()) and f != config.PROVIDER]
        config.FALLBACK_PROVIDERS = list(dict.fromkeys(fb))
        _save_providers()
    elif name == "editor_on":
        config.EDITOR_ON = bool(a.get("v"))
        core.save_settings(editor_on=config.EDITOR_ON)
        _editor_log()
    elif name == "editor":
        from . import editor
        if a.get("v") in editor.EDITORS:
            config.EDITOR = a["v"]
            core.save_settings(editor=config.EDITOR)
            editor.reset()
            _editor_log()
    elif name == "wizard_provider":
        v = a.get("v")
        config.PROVIDER = v
        config.FALLBACK_PROVIDERS = ["google"] if v != "google" else ["microsoft"]
        core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
        core.log(f"Переводчик: {v} (запасной — {config.FALLBACK_PROVIDERS[0]})", "ok")
    elif name == "wizard_done":
        core.save_settings(wizard_done=True)
    elif name == "stress_set":
        import re as _re
        k, v = str(a.get("k") or "").lower(), str(a.get("v") or "").strip().lower()
        d = core.SETTINGS.setdefault("stress", {})
        if k in d and v.replace("+", "") == k and v.count("+") == 1 and _re.search(r"\+[аеёиоуыэюя]", v):
            d[k] = v
            core.save_settings()
            core.log(f"Ударение: {v}", "ok")
        else:
            core.log("Ударение: поставьте один «+» перед ударной гласной, само слово не меняйте", "warn")
    elif name == "stress_del":
        core.SETTINGS.setdefault("stress", {}).pop(str(a.get("k") or ""), None)
        core.save_settings()
    elif name == "stress_play":
        from . import tts
        tts.say_test(text=str(a.get("v") or ""))
    elif name == "bad_del":
        b = core.SETTINGS.get("bad_lines", [])
        i = int(a.get("i", -1)) if isinstance(a, dict) else -1
        if 0 <= i < len(b):
            b.pop(i)
            core.save_settings()
    elif name == "bad_clear":
        core.SETTINGS["bad_lines"] = []
        core.save_settings()
        core.log("Отметки «плохой перевод» очищены", "ok")
    elif name == "editor2":
        from . import editor
        v = a.get("v") or ""
        if v == "" or v in editor.EDITORS:
            config.EDITOR2 = v
            core.save_settings(editor2=v)
            if v:
                core.log(f"Запасной ИИ-редактор: {editor.EDITORS[v][0].split(' —')[0]}", "ok")
    elif name == "key_save":
        _key_save(a.get("id"), str(a.get("v") or "").strip())
    elif name == "key_remove":
        from . import keys
        keys.remove(a.get("id"))
        core.log("Ключ удалён из Windows", "ok")
    elif name == "custom_save":
        from . import custom_ai
        cid, err = custom_ai.add_or_update(a.get("id") or None, a.get("name"), a.get("url"), a.get("model"),
                                           a.get("key") or None)
        if err:
            return {"error": err}
        core.log(f"Свой переводчик «{a.get('name')}» сохранён", "ok")
        return {"id": cid}
    elif name == "custom_test":
        from . import custom_ai
        ok, out = custom_ai.test(a.get("name"), a.get("url"), a.get("model"), a.get("key"), a.get("id"))
        return {"ok": ok, "text": out}
    elif name == "custom_remove":
        from . import custom_ai
        x = custom_ai.get(a.get("id"))
        if x:
            custom_ai.remove(x["id"])
            core.log(f"Свой переводчик «{x['name']}» удалён", "ok")
    elif name == "cache_clear":
        from . import tcache
        n = tcache.size()
        tcache.clear()
        core.log(f"Кэш переводов очищен ({n} фраз).", "ok")
    # --- озвучка ---
    elif name == "tts_on":
        from . import tts
        config.TTS_ENABLED = bool(a.get("v"))
        if not config.TTS_ENABLED:
            tts.stop()
        _save_tts()
    elif name == "tts_engine" and a.get("v") in ("neural", "silero", "windows"):
        from . import tts
        tts.stop()
        config.TTS_ENGINE = a["v"]
        _save_tts()
        tts.warm()
    elif name == "tts_voice":
        eng = config.TTS_ENGINE
        if eng == "neural":
            config.TTS_NEURAL_VOICE = a.get("v") or config.TTS_NEURAL_VOICE
        elif eng == "silero":
            config.TTS_SILERO_VOICE = a.get("v") or config.TTS_SILERO_VOICE
        else:
            config.TTS_VOICE = a.get("v") or ""
        _save_tts()
    elif name == "tts_rate":
        config.TTS_RATE = max(-5, min(6, int(a.get("v") or 0)))
        _save_tts()
    elif name == "tts_pause":
        config.TTS_PARAGRAPH_PAUSE = max(0.0, min(2.0, float(a.get("v") or 0)))
        core.save_settings(tts_paragraph_pause=config.TTS_PARAGRAPH_PAUSE)
    elif name == "tts_volume":
        config.TTS_VOLUME = max(10, min(100, int(a.get("v") or 100)))
        _save_tts()
    elif name == "tts_test":
        from . import tts
        _bg(tts.say_test, None, (str(a.get("v") or "").strip()[:300] or None))
    elif name == "voice_preview" and a.get("v") is not None:
        from . import tts
        if config.TTS_ENGINE in ("neural", "silero"):
            _bg(tts.say_test, (a["v"], 0), "Привет! Так звучит этот голос.")
        else:
            _bg(tts.say_test, None, "Привет! Так звучит этот голос.")
    elif name == "voice_mode" and a.get("v") in ("one", "gender", "each"):
        config.TTS_PER_CHARACTER = a["v"] != "one"
        config.TTS_VARY_IN_GENDER = a["v"] == "each"
        core.save_settings(tts_per_character=config.TTS_PER_CHARACTER, tts_vary_in_gender=config.TTS_VARY_IN_GENDER)
        from . import tts
        tts.apply_settings()
    elif name == "gender_voice" and a.get("g") in ("m", "f") and a.get("v"):
        from . import voices
        voices.set_default_voice("silero" if config.TTS_ENGINE == "silero" else "neural", a["g"], a["v"])
    elif name == "gender_test" and a.get("g") in ("m", "f"):
        from . import tts, voices
        e2 = "silero" if config.TTS_ENGINE == "silero" else "neural"
        vid = voices.default_voice(e2, a["g"])
        _bg(tts.say_test, (vid, 0) if vid else None, "Так звучит мужской голос персонажей." if a["g"] == "m"
            else "Так звучит женский голос персонажей.")
    elif name == "voicepack_install":
        from . import voicepack
        voicepack.install()
    elif name == "char_gender":
        from . import voices
        voices.set_manual(a.get("key"), gender_value=a.get("v") if a.get("v") in ("m", "f", "") else "")
    elif name == "char_voice":
        from . import voices
        voices.set_manual(a.get("key"), voice=a.get("v") or "", engine="silero" if config.TTS_ENGINE == "silero"
                          else "neural")
    elif name == "type_play":
        from . import tts, voices
        g = a.get("g") if a.get("g") in ("m", "f") else "m"
        k = a.get("k") or ""
        vp = voices.line_voice(g, k) or None
        names = {"": "Обычный", "young": "Молодой", "old": "Пожилой", "child": "Ребёнок", "noble": "Знатный",
                 "monster": "Чудовище"}
        _bg(tts.say_test, vp, f"{names.get(k, '')} голос. Путник, постой! Мне нужна твоя помощь.")
    elif name == "type_voice":
        from . import voices
        g = a.get("g") if a.get("g") in ("m", "f") else "m"
        voices.set_type_voice("silero" if config.TTS_ENGINE == "silero" else "neural", g, a.get("k") or "", a.get("v") or "")
    elif name == "char_type":
        from . import voices
        voices.set_type_manual(a.get("key"), a.get("v") or "")
    elif name == "char_rename":
        from . import glossary, voices
        en = voices.rename(a.get("key"), str(a.get("v") or ""))
        if en:
            try:
                glossary.set_entry(en, str(a.get("v")).strip())     # так и переводить дальше
            except Exception:
                pass
            core.log(f"Имя: {en} → {str(a.get('v')).strip()} (и в словаре игры)", "ok")
    elif name == "char_forget":
        from . import voices
        voices.forget(a.get("key"))
    elif name == "char_play":
        from . import tts, voices
        e2 = "silero" if config.TTS_ENGINE == "silero" else "neural"
        _bg(tts.say_test, voices.voice_for(a.get("key"), e2), f"{a.get('name', '')}. Привет, путник! Так звучит мой голос.")
    # --- история ---
    elif name == "hist_play":
        from . import tts
        _bg(tts.speak_text, str(a.get("v") or ""))
    elif name == "hist_folder":
        from . import history
        os.makedirs(history.HISTORY_DIR, exist_ok=True)
        _open(history.HISTORY_DIR)
    # --- клавиши ---
    elif name == "key_capture":
        from . import hotkeys
        if a.get("v") in hotkeys.hotkeys and not hotkeys.capturing:
            _bg(hotkeys.capture_hotkey, a["v"])
    elif name == "keys_default":
        from . import hotkeys
        for hid, _, default, _ in hotkeys.HOTKEY_DEFS:
            hotkeys.hotkeys[hid] = default
        core.save_settings(hotkeys=dict(hotkeys.hotkeys))
        hotkeys.register_hotkeys()
        core.log("Клавиши — как при установке", "ok")
    # --- настройки ---
    elif name == "backup_export" and p is not None:
        p._backup_export()
    elif name == "backup_import" and p is not None:
        p._backup_import()
    elif name == "backup_restore" and p is not None:
        from . import backup
        n = os.path.basename(str(a.get("v") or ""))
        path = os.path.join(backup.BACKUP_DIR, n)
        if n.endswith(".zip") and os.path.isfile(path):
            p._backup_restore(path)
    elif name == "uninstall" and p is not None:
        p._ask_uninstall()
    elif name == "open_folder":
        _open(config.APP_DIR)
    # --- вид перевода ---
    elif name == "style":
        _style(a)
    # --- словарь ---
    elif name == "gloss_set":
        from . import glossary
        en, ru = str(a.get("en") or "").strip(), str(a.get("ru") or "").strip()
        if en and ru and glossary.set_entry(en, ru):
            core.log(f"📖 Словарь: {en} = {ru}", "ok")
    elif name == "gloss_remove":
        from . import glossary
        glossary.remove_entry(a.get("v"))
    elif name == "ignore_add":
        from . import glossary
        w = str(a.get("v") or "").strip()
        if w and glossary.add_ignore(w):
            core.log(f"Не переводить: {w}", "ok")
    elif name == "ignore_remove":
        from . import glossary
        glossary.remove_ignore(a.get("v"))
    elif name == "gloss_file":
        from . import glossary
        glossary.open_glossary()
    # --- выбор программы («Добавить игру», «ещё файл») ---
    elif name == "pick_game":
        from . import game
        exe = str(a.get("v") or "")
        if profiles.for_exe(exe):
            core.log(f"{exe} уже есть в списке игр — «{profiles.name(profiles.for_exe(exe))}»", "warn")
        elif exe:
            if exe in game.not_games():
                game.unmark_not_game(exe)
            game.create_profile_for(exe, profiles._pretty(exe))
    elif name == "pick_exe" and a.get("id") in profiles.all_profiles():
        profiles.add_exe(a["id"], str(a.get("v") or ""))
    # --- новая игра (баннер на главной) ---
    elif name == "new_dismiss" and p is not None:
        p.show_new_game(None)
    elif name == "new_not_game" and p is not None:
        p._new_not_game()
    # --- резервная копия из файла ---
    elif name == "backup_save_to":
        from . import backup
        path = str(a.get("v") or "")
        if path:
            try:
                saved = backup.export(path)
                core.log(f"Резервная копия сохранена: {path} ({backup.describe(saved)})", "ok")
            except Exception as e:
                core.log(f"Не удалось сохранить копию: {e}", "error")
    elif name == "backup_info":
        from . import backup
        try:
            info = backup.read_manifest(str(a.get("v") or ""))
            return {"created": info.get("created", "?"), "version": info.get("version", "?"),
                    "what": backup.describe(info.get("files", []))}
        except Exception as e:
            return {"error": str(e)}
    elif name == "backup_restore_from" and app is not None:
        from . import backup
        path = str(a.get("v") or "")
        if os.path.basename(path) == path:                  # автокопия — по имени
            path = os.path.join(backup.BACKUP_DIR, path)
        try:
            restored, before = backup.restore(path)
        except Exception as e:
            core.log(f"Не удалось восстановить: {e}", "error")
            return True
        core.log(f"Восстановлено: {backup.describe(restored)}. Прежние настройки — в {before}", "ok")
        app.restart()
    elif name == "uninstall_run":
        from . import uninstall
        ok, msg = uninstall.run(backup_first=bool(a.get("backup", True)), keys_too=bool(a.get("keys", True)))
        if ok:
            core.events.put(("quit", None))
        else:
            core.log(f"Удаление отменено: {msg}", "error")
    # --- сообщить о проблеме ---
    elif name == "report":
        _bg(_report, str(a.get("text") or "").strip(), str(a.get("contact") or "").strip()[:200],
            bool(a.get("shot")), bool(a.get("send")))
    else:
        return False
    core.events.put(("panel", None))
    return True


def _style(a):
    """Вид перевода: шрифт/цвет/подложка — в пресет игры; остальное — общие настройки."""
    from . import chat, style
    app = None
    try:
        from . import web_api
        app = web_api._state["app"]
    except Exception:
        pass
    k, v = a.get("k"), a.get("v")
    if a.get("scope") == "default" and k in ("font", "color", "mode", "size", "alpha"):
        key = {"font": "font_family", "color": "text_color", "mode": "text_mode", "size": "font_size",
               "alpha": "overlay_alpha"}[k]
        val = (str(v) if k in ("font", "color") else v if k == "mode" else
               max(10, min(26, int(v))) if k == "size" else max(40, min(100, int(v))) / 100)
        if k == "mode" and v not in ("box", "outline"):
            return
        style.save_default(**{key: val})
    elif k == "font":
        style.save(font_family=str(v))
    elif k == "color":
        style.save(text_color=str(v))
    elif k == "mode" and v in ("box", "outline"):
        style.save(text_mode=v)
    elif k == "size":
        config.FONT = (config.FONT[0], max(10, min(26, int(v))))
        config.HISTORY_FONT = (config.FONT[0], max(8, config.FONT[1] - 2))
        style.save(font_size=config.FONT[1])
    elif k == "alpha":
        config.OVERLAY_ALPHA = max(40, min(100, int(v))) / 100
        style.save(overlay_alpha=config.OVERLAY_ALPHA)
    elif k == "history":
        config.SUBS_HISTORY = max(0, min(3, int(v)))
        core.save_settings(subs_history=config.SUBS_HISTORY)
    elif k == "delay":
        config.HIDE_DELAY = max(0.0, min(30.0, float(v)))
        config.MAX_SHOW_TIME = max(60, config.HIDE_DELAY + 30)
        core.save_settings(hide_delay=config.HIDE_DELAY)
    elif k == "keep":
        config.KEEP_UNTIL_NEXT = bool(v)
        core.save_settings(keep_until_next=config.KEEP_UNTIL_NEXT)
    elif k == "docked":
        if app is not None:
            app.set_docked(bool(v))
        return
    elif k == "orig":
        config.SHOW_ORIGINAL = bool(v)
        core.save_settings(show_original=config.SHOW_ORIGINAL)
    elif k == "chat_cover":
        config.CHAT_COVER = bool(v)
        chat._state["cover_mode"] = None
        core.save_settings(chat_cover=config.CHAT_COVER)
    elif k == "chat_height":
        config.CHAT_HEIGHT = max(0, min(600, int(v)))
        core.save_settings(chat_height=config.CHAT_HEIGHT)
    elif k == "chat_history":
        config.CHAT_HISTORY = max(20, min(1000, int(v)))
        core.save_settings(chat_history=config.CHAT_HISTORY)
        lines = getattr(app, "chat_lines", None)
        if lines is not None and len(lines) > config.CHAT_HISTORY:
            del lines[:-config.CHAT_HISTORY]
    elif k == "chat_alpha":
        config.CHAT_ALPHA = max(20, min(100, int(v))) / 100
        core.save_settings(chat_alpha=config.CHAT_ALPHA)
    elif k == "chat_fg":
        config.CHAT_FG = str(v)
        core.save_settings(chat_fg=config.CHAT_FG)
    else:
        return
    if app is not None:
        app.panel._apply_overlays()


def _open(path):
    try:
        os.startfile(path)
    except Exception as e:
        core.log(f"Не удалось открыть папку: {e}", "error")


def _save_providers():
    from . import translate
    core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
    names = {x[0]: x[1] for x in providers()}
    chain = translate.provider_chain()
    core.log(f"Переводчик: {' → '.join(names.get(p, p) for p in chain) or 'нет ключей!'} (сохранено)", "ok")
    for pid in [config.PROVIDER] + list(config.FALLBACK_PROVIDERS):
        if not translate.provider_has_key(pid):
            core.log(f"У «{names.get(pid, pid)}» нет ключа — он будет пропущен", "warn")


def _editor_log():
    from . import editor, translate
    eid = config.EDITOR if config.EDITOR_ON else ""
    nm = editor.EDITORS.get(config.EDITOR, ("",))[0].split(" —")[0]
    if not eid:
        core.log("ИИ-редактор выключен — показываю перевод основного переводчика как есть", "ok")
    elif not translate.provider_has_key(eid):
        core.log(f"ИИ-редактор: у {nm} нет ключа — пока не работает", "warn")
    else:
        core.log(f"ИИ-редактор: {nm} — правит перевод основного переводчика", "ok")


def _key_save(pid, value):
    from . import keys
    if not keys.kind(pid) or not value:
        return
    env, _, name, _ = keys.KEYS[keys.kind(pid)]
    err = keys.save(pid, value)
    if err:
        core.log(f"Ключ {name}: {err}", "error")
        return
    core.log(f"Ключ {name} сохранён в Windows ({env}) — проверяю…", "ok")

    def test():
        ok, msg = keys.check(pid)
        core.log(f"Ключ {name}: {msg}", "ok" if ok else "warn")
        core.events.put(("panel", None))
    _bg(test)


def _report(text, contact, shot, send):
    """Снимок экрана — когда панель спрятана, чтобы её не было на снимке."""
    import time
    from . import report, web_api
    img = None
    if shot:
        web_api.push("hide")
        time.sleep(0.6)
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True)
        except Exception:
            img = None
        web_api.push("show")
    if send:
        core.log("Отправляю отчёт автору…")
        ok, msg = report.send(text, img, contact)
        core.log("✓ Отчёт отправлен автору — спасибо!" if ok else f"Отчёт не отправлен: {msg}",
                 "ok" if ok else "warn")
    else:
        try:
            path = report.make(text, img)
        except Exception as e:
            core.log(f"Не удалось собрать архив: {e}", "error")
            return
        core.log(f"📦 Архив для разбора проблемы: {path}", "ok")
        report.show_in_folder(path)
