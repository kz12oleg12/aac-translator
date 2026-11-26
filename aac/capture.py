"""Скриншоты областей, подготовка картинок, определение смены текста."""
import base64

import io


import mss

from PIL import Image, ImageChops, ImageStat

from . import config


# ---------- скриншот ----------
def grab(reg):
    MSS = getattr(mss, "MSS", None) or mss.mss  # в новых версиях mss.mss устарел
    with MSS() as sct:
        mon = sct.monitors[1]
        box = {"left": reg[0], "top": reg[1], "width": reg[2], "height": reg[3]} if reg else mon
        shot = sct.grab(box)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def mask_out(img, reg, other):
    """Закрашивает чёрным часть картинки, которая попадает в другую область
    (чтобы субтитры не попадали в перевод ответов, если области пересекаются)."""
    if not other or not reg:
        return img
    if isinstance(other[0], (tuple, list)) or other[0] is None:   # несколько областей
        for o in other:
            img = mask_out(img, reg, o)
        return img
    x0, y0 = max(reg[0], other[0]), max(reg[1], other[1])
    x1 = min(reg[0] + reg[2], other[0] + other[2])
    y1 = min(reg[1] + reg[3], other[1] + other[3])
    if x1 <= x0 or y1 <= y0:
        return img
    from PIL import ImageDraw
    img = img.copy()
    ImageDraw.Draw(img).rectangle([x0 - reg[0], y0 - reg[1], x1 - reg[0] - 1, y1 - reg[1] - 1], fill=(0, 0, 0))
    return img


def encode(img, max_side=None):
    img = img.copy()
    side = max_side or config.MAX_IMAGE_SIDE
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def text_mask(img, brightness=None):
    """Уменьшенная чёрно-белая маска светлых пикселей — по ней видно, сменился ли текст,
    даже если за субтитрами двигается видео кат-сцены."""
    # сначала выделяем светлые пиксели в полном разрешении (иначе тонкие буквы размоются),
    # потом уменьшаем: каждая клетка = доля «текстовых» пикселей в ней
    thr = brightness or config.TEXT_BRIGHTNESS
    full = img.convert("L").point(lambda p: 255 if p >= thr else 0)
    w = 240
    h = max(8, int(img.height * w / max(img.width, 1)))
    return full.resize((w, h), Image.BOX)


def mask_diff(a, b):
    if a is None or b is None or a.size != b.size:
        return 1.0
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] / 255.0


def mask_change(a, b):
    """Насколько сменился текст — относительно его количества. Большая область с небольшой репликой:
    по общей разнице две похожие по длине реплики почти неотличимы, а по этой мере — явно разные."""
    if a is None or b is None or a.size != b.size:
        return 1.0
    d = mask_diff(a, b)
    amt = max(text_amount(a), text_amount(b))
    return d / amt if amt > 0.0005 else d


def text_amount(m):
    """Доля «текстовых» (светлых) пикселей в области."""
    return ImageStat.Stat(m).mean[0] / 255.0


def mask_empty(m):
    return text_amount(m) < 0.002
