"""Перевод игрового чата.

Входящие: отдельная область чата (её обводят один раз). Раз в секунду программа читает её, находит НОВЫЕ
строки (уже переведённые не трогает) и переводит только сам текст сообщения — «[World] Ник:» остаются
как есть. Переводы копятся в окошке «💬 Чат».

Исходящие: клавиша «написать в чат» открывает маленькое поле ввода. Пишете по-русски, Enter — английский
перевод сразу в буфере обмена: в игре открыть чат и Ctrl+V.
"""
import collections
import re
import threading
import time

from . import capture, config, core, game, history, llm, mt, ocr, translate

# «[World] Vanersis: текст», «Vanersis: текст», «[Faction] [Guild] Nick : текст»
_LINE = re.compile(r"^((?:\s*\[[^\]]{1,20}\])*\s*[^\s:\[\]][^:\[\]]{0,24}?\s*[:：]\s*)(.+)$")
_SYSTEM_HINT = re.compile(r"^\s*\[[^\]]{1,20}\]")

hide_for_capture = lambda on: False      # подставляет окно программы (режим «перевод поверх чата»)
seen = collections.deque(maxlen=400)       # ключи уже переведённых строк
_seen_set = set()
_state = {"prev": None, "started": False}

CHAT_PROMPT = """You translate messages from the in-game chat of the MMORPG ArcheAge Chronicles into {lang}.
Text was read by OCR — fix obvious recognition errors. Players write casually: keep slang, abbreviations
(lfg, wts, wtb, gg, lol) and item names understandable; do not add anything.
Translate each numbered line, keep the numbering, exactly {n} lines:
{text}"""

OUT_PROMPT = """Translate this message for the in-game chat of an English-language MMORPG (ArcheAge Chronicles).
Write it the way a friendly native player would type in chat: short, natural, casual. Keep names as they are.
Output only the translation, one line, no quotes.
Message: {text}"""


def _key(line):
    return re.sub(r"[^a-z0-9]", "", line.lower())[:80]


def _remember(key):
    if key in _seen_set:
        return
    if len(seen) == seen.maxlen:
        _seen_set.discard(seen[0])
    seen.append(key)
    _seen_set.add(key)


def split_line(line):
    """'[World] Nick: hello' → ('[World] Nick: ', 'hello'); строка без ника → ('', строка)."""
    m = _LINE.match(line)
    if m and len(m.group(2).strip()) >= 1:
        return m.group(1), m.group(2).strip()
    return "", line.strip()


def read_lines(img):
    """Строки чата с картинки. Фильтр мягче, чем у субтитров: ники с цифрами («Player123») — нормально."""
    lines = []
    with ocr._ocr_lock:          # распознаватель Windows читает только одну картинку за раз
        raw = ocr._ocr_raw(img)
    for text, _ in raw:
        t = text.strip()
        low = t.lower()
        if sum(ch.isalpha() for ch in t) < 3:
            continue
        if any(w in low for w in config.WATERMARK_WORDS) or "windows" in low:
            continue
        prefix, msg = split_line(t)
        if config.SOURCE_LANG == "en" and ocr._looks_like_garbage(msg):
            continue   # русский текст (прочитанный английским OCR) или мусор
        lines.append(t)
    return lines


def new_lines(lines):
    """Какие строки ещё не переводили (порядок сохраняем)."""
    out = []
    for ln in lines:
        k = _key(ln)
        if k and k not in _seen_set:
            out.append(ln)
    return out


def translate_messages(messages, lang=None):
    """Перевести список сообщений. Нейросеть из цепочки — одним запросом; иначе Google/Microsoft."""
    lang = lang or config.TARGET_LANG_EN
    if not messages:
        return []
    numbered = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(messages))
    out = translate.ask_text(CHAT_PROMPT.format(lang=lang, n=len(messages), text=numbered))
    if out:
        got = {}
        for ln in out.strip().splitlines():
            m = re.match(r"\s*(\d+)[.)]\s*(.*)", ln)
            if m:
                got[int(m.group(1))] = m.group(2).strip()
        if all(i + 1 in got for i in range(len(messages))):
            return [got[i + 1] for i in range(len(messages))]
    # машинный перевод (Google, потом Microsoft) — построчно одним запросом
    joined = "\n".join(messages)
    for fn in (mt._mt_google, mt._mt_microsoft):
        try:
            res = fn(joined)
            parts = [p.strip() for p in res.split("\n")]
            if len(parts) == len(messages):
                return parts
            return [fn(m) for m in messages]
        except Exception:
            continue
    return None


def translate_outgoing(text):
    """Русское сообщение → английское для чата игры."""
    out = translate.ask_text(OUT_PROMPT.format(text=text))
    if out:
        out = out.strip().strip('"«»').splitlines()[0].strip()
        if out:
            return out
    try:
        return mt._mt_google(text, sl="ru", tl="en")
    except Exception:
        pass
    try:
        return mt._mt_microsoft(text, sl="ru", tl="en")
    except Exception:
        return None


def _blink_grab(reg):
    """Снимок области, на миг сделав окно перевода прозрачным. None — окно не поверх чата."""
    if not hide_for_capture(True):
        return None
    try:
        time.sleep(0.04)                   # дать Windows перерисовать экран без нашего окна
        return capture.grab(reg)
    finally:
        hide_for_capture(False)


