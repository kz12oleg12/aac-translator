"""Автоперевод: слежение за областями, разовый перевод заданий и ответов."""


import difflib
import os
import re
import threading
import time


from . import capture, config, core, game, history, hotkeys, ocr, translate, tray, tts, voices


# ---------- разовый перевод (F7) — своя область, автоперевод не трогает ----------
once_lock = threading.Lock()


def translate_once(reg, speak=False):
    if not once_lock.acquire(blocking=False):
        return
    try:
        core.events.put(("quest", "⏳ Перевожу..."))
        text, err = translate.safe_translate(capture.mask_out(capture.grab(reg), reg, list(core.own_rects)))
        if err == "rate":
            err = "Превышен бесплатный лимит запросов. Подождите минуту."
        if err:
            core.log(f"Задание: {err}", "error")
            core.events.put(("quest", "❌ Не получилось перевести — подробности в системной панели."))
        else:
            orig = history.last_source()
            core.events.put(("quest", (text, orig) if text else "Текст не найден"))
            history.history_add("Задание", orig, text)
            if speak and text:
                tts.speak_text(text)   # «обвести и озвучить» — читаем, даже если озвучка субтитров выключена
    finally:
        once_lock.release()


subs_once_lock = threading.Lock()


def translate_subs_once():
    """Перевести субтитры один раз — по сохранённой области, без обводки мышкой и без автоперевода."""
    if core.region is None:
        core.log(f"Сначала выделите область субтитров ({hotkeys.K('select')}).", "warn")
        return
    if not subs_once_lock.acquire(blocking=False):
        return
    try:
        core.events.put(("busy", ("Субтитры", True)))     # «⏳» в заголовке окна субтитров
        img = capture.mask_out(capture.grab(core.region), core.region,
                               [core.answers_region, core.region2] + list(core.own_rects))
        text, err = translate.safe_translate(img, config.PROMPT)
        core.events.put(("busy", ("Субтитры", False)))
        if err == "rate":
            err = "лимит запросов — подождите несколько секунд и нажмите ещё раз"
        if err:
            core.log(f"Субтитры: {err}", "error")
        elif not text:
            core.log("Субтитры: в области сейчас нет текста", "warn")
        else:
            core.events.put(("subs_from", "subs_hide"))
            orig = history.last_source()
            core.events.put(("text", (text, orig)))
            history.history_add("Субтитры", orig, text)
            _remember_subtitle(text)
            tts.speak_subtitle_once(text, None, orig)
    finally:
        subs_once_lock.release()


answers_once_lock = threading.Lock()


def translate_answers_once():
    """Перевести варианты ответа один раз — по сохранённой области, без обводки мышкой."""
    if core.answers_region is None:
        core.log(f"Сначала выделите область ответов ({hotkeys.K('select_answers')}).", "warn")
        return
    if not answers_once_lock.acquire(blocking=False):
        return
    try:
        core.events.put(("answers", "⏳ Перевожу ответы..."))
        text, err = translate.safe_translate(capture.mask_out(capture.grab(core.answers_region), core.answers_region,
                                                       [core.region] + list(core.own_rects)), _answers_prompt())
        if err == "rate":
            err = "лимит запросов — подождите несколько секунд и нажмите ещё раз"
        if err:
            core.log(f"Ответы: {err}", "error")
            core.events.put(("answers", "❌ Не получилось — подробности в системной панели."))
        else:
            orig = history.last_source()
            core.events.put(("answers", (text, orig) if text else "Вариантов ответа не найдено"))
            history.history_add("Ответы", orig, text)
    finally:
        answers_once_lock.release()


# ---------- автоперевод (F8): следим за областью субтитров и областью ответов ----------
def growing(prev, cur):
    """Текст дописывается (печатается по буквам / появляется по словам): старое — начало нового."""
    if not prev or not cur:
        return True        # появился или пропал — это не «скачет»
    p, c = re.sub(r"\W+", " ", prev).strip().lower(), re.sub(r"\W+", " ", cur).strip().lower()
    if len(c) < len(p):
        p, c = c, p        # исчезает по буквам — тоже нормально
    return c.startswith(p) or difflib.SequenceMatcher(None, p, c[:len(p)]).ratio() >= 0.85


