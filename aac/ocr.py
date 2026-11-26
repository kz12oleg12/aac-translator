"""Распознавание текста на ПК (OCR Windows / RapidOCR) и фильтр мусора."""


import re

import threading


from PIL import Image

from . import config, core, glossary


# ---------- распознавание текста на ПК (OCR) + машинный перевод ----------
_ocr_engine = None
_ocr_kind = None        # "windows" или "rapid"
_rapid = None


def _init_ocr():
    """Встроенный OCR Windows; если не установлен — RapidOCR (если есть)."""
    global _ocr_engine, _ocr_kind, _rapid
    if _ocr_kind:
        return
    try:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        lang = Language(config.OCR_LANGUAGE)
        if not OcrEngine.is_language_supported(lang):
            raise core.ApiError(
                f"В Windows не установлено распознавание языка {config.OCR_LANGUAGE}. Откройте PowerShell от имени "
                f"администратора и выполните: Add-WindowsCapability -Online -Name "
                f"\"Language.OCR~~~{config.OCR_LANGUAGE}~0.0.1.0\" — затем перезапустите переводчик.")
        _ocr_engine = OcrEngine.try_create_from_language(lang)
        _ocr_kind = "windows"
        core.log(f"Распознавание текста: встроенный OCR Windows ({config.OCR_LANGUAGE})", "ok")
        return
    except ImportError:
        pass
    try:
        from rapidocr import RapidOCR
        _rapid = RapidOCR()
        _ocr_kind = "rapid"
        core.log("Распознавание текста: RapidOCR", "ok")
    except ImportError:
        raise core.ApiError("Не установлены пакеты распознавания текста. Выполните в командной строке:\n"
                       "py -m pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging "
                       "winrt-Windows.Globalization winrt-Windows.Foundation winrt-Windows.Storage.Streams")


_ocr_lock = threading.Lock()   # распознаватель Windows не умеет читать две картинки одновременно


def ocr_lines(img):
    """Возвращает список строк текста с картинки."""
    from . import bench
    if bench.active():                  # стенд проверки: текст из поля ввода, а не с экрана
        return list(bench.lines())
    with _ocr_lock:
        return _ocr_lines(img)


def _looks_like_garbage(line):
    """Русский текст, прочитанный английским распознавателем, выглядит как «PeHaJ1bA», «3T0 TaM?!»:
    цифры внутри слов и заглавные буквы посреди слова. Такие строки выбрасываем."""
    words = [w for w in re.split(r"\s+", line) if sum(ch.isalpha() for ch in w) >= 2]
    if not words:
        return True
    weird = sum(1 for w in words
                if re.search(r"[a-z][A-Z]", w) or re.search(r"[A-Za-z][0-9]|[0-9][A-Za-z]", w))
    return weird * 3 >= len(words)


def _ocr_raw(img):
    """Сырые строки с рамками: [(текст, (x0, y0, x1, y1))] в координатах исходной картинки."""
    _init_ocr()
    img = img.convert("RGB")
    scale = 1.0
    # мелкий текст OCR читает хуже — увеличиваем
    if img.height < 150:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        scale = 2.0
    if _ocr_kind == "windows":
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winrt.windows.media.ocr import OcrEngine
        limit = OcrEngine.max_image_dimension  # статическое свойство класса
        if max(img.size) > limit:
            w0 = img.width
            img.thumbnail((limit, limit))
            scale *= img.width / w0
        data = img.convert("RGBA").tobytes("raw", "BGRA")
        bmp = SoftwareBitmap.create_copy_from_buffer(data, BitmapPixelFormat.BGRA8, img.width, img.height,
                                                     BitmapAlphaMode.PREMULTIPLIED)
        result = _ocr_engine.recognize_async(bmp).get()
        out = []
        for ln in result.lines:
            box = None
            try:
                rects = [w.bounding_rect for w in ln.words]
                box = (min(r.x for r in rects), min(r.y for r in rects),
                       max(r.x + r.width for r in rects), max(r.y + r.height for r in rects))
            except Exception:
                pass
            out.append((ln.text, box))
    else:
        import numpy as np
        res = _rapid(np.array(img))
        boxes, texts = getattr(res, "boxes", None), getattr(res, "txts", None) or []
        items = []
        if boxes is not None:
            for b, t in zip(boxes, texts):
                xs, ys = [p[0] for p in b], [p[1] for p in b]
                items.append((min(ys), min(xs), t, (min(xs), min(ys), max(xs), max(ys))))
        items.sort()
        # склеиваем куски на одной строке
        out, cur_y = [], None
        for y, x, t, bx in items:
            if cur_y is not None and abs(y - cur_y) < 12:
                pt, pb = out[-1]
                out[-1] = (pt + " " + t, (min(pb[0], bx[0]), min(pb[1], bx[1]), max(pb[2], bx[2]), max(pb[3], bx[3])))
            else:
                out.append((t, bx))
                cur_y = y
    # координаты — целые пиксели (OCR Windows отдаёт дробные, Tk такие не принимает)
    out = [(t, tuple(int(v / scale) for v in b) if b else None) for t, b in out]
    return out


