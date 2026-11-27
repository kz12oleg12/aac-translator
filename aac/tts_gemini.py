"""Озвучка голосами Gemini TTS (Google): голос «играет» — ему словами говорят, кто говорит и как.

Каждой реплике передаётся короткая режиссёрская подсказка: кто говорит (старый волшебник, мальчик, голем…)
и с каким настроением — её собирает программа по тому, что поняли ИИ-редактор и таблица характеров.
Звук приходит как PCM 24 кГц, сохраняем в .wav (Windows играет его сам).

Нужен ключ Gemini (тот же, что для перевода). Бесплатный лимит у Google есть; кончился, нет сети или
ключа — реплика читается нейроголосом Microsoft (tts.py), озвучка не пропадает."""
import base64
import re
import struct
import threading
import time

import requests

from . import config, core

# модели по порядку: первая отключена у Google (404) — берём следующую
MODELS = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
RATE = 24000

# (голос, описание). Пол — у Google в описании голосов (Kore — женский, Charon — мужской…)
VOICES_F = [("Kore", "твёрдый"), ("Zephyr", "яркий"), ("Leda", "юный"), ("Aoede", "лёгкий"),
            ("Callirrhoe", "непринуждённый"), ("Autonoe", "яркий"), ("Despina", "мягкий"), ("Erinome", "чистый"),
            ("Laomedeia", "бодрый"), ("Achernar", "тихий"), ("Gacrux", "зрелый"), ("Pulcherrima", "напористый"),
            ("Vindemiatrix", "нежный"), ("Sulafat", "тёплый")]
VOICES_M = [("Charon", "дикторский"), ("Orus", "твёрдый"), ("Puck", "бодрый"), ("Fenrir", "эмоциональный"),
            ("Enceladus", "с придыханием"), ("Iapetus", "чистый"), ("Umbriel", "непринуждённый"),
            ("Algieba", "мягкий"), ("Algenib", "хриплый"), ("Rasalgethi", "ровный"), ("Alnilam", "твёрдый"),
            ("Schedar", "спокойный"), ("Achird", "дружелюбный"), ("Zubenelgenubi", "простой"),
            ("Sadachbia", "живой"), ("Sadaltager", "мудрый")]
VOICES = ([(v, f"{v} — {d} (жен.)") for v, d in VOICES_F] + [(v, f"{v} — {d} (муж.)") for v, d in VOICES_M])
POOL = {"f": [v for v, _ in VOICES_F], "m": [v for v, _ in VOICES_M]}
GENDER = {v: "f" for v, _ in VOICES_F} | {v: "m" for v, _ in VOICES_M}
DEFAULT_VOICE = "Charon"          # рассказчик и реплики без имени

# голос по характеру, если вы в таблице оставили «авто»
TYPE_VOICE = {"m_": "Orus", "f_": "Kore", "m_young": "Puck", "f_young": "Leda", "m_old": "Sadaltager",
              "f_old": "Gacrux", "m_child": "Fenrir", "f_child": "Laomedeia", "m_noble": "Alnilam",
              "f_noble": "Despina", "m_monster": "Algenib", "f_monster": "Pulcherrima"}

_WHO = {"old": {"m": "an old man, slightly hoarse and unhurried", "f": "an old woman, warm but aged voice"},
        "child": {"m": "a young boy of about ten, high, quick and lively", "f": "a little girl, high and lively"},
        "young": {"m": "a young man", "f": "a young woman"},
        "noble": {"m": "a noble lord, dignified and commanding", "f": "a noble lady, dignified and poised"},
        "monster": {"m": "a huge stone monster, very deep, slow, rumbling and inhuman",
                    "f": "a monstrous creature, deep and eerie"},
        "": {"m": "an adult man", "f": "an adult woman"}}
_MOOD = {"shout": "shouting loudly", "angry": "angry", "sad": "sad", "happy": "cheerful", "fear": "frightened",
         "whisper": "whispering", "calm": "calm", "ask": "", "pause": "", "question": "", "excited": "excited",
         "worried": "worried", "tired": "tired", "mysterious": "mysterious", "thoughtful": "thoughtful"}

state = {"cool_until": 0.0, "dead": set(), "warned": 0.0, "ok": False, "last_error": ""}
_lock = threading.Lock()


def ready():
    key = (config.API_KEY or "").strip()
    return bool(key) and "ВСТАВЬТЕ" not in key


def label(v):
    return dict(VOICES).get(v, v)


def type_voice(g, kind):
    return TYPE_VOICE.get(f"{g}_{kind or ''}") or TYPE_VOICE[f"{g if g in ('m', 'f') else 'm'}_"]


def style_for(gender, kind, mood="", narrator=False):
    """Короткая режиссёрская подсказка (по-английски — так модель слушается лучше всего)."""
    if narrator:
        who = "a calm storyteller narrating a fantasy tale"
    else:
        g = gender if gender in ("m", "f") else "m"
        who = (_WHO.get(kind or "") or _WHO[""])[g]
    m = _MOOD.get(mood or "", mood or "")
    return f"Say in Russian, like a voice actor in a fantasy RPG, as {who}" + (f", {m}" if m else "")


def _wav(pcm, path):
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
                struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)))
        f.write(pcm)


def synth(text, path, voice=None, style=""):
    """Фраза → .wav. Ошибка (лимит, сеть, ключ) — исключение: озвучка возьмёт запасной голос."""
    if not ready():
        raise RuntimeError("нет ключа Gemini")
    if time.time() < state["cool_until"]:
        raise RuntimeError("лимит Gemini TTS — пауза")
    text = re.sub(r"(?<=\w)\+|\+(?=[а-яёА-ЯЁ])", "", text or "").strip()     # «+» — ударения Silero
    prompt = f"{style}: {text}" if style else text
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {
                                     "voiceName": voice or config.TTS_GEMINI_VOICE or DEFAULT_VOICE}}}}}
    last = None
    for model in [config.TTS_GEMINI_MODEL] + [m for m in MODELS if m != config.TTS_GEMINI_MODEL]:
        if not model or model in state["dead"]:
            continue
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          params={"key": config.API_KEY}, json=body, timeout=max(20, config.REQUEST_TIMEOUT))
        if r.status_code == 404:
            state["dead"].add(model)
            last = f"{model}: нет у Google"
            continue
        if r.status_code == 429:
            state["cool_until"] = time.time() + 60
            raise RuntimeError("лимит Gemini TTS (429) — минуту читаю запасным голосом")
        if r.status_code != 200:
            last = f"код {r.status_code}: {r.text[:160]}"
            if r.status_code in (500, 503):
                continue
            raise RuntimeError(last)
        try:
            part = next(p for p in r.json()["candidates"][0]["content"]["parts"] if "inlineData" in p)
            pcm = base64.b64decode(part["inlineData"]["data"])
        except Exception:
            last = f"нет звука в ответе ({r.text[:120]})"
            continue
        if pcm[:4] == b"RIFF":
            with open(path, "wb") as f:
                f.write(pcm)
        else:
            if len(pcm) < 2000:
                raise RuntimeError("пустой звук")
            _wav(pcm, path)
        if not state["ok"]:
            state["ok"] = True
            core.log(f"Gemini TTS: голос работает ({model})", "ok")
        return path
    raise RuntimeError(last or "Gemini TTS не ответил")