def same_text(a, b):
    """Почти одинаковый текст (фон может добавить пару лишних символов) — считаем одним и тем же."""
    if not a or not b:
        return a == b
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= config.TEXT_SAME_RATIO


class Watcher:
    """Следит за областью экрана и переводит текст, когда он меняется; прячет перевод, когда текст исчезает."""

    def __init__(self, name, get_region, show_event, hide_event, brightness, make_prompt, on_text=None,
                 exclude=None):
        self.name = name
        self.exclude = exclude  # функция -> область, которую надо закрасить (чужая область поверх нашей)
        self.get_region = get_region
        self.show_event, self.hide_event = show_event, hide_event
        self.brightness = brightness
        self.make_prompt = make_prompt
        self.on_text = on_text
        self.working = threading.Event()  # сейчас идёт запрос на перевод
        self._prev_ocr = None   # что OCR прочитал на прошлом кадре
        self._sent_ocr = None   # какой распознанный текст уже переведён и показан
        self._unstable = 0      # сколько раз подряд текст прочитался по-другому (не считая «дописывается»)
        self._unstable_since = 0.0
        self._seen_at = None    # когда заметили текущую реплику (для замера задержки озвучки)

    def hide(self):
        core.events.put((self.hide_event, None))

    def _warn_unstable(self, prev, cur):
        """Текст в области долго «скачет» (фон, анимация) — подсказываем сузить область.
        Текст, который просто дописывается по буквам или словам, — это нормально, не считаем."""
        now = time.time()
        if growing(prev, cur):
            return
        letters = lambda t: sum(ch.isalpha() for ch in (t or ""))
        if min(letters(prev), letters(cur)) < 12:
            return    # обрывки с фона (мостовая, трава) — не реплика; на них не жалуемся
        if not self._unstable:
            self._unstable_since = now
        self._unstable += 1
        if (self._unstable >= config.UNSTABLE_READS and now - self._unstable_since >= config.UNSTABLE_SECONDS
                and now - getattr(self, "_warned_at", 0) > 300):
            self._warned_at = now
            core.log(f"{self.name}: текст в области долго не может «устояться» — каждый раз читается по-разному "
                     f"(«{(prev or '')[:40]}» → «{(cur or '')[:40]}»). Если перевод при этом появляется — "
                     f"не обращайте внимания. Если нет — сузьте область ({hotkeys.K('layout')}).", "warn")

    def run(self):
        """Цикл наблюдения. Если внутри случится ошибка — пишем её в журнал и запускаем цикл заново,
        а не «умираем» молча (иначе автоперевод этой области просто перестаёт работать)."""
        errors = 0
        while True:
            try:
                self._loop()
            except Exception as e:
                import traceback
                traceback.print_exc()
                errors += 1
                if errors <= 3:
                    tb = traceback.extract_tb(e.__traceback__)
                    where = f"{os.path.basename(tb[-1].filename)}:{tb[-1].lineno}" if tb else ""
                    core.log(f"{self.name}: ошибка ({type(e).__name__}: {str(e)[:100]} [{where}]) — "
                             "перезапускаю слежение", "error")
                self.working.clear()
                core.events.put(("busy", (self.name, False)))
                time.sleep(1)

    def _check_overlap(self, reg, others):
        """Чужая область закрывает заметную часть нашей — её текст закрашивается и не переводится. Скажем об этом."""
        if not others:
            return
        if not isinstance(others, list):
            others = [others]
        key = (tuple(reg), tuple(tuple(o) for o in others if o))
        if key == getattr(self, "_overlap_checked", None):
            return
        self._overlap_checked = key
        area = reg[2] * reg[3] or 1
        covered = 0
        for o in others:
            if not o:
                continue
            w = min(reg[0] + reg[2], o[0] + o[2]) - max(reg[0], o[0])
            h = min(reg[1] + reg[3], o[1] + o[3]) - max(reg[1], o[1])
            if w > 0 and h > 0:
                covered += w * h
        if covered > area * 0.25:
            core.log(f"{self.name}: другая область закрывает {min(100, covered * 100 // area)}% этой — там текст "
                     f"не переводится. Разведите рамки ({hotkeys.K('layout')}): пересечение подсвечено красным.",
                     "warn")

    def _loop(self):
        prev = None          # маска на прошлой проверке
        sent = None          # маска, которую последний раз отправили на перевод
        last_req = 0.0
        last_stable = time.time()
        last_shown = 0.0
        shown = None         # последний показанный перевод
        gone_since = None    # когда текст пропал из области
        while True:
            core.auto_on.wait()
            if not game.game_active.is_set():
                time.sleep(0.5)   # вы не в игре — ничего не переводим
                continue
            reg = self.get_region()
            if reg is None:
                time.sleep(1)
                continue
            try:
                img = capture.grab(reg)
                others = self.exclude() if self.exclude else None
                img = capture.mask_out(img, reg, others)
                img = capture.mask_out(img, reg, list(core.own_rects))   # наши окна (панель и т.п.) — не текст игры
                self._check_overlap(reg, others)
            except Exception as e:
                core.log(f"{self.name}: скриншот не удался: {e}", "error")
                time.sleep(1)
                continue
            m = capture.text_mask(img, self.brightness)
            stable = capture.mask_diff(m, prev) < config.STABLE_THRESHOLD   # текст перестал меняться (дописался)
            changed = capture.mask_diff(m, sent) > config.CHANGE_THRESHOLD  # и отличается от уже переведённого
            prev = m
            now = time.time()
            if stable:
                last_stable = now

            # текст пропал: светлых пикселей почти не осталось -> прячем перевод
            gone = capture.mask_empty(m) or (sent is not None and capture.text_amount(m) < config.GONE_RATIO * capture.text_amount(sent))
            if gone and shown is not None and not config.KEEP_UNTIL_NEXT:
                gone_since = gone_since or now
                if now - gone_since >= config.HIDE_DELAY:
                    self.hide()
                    shown = None
                    sent = None   # если тот же текст появится снова — переведём заново
                    self._sent_ocr = None
                    gone_since = None
            else:
                gone_since = None
            if shown is not None and not config.KEEP_UNTIL_NEXT and now - last_shown > config.MAX_SHOW_TIME:
                self.hide()  # страховка: перевод не висит вечно
                shown = None
            # фон всё время мигает и «спокойного» кадра нет — переводим по таймеру
            noisy = now - last_stable > config.FORCE_EVERY and now - last_req > config.FORCE_EVERY

            if (stable or noisy) and changed and not capture.mask_empty(m) and now - last_req >= config.MIN_REQUEST_GAP:
                if config.PROVIDER in translate.OCR_BASED:
                    # Режим OCR: переводим, только когда распознанный текст одинаковый два кадра подряд.
                    # Пока текст проявляется/исчезает (анимация), он читается кусками — такое не переводим.
                    try:
                        cur = "\n".join(ocr.ocr_lines(img))
                    except Exception:
                        cur = None
                    if cur is not None:
                        if not cur:
                            self._prev_ocr = cur
                            time.sleep(config.POLL_INTERVAL)
                            continue
                        if not same_text(cur, self._prev_ocr):
                            if not self._prev_ocr or same_text(self._prev_ocr, self._sent_ocr):
                                self._seen_at = now      # момент, когда новая реплика появилась на экране
                            self._warn_unstable(self._prev_ocr, cur)
                            self._prev_ocr = cur
                            time.sleep(config.OCR_CONFIRM_INTERVAL)   # перепроверяем быстро
                            continue
                        self._unstable = 0
                        if same_text(cur, self._sent_ocr):
                            sent = m          # тот же текст уже переведён — ничего не делаем
                            time.sleep(config.POLL_INTERVAL)
                            continue
                        if self.show_event == "text" and config.SKIP_SYSTEM and voices.is_system(cur):
                            # «You acquired…», «Quest completed» — системное, не реплика: не переводим
                            if config.SHOW_OCR_IN_LOG:
                                core.log(f"{self.name}: пропускаю системное сообщение: {cur.replace(chr(10), ' / ')[:100]}")
                            self._sent_ocr = cur
                            sent = m
                            time.sleep(config.POLL_INTERVAL)
                            continue
                        self._sent_ocr = cur
                wait = translate.chain_ready_in()
                if wait > 0:
                    # все переводчики на паузе — не долбим их, просто ждём (сообщение — один раз)
                    if not getattr(self, "_waiting", False):
                        core.log(f"{self.name}: все переводчики на паузе, жду ~{int(wait) + 1} с", "warn")
                        self._waiting = True
                    time.sleep(min(wait, 2))
                    continue
                self._waiting = False
                last_req = time.time()
                sent = m
                prompt = self.make_prompt()
                core.events.put(("busy", (self.name, True)))
                self.working.set()
                text, err = translate.safe_translate(img, prompt)
                self.working.clear()
                core.events.put(("busy", (self.name, False)))
                if err == "rate":
                    core.log("Лимит бесплатных запросов — пауза 15 с", "warn")
                    sent = None
                    time.sleep(15)
                elif err:
                    core.log(f"{self.name}: {err}", "error")
                elif text is None:
                    self.hide()   # нейросеть не нашла текста
                    shown = None
                elif core.auto_on.is_set():
                    if text != shown:
                        orig = history.last_source()
                        if self.show_event == "text":
                            core.events.put(("subs_from", self.hide_event))   # из какой области реплика
                        core.events.put((self.show_event, (text, orig)))
                        history.history_add(self.name, orig, text)
                        if self.show_event == "text":
                            tts.speak_subtitle_once(text, getattr(self, "_seen_at", None), orig)   # только субтитры
                        if self.on_text:
                            self.on_text(text)
                    shown = text
                    last_shown = time.time()
            time.sleep(config.POLL_INTERVAL)