_KEY_NAMES = {"esc", "tab", "shift", "ctrl", "alt", "enter", "space", "spacebar", "del", "lmb", "rmb", "mmb"}


def _is_key(tok):
    t = tok.strip("[](){}<>|:")
    if not t:
        return False
    return (t.lower() in _KEY_NAMES or (len(t) == 1 and (t.isupper() or t.isdigit()))
            or re.fullmatch(r"F\d{1,2}", t) is not None)


def is_key_hints(ln):
    """Строка подсказок клавиш внизу экрана: «Esc Close  T Track  F Fast Travel  H Destination List».
    Клавиша + слово с заглавной; таких пар 2 и больше (или одна короткая «F Talk»), без знаков предложения."""
    if re.search(r"[.!?,;\"«»]", ln):
        return False
    toks = ln.split()
    pairs = 0
    for a, b in zip(toks, toks[1:]):
        if _is_key(a) and b[:1].isupper() and not _is_key(b):
            pairs += 1
    if pairs >= 2:
        return True
    if pairs == 1 and len(toks) <= 3 and _is_key(toks[0]) and toks[0].strip("[](){}<>|:") not in ("I", "A"):
        return True
    return False


_VOWELS = set("AEIOUYaeiouyАЕЁИОУЫЭЮЯаеёиоуыэюя")


def _has_real_word(ln):
    """Есть ли хоть одно похожее на слово: 2+ буквы, есть гласная и есть буква кроме I/l
    (узор мостовой и травы OCR читает как «Il lI», «rn»)."""
    for w in re.findall(r"[^\W\d_]{2,}", ln):
        if any(ch in _VOWELS for ch in w) and any(ch not in "Iil" for ch in w):
            return True
    return False


def _clean_line(ln, clean):
    """Отфильтровать строку OCR: мусор, водяной знак, слова интерфейса. None — выбросить."""
    ln = ln.strip()
    low = ln.lower()
    letters = sum(ch.isalpha() for ch in ln)
    if letters < 2 or letters < 0.5 * len(ln.replace(" ", "")):
        return None  # мусор с фона
    if letters < 6 and not _has_real_word(ln):
        return None  # «Il II», «rn .» — узор мостовой/травы, прочитанный как буквы
    if any(w in low for w in config.WATERMARK_WORDS) or "windows" in low:
        return None  # водяной знак Windows (в т.ч. русский, прочитанный как латиница)
    if config.SOURCE_LANG == "en" and _looks_like_garbage(ln):
        return None  # не английский текст (наш же перевод, водяной знак, мусор с фона)
    if is_key_hints(ln):
        return None  # подсказки клавиш внизу экрана (карта, инвентарь, «F Talk»)
    # слова интерфейса (Skip, Next…): строка целиком — выбрасываем; в конце строки — отрезаем
    ignore = glossary.ignored_words()
    if glossary.normalize(ln) in ignore:
        return None
    words = ln.split()
    while len(words) > 1 and glossary.normalize(words[-1]) in ignore:
        words.pop()
    ln = " ".join(words)
    if ln in clean:
        return None  # одинаковые строки — один раз
    return ln


def _ocr_lines(img):
    clean = []
    for t, _ in _ocr_raw(img):
        ln = _clean_line(t, clean)
        if ln:
            clean.append(ln)
    return clean


def ocr_boxes(img):
    """Строки текста с рамками (для поиска подсказки под мышкой): [(текст, (x0, y0, x1, y1))]."""
    with _ocr_lock:
        raw = _ocr_raw(img)
    clean, out = [], []
    for t, b in raw:
        ln = _clean_line(t, clean)
        if ln and b:
            clean.append(ln)
            out.append((ln, b))
    return out
