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

# v5 — новее: живее интонация, правильнее ударения и омографы («зАмок / замОк»). Если не скачается — v4.
MODELS = [("v5", "https://models.silero.ai/models/tts/ru/v5_ru.pt"),
          ("v4", "https://models.silero.ai/models/tts/ru/v4_ru.pt")]
MODEL_DIR = os.path.join(config.APP_DIR, "models")
MODEL_FILE = os.path.join(MODEL_DIR, "silero_v4_ru.pt")    # путь последней загруженной модели (для проверок)
SAMPLE_RATE = 24000      # 24 кГц: звучит чисто и считается быстрее, чем 48
CPU_THREADS = 4          # не забираем все ядра у игры

VOICES = [
    ("xenia", "Ксения — женский"),
    ("baya", "Бая — женский"),
    ("kseniya", "Ксения 2 — женский"),
    ("aidar", "Айдар — мужской"),
    ("eugene", "Евгений — мужской"),
]

# Дополнительные голоса — другая модель Silero (v5_cis_base): много русских голосов, но ударения ей нужно
# расставлять отдельно (пакет silero-stress). Экспериментально: если не заработает — читает основной голос.
CIS_URL = "https://models.silero.ai/models/tts/ru/v5_cis_base.pt"
CIS_FILE = os.path.join(MODEL_DIR, "silero_v5_cis_base.pt")
CIS_VOICES = {
    "m": [("ru_eduard", "Эдуард"), ("ru_alexandr", "Александр"), ("ru_bogdan", "Богдан"),
          ("ru_dmitriy", "Дмитрий"), ("ru_igor", "Игорь"), ("ru_marat", "Марат")],
    "f": [("ru_aigul", "Айгуль"), ("ru_ekaterina", "Екатерина"), ("ru_albina", "Альбина"),
          ("ru_ramilia", "Рамиля"), ("ru_vika", "Вика"), ("ru_karina", "Карина"), ("ru_zinaida", "Зинаида"),
          ("ru_zhazira", "Жазира"), ("ru_zhadyra", "Жадыра"), ("ru_zara", "Зара")],
}
for _g, _items in CIS_VOICES.items():
    VOICES += [(v, f"{n} — {'мужской' if _g == 'm' else 'женский'} (доп.)") for v, n in _items]
BASE_FOR = {"m": "aidar", "f": "xenia"}      # чем читать, если доп. голос не заработал
_cis = {"m": None, "acc": None, "error": None, "speakers_logged": False}


def cis_available():
    """Доп. голоса возможны: стоит пакет расстановки ударений silero-stress."""
    import importlib.util
    try:
        return importlib.util.find_spec("silero_stress") is not None and _cis["error"] is None
    except Exception:
        return False


def is_cis(voice):
    return str(voice).startswith("ru_")


def cis_gender(voice):
    return "m" if any(v == voice for v, _ in CIS_VOICES["m"]) else "f"


def _load_cis():
    """Модель доп. голосов + расстановщик ударений. Вызывается в потоке executor."""
    if _cis["m"] is not None:
        return _cis["m"], _cis["acc"]
    if _cis["error"]:
        raise RuntimeError(_cis["error"])
    import time
    t0 = time.time()
    try:
        load()                                   # torch уже загружен основной моделью
        torch = _model["torch"]
        if not os.path.exists(CIS_FILE) or os.path.getsize(CIS_FILE) < 10_000_000:
            core.log("Silero: скачиваю доп. голоса (~90 МБ, один раз)…", "warn")
            tmp = CIS_FILE + ".part"
            torch.hub.download_url_to_file(CIS_URL, tmp, progress=False)
            os.replace(tmp, CIS_FILE)
        m = torch.package.PackageImporter(CIS_FILE).load_pickle("tts_models", "model")
        m.to(torch.device("cpu"))
        from silero_stress import load_accentor
        acc = load_accentor()
    except Exception as e:
        _cis["error"] = f"{type(e).__name__}: {str(e)[:150]}"
        core.log(f"Silero: доп. голоса не заработали ({_cis['error']}) — персонажи будут читаться "
                 "основными голосами Silero.", "error")
        raise
    _cis.update(m=m, acc=acc)
    speakers = [s for s in (getattr(m, "speakers", None) or []) if str(s).startswith("ru_")]
    core.log(f"Silero: доп. голоса готовы (подняты в память с диска) за {time.time() - t0:.1f} с"
             + (f" ({len(speakers)} русских)" if speakers else ""), "ok")
    return m, acc

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
        global MODEL_FILE
        last_err = None
        for ver, url in MODELS:
            path = os.path.join(MODEL_DIR, f"silero_{ver}_ru.pt")
            try:
                if not os.path.exists(path) or os.path.getsize(path) < 10_000_000:
                    os.makedirs(MODEL_DIR, exist_ok=True)
                    core.log(f"Silero: скачиваю голоса {ver} (~100 МБ, один раз)…", "warn")
                    tmp = path + ".part"
                    torch.hub.download_url_to_file(url, tmp, progress=False)
                    os.replace(tmp, path)
                model = torch.package.PackageImporter(path).load_pickle("tts_models", "model")
            except Exception as e:
                last_err = e
                core.log(f"Silero {ver}: не получилось ({type(e).__name__}: {str(e)[:100]}) — пробую другую версию",
                         "warn")
                continue
            model.to(torch.device("cpu"))
            MODEL_FILE = path
            _model.update(m=model, torch=torch, ver=ver)
            core.log(f"Silero {ver}: голоса готовы — подняты в память с диска за {time.time() - t0:.1f} с", "ok")
            return model
        raise RuntimeError(f"модель не загрузилась: {last_err}")


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