def _remember_subtitle(text):
    core.last_subtitle = text


def _answers_prompt():
    # ответы обычно появляются вместе с репликой NPC — ждём её перевод (до 5 с), чтобы использовать как контекст
    subs = WATCHERS[0]
    t0 = time.time()
    while subs.working.is_set() and time.time() - t0 < 5:
        time.sleep(0.1)
    ctx = f"The NPC just said (already translated): «{core.last_subtitle}»" if core.last_subtitle else ""
    return config.ANSWERS_PROMPT.replace("{context}", ctx)


WATCHERS = [
    Watcher("Субтитры", lambda: core.region, "text", "subs_hide", None, lambda: config.PROMPT, _remember_subtitle),
    Watcher("Ответы", lambda: core.answers_region if core.answers_auto else None, "answers", "answers_hide",
            config.ANSWERS_TEXT_BRIGHTNESS, _answers_prompt, exclude=lambda: [core.region, core.region2]),
    # вторая область реплик: НПС, которые говорят, когда проходите мимо (их текст в другом месте экрана)
    Watcher("Реплики 2", lambda: core.region2, "text", "subs2_hide", None, lambda: config.PROMPT, _remember_subtitle,
            exclude=lambda: [core.region, core.answers_region]),
]


def toggle_auto():
    if core.auto_on.is_set():
        core.auto_on.clear()
        core.log("Автоперевод выключен")
        tts.stop()
        core.events.put(("subs_hide", None))
        core.events.put(("subs2_hide", None))
        core.events.put(("answers_hide", None))
    else:
        if core.region is None and core.answers_region is None and core.region2 is None and core.chat_region is None:
            core.log(f"Сначала выделите область субтитров ({hotkeys.K('select')}) и/или ответов ({hotkeys.K('select_answers')}), "
                f"потом {hotkeys.K('auto')}.", "warn")
            return
        game.remember_game_window()
        core.auto_on.set()
        parts = [n for n, r in (("субтитры", core.region), ("реплики 2", core.region2),
                                ("ответы", core.answers_region if core.answers_auto else None),
                                ("чат", core.chat_region if core.chat_auto else None)) if r]
        core.log(f"Автоперевод включён: {', '.join(parts)}", "ok")
    core.events.put(("panel", None))
    if tray._tray is not None:  # обновить галочку «Автоперевод» в меню трея
        try:
            tray._tray.update_menu()
        except Exception:
            pass
