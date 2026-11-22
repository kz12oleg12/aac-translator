"""Свой голос для каждого персонажа.

Имя говорящего берём из субтитров (первая строка «Kesper» или «Kesper: …»). Пол угадываем:
  1) по русской грамматике в переводе: «я пришла / я рада» — женщина, «я пришёл / я рад» — мужчина
     (каждая реплика добавляет «голос» в копилку, решение крепнет со временем);
  2) пока подсказок нет — по имени («…a», «…ия» — женское), иначе мужской.
Голос выбирается из голосов нужного пола стабильно по имени (у Кеспера всегда один и тот же),
плюс немного сдвигается высота — чтобы персонажи с одним голосом всё равно отличались.
Всё запоминается в characters.json; пол и голос можно поменять вручную (Настройки → Голоса персонажей).
"""
import json
import os
import re
import threading
import time
import zlib

from . import config, core

FILE = os.path.join(config.APP_DIR, "characters.json")
_lock = threading.Lock()
_data = {"loaded": False, "chars": {}}

# голоса по полу для каждого движка (id голоса)
NEURAL_POOL = {
    "m": ["ru-RU-DmitryNeural", "en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural",
          "fr-FR-RemyMultilingualNeural", "de-DE-FlorianMultilingualNeural"],
    "f": ["ru-RU-SvetlanaNeural", "en-US-AvaMultilingualNeural", "en-US-EmmaMultilingualNeural",
          "fr-FR-VivienneMultilingualNeural", "de-DE-SeraphinaMultilingualNeural"],
}
SILERO_POOL = {"m": ["aidar", "eugene"], "f": ["xenia", "baya", "kseniya"]}
NEURAL_PITCH = [-6, -3, 0, 3, 6]        # сдвиг высоты, Гц
SILERO_PITCH = [-1, 0, 1]               # low / medium / high

_F_RE = re.compile(r"\bя\s+(?:[а-яё]+\s+)?[а-яё]+(?:ла|лась)\b|\bя\s+(?:так\s+|очень\s+|не\s+)?"
                   r"(?:рада|готова|уверена|должна|согласна|благодарна|счастлива|одна|сама|права|занята)\b", re.I)
_M_RE = re.compile(r"\bя\s+(?:[а-яё]+\s+)?[а-яё]+(?:л|лся|шёл|шел)\b|\bя\s+(?:так\s+|очень\s+|не\s+)?"
                   r"(?:рад|готов|уверен|должен|согласен|благодарен|счастлив|один|сам|прав|занят)\b", re.I)
_NAME_LINE = re.compile(r"^[A-ZА-ЯЁ][\w'’\-]*(?:\s+[A-ZА-ЯЁ][\w'’\-]*){0,2}$")
_NAME_COLON = re.compile(r"^([A-ZА-ЯЁ][\w'’\-]*(?:\s+[A-ZА-ЯЁ][\w'’\-]*){0,2})\s*[:：]\s*\S")


def _load():
    if _data["loaded"]:
        return
    _data["loaded"] = True
    try:
        with open(FILE, encoding="utf-8") as f:
            _data["chars"] = json.load(f)
    except Exception:
        _data["chars"] = {}


def _save():
    try:
        tmp = FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_data["chars"], f, ensure_ascii=False, indent=1)
        os.replace(tmp, FILE)
    except Exception as e:
        core.log(f"Не удалось сохранить голоса персонажей: {e}", "error")


def _name_from(text):
    """Имя говорящего из текста субтитров (оригинала или перевода) или None."""
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1 and len(lines[0]) <= 30 and _NAME_LINE.match(lines[0]):
        return lines[0]
    if lines:
        m = _NAME_COLON.match(lines[0])
        if m:
            return m.group(1)
    return None


def key_of(name):
    return re.sub(r"[^\w]", "", (name or "").lower())