_UNITS = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять",
          "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
          "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят",
         "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот",
             "девятьсот"]
# (одна форма, 2–4, 5+, женский род?)
_SCALES = [("тысяча", "тысячи", "тысяч", True), ("миллион", "миллиона", "миллионов", False),
           ("миллиард", "миллиарда", "миллиардов", False)]


def _plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def _triple(n, female=False, neuter=False):
    words = []
    h, rest = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    if rest < 20:
        if rest or not words:
            w = _UNITS[rest]
            if female and rest in (1, 2):
                w = "одна" if rest == 1 else "две"
            elif neuter and rest == 1:
                w = "одно"
            if rest or not h:
                words.append(w)
    else:
        t, u = divmod(rest, 10)
        words.append(_TENS[t])
        if u:
            if female and u in (1, 2):
                words.append("одна" if u == 1 else "две")
            elif neuter and u == 1:
                words.append("одно")
            else:
                words.append(_UNITS[u])
    return words


def number_words(n, gender="m", accusative_animate=False):
    """1234 → «одна тысяча двести тридцать четыре» (Silero сам цифры не читает).
    gender: род слова после числа — «двадцать одна монета», «две шкуры», «одно зелье»."""
    if n == 0:
        return "ноль"
    words = []
    if n < 0:
        words.append("минус")
        n = -n
    groups = []
    while n:
        n, r = divmod(n, 1000)
        groups.append(r)
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        if i == 0:
            words += _triple(g, gender in ("f", "fa"), gender == "n")
            if gender == "fa" and words and words[-1] == "одна":
                words[-1] = "одну"
            if gender == "m" and accusative_animate and words and words[-1] == "один":
                words[-1] = "одного"
        else:
            one, few, many, female = _SCALES[i - 1]
            words += _triple(g, female) + [_plural(g, one, few, many)]
    return " ".join(words)


def say_numbers(text):
    """Цифры → слова: «+120» → «плюс сто двадцать», «15%» → «пятнадцать процентов», «2.5» → «два и пять»."""
    def pct(m):
        n = int(m.group(1))
        return f"{number_words(n)} {_plural(n, 'процент', 'процента', 'процентов')}"
    text = re.sub(r"(?<=\d)[ \u00a0](?=\d{3}\b)", "", text)                  # «10 000» → «10000»
    text = re.sub(r"(\d+)\s*%", pct, text)
    text = re.sub(r"(\d+)[.,](\d+)", lambda m: f"{number_words(int(m.group(1)))} и "
                  f"{number_words(int(m.group(2)))}", text)
    text = re.sub(r"(\d+)\s*/\s*(\d+)", lambda m: f"{m.group(1)} из {m.group(2)}", text)
    text = re.sub(r"(?:(?<=\s)|^)\+(?=\d)", "плюс ", text)
    text = re.sub(r"(?:(?<=\s)|^)[-−](?=\d)", "минус ", text)
    text = re.sub(r"(?:([а-яёА-ЯЁ]+)(\s+))?(\d{1,12})(\s+)([а-яёА-ЯЁ]+(?:\s+[а-яёА-ЯЁ]+)?)",
                  lambda m: (m.group(1) or "") + (m.group(2) or "")
                  + _num_with_noun(int(m.group(3)), m.group(5), m.group(1))
                  + m.group(4) + m.group(5), text)
    text = re.sub(r"\d{1,12}", lambda m: number_words(int(m.group(0))), text)
    return text


