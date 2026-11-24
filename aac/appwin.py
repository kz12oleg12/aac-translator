"""Главное окно программы: обработка событий, расстановка окон и областей."""


import os
import time
import queue


import threading

import tkinter as tk


from . import chat, config, menu, core, editor, game, gamefacts, history, hotkeys, profiles, screens, tcache, tooltip, tray, tts, ui_overlay, ui_panel, ui_shell, ui_windows, updater, watcher


def _on_monitor(place, box, pos, w, h):
    """tooltip.place/place_word считают от (0, 0) экрана — пересчитываем для монитора, где мышка."""
    l, t, r, b = screens.monitor_at(*pos)
    box2 = (box[0] - l, box[1] - t, box[2], box[3]) if box else None
    x, y = place(box2, (pos[0] - l, pos[1] - t), w, h, r - l, b - t)
    return x + l, y + t


class App:
    def __init__(self):
        self.root = tk.Tk()
        screens.set_fallback(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
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
        self.word = ui_overlay.WordTip(tk.Toplevel(self.root))   # лёгкий перевод надписи под мышкой
        self.word_state = None
        # перевод игрового чата — над областью чата
        self.chat = ui_overlay.Overlay(tk.Toplevel(self.root), "chat", (20, max(60, self.root.winfo_screenheight() // 2)), config.CHAT_WIDTH,
                                       title="💬 Чат (правый клик — скрыть)")
        self.chat.anchor = lambda: core.chat_region
        self.chat.cover = lambda: core.chat_region if config.CHAT_COVER else None
        self.chat.max_height = lambda: (core.chat_region[3] if (config.CHAT_COVER and core.chat_region)
                                        else config.CHAT_HEIGHT or None)
        self.chat.style_alpha = lambda: config.CHAT_ALPHA
        self.chat.style_fg = lambda: config.CHAT_FG
        self.chat.label.config(anchor="sw")    # как в игровом чате: свежие сообщения внизу
        # кнопка «Перевести» прямо на окне чата (справа в заголовке)
        self.chat_btn = tk.Button(self.chat.win, text="⟳ Перевести", font=("Segoe UI", 8), relief="flat", bd=0,
                                  highlightthickness=0, padx=6, bg="#2b3040", fg="#8cf", activebackground="#3a4258",
                                  activeforeground="#fff", cursor="hand2",
                                  command=lambda: core.events.put(("chat_once", None)))
        self.chat_btn.place(relx=1.0, x=-14, y=2, anchor="ne")
        self.chat.enable_height_grip(self._chat_height_drag,
                                     lambda: core.save_settings(chat_height=config.CHAT_HEIGHT))
        self.chat.apply_style()
        self.apply_game_style()
        self.chat.hide()
        self.chat.win.after(400, self._remember_chat_hwnd)
        self.chat_lines = []      # все переведённые сообщения (для прокрутки)
        self.chat_scroll = 0      # на сколько сообщений прокручено вверх (0 — внизу, свежие)
        self.chat_last = 0.0
        self.chat.wheel_handler = self._chat_wheel
        self.indicator = ui_overlay.Indicator(tk.Toplevel(self.root))   # «● AAC: перевод вкл»
        self.indicator.update(False)
        if config.ANSWERS_DOCKED:
            self.answers.dock(self.subs)
        self.quest.on_hide = tts.stop   # закрыли окно задания (правый клик) — чтение тоже останавливается
        self.quest.hide()
        self.answers.hide()
        self.subs.hide()  # окно субтитров появится с первым переводом
        self.busy = set()
        self.panel = ui_shell.Shell(self, tk.Toplevel(self.root))   # главное окно: разделы слева
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
        self.root.after(2500, self.auto_start_check)    # игра уже была запущена до программы

    def _check_game_focus(self):
        self.sync_region_frames()         # расстановка открыта, а область удалили/обвели заново/сменилась игра
        game.follow_foreground()          # игра из списка на экране — её пресет (всегда, без клавиш)
        new = game.detect_new_game() or game.scan_running()   # новая игра: на экране или в фоне — пресет сам
        if new:
            prof = game.create_profile_for(*new)
            self.game_created(prof)
        fs = game.check_fullscreen()
        if fs:
            name = profiles.name(profiles.for_exe(fs))
            core.log(f"⚠ {name} запущена в полноэкранном режиме — окна перевода поверх неё не видны. "
                     "В настройках графики игры выберите «Оконный без рамки» (Borderless / Windowed fullscreen).",
                     "warn")
            tray.notify(f"{name}: переводы не видны",
                        "Игра в полноэкранном режиме. Выберите в её настройках «Оконный без рамки» (Borderless).")
        watch = config.GAMES_ONLY or (config.PAUSE_OUTSIDE_GAME and game.game_exe)
        if not (watch and core.auto_on.is_set()):
            if not game.game_active.is_set():
                game.game_active.set()
            return
        exe, pid = game.foreground_exe()
        if game.no_game():
            in_game = False                     # игра закрылась (даже если сейчас на экране панель) — пауза
            exe = "игра не запущена"
        elif exe is None or pid == os.getpid():
            return  # своё окно (панель) или неизвестно — состояние не меняем
        else:
            in_game = game.is_game(exe)
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
            core.log("Игра закрыта — пауза, жду игру" if exe == "игра не запущена" else
                     f"Вы не в игре ({exe}) — пауза" + (
                ". Её вы отметили «не игра» — вернуть: раздел «Игры», внизу" if exe in game.not_games() else ""))
            self.panel.refresh()

    def game_created(self, prof):
        """Программа сама узнала новую игру и завела ей пресет: баннер на Главной и одно уведомление."""
        self.panel.show_new_game(prof)
        gamefacts.gather(prof)
        tray.notify(f"Новая игра: {profiles.name(prof)}",
                    f"Пресет создан. Обведите субтитры ({hotkeys.K('select')}) — и можно переводить.")

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
        if self.subs.visible or self.quest.visible or self.answers.visible or self.chat.visible:
            self.subs.hide()
            self.quest.hide()
            self.answers.hide()
            self.chat.hide()
        else:
            if self.subs.label.cget("text"):
                self.subs.show(self.subs.label.cget("text"))
            self.show_chat_window()

    def _area_target(self):
        """Для какой игры обводим область — решаем В МОМЕНТ НАЖАТИЯ клавиши, по окну на экране.
        Игра из списка — её пресет. Незнакомая программа — раз вы обводите в ней область, это игра: пресет сразу.
        Браузер и «не игры» — отказ. Нажали в панели программы — пресет, выбранный в разделе «Области»."""
        if game.locked():
            return core.active_profile
        exe, pid = game.foreground_exe()
        if not exe or pid == os.getpid():
            if core.active_profile is None:
                core.log("Игра не выбрана: обведите область в самой игре или выберите игру в разделе «Области»",
                         "warn")
                self.panel.show("areas")
            return core.active_profile
        prof = profiles.for_exe(exe)
        if prof:
            if prof != core.active_profile:
                profiles.activate(prof)
            return prof
        if not config.GAMES_ONLY and (exe in game.NOT_GAME_EXE or exe in game.not_games()
                                      or not game.in_game_folder(pid)):
            return self._free_target()           # режим без игры: обычная программа — пресет «Без игры»
        if exe in game.NOT_GAME_EXE or exe in game.not_games():
            core.log(f"{exe} — не игра: области обводятся в самой игре (или в панели → «Области»)", "warn")
            return None
        prof = game.create_profile_for(exe, game.nice_title(game.foreground_title(), exe))
        self.game_created(prof)
        return prof

    def _free_target(self):
        pid = profiles.free_pid()
        if core.active_profile != pid:
            profiles.activate(pid, announce=False)
        return pid

    def pick_area(self, prompt, on_done, on_clear=None, game_area=False, layout=False):
        """Затемняет экран и даёт обвести прямоугольник мышкой.
        game_area — область игры (субтитры, ответы, чат, меню): сохраняется в пресет игры, которая была
        на экране в момент нажатия клавиши, даже если за время обводки активная игра сменилась."""
        key = prompt
        cur = getattr(self, "_picking", None)
        if cur is not None:                 # затемнение уже открыто — второе поверх не открываем
            same = cur["prompt"] == key
            cur["cancel"]()                 # закрыть прежнее (и вернуть автоперевод, если был)
            if same:
                return                      # та же клавиша ещё раз — просто отмена
        if game_area:
            target = self._area_target()
            if target is None:
                return
            prompt = f"«{profiles.name(target)}» — " + prompt[0].lower() + prompt[1:]
            done0 = on_done

            def on_done(result, target=target):
                if result and core.active_profile != target and target in profiles.all_profiles():
                    profiles.activate(target, announce=False)
                done0(result)
            if on_clear is not None:
                clear0 = on_clear

                def on_clear(target=target):
                    if core.active_profile != target and target in profiles.all_profiles():
                        profiles.activate(target, announce=False)
                    clear0()
        if layout:
            # обводим область — сразу режим расстановки: видны рамки других областей и окна перевода
            opened = not getattr(self, "layout", False)
            if opened:
                self.toggle_layout()
            done1, clear1 = on_done, on_clear

            def on_done(result):
                done1(result)
                if result:
                    self.sync_region_frames()          # рамка — по новой области, можно сразу поправить
                elif opened and getattr(self, "layout", False):
                    self.toggle_layout()               # отменили — расстановку, которую открыли сами, закрыть
            if clear1 is not None:
                def on_clear():
                    clear1()
                    self.sync_region_frames()
        was_auto = core.auto_on.is_set()
        core.auto_on.clear()  # пока выделяем — автоперевод на паузе, чтобы не поймать затемнение
        sel = tk.Toplevel(self.root)
        sel.overrideredirect(True)
        sel.attributes("-topmost", True)
        sel.attributes("-alpha", 0.3)
        vx, vy, vw, vh = screens.virtual()           # все мониторы, а не только основной
        sel.geometry(f"{vw}x{vh}+{vx}+{vy}")
        cv = tk.Canvas(sel, cursor="cross", bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cur = tooltip.cursor_pos() or (vx + vw // 2, vy)
        ml, mt, mr, mb = screens.monitor_at(*cur)     # подсказка — на мониторе, где мышка
        cv.create_text((ml + mr) // 2 - vx, mt + 40 - vy, text=prompt + "   Esc — отмена.", fill="white",
                       font=("Segoe UI", 18))
        state = {}

        def close():
            if getattr(self, "_picking", None) is picking:
                self._picking = None
            try:
                sel.destroy()
            except tk.TclError:
                pass
            if was_auto:
                # дать окну затемнения исчезнуть, потом вернуть автоперевод
                self.root.after(150, core.auto_on.set)

        def finish(result):
            close()
            on_done(result)

        picking = {"prompt": key, "cancel": lambda: finish(None)}
        self._picking = picking

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
            finish((x0 + vx, y0 + vy, w, h) if w > 10 and h > 10 else None)    # в координаты экрана

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", drag)
        cv.bind("<ButtonRelease-1>", up)
        sel.bind("<Escape>", lambda e: finish(None))
        if on_clear:   # правый клик — убрать область
            def clear(e):
                close()
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
        self.pick_area("Обведите область СУБТИТРОВ (для автоперевода).", done, game_area=True, layout=True)

    LAYOUT_SUBS = ("Перевод СУБТИТРОВ\nТащите за текст — положение.\n"
                   "Тяните за зелёный правый край (или колесо мыши) — ширина.")
    LAYOUT_ANSWERS = ("Перевод ОТВЕТОВ\n1. Тащите за текст — положение\n"
                      "2. Зелёный правый край или колесо — ширина")
    LAYOUT_DOCKED = ("Перевод ОТВЕТОВ — склеен с субтитрами: двигается и тянется вместе с ними.\n"
                     "Разъединить — галочка в системной панели.")

    # --- подсказка под мышкой ---
    def tooltip_key(self):
        """Одна кнопка: подсказка предмета — большим окном, короткая надпись — маленькой плашкой."""
        pos = tooltip.cursor_pos()
        near = lambda st: st and pos and abs(pos[0] - st["pos"][0]) + abs(pos[1] - st["pos"][1]) < 40
        if (self.tip.visible and near(self.tip_state)) or (self.word.visible and near(self.word_state)):
            self.tip.hide()          # повторное нажатие на том же месте — убрать перевод
            self.tip_state = None
            self.word.hide()
            self.word_state = None
            return
        threading.Thread(target=tooltip.translate_smart, args=(pos,), daemon=True).start()

    def show_tooltip(self, data):
        self.tip.width = config.TOOLTIP_WIDTH
        self.tip._set_wrap(self.tip.width)
        self.tip.show(data["text"])
        _, h, _, _ = self.tip._pos()
        x, y = _on_monitor(tooltip.place, data["box"], data["pos"], self.tip.width, h)
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

    # --- лёгкий перевод надписи под мышкой ---
    def show_word(self, data):
        w, h = self.word.show(data["text"], data.get("orig"))
        self.word.move(*_on_monitor(tooltip.place_word, data["box"], data["pos"], w, h))
        first = self.word_state is None
        self.word_state = {"pos": data["pos"], "t": time.time()}
        if first:
            self.root.after(300, self._word_watch)

    def _word_watch(self):
        st = self.word_state
        if not st or not self.word.visible:
            self.word_state = None
            return
        pos = tooltip.cursor_pos()
        far = pos and ((pos[0] - st["pos"][0]) ** 2 + (pos[1] - st["pos"][1]) ** 2) ** 0.5 > config.WORD_MOVE_HIDE
        if far or time.time() - st["t"] > config.WORD_SHOW_TIME:
            self.word.hide()
            self.word_state = None
            return
        self.root.after(300, self._word_watch)

    def restart(self):
        """Перезапуск: новая копия ждёт, пока эта закроется, и запускается."""
        import subprocess
        import sys
        script = os.path.join(config.APP_DIR, "aac_translator.py")
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # отдельно от этой копии
        try:
            subprocess.Popen([sys.executable, script, "--after-pid", str(os.getpid())], cwd=config.APP_DIR,
                             creationflags=flags, close_fds=True)
        except Exception as e:
            core.log(f"Не удалось перезапустить: {e}", "error")
            return
        core.log("Перезапускаю программу…", "ok")
        core.events.put(("quit", None))

    def _update_own_rects(self):
        """Прямоугольники видимых окон программы (панель, настройки, окна перевода…).
        Windows обычно сама прячет их от снимков, но не везде это срабатывает — подстраховываемся."""
        rects = []
        for w in [self.root] + [c for c in self.root.winfo_children() if isinstance(c, tk.Toplevel)]:
            if config.CHAT_COVER and w is self.chat.win:
                continue      # окно чата поверх области на время снимка становится прозрачным само
            try:
                if w.winfo_ismapped() and w.state() != "withdrawn":
                    rects.append((w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()))
            except tk.TclError:
                pass
        core.own_rects = rects

    # --- игровой чат ---
    def show_chat(self, pairs):
        for prefix, text in pairs:
            self.chat_lines.append(f"{prefix}{text}")
            if self.chat_scroll:
                self.chat_scroll += 1      # вы листаете вверх — вид не уезжает из-за новых сообщений
        self.chat_lines = self.chat_lines[-config.CHAT_HISTORY:]
        self.chat_last = time.time()
        self.chat.show("")
        self._trim_chat()

    def _chat_wheel(self, e):
        """Колесо мыши над окном чата — прокрутка истории сообщений."""
        step = 1 if e.delta > 0 else -1
        self.chat_scroll = max(0, min(len(self.chat_lines) - 1, self.chat_scroll + step))
        self.chat_last = time.time()        # пока листаете — окно не прячется
        self._trim_chat()

    def _chat_height_drag(self, h):
        """Тянут нижний край окна чата — это и есть предельная высота (в режиме «поверх чата» — высота области)."""
        if config.CHAT_COVER and core.chat_region:
            x, y, w, _ = core.chat_region
            core.chat_region = (x, y, w, int(h))
            core.save_settings(chat_region=core.chat_region)
        else:
            config.CHAT_HEIGHT = int(h)
        self._trim_chat()

    def chat_view(self):
        """Какие сообщения сейчас видны: до текущей прокрутки, сколько помещается по высоте."""
        end = len(self.chat_lines) - self.chat_scroll
        limit = self.chat.max_height() if self.chat.max_height else None
        start = max(0, end - (config.CHAT_LINES if not limit else config.CHAT_HISTORY))
        view = self.chat_lines[start:end]
        return view

    def _trim_chat(self):
        view = self.chat_view()
        marker = f"↓ ещё {self.chat_scroll} нов. (колесо вниз)" if self.chat_scroll else ""

        def put(v):
            self.chat.label.config(text="\n".join(v + ([marker] if marker else [])))
        put(view)
        limit = self.chat.max_height() if self.chat.max_height else None
        while limit and len(view) > 1 and self.chat.natural_height() > limit:
            view = view[1:]                 # сверху убираем то, что не помещается
            put(view)
        if self.chat.visible:
            self.chat.fit()

    def _remember_chat_hwnd(self):
        """Окно чата «поверх области»: на время снимка чата делаем его прозрачным (иначе прочитаем себя)."""
        try:
            hwnd = int(self.chat.win.wm_frame(), 16)
        except Exception:
            hwnd = None

        def hide_for_capture(on):
            if not (config.CHAT_COVER and self.chat.visible and hwnd):
                return False
            try:
                import ctypes
                alpha = 0 if on else int(255 * config.CHAT_ALPHA)
                ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, alpha, 2)   # LWA_ALPHA
                return True
            except Exception:
                return False
        chat.hide_for_capture = hide_for_capture

    # --- меню игры ---
    def menu_learn(self):
        def done(reg):
            if reg:
                self.root.after(200, lambda: threading.Thread(target=menu.learn, args=(reg,), daemon=True).start())

        self.pick_area("Меню игры должно быть ОТКРЫТО. Обведите кусочек меню, который всегда одинаковый "
                       "(заголовок или кнопки). Правый клик — забыть меню.", done, menu.forget, game_area=True)

    def menu_state(self, opened):
        """Меню игры открыли/закрыли: прячем/возвращаем окна перевода."""
        if opened:
            tts.stop()
            self._menu_hidden = [ov for ov in (self.subs, self.answers, self.chat) if ov.visible]
            for ov in self._menu_hidden:
                ov.hide()
            core.log("Меню игры — автоперевод на паузе")
        else:
            for ov in getattr(self, "_menu_hidden", []):
                if ov is self.chat:
                    self.show_chat_window()
                else:
                    ov.show(ov.label.cget("text"))
            self._menu_hidden = []
            core.log("Меню закрыто — продолжаю переводить")
        self.panel.refresh()

    def show_chat_window(self):
        """Вернуть окно чата (после правого клика): последние переводы или подсказку."""
        self.chat_last = time.time()
        if not self.chat_lines:
            self.chat.show("Здесь появятся переводы новых сообщений чата.")
            return
        self.chat.show("")
        self._trim_chat()

    def select_chat_region(self):
        def done(reg):
            if reg:
                core.chat_region = reg
                core.save_settings(chat_region=reg)
                core.log(f"Область чата сохранена: {reg[2]}×{reg[3]}. Новые сообщения будут переводиться, "
                         f"пока включён автоперевод ({hotkeys.K('auto')}).", "ok")
                self.panel.refresh()

        def clear():
            core.chat_region = None
            core.save_settings(chat_region=None)
            self.chat.hide()
            core.log("Область чата убрана")
            self.panel.refresh()
        self.pick_area("Обведите ОКНО ЧАТА игры (только строки сообщений, без вкладок и поля ввода). "
                       "Правый клик — убрать область.", done, clear, game_area=True, layout=True)

    def chat_compose(self):
        """Маленькое поле: пишете по-русски → Enter → английский перевод в буфере обмена."""
        old = getattr(self, "compose", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        w = self.compose = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg="#1a1d23", highlightthickness=2, highlightbackground="#4d86ff")
        ml, mt, mr, mb = screens.monitor_at(*(tooltip.cursor_pos() or (0, 0)))   # на мониторе, где мышка
        width = 620
        w.geometry(f"{width}x86+{(ml + mr - width) // 2}+{mb - 220}")
        tk.Label(w, text="💬 Напишите по-русски → Enter: английский перевод — в буфер обмена.  Esc — закрыть",
                 fg="#8cf", bg="#1a1d23", font=("Segoe UI", 9), anchor="w").pack(
            fill="x", padx=8, pady=(6, 2))
        self.compose_var = tk.StringVar()
        e = tk.Entry(w, textvariable=self.compose_var, bg="#2b3040", fg="#fff", insertbackground="#fff",
                     relief="flat", font=("Segoe UI", 12))
        e.pack(fill="x", padx=8)
        self.compose_info = tk.Label(w, text="", fg="#9aa4b2", bg="#1a1d23", font=("Segoe UI", 9), anchor="w")
        self.compose_info.pack(fill="x", padx=8, pady=(2, 4))

        def send(_e=None):
            text = self.compose_var.get().strip()
            if not text:
                return
            self.compose_info.config(text="⏳ Перевожу…", fg="#8cf")
            threading.Thread(target=lambda: core.events.put(("chat_out", (text, chat.translate_outgoing(text)))),
                             daemon=True).start()
        e.bind("<Return>", send)
        e.bind("<Escape>", lambda _e: self._close_compose())
        w.after(50, lambda: (w.lift(), w.focus_force(), e.focus_set()))
        ui_overlay.exclude_from_capture(w)

    def _close_compose(self):
        w = getattr(self, "compose", None)
        self.compose = None
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass

    def chat_out_ready(self, src, en):
        if not en:
            core.log("Чат: не удалось перевести сообщение (нет связи с переводчиками?)", "error")
            if getattr(self, "compose", None) is not None:
                self.compose_info.config(text="❌ Не получилось перевести — попробуйте ещё раз", fg="#f88")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(en)
        self.root.update()
        core.log(f"Чат → «{en}» — в буфере обмена, вставьте в чат игры (Ctrl+V)", "ok")
        history.history_add("Чат (вы)", en, src)
        if getattr(self, "compose", None) is not None:
            self.compose_info.config(text=f"✅ Скопировано: {en}   — в игре откройте чат и нажмите Ctrl+V", fg="#6f6")
            self.compose.after(2500, self._close_compose)

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
            self.sync_region_frames()
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

    REGION_FRAMES = (("subs", "region", "Область СУБТИТРОВ", "#2060d0"),
                     ("answers", "answers_region", "Область ОТВЕТОВ", "#d07010"),
                     ("chat", "chat_region", "Область ЧАТА", "#9050d0"),
                     ("subs2", "region2", "Область РЕПЛИК 2", "#18a090"))

    def sync_region_frames(self):
        """Рамки расстановки = текущие области. Область удалили — рамка исчезает (и при выходе не вернёт её);
        обвели заново или сменилась игра — рамка встаёт по новой области. Перетаскивание рамки не сбивается."""
        if not getattr(self, "layout", False):
            return
        frames = self.region_frames
        changed = False
        for key, attr, title, color in self.REGION_FRAMES:
            reg = getattr(core, attr)
            fr = frames.get(key)
            if fr is not None and getattr(fr, "src", None) == reg:
                continue
            if fr is not None:
                fr.destroy()
                frames.pop(key)
                changed = True
            if reg:
                fr = ui_windows.RegionFrame(self, title, color, reg, self._regions_changed)
                fr.src = reg
                frames[key] = fr
                changed = True
        if changed:
            self._regions_changed(live=True)

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
        self.sync_region_frames()          # удалённые за время расстановки области — не сохранять обратно
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
        if "chat" in frames:
            core.chat_region = frames["chat"].rect()
            core.save_settings(chat_region=core.chat_region)
        if frames:
            msg = "Области сохранены"
            regs = [core.region, core.answers_region, core.region2, core.chat_region]
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
                       "Правый клик — убрать её.", done, clear, game_area=True, layout=True)

    def select_answers_region(self):
        def done(reg):
            if reg:
                core.answers_region = reg
                core.save_settings(answers_region=reg)
                core.log(f"Область ответов сохранена: {reg[2]}×{reg[3]}", "ok")
                self.panel.refresh()
                if self.answers.visible:
                    self.answers.fit()
        self.pick_area("Обведите область ВАРИАНТОВ ОТВЕТА (для автоперевода).", done, game_area=True, layout=True)

    def profile_changed(self):
        """Переключились на другую игру: убрать переводы прежней, перечитать её области."""
        editor.reset()
        self.apply_game_style()
        for ov in (self.subs, self.answers, self.quest):
            ov.hide()
        self.subs.clear_history()
        lines = getattr(self, "chat_lines", None)
        if lines is not None:
            lines.clear()
        self.chat.hide()
        self.panel.profile_changed()
        tray.update()
        if core.active_profile and profiles.is_running():
            gamefacts.gather(core.active_profile)      # один раз на игру: Groq собирает имена, термины, персонажей
        self.auto_start_check()

    def apply_game_style(self):
        """Вид перевода текущей игры (шрифт, цвет, плашка/обводка) — на все окна перевода."""
        from . import style
        style.apply()
        for ov in (self.subs, self.answers, self.quest):
            ov.apply_style()

    def auto_start_check(self):
        """Галочка пресета «Автоперевод при запуске игры»: игра запущена — включаем автоперевод сами."""
        p = profiles.active()
        done = self.__dict__.setdefault("_auto_done", set())
        done &= set(profiles.running())          # игру закрыли — при следующем запуске включим снова
        pid = core.active_profile
        if not p.get("auto_start") or pid in done or core.auto_on.is_set() or not profiles.is_running():
            return
        if not (core.region or core.region2 or core.answers_region or core.chat_region):
            return                                  # областей ещё нет — включать нечего
        done.add(pid)                             # один раз за запуск игры: выключили сами — не включаем снова
        core.auto_on.set()
        core.log(f"▶ {profiles.name()} запущена — автоперевод включён сам (галочка в «Играх»)", "ok")
        self.panel.refresh()
        tray.update()

    def repeat_line(self):
        """Клавиша «повторить реплику»: последняя реплика снова на экране и звучит заново."""
        if not core.last_line:
            core.log("Повторять пока нечего — ещё не было ни одной реплики.", "warn")
            return
        text, orig = core.last_line
        was_visible = self.subs.visible
        self.subs.push((text, orig))
        threading.Thread(target=tts.repeat_line, args=(text, orig), daemon=True).start()
        if not was_visible and not config.KEEP_UNTIL_NEXT:
            # реплика в игре уже пропала — повтор сам уберётся, когда его успеют прочитать/дослушать
            ms = int(max(config.HIDE_DELAY, 6) * 1000 + len(text) * 80)
            self.root.after(ms, lambda: self.subs.label.cget("text") == text and self.subs.hide())

    def select_quest_once(self, speak=False):
        if self.quest.visible:
            # окно задания открыто — та же клавиша его закрывает (мышкой не дотянуться, когда управляете персонажем)
            self.quest.hide()
            return
        def done(reg):
            if reg:
                # небольшая пауза, чтобы затемнение успело пропасть со скриншота
                self.root.after(150, lambda: threading.Thread(
                    target=watcher.translate_once, args=(reg, speak), daemon=True).start())
        self.pick_area("Обведите текст — переведу и прочитаю вслух." if speak else
                       "Обведите ЗАДАНИЕ / текст для разового перевода.", done)

    def _poll(self):
        """Главный цикл программы (каждые 50 мс). Ошибка в одном событии не должна его останавливать —
        иначе программа перестаёт реагировать на всё (так и было после закрытия перевода подсказки)."""
        try:
            self._poll_body()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(tb)
            core.error_traces.append(time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + tb)
            key = f"{type(e).__name__}:{e}"
            if key not in getattr(self, "_poll_errors", set()):
                self._poll_errors = getattr(self, "_poll_errors", set()) | {key}
                last = tb.strip().splitlines()
                where = next((ln.strip() for ln in reversed(last) if ln.strip().startswith("File")), "")
                core.log(f"Ошибка в программе (работа продолжается): {type(e).__name__}: {str(e)[:120]} "
                         f"[{where[-90:]}]", "error")
        finally:
            if not getattr(self, "_closing", False):
                try:
                    self.root.after(50, self._poll)
                except tk.TclError:
                    pass

    def _poll_body(self):
        core.heartbeat = time.time()
        try:
            self.indicator.update(core.auto_on.is_set() or getattr(self, "_paused_auto", False),
                                  paused=not game.game_active.is_set() or core.in_menu, busy=bool(self.busy),
                                  tts_on=config.TTS_ENABLED)
        except Exception:
            pass
        try:
            while True:
                kind, payload = core.events.get_nowait()
                if kind == "text":
                    self.subs.push(payload)
                elif kind == "text_improve":
                    # ИИ-редактор ответил позже — тихо подменяем ещё показанный черновик
                    draft, better = payload
                    for ov in (self.subs, self.answers, self.quest):
                        if ov.visible and ov.label.cget("text") == draft:
                            ov.label.config(text=better)
                            ov.fit()
                    if core.last_line and core.last_line[0] == draft:
                        core.last_line = (better, core.last_line[1])
                elif kind == "repeat_line":
                    self.repeat_line()
                elif kind == "profile_changed":
                    self.profile_changed()
                elif kind == "game_new":
                    self.panel.ask_new_game(payload)
                elif kind == "game_created":
                    self.game_created(payload)
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
                    self.panel.history_new(payload)
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
                elif kind == "once_tts":
                    self.select_quest_once(speak=True)
                elif kind == "once":
                    self.select_quest_once()
                elif kind == "subs_once":
                    threading.Thread(target=watcher.translate_subs_once, daemon=True).start()
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
                    if updater.state.get("announced") != payload["version"] and not updater.state.get("auto_installing"):
                        updater.state["announced"] = payload["version"]          # уведомление — один раз на версию
                        tray.notify(f"AAC Translator {payload['version']}",
                                    "Вышла новая версия — " + ("установится при следующем запуске программы."
                                                               if config.UPDATE_AUTO else
                                                               "кнопка «Обновить» на Главной."))
                elif kind == "update_install":
                    info = updater.state.get("latest")
                    if info and updater.is_newer(info["version"]):
                        updater.install_async(info)
                    else:
                        updater.check_async(quiet=False)
                elif kind == "chat":
                    self.show_chat(payload)
                elif kind == "select_chat":
                    self.select_chat_region()
                elif kind == "menu_state":
                    self.menu_state(payload)
                elif kind == "menu_learn":
                    self.menu_learn()
                elif kind == "chat_once":
                    threading.Thread(target=chat.translate_chat_once, daemon=True).start()
                elif kind == "chat_show":
                    self.show_chat_window()
                elif kind == "chat_compose":
                    self.chat_compose()
                elif kind == "chat_out":
                    self.chat_out_ready(*payload)
                elif kind == "flip_gender":
                    from . import voices
                    res = voices.flip_last()
                    if res:
                        core.log(f"🎭 {res[0]} — теперь {'женщина' if res[1] == 'f' else 'мужчина'} "
                                 f"(голос сменится со следующей реплики; запомнено)", "ok")
                        cw = getattr(self, "chars_win", None)
                        if cw is not None and cw.alive():
                            cw.render()
                    else:
                        core.log("Сменить пол: ещё не было реплик с именем говорящего", "warn")
                elif kind == "restart":
                    self.restart()
                elif kind == "update_check":
                    updater.check_async(quiet=False)
                elif kind == "tooltip_key":
                    self.tooltip_key()
                elif kind == "word_show":
                    self.show_word(payload)
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
                    self.panel.fill_voices(payload)
                elif kind == "quit":
                    self._closing = True
                    tts.shutdown()
                    tcache.save()
                    tray.stop_tray()
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 6 == 0:    # где сейчас наши окна — их закрашиваем на снимках областей
            self._update_own_rects()
        if self._tick % 10 == 0:   # 2 раза в секунду проверяем, игра ли на переднем плане
            self._check_game_focus()
        if self._tick % 20 == 0:  # раз в секунду обновляем панель (обратный отсчёт пауз моделей)
            self.panel.refresh()
        self.subs.set_status("⏳" if "Субтитры" in self.busy else "")
        self.answers.set_status("💬 Варианты ответа" + ("  ⏳" if "Ответы" in self.busy else ""))