def speaker(translation, orig=None):
    """(ключ, английское имя, русское имя) говорящего или None, если реплика без имени."""
    en = _name_from(orig)
    ru = _name_from(translation)
    name = en or ru
    if not name:
        return None
    return key_of(name), en or "", ru or ""


def gender_votes(translation):
    """Подсказки пола из русской грамматики реплики: (за женский, за мужской)."""
    text = translation or ""
    return len(_F_RE.findall(text)), len(_M_RE.findall(text))


def guess_by_name(en, ru):
    n_en = (en or "").lower()
    n_ru = (ru or "").lower()
    if n_ru and n_ru[-1:] in "ая" and not n_ru.endswith(("ия", "ья")) or n_ru.endswith("ия"):
        return "f"
    if n_en.endswith(("a", "ia", "ette", "elle", "ine", "lyn", "ie")):
        return "f"
    return "m"


def gender(c):
    """Пол персонажа: ваш выбор → догадка нейросети по имени и реплике → русская грамматика → имя."""
    if c.get("gender_manual") in ("m", "f"):
        return c["gender_manual"]
    if c.get("ai") in ("m", "f"):
        return c["ai"]
    f, m = c.get("f", 0), c.get("m", 0)
    if f > m:
        return "f"
    if m > f:
        return "m"
    return c.get("guess", "m")


def known_gender(c):
    """Пол, в котором мы уверены (для подсказки переводчику), или None."""
    if c.get("gender_manual") in ("m", "f"):
        return c["gender_manual"]
    if c.get("ai") in ("m", "f"):
        return c["ai"]
    f, m = c.get("f", 0), c.get("m", 0)
    if abs(f - m) >= 2:
        return "f" if f > m else "m"
    return None


AI_PROMPT = ("In the fantasy MMORPG ArcheAge Chronicles an NPC named \"{name}\" says: \"{line}\"\n"
             "Is this character male or female? Judge by the name and the line. "
             "Answer with exactly one letter: m (male), f (female) or u (cannot tell).")
ask_ai = None        # функция prompt -> ответ (подставляет translate: та же нейросеть, что переводит)


def _ai_gender(key, en, line):
    """Спросить нейросеть о поле нового персонажа (один раз на персонажа, ответ запоминается)."""
    if ask_ai is None or not en:
        return
    try:
        ans = (ask_ai(AI_PROMPT.format(name=en, line=(line or "")[:200])) or "").strip().lower()
    except Exception:
        return
    g = ans[:1] if ans[:1] in ("m", "f") else "u"
    with _lock:
        c = _data["chars"].get(key)
        if c is not None:
            c["ai"] = g
            _save()


def gender_hint(src):
    """Подсказка переводчику: кто из говорящих мужчина/женщина (чтобы «я пришёл/пришла» было верно)."""
    name = _name_from(src)
    if not name:
        return ""
    with _lock:
        _load()
        c = _data["chars"].get(key_of(name))
        g = known_gender(c) if c else None
    if not g:
        return ""
    return (f"\nThe speaker {name} is {'a woman' if g == 'f' else 'a man'} — use matching "
            f"{config.TARGET_LANG_EN} grammar (verb and adjective endings).")


def flip_last():
    """Клавиша «сменить пол говорящего»: последний персонаж — противоположного пола (запоминается)."""
    with _lock:
        _load()
        key = _data.get("last")
        c = _data["chars"].get(key) if key else None
        if c is None:
            return None
        new = "f" if gender(c) == "m" else "m"
        c["gender_manual"] = new
        _save()
        return (c.get("ru") or c.get("en") or key), new