_PREPOSITIONS = {"в", "во", "на", "о", "об", "обо", "при", "по", "к", "ко", "с", "со", "у", "от", "до", "из",
                 "за", "под", "над", "без", "для", "через", "про"}


def _imperative(word):
    """Похоже на повелительный глагол: «убей», «найди», «принесите», «брось» (но не «осталась»)."""
    w = (word or "").lower()
    if not w or w in _PREPOSITIONS or w.endswith(("сь", "ся")):
        return False
    return w.endswith(("й", "и", "ь", "те"))


def _num_with_noun(n, words, prev):
    if prev and prev.lower() in _PREPOSITIONS:
        return number_words(n)       # «в 1 году», «из 2 частей» — падеж не угадываем, читаем как есть
    g = noun_gender(n, words, prev)
    w = words.split()[0].lower()
    animate_acc = (g == "m" and n % 10 == 1 and n % 100 != 11 and _imperative(prev)
                   and w.endswith(("а", "я")))
    return number_words(n, g, animate_acc)


_ADJ_ENDINGS = ("ые", "ие", "ых", "их", "ый", "ий", "ой", "ая", "яя", "ое", "ее")


def noun_gender(n, words, prev=None):
    """Род слова после числа — по его окончанию (переводчик уже поставил нужную форму):
    1/21 → «монета» (ж), «зелье» (ср), «меч» (м); 2–4 → «монеты» (ж) / «меча» (м)."""
    last2, last = n % 100, n % 10
    if 11 <= last2 <= 19 or last not in (1, 2):
        return "m"                     # для остальных чисел род не важен
    ws = [w.lower() for w in words.split()]
    if last == 1:
        w = ws[0]
        if w.endswith(("ую", "юю")) or (not w.endswith(_ADJ_ENDINGS) and w.endswith(("у", "ю"))):
            return "fa"                # «принеси одну шкуру» (винительный, женский род)
        verb_before = _imperative(prev)
        if verb_before and w.endswith(("а", "я")) and not w.endswith(("ая", "яя")):
            return "m"                 # «убей одного волка»: после глагола «-а» — это мужской род
        if w.endswith(("ого", "его")):
            return "m"
        if w.endswith(("ая", "яя")):
            return "f"
        if w.endswith(("ое", "ее")):
            return "n"
        if w.endswith(_ADJ_ENDINGS):
            return "m"
        if w.endswith(("а", "я")):
            return "f"
        if w.endswith(("о", "е", "ё")):
            return "n"
        return "m"
    # 2, 22…: прилагательное («две старые монеты») пропускаем, смотрим на существительное
    noun = next((w for w in ws if not w.endswith(_ADJ_ENDINGS)), ws[-1])
    return "f" if noun.endswith(("ы", "и")) else "m"


def clean(text):
    """Silero читает только кириллицу: английские слова переводим в русские буквы, лишние значки убираем."""
    text = say_numbers(text)
    text = re.sub(r"[A-Za-z]+", lambda m: translit(m.group(0)), text)
    text = re.sub(r"[«»\"“”„*_#~<>\[\]{}|/\\]", " ", text)
    text = text.replace("…", "...")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.!?:;])", r"\1", text)      # «друг ,» → «друг,»
    text = re.sub(r"([,.!?:;])(?:\s*[,:;])+", r"\1", text)  # «Привет, , мир» → «Привет, мир»
    return text.strip(" ,:;-—")


def _apply(model, kw, **text_kw):
    """apply_tts с удачными настройками ударений; у старых моделей части параметров нет — без них."""
    try:
        return model.apply_tts(**text_kw, **kw, put_stress_homo=True, put_yo_homo=True)
    except TypeError:
        return model.apply_tts(**text_kw, **kw)


_PITCHES = {-2: "x-low", -1: "low", 0: "medium", 1: "high", 2: "x-high"}


