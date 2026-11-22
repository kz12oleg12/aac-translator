"""Главное окно программы: обработка событий, расстановка окон и областей."""


import os
import time
import queue


import threading

import tkinter as tk


from . import config, core, game, hotkeys, tooltip, tray, tts, ui_overlay, ui_panel, ui_windows, updater, watcher


class App:
    def __init__(self):
        self.root = tk.Tk()
        ico = os.path.join(config.APP_DIR, "icon.ico")
        try:
            if os.path.exists(ico):
                self.root.iconbitmap(default=ico)  # иконка для всех окон программы
        except Exception:
            pass
        sw = self.root.winfo_screenwidth()
        # окно субтитров (автоперевод)
        self.subs = ui_overlay.Overlay(self.root, "overlay", (sw - config.OVERLAY_WIDTH - 20, 60), config.OVERLAY_WIDTH)
        self.subs_src = "subs_hide"   # из какой области пришла показанная реплика (основная / вторая)
        if config.SUBS_ABOVE_REGION:
            self.subs.anchor = lambda: (core.region2 if self.subs_src == "subs2_hide" and core.region2 else core.region)
        # отдельное окно для разового перевода заданий (F7)
        self.quest = ui_overlay.Overlay(tk.Toplevel(self.root), "quest", (20, 60), config.QUEST_WIDTH,
                             title="📜 Задание (правый клик — закрыть)")
        # окно перевода вариантов ответа — рядом с их областью
        self.answers = ui_overlay.Overlay(tk.Toplevel(self.root), "answers", (20, 300), config.ANSWERS_WIDTH,
                               title="💬 Варианты ответа")
        self.answers.anchor = lambda: core.answers_region
        self.answers.anchor_side = config.ANSWERS_SIDE
        # перевод подсказки под мышкой (предметы, навыки)
        self.tip = ui_overlay.Overlay(tk.Toplevel(self.root), "tooltip", (20, 60), config.TOOLTIP_WIDTH,
                                      title="🔎 Подсказка (правый клик — закрыть)")
        self.tip.manual = True     # ставится рядом с подсказкой, а не в сохранённое место
        self.tip.hide()
        self.tip_state = None
        if config.ANSWERS_DOCKED:
            self.answers.dock(self.subs)
        self.quest.hide()
        self.answers.hide()
        self.subs.hide()  # окно субтитров появится с первым переводом
        self.busy = set()
        self.panel = ui_panel.Panel(tk.Toplevel(self.root))
        self.panel.refresh()

        core.log(f"AAC Translator v{config.VERSION} запущен", "ok")
        updater.announce_if_updated()
        if core.region or core.answers_region or core.region2:
            parts = [n for n, r in (("субтитров", core.region), ("реплик 2", core.region2),
                                    ("ответов", core.answers_region)) if r]
            core.log(f"Загружены области: {', '.join(parts)}. {hotkeys.K('auto')} — включить автоперевод.")
        else:
            core.log(f"Выделите область субтитров ({hotkeys.K('select')}) и ответов ({hotkeys.K('select_answers')}), "
                f"потом включите автоперевод ({hotkeys.K('auto')}).")
        self.root.after(50, self._poll)

    def _check_game_focus(self):
        if not (config.PAUSE_OUTSIDE_GAME and game.game_exe and core.auto_on.is_set()):
            if not game.game_active.is_set():
                game.game_active.set()
            return
        exe, pid = game.foreground_exe()
        if exe is None or pid == os.getpid():
            return  # своё окно (панель) или неизвестно — состояние не меняем
        in_game = exe == game.game_exe
        if in_game and not game.game_active.is_set():
            game.game_active.set()
            for ov in getattr(self, "_away_hidden", []):
                ov.show(ov.label.cget("text"))
            self._away_hidden = []
            core.log("Игра снова на экране — продолжаю переводить")
            self.panel.refresh()
        elif not in_game and game.game_active.is_set():
            game.game_active.clear()
            tts.stop()
            self._away_hidden = [ov for ov in (self.subs, self.answers) if ov.visible]
            for ov in self._away_hidden:
                ov.hide()
            core.log(f"Вы не в игре ({exe}) — пауза")
            self.panel.refresh()

    def open_history(self):
        hw = getattr(self, "history_win", None)
        if hw and hw.alive():
            hw.win.deiconify()
            hw.win.lift()
        else:
            self.history_win = ui_windows.HistoryWindow(self)

    def open_settings(self):
        sw = getattr(self, "settings_win", None)
        if sw and sw.alive():
            sw.win.deiconify()
            sw.win.lift()
        else:
            self.settings_win = ui_windows.SettingsWindow(self)

    def toggle_all(self):
        if self.subs.visible or self.quest.visible or self.answers.visible:
            self.subs.hide()
            self.quest.hide()
            self.answers.hide()
        elif self.subs.label.cget("text"):
            self.subs.show(self.subs.label.cget("text"))

    def pick_area(self, prompt, on_done, on_clear=None):
        """Затемняет экран и даёт обвести прямоугольник мышкой."""
        was_auto = core.auto_on.is_set()
        core.auto_on.clear()  # пока выделяем — автоперевод на паузе, чтобы не поймать затемнение
        sel = tk.Toplevel(self.root)
        sel.overrideredirect(True)
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.3)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        sel.geometry(f"{sw}x{sh}+0+0")
        cv = tk.Canvas(sel, cursor="cross", bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(sw // 2, 40, text=prompt + "   Esc — отмена.", fill="white", font=("Segoe UI", 18))
        state = {}

        def finish(result):
            sel.destroy()
            if was_auto:
                # дать окну затемнения исчезнуть, потом вернуть автоперевод
                self.root.after(150, core.auto_on.set)
            on_done(result)

        def down(e):
            state["x0"], state["y0"] = e.x, e.y
            state["rect"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=3)

        def drag(e):
            if "rect" in state:
                cv.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

        def up(e):
            if "x0" not in state:
                return
            x0, y0 = min(state["x0"], e.x), min(state["y0"], e.y)
            w, h = abs(e.x - state["x0"]), abs(e.y - state["y0"])
            finish((x0, y0, w, h) if w > 10 and h > 10 else None)

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", drag)
        cv.bind("<ButtonRelease-1>", up)
        sel.bind("<Escape>", lambda e: finish(None))
        if on_clear:   # правый клик — убрать область
            def clear(e):
                sel.destroy()
                if was_auto:
                    self.root.after(150, core.auto_on.set)
                on_clear()
            cv.bind("<Button-3>", clear)
        sel.focus_force()

    def select_subs_region(self):
        def done(reg):
            if reg:
                core.region = reg
                core.save_settings(region=reg)
                core.log(f"Область субтитров сохранена: {reg[2]}×{reg[3]}", "ok")
                self.panel.refresh()
                if self.subs.visible:
                    self.subs.fit()  # переезжает к новой области
        self.pick_area("Обведите область СУБТИТРОВ (для автоперевода).", done)

    LAYOUT_SUBS = ("Перевод СУБТИТРОВ\nТащите за текст — положение.\n"
                   "Тяните за зелёный правый край (или колесо мыши) — ширина.")
    LAYOUT_ANSWERS = ("Перевод ОТВЕТОВ\n1. Тащите за текст — положение\n"
                      "2. Зелёный правый край или колесо — ширина")
    LAYOUT_DOCKED = ("Перевод ОТВЕТОВ — склеен с субтитрами: двигается и тянется вместе с ними.\n"
                     "Разъединить — галочка в системной панели.")

    # --- подсказка под мышкой ---
    def tooltip_key(self):
        pos = tooltip.cursor_pos()
        st = self.tip_state
        if st and self.tip.visible and pos and abs(pos[0] - st["pos"][0]) + abs(pos[1] - st["pos"][1]) < 40:
            self.tip.hide()          # повторное нажатие на том же месте — убрать перевод
            self.tip_state = None
            return
        threading.Thread(target=tooltip.translate_at_cursor, args=(pos,), daemon=True).start()

    def show_tooltip(self, data):
        self.tip.width = config.TOOLTIP_WIDTH
        self.tip._set_wrap(self.tip.width)
        self.tip.show(data["text"])
        _, h, _, _ = self.tip._pos()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = tooltip.place(data["box"], data["pos"], self.tip.width, h, sw, sh)
        self.tip._place(self.tip.width, h, x, y)
        self.tip.win.lift()
        first = self.tip_state is None
        self.tip_state = {"pos": data["pos"], "t": time.time()}
        if first:
            self.root.after(300, self._tip_watch)

    def _tip_watch(self):
        """Прячем перевод подсказки, когда мышку увели или прошло много времени."""
        st = self.tip_state
        if not st or not self.tip.visible:
            self.tip_state = None
            return
        pos = tooltip.cursor_pos()
        far = pos and ((pos[0] - st["pos"][0]) ** 2 + (pos[1] - st["pos"][1]) ** 2) ** 0.5 > config.TOOLTIP_MOVE_HIDE
        if far or time.time() - st["t"] > config.TOOLTIP_SHOW_TIME:
            self.tip.hide()
            self.tip_state = None
            return
        self.root.after(300, self._tip_watch)

    def set_docked(self, on):
        """Ответы и субтитры — одним окном (ответы вплотную под субтитрами) или отдельными окнами."""
        config.ANSWERS_DOCKED = on
        core.save_settings(answers_docked=on)
        self.answers.dock(self.subs if on else None)
        if getattr(self, "layout", False) and self.answers.label.cget("text") in (self.LAYOUT_ANSWERS, self.LAYOUT_DOCKED):
            self.answers.show(self.LAYOUT_DOCKED if on else self.LAYOUT_ANSWERS)
        core.log("Ответы и субтитры — одним окном (ответы под субтитрами, двигаются вместе)" if on
                 else "Ответы и субтитры — отдельными окнами", "ok")
        self.panel.refresh()
        tray.update()

    def toggle_layout(self):
        """Режим расстановки: показывает окна-заготовки, чтобы их можно было перетащить."""
        self.layout = not getattr(self, "layout", False)
        if self.layout:
            # пока правим области — автоперевод на паузе (рамки не должны попасть в перевод)
            self._layout_was_auto = core.auto_on.is_set()
            core.auto_on.clear()
            self.region_frames = {}
            if core.region:
                self.region_frames["subs"] = ui_windows.RegionFrame(self, "Область СУБТИТРОВ", "#2060d0", core.region,
                                                         self._regions_changed)
            if core.answers_region:
                self.region_frames["answers"] = ui_windows.RegionFrame(self, "Область ОТВЕТОВ", "#d07010", core.answers_region,
                                                            self._regions_changed)
            if core.region2:
                self.region_frames["subs2"] = ui_windows.RegionFrame(self, "Область РЕПЛИК 2", "#18a090", core.region2,
                                                          self._regions_changed)
            self._regions_changed(live=True)
            for ov, txt in ((self.subs, self.LAYOUT_SUBS),
                            (self.answers, self.LAYOUT_DOCKED if config.ANSWERS_DOCKED else self.LAYOUT_ANSWERS)):
                if not ov.visible:
                    ov.show(txt)
                ov.win.lift()
            for ov in (self.subs, self.answers, self.quest):
                ov.highlight_grip(True)
            core.log(f"Режим расстановки: синяя рамка — субтитры, оранжевая — ответы (тащите, растягивайте за края). "
                f"Окна перевода — за текст, ширина — за зелёный край. {hotkeys.K('layout')} — готово.", "ok")
        else:
            self._save_regions()
            for fr in self.region_frames.values():
                fr.destroy()
            self.region_frames = {}
            if getattr(self, "_layout_was_auto", False):
                self.root.after(200, core.auto_on.set)
            for ov in (self.subs, self.answers):
                if ov.label.cget("text") in (self.LAYOUT_SUBS, self.LAYOUT_ANSWERS, self.LAYOUT_DOCKED):
                    ov.label.config(text="")
                    ov.hide()
            for ov in (self.subs, self.answers, self.quest):
                ov.highlight_grip(False)
            core.log("Расстановка сохранена")

    def _regions_changed(self, live=False):
        frames = getattr(self, "region_frames", {})
        warn = {k: False for k in frames}
        keys = list(frames)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                if ui_windows.regions_overlap(frames[a].rect(), frames[b].rect()):
                    warn[a] = warn[b] = True
        for k, fr in frames.items():
            fr.set_warn(warn[k])

    def _save_regions(self):
        frames = getattr(self, "region_frames", {})
        if "subs" in frames:
            core.region = frames["subs"].rect()
            core.save_settings(region=core.region)
        if "answers" in frames:
            core.answers_region = frames["answers"].rect()
            core.save_settings(answers_region=core.answers_region)
        if "subs2" in frames:
            core.region2 = frames["subs2"].rect()
            core.save_settings(region2=core.region2)
        if frames:
            msg = "Области сохранены"
            regs = [core.region, core.answers_region, core.region2]
            if any(ui_windows.regions_overlap(a, b) for i, a in enumerate(regs) for b in regs[i + 1:]):
                core.log(msg + ", но некоторые ПЕРЕСЕКАЮТСЯ — общая часть попадёт только в одну из них.", "warn")
            else:
                core.log(msg + " (не пересекаются)", "ok")
        self.panel.refresh()
        for ov in (self.subs, self.answers):
            if ov.visible:
                ov.fit()

    def select_subs2_region(self):
        def done(reg):
            if reg:
                core.region2 = reg
                core.save_settings(region2=reg)
                core.log(f"Вторая область реплик сохранена: {reg[2]}×{reg[3]}. Реплики из неё показываются "
                         "в том же окне субтитров и тоже озвучиваются.", "ok")
                self.panel.refresh()

        def clear():
            core.region2 = None
            core.save_settings(region2=None)
            core.log("Вторая область реплик убрана")
            core.events.put(("subs2_hide", None))
            self.panel.refresh()
        self.pick_area("Обведите ВТОРУЮ область реплик (где НПС говорят, когда проходите мимо). "
                       "Правый клик — убрать её.", done, clear)

    def select_answers_region(self):
        def done(reg):
            if reg:
                core.answers_region = reg
                core.save_settings(answers_region=reg)
                core.log(f"Область ответов сохранена: {reg[2]}×{reg[3]}", "ok")
                self.panel.refresh()
                if self.answers.visible:
                    self.answers.fit()
        self.pick_area("Обведите область ВАРИАНТОВ ОТВЕТА (для автоперевода).", done)

    def select_quest_once(self):
        def done(reg):
            if reg:
                # небольшая пауза, чтобы затемнение успело пропасть со скриншота
                self.root.after(150, lambda: threading.Thread(
                    target=watcher.translate_once, args=(reg,), daemon=True).start())
        self.pick_area("Обведите ЗАДАНИЕ / текст для разового перевода.", done)

    def _poll(self):
        try:
            while True:
                kind, payload = core.events.get_nowait()
                if kind == "text":
                    self.subs.push(payload)
                elif kind == "quest":
                    self.quest.show(payload)
                elif kind == "busy":
                    name, on = payload
                    (self.busy.add if on else self.busy.discard)(name)
                    self.panel.busy = bool(self.busy)
                    self.panel.refresh()
                elif kind == "answers":
                    self.answers.show(payload)
                elif kind == "answers_hide":
                    self.answers.hide()
                elif kind == "select_answers":
                    self.select_answers_region()
                elif kind == "log":
                    self.panel.add_log(*payload)
                    self.panel.refresh()
                elif kind == "panel":
                    self.panel.refresh()
                elif kind == "history_new":
                    hw = getattr(self, "history_win", None)
                    if hw and hw.alive():
                        hw.add(payload)
                elif kind == "history_open":
                    self.open_history()
                elif kind == "settings_open":
                    self.open_settings()
                elif kind == "second_copy":
                    if not self.panel.visible:
                        self.panel.toggle()
                    self.panel.win.lift()
                    core.log("Переводчик уже запущен — вторая копия не нужна (значок-кот в трее)", "warn")
                elif kind == "panel_toggle":
                    self.panel.toggle()
                elif kind == "subs_from":
                    self.subs_src = payload
                elif kind in ("subs_hide", "subs2_hide"):
                    # каждая область прячет только свою реплику, а не чужую
                    if kind == self.subs_src or payload == "force":
                        self.subs.hide()
                elif kind == "select_subs2":
                    self.select_subs2_region()
                elif kind == "select":
                    self.select_subs_region()
                elif kind == "once":
                    self.select_quest_once()
                elif kind == "answers_once":
                    threading.Thread(target=watcher.translate_answers_once, daemon=True).start()
                elif kind == "toggle":
                    self.toggle_all()
                elif kind == "keys":
                    self.panel.update_keys()
                elif kind == "auto":
                    watcher.toggle_auto()
                elif kind == "layout":
                    self.toggle_layout()
                elif kind == "reset":
                    self.subs.reset_pos()
                    self.quest.reset_pos()
                    self.panel.reset_pos()
                    if not self.panel.visible:
                        self.panel.toggle()
                    self.answers.reset_pos()
                    self.quest.show("Окно заданий здесь. Правый клик — закрыть.")
                    core.log("Окна возвращены на место, субтитры и ответы снова прилипают к своим областям")
                elif kind == "update_available":
                    notes = " / ".join(ln.strip("-* ") for ln in payload["notes"].splitlines() if ln.strip())[:200]
                    core.log(f"Доступна новая версия {payload['version']}" + (f": {notes}" if notes else "") +
                             ". Кнопка «⬇ Обновить» в панели или в меню значка.", "ok")
                    self.panel.show_update(payload["version"])
                    tray.update()
                elif kind == "update_install":
                    info = updater.state.get("latest")
                    if info and updater.is_newer(info["version"]):
                        updater.install_async(info)
                    else:
                        updater.check_async(quiet=False)
                elif kind == "update_check":
                    updater.check_async(quiet=False)
                elif kind == "tooltip_key":
                    self.tooltip_key()
                elif kind == "tooltip_show":
                    self.show_tooltip(payload)
                elif kind == "tooltip_hide":
                    self.tip.hide()
                    self.tip_state = None
                elif kind == "tts_toggle":
                    tts.toggle()
                elif kind == "dock_toggle":
                    self.set_docked(not config.ANSWERS_DOCKED if payload is None else bool(payload))
                elif kind == "tts_changed":
                    sw = getattr(self, "settings_win", None)
                    if sw and sw.alive():
                        sw.tts_on.set(config.TTS_ENABLED)
                    self.panel.refresh()
                    tray.update()
                elif kind == "tts_voices":
                    sw = getattr(self, "settings_win", None)
                    if sw and sw.alive():
                        sw.fill_voices(payload)
                elif kind == "quit":
                    tts.shutdown()
                    tray.stop_tray()
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 10 == 0:   # 2 раза в секунду проверяем, игра ли на переднем плане
            self._check_game_focus()
        if self._tick % 20 == 0:  # раз в секунду обновляем панель (обратный отсчёт пауз моделей)
            self.panel.refresh()
        self.subs.set_status("⏳" if "Субтитры" in self.busy else "")
        self.answers.set_status("💬 Варианты ответа" + ("  ⏳" if "Ответы" in self.busy else ""))
        self.root.after(50, self._poll)
