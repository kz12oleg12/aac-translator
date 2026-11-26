"""Офлайн-переводчик на этом ПК: модель Opus-MT (англ. → рус.) из проекта Argos Translate, движок CTranslate2.

Модель (~100 МБ) скачивается один раз в папку программы (offline_mt) — или ставится из скачанного заранее
файла .argosmodel (удобно, если интернет на этом ПК закрыт). Дальше перевод идёт без интернета, на процессоре,
доли секунды на реплику. Качество — примерно как у машинных переводчиков; имена берутся из словаря игры.
"""
import os
import shutil
import tempfile
import threading
import zipfile

from . import config, core

MODEL_URLS = ["https://argos-net.com/v1/translate-en_ru-1_9.argosmodel"]
state = {"busy": False, "progress": "", "error": ""}
_m = {"tr": None, "sp": None}
_lock = threading.Lock()


def folder():
    return os.path.join(config.APP_DIR, "offline_mt", "en_ru")


def available():
    """Есть ли в программе сам движок (ctranslate2 + sentencepiece)."""
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
        return True
    except Exception:
        return False


def installed():
    d = folder()
    return os.path.exists(os.path.join(d, "model", "model.bin")) and os.path.exists(os.path.join(d, "sentencepiece.model"))


def ready():
    return installed() and available()


def _unpack(zpath):
    """Из архива .argosmodel берём папку model/ и sentencepiece.model."""
    d = folder()
    tmp = d + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        root = next((n.split("/")[0] for n in names if n.endswith("/model/model.bin")), None)
        if not root or not any(n == f"{root}/sentencepiece.model" for n in names):
            raise ValueError("это не модель перевода Argos (нет model/model.bin или sentencepiece.model)")
        for n in names:
            if n.endswith("/"):
                continue
            rel = n[len(root) + 1:]
            if not (rel.startswith("model/") or rel == "sentencepiece.model"):
                continue
            out = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    os.replace(tmp, d)
    with _lock:
        _m.update(tr=None, sp=None)


def install(path=None):
    """Скачать модель (или поставить из файла path) в фоне. Ход — в state, итог — в журнале."""
    if state["busy"]:
        return

    def run():
        state.update(busy=True, progress="", error="")
        try:
            if path:
                state["progress"] = "распаковываю…"
                _unpack(path)
            else:
                import requests
                tmp = os.path.join(tempfile.gettempdir(), "aac_offline_mt.zip")
                err = None
                for url in MODEL_URLS:
                    try:
                        with requests.get(url, stream=True, timeout=30) as r:
                            r.raise_for_status()
                            total = int(r.headers.get("Content-Length") or 0)
                            got = 0
                            with open(tmp, "wb") as f:
                                for chunk in r.iter_content(512 * 1024):
                                    f.write(chunk)
                                    got += len(chunk)
                                    state["progress"] = (f"{got * 100 // total}%" if total else f"{got >> 20} МБ")
                        err = None
                        break
                    except Exception as e:
                        err = e
                if err:
                    raise err
                state["progress"] = "распаковываю…"
                _unpack(tmp)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            core.log("Офлайн-переводчик установлен — теперь переводит без интернета", "ok")
        except Exception as e:
            state["error"] = str(e)[:200]
            core.log(f"Офлайн-переводчик: не удалось установить ({str(e)[:160]}). Можно скачать файл модели "
                     f"на другом компьютере ({MODEL_URLS[0]}) и выбрать его кнопкой «Из файла».", "error")
        finally:
            state.update(busy=False, progress="")
            core.events.put(("panel", None))
    threading.Thread(target=run, daemon=True).start()


def remove():
    shutil.rmtree(os.path.dirname(folder()), ignore_errors=True)
    with _lock:
        _m.update(tr=None, sp=None)


def _load():
    with _lock:
        if _m["tr"] is None:
            import ctranslate2
            import sentencepiece
            d = folder()
            threads = max(1, min(4, (os.cpu_count() or 2) // 2))
            _m["tr"] = ctranslate2.Translator(os.path.join(d, "model"), device="cpu", compute_type="auto",
                                              inter_threads=1, intra_threads=threads)
            _m["sp"] = sentencepiece.SentencePieceProcessor(model_file=os.path.join(d, "sentencepiece.model"))
        return _m["tr"], _m["sp"]


def translate(text):
    """Перевести текст построчно (строки субтитра/вариантов ответа сохраняются)."""
    if not ready():
        raise core.ApiError("офлайн-переводчик не установлен")
    tr, sp = _load()
    lines = [ln for ln in (text or "").split("\n")]
    todo = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.strip()]
    if not todo:
        return text
    toks = [sp.encode(ln, out_type=str) for _, ln in todo]
    res = tr.translate_batch(toks, beam_size=2, max_decoding_length=256)
    out = list(lines)
    for (i, _), r in zip(todo, res):
        out[i] = sp.decode(r.hypotheses[0]).replace("▁", " ").strip()
    return "\n".join(out)
