"""Офлайн-нейроголоса Silero: русская речь синтезируется прямо на компьютере (без интернета).

Нужна библиотека PyTorch (ставится отдельно: install_silero.bat). Модель голосов (~100 МБ)
скачивается один раз при первом запуске в папку models рядом с программой.
Синтез идёт в одном фоновом потоке на процессоре (видеокарта остаётся игре).
"""
import array
import os
import re
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

from . import config, core

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
MODEL_DIR = os.path.join(config.APP_DIR, "models")
MODEL_FILE = os.path.join(MODEL_DIR, "silero_v4_ru.pt")
SAMPLE_RATE = 24000      # 24 кГц: звучит чисто и считается быстрее, чем 48
CPU_THREADS = 4          # не забираем все ядра у игры

VOICES = [
    ("xenia", "Ксения — женский"),
    ("baya", "Бая — женский"),
    ("kseniya", "Ксения 2 — женский"),
    ("aidar", "Айдар — мужской"),
    ("eugene", "Евгений — мужской"),
]

# один поток: модель не любит, когда её вызывают одновременно
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="silero")
_model = {"m": None, "torch": None, "error": None}
_lock = threading.Lock()


def label(voice_id):
    for vid, lab in VOICES:
        if vid == voice_id:
            return lab
    return voice_id


def voice_id(lab):
    for vid, l in VOICES:
        if l == lab:
            return vid
    return lab


def installed():
    """Стоит ли PyTorch (быстрая проверка, без импорта)."""
    import importlib.util
    try:
        return importlib.util.find_spec("torch") is not None
    except Exception:
        return False


def load():
    """Загрузить модель (при необходимости скачать). Вызывается в потоке executor."""
    import time
    with _lock:
        if _model["m"] is not None:
            return _model["m"]
        err = _model["error"]
        if err and time.time() - err[1] < 300:
            raise RuntimeError(err[0])      # не долбим скачивание/загрузку каждую реплику
        try:
            return _load(time)
        except Exception as e:
            _model["error"] = (f"{type(e).__name__}: {str(e)[:150]}", time.time())
            raise


def _load(time):
    if True:
        t0 = time.time()
        import torch
        import torch.package  # noqa: F401  (загрузчик модели)
        torch.set_num_threads(CPU_THREADS)
        if not os.path.exists(MODEL_FILE) or os.path.getsize(MODEL_FILE) < 10_000_000:
            os.makedirs(MODEL_DIR, exist_ok=True)
            core.log("Silero: скачиваю голоса (~100 МБ, один раз)…", "warn")
            tmp = MODEL_FILE + ".part"
            torch.hub.download_url_to_file(MODEL_URL, tmp, progress=False)
            os.replace(tmp, MODEL_FILE)
        model = torch.package.PackageImporter(MODEL_FILE).load_pickle("tts_models", "model")
        model.to(torch.device("cpu"))
        _model.update(m=model, torch=torch)
        core.log(f"Silero: голоса загружены за {time.time() - t0:.1f} с", "ok")
        return model


def _prosody_rate(level):
    """Ползунок скорости (−5…6, плюс «догоняем») → значение SSML."""
    if level <= -4:
        return "x-slow"
    if level <= -1:
        return "slow"
    if level == 0:
        return "medium"
    if level <= 3:
        return "fast"
    return "x-fast"


_LAT2 = [("sch", "ш"), ("sh", "ш"), ("ch", "ч"), ("th", "т"), ("ph", "ф"), ("ck", "к"), ("qu", "кв"),
         ("ee", "и"), ("oo", "у"), ("ea", "и"), ("ou", "ау"), ("ai", "эй"), ("ay", "эй"), ("oa", "о"),
         ("ce", "се"), ("ci", "си"), ("cy", "си"), ("ge", "дже"), ("gi", "джи"), ("kn", "н"), ("wh", "у")]
_LAT1 = {"a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и", "j": "дж",
         "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т",
         "u": "у", "v": "в", "w": "у", "x": "кс", "y": "и", "z": "з"}


def translit(word):
    """Грубое чтение английских имён по-русски («Seaglass» → «Сигласс»), чтобы Silero их не пропускал."""
    w = word.lower()
    out = ""
    i = 0
    while i < len(w):
        for a, b in _LAT2:
            if w.startswith(a, i):
                out += b
                i += len(a)
                break
        else:
            ch = w[i]
            if ch == "e" and i == len(w) - 1 and len(w) > 3:
                pass                      # немая «e» на конце: «Blade» → «Блад»
            elif i > 0 and ch == w[i - 1] and ch not in "sl":
                pass                      # двойные согласные, кроме ss/ll
            else:
                out += _LAT1.get(ch, "")
            i += 1
    return out[:1].upper() + out[1:] if word[:1].isupper() else out


def clean(text):
    """Silero читает только кириллицу: английские слова переводим в русские буквы, лишние значки убираем."""
    text = re.sub(r"[A-Za-z]+", lambda m: translit(m.group(0)), text)
    text = re.sub(r"[«»\"“”„*_#~<>\[\]{}|/\\]", " ", text)
    text = text.replace("…", "...")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.!?:;])", r"\1", text)      # «друг ,» → «друг,»
    text = re.sub(r"([,.!?:;])(?:\s*[,:;])+", r"\1", text)  # «Привет, , мир» → «Привет, мир»
    return text.strip(" ,:;-—")


_PITCHES = {-2: "x-low", -1: "low", 0: "medium", 1: "high", 2: "x-high"}


def synth_to_wav(text, path, voice, rate_level=0, pitch_level=0):
    """Синтез фразы в wav-файл. Вызывается в потоке executor."""
    model = load()
    torch = _model["torch"]
    text = clean(text)
    if sum(ch.isalpha() for ch in text) < 2:
        raise ValueError("нечего читать")
    rate = _prosody_rate(rate_level)
    pitch = _PITCHES.get(max(-2, min(2, int(pitch_level))), "medium")
    kw = dict(speaker=voice, sample_rate=SAMPLE_RATE, put_accent=True, put_yo=True)
    with torch.no_grad():
        if rate != "medium" or pitch != "medium":
            attrs = (f' rate="{rate}"' if rate != "medium" else "") + (f' pitch="{pitch}"' if pitch != "medium" else "")
            audio = model.apply_tts(ssml_text=f'<speak><prosody{attrs}>{escape(text)}</prosody></speak>', **kw)
        else:
            audio = model.apply_tts(text=text, **kw)
    pcm = (audio.clamp(-1, 1) * 32767).to(torch.int16).tolist()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(array.array("h", pcm).tobytes())
    return path
