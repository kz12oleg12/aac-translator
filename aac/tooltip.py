"""Перевод подсказки под мышкой (предмет, навык, эффект).

Наводите мышку на предмет → жмёте клавишу «подсказка у мыши» → программа снимает кусок экрана
вокруг курсора, находит блок текста, ближайший к мышке (саму подсказку), и переводит только его.
Перевод встаёт рядом с подсказкой и прячется, когда уводите мышку.
"""
import ctypes
import threading
import time

from . import capture, config, core, history, ocr, translate

_lock = threading.Lock()


def cursor_pos():
    """Положение мышки на экране (None — не Windows)."""
    try:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return None


def screen_size():
    try:
        u = ctypes.windll.user32
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


def search_box(cx, cy, sw, sh, box=None):
    """Прямоугольник экрана вокруг курсора, где ищем подсказку: (x, y, w, h)."""
    bw, bh = box or config.TOOLTIP_BOX
    bw, bh = min(bw, sw), min(bh, sh)
    x = min(max(0, cx - bw // 2), sw - bw)
    y = min(max(0, cy - bh // 2), sh - bh)
    return x, y, bw, bh


def group_blocks(lines):
    """Строки OCR с рамками → блоки текста (строки, стоящие плотно друг под другом).
    lines: [(текст, (x0, y0, x1, y1))]. Возвращает [{"lines": [...], "box": (x0, y0, x1, y1)}]."""
    blocks = []
    for text, b in sorted(lines, key=lambda t: (t[1][1], t[1][0])):
        h = max(8, b[3] - b[1])
        best = None
        for bl in blocks:
            bx0, by0, bx1, by1 = bl["box"]
            gap = b[1] - by1
            lh = bl["lh"]
            near_v = -h <= gap <= max(1.8 * lh, 14)
            near_h = b[0] < bx1 + 2 * lh and b[2] > bx0 - 2 * lh
            if near_v and near_h:
                best = bl
                break
        if best is None:
            blocks.append({"lines": [text], "box": tuple(b), "lh": h})
        else:
            bx0, by0, bx1, by1 = best["box"]
            best["lines"].append(text)
            best["box"] = (min(bx0, b[0]), min(by0, b[1]), max(bx1, b[2]), max(by1, b[3]))
            best["lh"] = (best["lh"] * (len(best["lines"]) - 1) + h) / len(best["lines"])
    return blocks


def pick_block(blocks, cx, cy):
    """Подсказка — блок рядом с курсором; среди близких предпочитаем блок из нескольких строк."""
    def score(bl):
        x0, y0, x1, y1 = bl["box"]
        dx = max(x0 - cx, 0, cx - x1)
        dy = max(y0 - cy, 0, cy - y1)
        dist = (dx * dx + dy * dy) ** 0.5
        return dist - 40 * min(len(bl["lines"]), 6)
    return min(blocks, key=score) if blocks else None


def translate_at_cursor(pos=None):
    """Найти подсказку у курсора и перевести. Работает в фоновом потоке."""
    if not _lock.acquire(blocking=False):
        return
    try:
        pos = pos or cursor_pos()
        if pos is None:
            core.log("Подсказка: не удалось узнать, где мышка", "error")
            return
        cx, cy = pos
        sw, sh = screen_size()
        x, y, w, h = search_box(cx, cy, sw, sh)
        core.events.put(("tooltip_show", {"text": "⏳ Перевожу подсказку…", "pos": pos, "box": None}))
        img = capture.grab((x, y, w, h))
        try:
            lines = ocr.ocr_boxes(img)
        except core.ApiError as e:
            core.log(f"Подсказка: {e}", "error")
            core.events.put(("tooltip_hide", None))
            return
        bl = pick_block(group_blocks(lines), cx - x, cy - y)
        if bl is None:
            core.events.put(("tooltip_show", {"text": "Текста возле мышки не нашёл. Наведите на предмет и нажмите ещё раз.",
                                         "pos": pos, "box": None}))
            return
        pad = 10
        bx0, by0, bx1, by1 = bl["box"]
        crop = (max(0, bx0 - pad), max(0, by0 - pad), min(w, bx1 + pad), min(h, by1 + pad))
        screen_box = (x + crop[0], y + crop[1], crop[2] - crop[0], crop[3] - crop[1])
        if config.SHOW_OCR_IN_LOG:
            core.log(f"Подсказка: {' / '.join(bl['lines'])[:150]}")
        t0 = time.time()
        text, err = translate.safe_translate(img.crop(crop), config.TOOLTIP_PROMPT)
        if err == "rate":
            err = "лимит запросов — подождите несколько секунд и нажмите ещё раз"
        if err:
            core.log(f"Подсказка: {err}", "error")
            core.events.put(("tooltip_show", {"text": "❌ Не получилось — подробности в системной панели.",
                                         "pos": pos, "box": screen_box}))
            return
        orig = history.last_source() or "\n".join(bl["lines"])
        core.events.put(("tooltip_show", {"text": (text, orig) if text else "Текст не найден",
                                     "pos": pos, "box": screen_box}))
        if text:
            history.history_add("Подсказка", orig, text)
            core.log(f"Подсказка переведена за {time.time() - t0:.1f} с")
    finally:
        _lock.release()


def place(box, pos, win_w, win_h, sw, sh, gap=12):
    """Куда поставить окно перевода: слева от подсказки, если там есть место, иначе справа/под ней."""
    if box:
        x0, y0, bw, bh = box
        if x0 - gap - win_w >= 0:
            x = x0 - gap - win_w
        elif x0 + bw + gap + win_w <= sw:
            x = x0 + bw + gap
        else:
            x = max(0, min(sw - win_w, x0))
        y = max(0, min(sh - win_h, y0))
        return x, y
    cx, cy = pos
    return max(0, min(sw - win_w, cx + 24)), max(0, min(sh - win_h, cy + 24))