def _grab_under_overlay(reg):
    """Снимок чата, когда перевод лежит поверх него.
    Обычно Windows сама не показывает наши окна на снимках — тогда моргать не нужно. Проверяем это один раз:
    снимок с окном и без окна должны совпасть. Не совпали — Windows окно не прячет, тогда «моргаем»."""
    st = _state
    plain = capture.grab(reg)
    mode = st.get("cover_mode")          # None — не проверяли, "ok" — Windows прячет окно, "blink" — моргаем
    if mode == "ok":
        return plain
    if mode == "blink":
        if time.time() - st.get("blink_t", 0) < config.CHAT_BLINK_EVERY:
            return None                  # моргаем реже, чем читаем: между морганиями снимок не делаем
        st["blink_t"] = time.time()
        shot = _blink_grab(reg)
        return shot if shot is not None else plain
    under = _blink_grab(reg)
    if under is None:                    # окно сейчас не поверх чата (режим выключен или окно скрыто)
        return plain
    from PIL import ImageChops, ImageStat
    diff = sum(ImageStat.Stat(ImageChops.difference(plain.convert("L"), under.convert("L"))).mean)
    if diff < 6:
        st["cover_mode"] = "ok"
        core.log("Чат: Windows прячет окно перевода от снимков — читаю чат под ним без моргания", "ok")
    else:
        st["cover_mode"] = "blink"
        st["blink_t"] = time.time()
        core.log("Чат: Windows не прячет окно перевода от снимков, поэтому оно будет коротко моргать "
                 f"раз в {config.CHAT_BLINK_EVERY:g} с, когда я читаю чат под ним. Если мешает — выключите "
                 "«перевод поверх чата» в Настройках.", "warn")
    return under


def _step():
    """Одна проверка области чата (вызывается раз в секунду)."""
    reg = core.chat_region
    shot = _grab_under_overlay(reg)
    if shot is None:
        return                              # в этот раз не снимаем (окно поверх чата моргает реже)
    img = capture.mask_out(shot, reg, list(core.own_rects))   # панель и окна программы — не чат
    try:
        lines = read_lines(img)
    except core.ApiError as e:
        core.log(f"Чат: {e}", "error")
        time.sleep(10)
        return
    prev = _state["prev"]
    _state["prev"] = lines
    if lines != prev and _state.get("cover_mode") != "blink":
        return                      # строки ещё «плывут» (чат прокручивается) — ждём, пока устоятся
    fresh = new_lines(lines)
    if not fresh:
        return
    if not _state["started"]:
        # первое чтение после включения: всё старое — уже прочитано, переводим только последние 3 строки
        _state["started"] = True
        for ln in fresh[:-3]:
            _remember(_key(ln))
        fresh = fresh[-3:]
    pairs = [split_line(ln) for ln in fresh]
    msgs = [m for _, m in pairs]
    if config.SHOW_OCR_IN_LOG:
        core.log("Чат прочитал: " + " / ".join(fresh)[:160])
    tr = translate_messages(msgs)
    if tr is None:
        core.log("Чат: не удалось перевести (все переводчики недоступны)", "warn")
        return
    for ln in fresh:
        _remember(_key(ln))
    out = [(p, t) for (p, _), t in zip(pairs, tr) if t]
    core.events.put(("chat", out))
    for (p, m), t in zip(pairs, tr):
        history.history_add("Чат", p + m, p + (t or ""))


_once_lock = threading.Lock()


def translate_chat_once():
    """Клавиша «перевести чат»: прочитать чат сейчас и перевести новые сообщения (без автоперевода)."""
    if core.chat_region is None:
        core.log("Сначала обведите окно чата (клавиша «область чата»).", "warn")
        return
    if not _once_lock.acquire(blocking=False):
        return
    try:
        reg = core.chat_region
        shot = _blink_grab(reg) or capture.grab(reg)
        img = capture.mask_out(shot, reg, list(core.own_rects))
        lines = read_lines(img)
        fresh = new_lines(lines)
        if not fresh:
            core.log("Чат: новых сообщений нет")
            core.events.put(("chat_show", None))
            return
        pairs = [split_line(ln) for ln in fresh]
        tr = translate_messages([m for _, m in pairs])
        if tr is None:
            core.log("Чат: не удалось перевести (все переводчики недоступны)", "warn")
            return
        for ln in fresh:
            _remember(_key(ln))
        _state["started"] = True
        core.events.put(("chat", [(p, t) for (p, _), t in zip(pairs, tr) if t]))
        for (p, m), t in zip(pairs, tr):
            history.history_add("Чат", p + m, p + (t or ""))
    finally:
        _once_lock.release()


def run():
    """Поток слежения за чатом."""
    errors = 0
    while True:
        try:
            core.auto_on.wait()
            if not (core.chat_auto and core.chat_region) or not game.game_active.is_set():
                _state.update(prev=None, started=False, cover_mode=None)
                time.sleep(1)
                continue
            _step()
            time.sleep(config.CHAT_POLL)
        except Exception as e:
            errors += 1
            if errors <= 3:
                core.log(f"Чат: ошибка ({type(e).__name__}: {str(e)[:100]}) — продолжаю", "error")
            time.sleep(2)


def start():
    threading.Thread(target=run, daemon=True, name="chat").start()