def note_line(translation, orig=None):
    """Учесть реплику: запомнить персонажа и подсказки его пола. Возвращает ключ или None."""
    sp = speaker(translation, orig)
    if not sp:
        return None
    key, en, ru = sp
    f, m = gender_votes(translation)
    with _lock:
        _load()
        if key not in _data["chars"] and ru:
            # тот же персонаж, но в прошлый раз имя пришло по-русски (или наоборот) — не заводим двойника
            for k, c in _data["chars"].items():
                if c.get("ru") == ru or (en and c.get("en") == en):
                    key = k
                    break
        c = _data["chars"].setdefault(key, {"en": en, "ru": ru, "guess": guess_by_name(en, ru), "f": 0, "m": 0})
        if en and not c.get("en"):
            c["en"] = en
        if ru:
            c["ru"] = ru
        c["f"] = c.get("f", 0) + f
        c["m"] = c.get("m", 0) + m
        c["seen"] = time.time()
        c["lines"] = c.get("lines", 0) + 1
        _data["last"] = key
        need_ai = "ai" not in c and not c.get("gender_manual")
        _save()
    if need_ai:
        # новый персонаж: спрашиваем нейросеть (с ожиданием до ~3 с — чтобы уже первая реплика была нужным голосом)
        t = threading.Thread(target=_ai_gender, args=(key, en or ru, _line_of(orig or translation)), daemon=True)
        t.start()
        t.join(3.0)
    return key


def _line_of(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) > 1 and _name_from(text) == lines[0]:
        return " ".join(lines[1:])
    m = _NAME_COLON.match(lines[0]) if lines else None
    return lines[0][m.end(1):].lstrip(" :：") if m else " ".join(lines)


def voice_for(key, engine=None, auto_only=False):
    """(голос, сдвиг высоты) для персонажа на текущем движке; None — читать основным голосом."""
    engine = engine or config.TTS_ENGINE
    if not key or engine not in ("neural", "silero"):
        return None
    with _lock:
        _load()
        c = _data["chars"].get(key)
        if c is None:
            return None
        g = gender(c)
        manual = c.get(f"voice_{engine}")
    h = zlib.crc32(key.encode("utf-8"))
    if engine == "neural":
        pool, pitches, main = NEURAL_POOL[g], NEURAL_PITCH, config.TTS_NEURAL_VOICE
    else:
        pool, pitches, main = SILERO_POOL[g], SILERO_PITCH, config.TTS_SILERO_VOICE
    if manual and not auto_only:
        return manual, 0
    pitch = pitches[(h // 7) % len(pitches)]
    default = default_voice(engine, g)
    if default:
        # голос по умолчанию для мужчин/женщин; высота чуть разная, чтобы персонажи всё же отличались
        return default, pitch
    # основной голос (которым читается рассказчик) персонажам — пореже: ставим его в конец очереди
    pool = [v for v in pool if v != main] + [v for v in pool if v == main]
    if config.TTS_RUSSIAN_ONLY and engine == "neural":
        pool = [v for v in pool if v.startswith("ru-")] or pool
    voice = pool[h % len(pool)]
    pitch = pitches[(h // 7) % len(pitches)]
    return voice, pitch


def default_voice(engine, g):
    """Голос по умолчанию для пола g ("m"/"f") на движке engine; "" — подбирать разные автоматически."""
    return (config.TTS_DEFAULT_VOICES.get(engine) or {}).get(g, "")


def set_default_voice(engine, g, voice):
    config.TTS_DEFAULT_VOICES.setdefault(engine, {})[g] = voice or ""
    core.save_settings(tts_default_voices=config.TTS_DEFAULT_VOICES)


def all_chars():
    """Список персонажей для окна настроек: свежие — сверху."""
    with _lock:
        _load()
        items = [(k, dict(c)) for k, c in _data["chars"].items()]
    return sorted(items, key=lambda kc: -kc[1].get("seen", 0))


def set_manual(key, gender_value=None, voice=None, engine=None):
    """gender_value: "m"/"f"/"" (авто); voice: id голоса или "" (авто) для движка engine."""
    with _lock:
        _load()
        c = _data["chars"].get(key)
        if c is None:
            return
        if gender_value is not None:
            c["gender_manual"] = gender_value
        if voice is not None:
            c[f"voice_{engine or config.TTS_ENGINE}"] = voice
        _save()


def forget(key):
    with _lock:
        _load()
        _data["chars"].pop(key, None)
        _save()