TIMBRE = {-3: 0.80, -2: 0.88, -1: 0.94, 1: 1.07, 2: 1.18}   # характер голоса: чудовище … ребёнок


def _split_pitch(p):
    """Число высоты → (ступень разметки -2…2, множитель тембра). Десятки — тембр характера (voices.TYPE_PITCH)."""
    p = int(p or 0)
    k = int(round(p / 10)) if abs(p) >= 8 else 0
    return max(-2, min(2, p - 10 * k)), TIMBRE.get(max(-3, min(2, k)), 1.0)


def _timbre(audio, f, torch):
    """Сдвинуть тембр: f<1 — ниже и чуть медленнее (старик, чудовище), f>1 — выше и быстрее (ребёнок)."""
    if abs(f - 1.0) < 0.01:
        return audio
    n = max(1, int(audio.shape[-1] / f))
    return torch.nn.functional.interpolate(audio.reshape(1, 1, -1).float(), size=n, mode="linear",
                                           align_corners=False).reshape(-1)


def synth_to_wav(text, path, voice, rate_level=0, pitch_level=0):
    """Синтез фразы в wav-файл. Вызывается в потоке executor."""
    if is_cis(voice):
        try:
            return _synth_cis(text, path, voice, rate_level, pitch_level)
        except ValueError:
            raise
        except Exception:
            voice = BASE_FOR[cis_gender(voice)]      # доп. голос не вышел — основной того же пола
    model = load()
    torch = _model["torch"]
    text = clean(text)
    if sum(ch.isalpha() for ch in text) < 2:
        raise ValueError("нечего читать")
    rate = _prosody_rate(rate_level)
    step, timbre = _split_pitch(pitch_level)
    pitch = _PITCHES.get(step, "medium")
    kw = dict(speaker=voice, sample_rate=SAMPLE_RATE, put_accent=True, put_yo=True)
    with torch.no_grad():
        audio = None
        if rate != "medium" or pitch != "medium":
            attrs = (f' rate="{rate}"' if rate != "medium" else "") + (f' pitch="{pitch}"' if pitch != "medium" else "")
            try:
                audio = _apply(model, kw, ssml_text=f'<speak><prosody{attrs}>{escape(text)}</prosody></speak>')
            except Exception:
                audio = None     # модель не поняла разметку скорости/высоты — читаем обычным голосом
        if audio is None:
            audio = _apply(model, kw, text=text)
    _write_wav(path, _timbre(audio, timbre, torch), torch)
    return path


def _write_wav(path, audio, torch):
    pcm = (audio.clamp(-1, 1) * 32767).to(torch.int16).tolist()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(array.array("h", pcm).tobytes())


def _synth_cis(text, path, voice, rate_level=0, pitch_level=0):
    """Доп. голос: расставляем ударения («мен+я») и синтезируем моделью v5_cis_base."""
    model, acc = _load_cis()
    torch = _model["torch"]
    text = clean(text)
    if sum(ch.isalpha() for ch in text) < 2:
        raise ValueError("нечего читать")
    speakers = getattr(model, "speakers", None)
    if speakers and voice not in speakers:
        if not _cis["speakers_logged"]:
            _cis["speakers_logged"] = True
            core.log("Silero: такого доп. голоса нет в модели. Есть: "
                     + ", ".join(s for s in speakers if str(s).startswith("ru_"))[:300], "warn")
        raise RuntimeError(f"нет голоса {voice}")
    stressed = re.sub(r"\+{2,}", "+", acc(text))
    rate = _prosody_rate(rate_level)
    step, timbre = _split_pitch(pitch_level)
    pitch = _PITCHES.get(step, "medium")
    kw = dict(speaker=voice, sample_rate=SAMPLE_RATE)
    with torch.no_grad():
        audio = None
        if rate != "medium" or pitch != "medium":
            attrs = (f' rate="{rate}"' if rate != "medium" else "") + (f' pitch="{pitch}"' if pitch != "medium" else "")
            try:
                audio = model.apply_tts(ssml_text=f'<speak><prosody{attrs}>{escape(stressed)}</prosody></speak>', **kw)
            except Exception:
                audio = None
        if audio is None:
            audio = model.apply_tts(text=stressed, **kw)
    _write_wav(path, _timbre(audio, timbre, torch), torch)
    return path
