"""Стенд проверки: перевести свою фразу всеми выбранными переводчиками сразу — без игры.

Фраза идёт по тому же пути, что и в игре (словарь, подсказки о поле, тот же запрос к нейросети), только текст
не распознаётся с экрана, а берётся из поля ввода. Кэш не используется — каждый раз настоящий запрос.
Редактор показывается отдельно: что он поправил и что подготовил для озвучки.
"""
import threading
import time

from . import config, core

_local = threading.local()
state = {"busy": False, "rows": [], "src": "", "started": 0.0}
_lock = threading.Lock()


def active():
    """Идёт ли сейчас стендовый перевод в этом потоке (OCR берёт текст отсюда, кэш выключен)."""
    return getattr(_local, "lines", None) is not None


def lines():
    return getattr(_local, "lines", None)


def _one(pid, src, kind):
    from . import editor, translate
    t0 = time.time()
    row = {"id": pid, "name": _name(pid), "text": "", "time": 0.0, "error": "", "ed": None}
    prompt = (config.ANSWERS_PROMPT if kind == "answers" else None)
    _local.lines = [ln for ln in src.split("\n") if ln.strip()]
    try:
        out = translate._ask(pid, None, prompt)
        out = translate.clean_translation(out or "", strict=False) or (out or "")
        row["text"] = out.strip()
    except Exception as e:
        row["error"] = str(e)[:200]
    finally:
        _local.lines = None
    row["time"] = round(time.time() - t0, 2)
    if row["text"] and config.EDITOR_ON and editor.candidates():
        t1 = time.time()
        try:
            info = editor.parse(editor._ask(editor.build_prompt(src, row["text"], kind)))
            fixed = editor._clean(info.get("text"), row["text"]) or row["text"]       # как в игре: строгий режим
            rejected = fixed == row["text"] and editor.similarity(info.get("text", ""), row["text"]) < 0.999
            info["text"] = fixed
            row["ed"] = {"text": info.get("text", ""), "voice": editor.filter_stress(info.get("voice", "")),
                         "speaker": info.get("speaker", ""), "gender": info.get("gender", ""),
                         "mood": info.get("mood", ""), "type": info.get("type", ""),
                         "time": round(time.time() - t1, 2), "by": editor.name_of(editor.name()),
                         "diff": editor.diff_words(row["text"], fixed), "rejected": rejected}
        except Exception as e:
            row["ed"] = {"error": str(e)[:200], "time": round(time.time() - t1, 2)}
    return row


def _name(pid):
    try:
        from . import custom_ai, ui_panel
        if custom_ai.is_custom(pid):
            return custom_ai.get(pid)["name"]
        return ui_panel.PROVIDER_NAMES.get(pid, pid)
    except Exception:
        return pid


def run(src, providers, kind="subs"):
    """Запустить проверку в фоне; результаты появляются в state["rows"] по мере готовности."""
    from . import translate
    src = (src or "").strip()
    if not src or state["busy"]:
        return
    providers = [p for p in providers if translate.provider_has_key(p)]
    state.update(busy=True, rows=[{"id": p, "name": _name(p), "wait": True} for p in providers], src=src,
                 started=time.time())
    saved = list(translate.dialogue_history)

    def worker(i, pid):
        r = _one(pid, src, kind)
        with _lock:
            state["rows"][i] = r
        core.events.put(("panel", None))

    def main():
        try:
            ts = [threading.Thread(target=worker, args=(i, p), daemon=True) for i, p in enumerate(providers)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(120)
        finally:
            translate.dialogue_history[:] = saved      # проверка не попадает в историю разговора
            state["busy"] = False
            core.events.put(("panel", None))
    threading.Thread(target=main, daemon=True).start()
