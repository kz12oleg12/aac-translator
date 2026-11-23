"""Главное окно в новом виде: боковая колонка разделов слева, выбранный раздел справа.

Заменяет старую системную панель (ui_panel.Panel) и умеет всё то же: refresh(), add_log(), toggle(),
update_keys(), reset_pos(), show_update(). Пока не перенесённые разделы открывают прежние окна.
"""
import os
import threading
import time
import tkinter as tk

from . import config, core, game, glossary, hotkeys, limits, menu, profiles, tcache, translate, tts, ui_overlay
from . import ui_kit as K
from .ui_sections import GamesMixin, SectionsMixin
from .ui_panel import LOG_COLORS, PROVIDER_LABELS, PROVIDER_NAMES

W, H = 960, 720
SIDE_W = 220
LOG_W = 380

NAV = [  # (группа, [(id, название)])
    ("Перевод", [("home", "Главная"), ("games", "Игры"), ("areas", "Области"), ("tr", "Переводчики"),
                 ("win", "Окна перевода")]),
    ("Озвучка", [("voice", "Голос и интонация"), ("chars", "Персонажи")]),
    ("Данные", [("hist", "История"), ("gloss", "Словарь"), ("keys", "Клавиши"), ("backup", "Резервная копия")]),
]
KEY_GROUPS = [
    ("Перевод", ["auto", "subs_once", "answers_once", "once", "once_tts", "tooltip", "repeat"]),
    ("Чат", ["chat_once", "chat_compose"]),
    ("Области", ["select", "select_subs2", "select_answers", "select_chat", "menu_learn"]),
    ("Окна и озвучка", ["toggle", "layout", "reset", "panel", "tts", "flip_gender", "quit"]),
]
HOME_KEYS = ["auto", "tooltip", "once", "repeat"]


class Shell(SectionsMixin, GamesMixin):
    def __init__(self, app, win):
        self.app, self.win = app, win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.97)
        win.configure(bg=K.BG)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        h = min(H, sh - 80)
        default = (sw - W - 20, 40)
        x, y = core.SETTINGS.get("panel_pos", default)
        if not (0 <= x <= sw - 100 and 0 <= y <= sh - 60):
            x, y = default
        x = max(0, min(x, sw - W))
        self.default_pos = default
        self.height = h
        self.log_on = bool(core.SETTINGS.get("log_visible", True))
        width = W + (LOG_W if self.log_on else 0)
        x = max(0, min(x, sw - width))
        win.geometry(f"{width}x{h}+{x}+{y}")
        self.visible = True
        self.busy = False
        self.update_version = None
        self.sections, self.nav_items, self.current = {}, {}, None
        self._build_sidebar()
        self.logwin = LogColumn(self, win)       # журнал — своя колонка справа, не зависит от раздела
        self.content = tk.Frame(win, bg=K.BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.show("home")
        K.install_wheel(win, self._current_scroll)     # колесо мыши — где бы ни был курсор в разделе
        win.after(200, lambda: ui_overlay.exclude_from_capture(win))

    # ---------- боковая колонка ----------
    def _build_sidebar(self):
        side = tk.Frame(self.win, bg=K.SIDEBAR, width=SIDE_W)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(self.win, bg=K.LINE, width=1).pack(side="left", fill="y")
        head = tk.Frame(side, bg=K.SIDEBAR)
        head.pack(fill="x", padx=14, pady=(16, 10))
        self._logo = None
        for name in ("icon_32.png", "icon_22.png"):
            path = os.path.join(config.APP_DIR, name)
            try:
                if os.path.exists(path):
                    self._logo = tk.PhotoImage(file=path)
                    break
            except Exception:
                self._logo = None
        if self._logo:
            tk.Label(head, image=self._logo, bg=K.SIDEBAR).pack(side="left", padx=(0, 10))
        tbox = tk.Frame(head, bg=K.SIDEBAR)
        tbox.pack(side="left")
        title = K.label(tbox, "AAC Translator", 13, K.TEXT, "bold")
        title.pack(anchor="w")
        self.game_lbl = K.label(tbox, "", 9, K.ACCENT_TEXT)
        self.game_lbl.config(cursor="hand2")
        self.game_lbl.bind("<Button-1>", lambda e: self.show("games"))
        self.game_lbl.pack(anchor="w")
        for w in (head, title, tbox):        # окно без рамки — тащим за заголовок
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._end_move)

        nav = tk.Frame(side, bg=K.SIDEBAR)
        nav.pack(fill="both", expand=True, padx=8)
        for group, items in NAV:
            K.caps(nav, group).pack(anchor="w", padx=10, pady=(12, 3))
            for sid, text in items:
                row = tk.Frame(nav, bg=K.SIDEBAR, cursor="hand2")
                row.pack(fill="x", pady=1)
                bar = tk.Frame(row, bg=K.SIDEBAR, width=4, height=18)
                bar.pack(side="left", padx=(6, 8), pady=7)
                lab = tk.Label(row, text=text, bg=K.SIDEBAR, fg=K.MUTED, font=K.f(10), anchor="w", cursor="hand2")
                lab.pack(side="left", fill="x", expand=True)
                for w in (row, bar, lab):
                    w.bind("<Button-1>", lambda e, s=sid: self.show(s))
                    w.bind("<Enter>", lambda e, s=sid: self._hover(s, True))
                    w.bind("<Leave>", lambda e, s=sid: self._hover(s, False))
                self.nav_items[sid] = (row, bar, lab)

        bottom = tk.Frame(side, bg=K.SIDEBAR)
        bottom.pack(fill="x", side="bottom", padx=8, pady=(0, 10))
        K.separator(bottom).pack(fill="x", pady=(0, 6))
        self.update_btn = K.button(bottom, "⬇ Обновить", lambda: core.events.put(("update_install", None)),
                                   kind="primary", size=9)
        self.log_btn = K.button(bottom, "Журнал", lambda: self.logwin.toggle(), kind="flat")
        self.log_btn.pack(fill="x")
        self.check_btn = K.button(bottom, "Проверить обновления", lambda: core.events.put(("update_check", None)),
                                  kind="flat")
        self.check_btn.pack(fill="x")
        K.button(bottom, "Перезапустить", lambda: core.events.put(("restart", None)), kind="flat").pack(fill="x")
        K.button(bottom, "Выключить программу", lambda: core.events.put(("quit", None)),
                 kind="danger").pack(fill="x")
        K.label(bottom, f"версия {config.VERSION}", 8, K.FAINT).pack(anchor="w", padx=10, pady=(6, 0))
        self.bottom = bottom

    def _hover(self, sid, on):
        if sid == self.current:
            return
        row, bar, lab = self.nav_items[sid]
        bg = K.CARD if on else K.SIDEBAR
        for w in (row, bar):
            w.config(bg=bg)
        lab.config(bg=bg)

    def _mark(self, sid):
        for s, (row, bar, lab) in self.nav_items.items():
            on = s == sid
            bg = K.CARD if on else K.SIDEBAR
            row.config(bg=bg)
            bar.config(bg=K.ACCENT if on else bg)
            lab.config(bg=bg, fg=K.TEXT if on else K.MUTED)

    # ---------- переключение разделов ----------
    HEAVY = ("chars", "gloss", "hist", "games")    # длинные списки — пересобираются при открытии, а не на каждое событие

    def show(self, sid):
        if self.current == sid:
            self.refresh()
            self._on_show(sid)
            return
        if self.current in self.sections:
            self.sections[self.current].pack_forget()
        if sid not in self.sections:
            self.sections[sid] = getattr(self, f"_build_{sid}")()
        self.current = sid
        self.sections[sid].pack(fill="both", expand=True)
        self._mark(sid)
        self.refresh()
        self._on_show(sid)

    def _on_show(self, sid):
        if sid == "chars":
            self._chars_render()
        elif sid == "gloss":
            self._gl_render()
        elif sid == "hist":
            self._hist_render()
        elif sid == "games":
            self._games_render()

    def _current_scroll(self):
        sc = self.sections.get(self.current)
        return sc if isinstance(sc, K.Scroll) else None

    def _open_characters(self):
        from . import ui_windows
        ui_windows.CharactersWindow(self.app)

    def _page(self, title, sub=None):
        sc = K.Scroll(self.content)
        body = tk.Frame(sc.body, bg=K.BG)
        body.pack(fill="both", expand=True, padx=26, pady=20)
        hdr = K.section_title(body, title, sub)
        hdr.pack(fill="x", pady=(0, 14))
        for w in [hdr] + hdr.winfo_children():
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._move)
            w.bind("<ButtonRelease-1>", self._end_move)
        return sc, body

    # ---------- Главная ----------
    def _build_home(self):
        sc, b = self._page("Главная")
        self.upd_banner = tk.Frame(b, bg=K.ACCENT_TINT, highlightthickness=1, highlightbackground=K.ACCENT_LINE)
        self.upd_text = K.label(self.upd_banner, "", 10, K.TEXT, bg=K.ACCENT_TINT)
        self.upd_text.pack(side="left", padx=14, pady=10)
        K.button(self.upd_banner, "Обновить", lambda: core.events.put(("update_install", None)),
                 kind="primary").pack(side="right", padx=10, pady=6)

        hero, hi = K.card(b, padx=20, pady=16)
        hero.pack(fill="x")
        self.hero_card = hero
        self.hero_dot = K.Dot(hi, K.ACCENT, 12)
        self.hero_dot.pack(side="left", padx=(0, 14))
        txt = tk.Frame(hi, bg=K.CARD)
        txt.pack(side="left", fill="x", expand=True)
        self.hero_title = K.label(txt, "", 15, K.TEXT, "bold")
        self.hero_title.pack(anchor="w")
        self.hero_sub = K.label(txt, "", 9, K.MUTED, wraplength=470)
        self.hero_sub.pack(anchor="w")
        self.hero_btn = K.button(hi, "", lambda: core.events.put(("auto", None)), kind="primary")
        self.hero_btn.pack(side="right")

        cards = tk.Frame(b, bg=K.BG)
        cards.pack(fill="x", pady=(12, 0))
        self.info = {}
        for i, (key, title) in enumerate((("tts", "Озвучка"), ("tr", "Переводчик"), ("cache", "Из кэша"))):
            c, ci = K.card(cards, bg=K.BG, padx=14, pady=10)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            cards.columnconfigure(i, weight=1, uniform="c")
            K.label(ci, title, 9, K.DIM).pack(anchor="w")
            v = K.label(ci, "", 11, K.TEXT)
            v.pack(anchor="w")
            s = K.label(ci, "", 8, K.FAINT)
            s.pack(anchor="w")
            self.info[key] = (v, s)

        lim = tk.Frame(b, bg=K.BG)
        lim.pack(fill="x", pady=(16, 0))
        K.h2(lim, "Лимиты").pack(anchor="w", pady=(0, 6))
        self.lim_box = tk.Frame(lim, bg=K.BG)
        self.lim_box.pack(fill="x")
        self.lim_rows = []

        K.separator(b).pack(fill="x", pady=16)
        K.h2(b, "Что переводить").pack(anchor="w", pady=(0, 8))
        tiles = tk.Frame(b, bg=K.BG)
        tiles.pack(fill="x")

        def set_answers(v):
            core.answers_auto = bool(v)
            core.save_settings(answers_auto=core.answers_auto)
            if not v:
                core.events.put(("answers_hide", None))
            core.log("Автоперевод ответов " + ("включён" if v else f"выключен — кнопка {hotkeys.K('answers_once')}"),
                     "ok")

        def set_docked(v):
            core.events.put(("dock_toggle", bool(v)))
            config.ANSWERS_DOCKED = bool(v)

        def set_chat(v):
            core.chat_auto = bool(v)
            core.save_settings(chat_auto=core.chat_auto)
            core.log("Автоперевод чата " + ("включён" if v else "выключен"), "ok")

        def set_pause(v):
            config.PAUSE_OUTSIDE_GAME = bool(v)
            core.save_settings(pause_outside_game=config.PAUSE_OUTSIDE_GAME)
            if not v:
                game.game_active.set()
            core.log("Пауза вне игры " + ("включена" if v else "выключена"))

        self.tiles = {
            "answers": K.Tile(tiles, "❝", "Ответы сами", "переводятся без клавиши", None,
                              lambda: core.answers_auto, set_answers),
            "docked": K.Tile(tiles, "▤", "Одним окном", "ответы под субтитрами", None,
                             lambda: config.ANSWERS_DOCKED, set_docked),
            "chat": K.Tile(tiles, "#", "Чат", "", None, lambda: core.chat_auto, set_chat),
            "pause": K.Tile(tiles, "Ⅱ", "Пауза", "игра свёрнута или меню", None,
                            lambda: config.PAUSE_OUTSIDE_GAME, set_pause),
        }
        for i, t in enumerate(self.tiles.values()):
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            tiles.columnconfigure(i, weight=1, uniform="t")

        def set_stream(v):
            from . import chat
            config.SHOW_ON_STREAM = bool(v)
            core.save_settings(show_on_stream=config.SHOW_ON_STREAM)
            ui_overlay.apply_stream_visibility()
            chat._state["cover_mode"] = None      # заново проверить, прячет ли Windows окно чата от снимков
            core.log("Окна перевода " + ("видны на трансляции и записи экрана" if v else
                                          "скрыты от трансляции и записи экрана"), "ok")
        sc_, si = K.card(b, padx=16, pady=2)
        sc_.pack(fill="x", pady=(12, 0))

        def set_auto_upd(v):
            config.UPDATE_AUTO = bool(v)
            core.save_settings(update_auto=config.UPDATE_AUTO)
        self.upd_row = K.ToggleRow(si, "Обновлять автоматически при запуске",
                                   "есть новая версия, когда вы запускаете программу, — поставится сразу, ещё до игры. "
                                   "Пока программа работает, она сама не обновляется: только кнопка «Обновить».",
                                   lambda: config.UPDATE_AUTO, set_auto_upd, last=True)
        self.stream_row = K.ToggleRow(si, "Показывать переводы на трансляции",
                                      "зрители в Discord, OBS и на записи экрана видят субтитры, ответы и подсказки. "
                                      "Это окно и журнал остаются скрытыми.",
                                      lambda: config.SHOW_ON_STREAM, set_stream)

        def set_only(v):
            config.GAMES_ONLY = bool(v)
            core.save_settings(games_only=config.GAMES_ONLY)
            if not v:
                game.game_active.set()
            core.log("Перевод " + ("только в играх из списка (раздел «Игры»)" if v else
                                   "в любой программе, где включён автоперевод"), "ok")
        self.only_row = K.ToggleRow(si, "Только игры из списка",
                                    "в других программах перевод на паузе. Новая игра добавляется сама, когда вы "
                                    "включаете в ней автоперевод, — со своими областями, словарём и персонажами.",
                                    lambda: config.GAMES_ONLY, set_only)
        self.only_row.pack(fill="x")
        self.stream_row.pack(fill="x")
        self.upd_row.pack(fill="x")

        keys = tk.Frame(b, bg=K.BG)
        keys.pack(fill="x", pady=(18, 0))
        top = tk.Frame(keys, bg=K.BG)
        top.pack(fill="x")
        K.h2(top, "Главные клавиши").pack(side="left")
        more = K.label(top, f"Все {len(hotkeys.HOTKEY_DEFS)} — в разделе «Клавиши» →", 9, K.ACCENT_TEXT)
        more.config(cursor="hand2")
        more.bind("<Button-1>", lambda e: self.show("keys"))
        more.pack(side="right")
        grid = tk.Frame(keys, bg=K.BG)
        grid.pack(fill="x", pady=(8, 0))
        self.home_keys = {}
        desc = {d[0]: d[1] for d in hotkeys.HOTKEY_DEFS}
        for n, hid in enumerate(HOME_KEYS):
            cell = tk.Frame(grid, bg=K.BG)
            cell.grid(row=n // 2, column=n % 2, sticky="w", pady=3, padx=(0, 30))
            chip = K.key_chip(cell)
            chip.config(width=14)
            chip.pack(side="left")
            d = desc.get(hid, hid)
            K.label(cell, d[:1].upper() + d[1:], 10, K.TEXT2).pack(side="left", padx=(10, 0))
            self.home_keys[hid] = chip

        return sc

    def _refresh_home(self):
        on = core.auto_on.is_set()
        paused = on and (core.in_menu or not game.game_active.is_set())
        if not on:
            title, color, btn = "Автоперевод выключен", K.FAINT, f"Включить · {hotkeys.K('auto')}"
        elif paused:
            title = ("Пауза — открыто меню игры" if core.in_menu else
                     "Пауза — на экране не игра из списка" if config.GAMES_ONLY else "Пауза — игра не на экране")
            color, btn = K.AMBER, f"Выключить · {hotkeys.K('auto')}"
        else:
            title = "Перевожу…" if self.busy else "Перевожу игру"
            color, btn = K.ACCENT, f"Пауза · {hotkeys.K('auto')}"
        self.hero_title.config(text=title)
        self.hero_dot.set(color)
        self.hero_btn.config(text=btn)
        parts = []
        if not core.region:
            parts.append(f"Обведите субтитры: {hotkeys.K('select')}")
        else:
            parts.append(f"Игра: {profiles.name()}")
        if core.stats["last"] and core.stats["last"] != "—":
            parts.append(f"последний перевод: {core.stats['last']}")
        self.hero_sub.config(text=" · ".join(parts) or "Включите автоперевод, находясь в игре")
        # карточки
        self.info["tts"][0].config(text=tts.voice_title() if config.TTS_ENABLED else "выключена")
        self.info["tts"][1].config(text=f"вкл/выкл: {hotkeys.K('tts')}")
        chain = translate.provider_chain()
        self.info["tr"][0].config(text=" → ".join(PROVIDER_NAMES.get(p, p).replace(" (OCR)", "")
                                                 for p in chain[:2]) or "нет ключей!")
        err = core.stats["errors"]
        self.info["tr"][1].config(text=f"запросов {core.stats['requests']} · ошибок {err}",
                                  fg=K.RED if err else K.FAINT)
        total = tcache.stats["hits"] + tcache.stats["misses"]
        pct = f"{100 * tcache.stats['hits'] // total}%" if total else "—"
        self.info["cache"][0].config(text=pct if config.CACHE_ENABLED else "кэш выключен")
        self.info["cache"][1].config(text=f"{tcache.size()} фраз в кэше" if config.CACHE_ENABLED else "")
        # лимиты
        bars = limits.bars()
        if len(bars) != len(self.lim_rows):
            for r in self.lim_rows:
                r[0].destroy()
            self.lim_rows = []
            for _ in bars:
                row = tk.Frame(self.lim_box, bg=K.BG)
                row.pack(fill="x", pady=3)
                name = K.label(row, "", 10, K.TEXT2, width=9)
                name.pack(side="left")
                bar = K.Bar(row, 300)
                bar.pack(side="left", fill="x", expand=True, padx=10)
                txt = K.label(row, "", 9, K.MUTED, width=28, anchor="e")
                txt.pack(side="right")
                self.lim_rows.append((row, name, bar, txt))
            if not bars:
                row = tk.Frame(self.lim_box, bg=K.BG)
                row.pack(fill="x")
                K.label(row, "появятся после первых переводов", 9, K.FAINT).pack(anchor="w")
                self.lim_rows.append((row, None, None, None))
        for (row, name, bar, txt), (n, frac, text) in zip(self.lim_rows, bars):
            name.config(text=n)
            txt.config(text=text)
            if frac is None:
                bar.set(0)
            else:
                bar.set(frac, K.ACCENT if frac > 0.25 else (K.AMBER if frac > 0.08 else K.RED))
        # плитки
        self.tiles["chat"].set_sub("переводится сам" if core.chat_region else "область не задана")
        for t in self.tiles.values():
            t.sync()
        self.stream_row.sync()
        self.upd_row.sync()
        self.only_row.sync()
        for hid, chip in self.home_keys.items():
            chip.config(text=hotkeys.K(hid))
        if self.update_version:
            self.upd_text.config(text=f"Доступна новая версия {self.update_version}")
            if not self.upd_banner.winfo_manager():
                self.upd_banner.pack(fill="x", pady=(0, 12), before=self.hero_card)

    # ---------- Области ----------
    def _build_areas(self):
        sc, b = self._page("Области", "Где программа читает текст на экране. Цвет — как у рамки в режиме расстановки.")
        K.button(b, f"Расставить окна и рамки · {hotkeys.K('layout')}", lambda: core.events.put(("layout", None)),
                 kind="primary").pack(anchor="w", pady=(0, 14))
        grid = tk.Frame(b, bg=K.BG)
        grid.pack(fill="x")
        self.area_cards = {}
        specs = [("region", "Субтитры", "#4c8dff", "select", "основная область реплик", None),
                 ("region2", "Реплики 2", "#4c8dff", "select_subs2", "НПС говорят мимоходом в другом месте",
                  "region2"),
                 ("answers_region", "Ответы", "#f0a040", "select_answers", "варианты ответа игрока", None),
                 ("chat_region", "Чат", "#3fb37f", "select_chat", "окно чата игры", "chat_region")]
        for i, (attr, name, color, ev, sub, clearable) in enumerate(specs):
            c, ci = K.card(grid, padx=14, pady=12)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 10, 0), pady=(0, 10))
            grid.columnconfigure(i % 2, weight=1, uniform="a")
            top = tk.Frame(ci, bg=K.CARD)
            top.pack(fill="x")
            tk.Frame(top, bg=color, width=12, height=12).pack(side="left", padx=(0, 10))
            K.label(top, name, 11, K.TEXT, "bold").pack(side="left")
            chip = K.key_chip(top, hotkeys.K(ev))
            chip.pack(side="right")
            size = K.label(ci, "", 9, K.MUTED)
            size.pack(anchor="w", pady=(8, 0))
            K.label(ci, sub, 9, K.DIM).pack(anchor="w")
            btns = tk.Frame(ci, bg=K.CARD)
            btns.pack(fill="x", pady=(10, 0))
            pick = K.button(btns, "", lambda e=ev: core.events.put((e, None)), kind="ghost", size=9)
            pick.pack(side="left")
            clear = None
            if clearable:
                clear = K.button(btns, "Убрать", lambda a=clearable: self._clear_area(a), kind="danger", size=9)
            self.area_cards[attr] = (size, pick, clear, chip, ev)
        mc, mi = K.card(b, padx=14, pady=12)
        mc.pack(fill="x", pady=(4, 0))
        top = tk.Frame(mi, bg=K.CARD)
        top.pack(fill="x")
        K.label(top, "Меню игры", 11, K.TEXT, "bold").pack(side="left")
        self.menu_chip = K.key_chip(top, hotkeys.K("menu_learn"))
        self.menu_chip.pack(side="right")
        self.menu_state = K.label(mi, "", 9, K.MUTED, wraplength=600)
        self.menu_state.pack(anchor="w", pady=(8, 0))
        K.label(mi, "Пока меню открыто, автоперевод на паузе. Узнаётся по надписям и рамкам, а не по цвету.",
                9, K.DIM, wraplength=600).pack(anchor="w")
        mb = tk.Frame(mi, bg=K.CARD)
        mb.pack(fill="x", pady=(10, 0))
        self.menu_pick = K.button(mb, "", lambda: core.events.put(("menu_learn", None)), kind="ghost", size=9)
        self.menu_pick.pack(side="left")
        self.menu_forget = K.button(mb, "Забыть", lambda: (menu.forget(), self.refresh()), kind="danger", size=9)
        return sc

    def _clear_area(self, attr):
        setattr(core, attr, None)
        core.save_settings(**{attr: None})
        if attr == "chat_region":
            self.app.chat.hide()
            core.log("Область чата убрана")
        else:
            core.events.put(("subs2_hide", None))
            core.log("Вторая область реплик убрана")
        self.refresh()

    def _refresh_areas(self):
        for attr, (size, pick, clear, chip, ev) in self.area_cards.items():
            reg = getattr(core, attr)
            if reg:
                size.config(text=f"{reg[2]} × {reg[3]} · x {reg[0]}, y {reg[1]}", fg=K.MUTED)
                pick.config(text="Обвести заново")
                if clear and not clear.winfo_manager():
                    clear.pack(side="left", padx=(8, 0))
            else:
                size.config(text="не задана", fg=K.AMBER)
                pick.config(text="Обвести")
                if clear and clear.winfo_manager():
                    clear.pack_forget()
            chip.config(text=hotkeys.K(ev))
        has = bool(core.menu_region)
        self.menu_state.config(text=("Запомнено" + (" · сейчас открыто — пауза" if core.in_menu else ""))
                               if has else "Не запомнено: откройте меню в игре и нажмите клавишу справа",
                               fg=K.MUTED if has else K.AMBER)
        self.menu_pick.config(text="Запомнить заново" if has else "Запомнить меню")
        if has and not self.menu_forget.winfo_manager():
            self.menu_forget.pack(side="left", padx=(8, 0))
        elif not has and self.menu_forget.winfo_manager():
            self.menu_forget.pack_forget()
        self.menu_chip.config(text=hotkeys.K("menu_learn"))

    # ---------- Переводчики ----------
    def _build_tr(self):
        sc, b = self._page("Переводчики", "Кто переводит текст. Если основной упрётся в лимит, сразу подхватит запасной.")
        row = tk.Frame(b, bg=K.BG)
        row.pack(fill="x")
        self.main_var = tk.StringVar(value=PROVIDER_LABELS.get(config.PROVIDER, config.PROVIDER))
        self.fb_var = tk.StringVar(value=PROVIDER_LABELS.get(config.FALLBACK_PROVIDERS[0], "нет")
                                   if config.FALLBACK_PROVIDERS else "нет")
        for i, (title, var, opts) in enumerate((("Основной", self.main_var, list(PROVIDER_LABELS.values())),
                                                ("Запасной", self.fb_var, ["нет"] + list(PROVIDER_LABELS.values())))):
            c, ci = K.card(row, padx=14, pady=10)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            row.columnconfigure(i, weight=1, uniform="p")
            K.label(ci, title, 9, K.DIM).pack(anchor="w", pady=(0, 4))
            K.select(ci, var, opts, self._provider_changed, width=30).pack(fill="x")

        c, ci = K.card(b, padx=16, pady=8)
        c.pack(fill="x", pady=(14, 0))
        K.h2(ci, "Все переводчики").pack(anchor="w", pady=(4, 2))
        self.prov_box = tk.Frame(ci, bg=K.CARD)
        self.prov_box.pack(fill="x")

        c, ci = K.card(b, padx=16, pady=6)
        c.pack(fill="x", pady=(14, 0))
        K.h2(ci, "Как переводить").pack(anchor="w", pady=(6, 0))

        def setter(attr, key):
            def s(v):
                setattr(config, attr, bool(v))
                core.save_settings(**{key: bool(v)})
            return s
        self.tr_rows = [
            K.ToggleRow(ci, "Кэш переводов", "повторы фраз — мгновенно и без запросов",
                        lambda: config.CACHE_ENABLED, setter("CACHE_ENABLED", "cache_enabled")),
            K.ToggleRow(ci, "Не переводить системные сообщения игры", "и не озвучивать их",
                        lambda: config.SKIP_SYSTEM, setter("SKIP_SYSTEM", "skip_system")),
            K.ToggleRow(ci, "Пополнять словарь сам", "имена, предметы и места из переводов",
                        lambda: config.GLOSSARY_AUTO, setter("GLOSSARY_AUTO", "glossary_auto")),
            K.ToggleRow(ci, "Показывать распознанный текст в журнале", "чтобы видеть, что программа читает",
                        lambda: config.SHOW_OCR_IN_LOG, setter("SHOW_OCR_IN_LOG", "show_ocr_in_log")),
            K.ToggleRow(ci, "Сохранять историю в файл", "папка history, по файлу на день",
                        lambda: config.SAVE_HISTORY, setter("SAVE_HISTORY", "save_history"), last=True),
        ]
        for r in self.tr_rows:
            r.pack(fill="x")
        cb = tk.Frame(b, bg=K.BG)
        cb.pack(fill="x", pady=(10, 0))
        K.button(cb, "Очистить кэш переводов", self._clear_cache, kind="ghost", size=9).pack(side="left")
        return sc

    def _clear_cache(self):
        n = tcache.size()
        tcache.clear()
        core.log(f"Кэш переводов очищен ({n} фраз).")
        self.refresh()

    def _provider_changed(self):
        by_label = {v: k for k, v in PROVIDER_LABELS.items()}
        config.PROVIDER = by_label.get(self.main_var.get(), config.PROVIDER)
        fb = by_label.get(self.fb_var.get())
        config.FALLBACK_PROVIDERS = [fb] if fb and fb != config.PROVIDER else []
        core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
        chain = translate.provider_chain()
        core.log(f"Переводчик: {' → '.join(PROVIDER_NAMES.get(p, p) for p in chain) or 'нет ключей!'} (сохранено)", "ok")
        for p in [config.PROVIDER] + config.FALLBACK_PROVIDERS:
            if not translate.provider_has_key(p):
                core.log(f"У «{PROVIDER_NAMES.get(p, p)}» нет ключа — он будет пропущен", "warn")
        self.refresh()

    TR_ROWS = [("deepl", "DeepL"), ("microsoft", "Microsoft"), ("google", "Google"), ("groq_ocr", "Groq · нейросеть"),
               ("gemini_ocr", "Gemini · нейросеть"), ("claude_ocr", "Claude · нейросеть, платно")]

    def _build_prov_rows(self):
        """Строки «Все переводчики» создаются один раз; дальше меняется только их текст и цвет (без мигания)."""
        self.prov_rows = {}
        for i, (pid, name) in enumerate(self.TR_ROWS):
            r = tk.Frame(self.prov_box, bg=K.CARD)
            r.pack(fill="x")
            body = tk.Frame(r, bg=K.CARD)
            body.pack(fill="x", pady=7)
            dot = K.Dot(body, K.FAINT, 8)
            dot.pack(side="left", padx=(0, 12))
            t = tk.Frame(body, bg=K.CARD)
            t.pack(side="left", fill="x", expand=True)
            top = tk.Frame(t, bg=K.CARD)
            top.pack(anchor="w")
            title = K.label(top, name, 10, K.TEXT, "bold")
            title.pack(side="left")
            role = tk.Label(top, text="", bg=K.ACCENT, fg="#ffffff", font=K.f(8, "bold"), padx=6)
            sub = K.label(t, "", 9, K.DIM)
            sub.pack(anchor="w")
            info = K.label(body, "", 9, K.MUTED)
            info.pack(side="right")
            if i < len(self.TR_ROWS) - 1:
                K.separator(r).pack(fill="x")
            self.prov_rows[pid] = {"dot": dot, "title": title, "role": role, "sub": sub, "info": info, "state": None}

    def _refresh_tr(self):
        if not hasattr(self, "prov_rows"):
            self._build_prov_rows()
        chain = translate.provider_chain()
        lim = {n.lower(): t for n, _, t in limits.bars()}
        for pid, name in self.TR_ROWS:
            w = self.prov_rows[pid]
            has = translate.provider_has_key(pid)
            role = "основной" if chain[:1] == [pid] else ("запасной" if pid in chain[1:] else "")
            need_key = pid not in ("microsoft", "google")
            sub = ("ключ сохранён в Windows" if has else "нет ключа") if need_key else "без ключа"
            info = lim.get(name.split(" ")[0].lower(), "без лимита" if not need_key else "")
            state = (has, role, sub, info)
            if state == w["state"]:
                continue                       # ничего не поменялось — не трогаем (иначе мигает)
            w["state"] = state
            w["dot"].set(K.GREEN if has else K.FAINT)
            w["title"].config(fg=K.TEXT if has else K.MUTED)
            w["sub"].config(text=sub)
            w["info"].config(text=info)
            if role:
                w["role"].config(text=role)
                if not w["role"].winfo_manager():
                    w["role"].pack(side="left", padx=(8, 0))
            elif w["role"].winfo_manager():
                w["role"].pack_forget()
        for r in self.tr_rows:
            r.sync()
        main = PROVIDER_LABELS.get(config.PROVIDER, config.PROVIDER)
        fb = PROVIDER_LABELS.get(config.FALLBACK_PROVIDERS[0], "нет") if config.FALLBACK_PROVIDERS else "нет"
        if self.main_var.get() != main:
            self.main_var.set(main)
        if self.fb_var.get() != fb:
            self.fb_var.set(fb)

    # ---------- Клавиши ----------
    def _build_keys(self):
        sc, b = self._page("Клавиши", "Нажмите «Изменить», затем нужную клавишу или кнопку мыши. Можно с Ctrl / Shift / Alt.")
        cols = tk.Frame(b, bg=K.BG)
        cols.pack(fill="x")
        desc = {d[0]: d[1] for d in hotkeys.HOTKEY_DEFS}
        known = {h for _, ids in KEY_GROUPS for h in ids}
        groups = [(g, [h for h in ids if h in desc]) for g, ids in KEY_GROUPS]
        rest = [d[0] for d in hotkeys.HOTKEY_DEFS if d[0] not in known]
        if rest:
            groups.append(("Другое", rest))
        self.key_chips = {}
        for g, ids in groups:
            c, ci = K.card(cols, padx=16, pady=8)
            c.pack(fill="x", pady=(0, 12))
            K.caps(ci, g).pack(anchor="w", pady=(2, 4))
            for n, hid in enumerate(ids):
                r = tk.Frame(ci, bg=K.CARD)
                r.pack(fill="x")
                line = tk.Frame(r, bg=K.CARD)
                line.pack(fill="x", pady=5)
                d = desc[hid]
                btn = tk.Label(line, text="Изменить", bg=K.CARD, fg=K.ACCENT_TEXT, font=K.f(9), cursor="hand2")
                btn.pack(side="right", padx=(8, 0))
                btn.bind("<Button-1>", lambda e, h=hid: threading.Thread(
                    target=hotkeys.capture_hotkey, args=(h,), daemon=True).start())
                chip = K.key_chip(line)
                chip.config(width=16)
                chip.pack(side="right", padx=(8, 0))
                K.label(line, d[:1].upper() + d[1:], 10, K.TEXT).pack(side="left", fill="x", expand=True)
                self.key_chips[hid] = chip
                if n < len(ids) - 1:
                    K.separator(r).pack(fill="x")
        return sc

    # ---------- Резервная копия ----------
    def _build_backup(self):
        from . import backup
        sc, b = self._page("Резервная копия", "Настройки, области, голоса персонажей, словарь и кэш — одним файлом. "
                                              "Для переноса на другой ПК или после переустановки.")
        row = tk.Frame(b, bg=K.BG)
        row.pack(fill="x")
        for i, (title, text, btxt, cmd, kind) in enumerate((
                ("Сохранить в файл", "Создаст zip-файл. Лучше хранить его на флешке или в облаке.",
                 "Сохранить…", self._backup_export, "primary"),
                ("Загрузить из файла", "Текущие настройки сначала сохранятся в папку backups. "
                 "Программа перезапустится.", "Выбрать файл…", self._backup_import, "ghost"))):
            c, ci = K.card(row, padx=16, pady=14)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            row.columnconfigure(i, weight=1, uniform="b")
            K.label(ci, title, 12, K.TEXT, "bold").pack(anchor="w")
            K.label(ci, text, 9, K.MUTED, wraplength=290).pack(anchor="w", pady=(4, 10))
            K.button(ci, btxt, cmd, kind=kind).pack(anchor="w")
        c, ci = K.card(b, padx=16, pady=12)
        c.pack(fill="x", pady=(14, 0))
        K.h2(ci, "Что входит в копию").pack(anchor="w", pady=(0, 8))
        g = tk.Frame(ci, bg=K.CARD)
        g.pack(fill="x")
        items = [("Настройки и области", "все переключатели и рамки"), ("Голоса персонажей", "кто каким голосом"),
                 ("Словарь", "имена и названия"), ("Кэш переводов", "готовые переводы фраз"),
                 ("Образец меню", "для паузы в меню"), ("Ключи переводчиков", "не входят — они в Windows")]
        for i, (a, s) in enumerate(items):
            cell = tk.Frame(g, bg=K.SIDEBAR)
            cell.grid(row=i // 3, column=i % 3, sticky="nsew", padx=(0 if i % 3 == 0 else 8, 0), pady=(0, 8))
            g.columnconfigure(i % 3, weight=1, uniform="i")
            K.label(cell, a, 10, K.TEXT, bg=K.SIDEBAR).pack(anchor="w", padx=10, pady=(8, 0))
            K.label(cell, s, 9, K.DIM, bg=K.SIDEBAR).pack(anchor="w", padx=10, pady=(0, 8))
        self.bk_box_card, self.bk_box = K.card(b, padx=16, pady=10)
        self.bk_box_card.pack(fill="x", pady=(14, 0))
        return sc

    def _refresh_backup(self):
        from . import backup
        for w in self.bk_box.winfo_children():
            w.destroy()
        K.h2(self.bk_box, "Автокопии перед восстановлением").pack(anchor="w", pady=(2, 6))
        try:
            names = sorted((n for n in os.listdir(backup.BACKUP_DIR) if n.endswith(".zip")), reverse=True)[:5]
        except OSError:
            names = []
        if not names:
            K.label(self.bk_box, "пока нет", 9, K.FAINT).pack(anchor="w", pady=(0, 4))
        for i, n in enumerate(names):
            r = tk.Frame(self.bk_box, bg=K.CARD)
            r.pack(fill="x", pady=4)
            K.label(r, n, 10, K.TEXT).pack(side="left")
            K.button(r, "Вернуть", lambda p=os.path.join(backup.BACKUP_DIR, n): self._backup_restore(p),
                     kind="ghost", size=9).pack(side="right")

    def _backup_export(self):
        from tkinter import filedialog, messagebox
        from . import backup
        path = filedialog.asksaveasfilename(parent=self.win, title="Сохранить резервную копию",
                                            initialfile=backup.default_name(), defaultextension=".zip",
                                            filetypes=[("Резервная копия AAC", "*.zip")])
        if not path:
            return
        try:
            saved = backup.export(path)
        except Exception as e:
            messagebox.showerror("AAC Translator", f"Не удалось сохранить: {e}", parent=self.win)
            return
        core.log(f"Резервная копия сохранена: {path} ({backup.describe(saved)})", "ok")
        messagebox.showinfo("AAC Translator", f"Сохранено: {backup.describe(saved)}.\n\n{path}", parent=self.win)

    def _backup_import(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.win, title="Загрузить резервную копию",
                                          filetypes=[("Резервная копия AAC", "*.zip"), ("Все файлы", "*.*")])
        if path:
            self._backup_restore(path)

    def _backup_restore(self, path):
        from tkinter import messagebox
        from . import backup
        try:
            info = backup.read_manifest(path)
        except Exception as e:
            messagebox.showerror("AAC Translator", f"Не получилось открыть файл: {e}", parent=self.win)
            return
        if not messagebox.askyesno(
                "AAC Translator",
                f"Копия от {info.get('created', '?')} (версия {info.get('version', '?')}).\n"
                f"В ней: {backup.describe(info.get('files', []))}.\n\n"
                "Заменить текущие настройки? Нынешние сохранятся в папку backups. Программа перезапустится.",
                parent=self.win):
            return
        try:
            restored, before = backup.restore(path)
        except Exception as e:
            messagebox.showerror("AAC Translator", f"Не удалось восстановить: {e}", parent=self.win)
            return
        core.log(f"Восстановлено: {backup.describe(restored)}. Прежние настройки — в {before}", "ok")
        self.app.restart()

    # ---------- то, что вызывает остальная программа ----------
    def refresh(self):
        g = ("📌 " if core.SETTINGS.get("profile_lock") else "🎮 ") + profiles.name()
        if self.game_lbl.cget("text") != g:
            self.game_lbl.config(text=g)
        if self.current in self.HEAVY:
            return
        fn = getattr(self, f"_refresh_{self.current}", None)
        if fn:
            try:
                fn()
            except tk.TclError:
                pass

    def _refresh_keys(self):
        for hid, chip in getattr(self, "key_chips", {}).items():
            if hotkeys.capturing == hid:
                chip.config(text="нажмите…", fg=K.AMBER)
            else:
                chip.config(text=hotkeys.K(hid), fg=K.TEXT2)

    def update_keys(self):
        self._refresh_keys()
        self.refresh()

    def add_log(self, t, msg, level):
        self.logwin.add(t, msg, level)
        if level == "error" and not self.logwin.visible:
            self.logwin.toggle()   # при ошибке журнал сам показывается

    def show_update(self, version):
        self.update_version = version
        self.update_btn.config(text=f"⬇ Обновить до {version}")
        if not self.update_btn.winfo_manager():
            self.update_btn.pack(fill="x", pady=(0, 6), before=self.check_btn)
        self.refresh()

    def ask(self, title, text, yes_text, on_yes, no_text="Позже", on_no=None, entry=None):
        """Вопрос в стиле программы поверх игры (не забирает фокус у игры). Один вопрос за раз.
        entry — начальный текст поля ввода; тогда on_yes получает введённый текст."""
        old = getattr(self, "_dialog", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        d = tk.Toplevel(self.win.master)
        self._dialog = d
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=K.ACCENT_LINE)
        box = tk.Frame(d, bg=K.CARD)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(box, bg=K.CARD)
        inner.pack(fill="both", expand=True, padx=22, pady=18)
        K.label(inner, title, 13, K.TEXT, "bold").pack(anchor="w")
        K.label(inner, text, 10, K.MUTED, wraplength=380).pack(anchor="w", pady=(6, 12 if entry is not None else 16))
        var = tk.StringVar(value=entry or "")
        if entry is not None:
            e = K.entry(inner, var, width=34)
            e.pack(fill="x", pady=(0, 16), ipady=3)
            e.bind("<Return>", lambda ev: yes())
        btns = tk.Frame(inner, bg=K.CARD)
        btns.pack(fill="x")

        def close():
            try:
                d.destroy()
            except tk.TclError:
                pass
            self._dialog = None

        def yes():
            value = var.get()
            close()
            on_yes(value) if entry is not None else on_yes()

        def no():
            close()
            if on_no:
                on_no()
        K.button(btns, yes_text, yes, kind="primary").pack(side="right")
        K.button(btns, no_text, no, kind="ghost").pack(side="right", padx=(0, 8))
        d.update_idletasks()
        w, h = d.winfo_reqwidth(), d.winfo_reqheight()
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
        d.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        d.after(200, lambda: ui_overlay.exclude_from_capture(d))
        return d

    def pick_program(self, title, text, on_pick, hide_known=False):
        """Окно со списком запущенных программ (кнопки). Не забирает фокус у игры."""
        from . import game
        progs = [(e, t) for e, t in game.running_programs() if not (hide_known and profiles.for_exe(e))]
        old = getattr(self, "_dialog", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        d = tk.Toplevel(self.win.master)
        self._dialog = d
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=K.ACCENT_LINE)
        box = tk.Frame(d, bg=K.CARD)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(box, bg=K.CARD)
        inner.pack(fill="both", expand=True, padx=22, pady=18)
        K.label(inner, title, 13, K.TEXT, "bold").pack(anchor="w")
        K.label(inner, text, 10, K.MUTED, wraplength=420).pack(anchor="w", pady=(6, 12))

        def close():
            try:
                d.destroy()
            except tk.TclError:
                pass
            self._dialog = None
        lst = tk.Frame(inner, bg=K.CARD)
        lst.pack(fill="x")
        if not progs:
            K.label(lst, "Не нашёл открытых программ. Запустите игру и откройте этот список снова.", 10,
                    K.AMBER, wraplength=420).pack(anchor="w", pady=(0, 8))
        for exe, wtitle in progs[:14]:
            row = tk.Frame(lst, bg=K.SIDEBAR, cursor="hand2", highlightthickness=1, highlightbackground=K.LINE)
            row.pack(fill="x", pady=2)
            a = K.label(row, exe, 10, K.TEXT, "bold", bg=K.SIDEBAR)
            a.pack(anchor="w", padx=10, pady=(4, 0))
            b_ = K.label(row, wtitle[:60], 9, K.DIM, bg=K.SIDEBAR)
            b_.pack(anchor="w", padx=10, pady=(0, 4))
            for w in (row, a, b_):
                w.bind("<Button-1>", lambda e, x=exe: (close(), on_pick(x)))
                w.bind("<Enter>", lambda e, r=row: r.config(highlightbackground=K.ACCENT_LINE))
                w.bind("<Leave>", lambda e, r=row: r.config(highlightbackground=K.LINE))
        btns = tk.Frame(inner, bg=K.CARD)
        btns.pack(fill="x", pady=(12, 0))
        K.button(btns, "Отмена", close, kind="ghost").pack(side="right")
        d.update_idletasks()
        w, h = d.winfo_reqwidth(), d.winfo_reqheight()
        sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
        d.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(20, (sh - h) // 3)}")
        d.after(200, lambda: ui_overlay.exclude_from_capture(d))
        self._pick_rows = lst
        return d

    def ask_new_game(self, exe):
        """«Новая игра: … — создать пресет?» (только по вашей клавише автоперевода, не при Alt+Tab)."""
        if getattr(self, "_asking_exe", None) == exe and getattr(self, "_dialog", None) is not None:
            return
        self._asking_exe = exe

        def create(title):
            self._asking_exe = None
            game.create_profile_for(exe, title.strip() or None)

        def not_game():
            self._asking_exe = None
            game.mark_not_game(exe)
        self.ask(f"Новая игра: {exe}",
                 "Создать для неё пресет? У игры будут свои области, словарь и персонажи. Название можно исправить:",
                 "Создать", create, no_text="Не игра", on_no=not_game, entry=profiles._pretty(exe))

    def profile_changed(self):
        """Другая игра: разделы со своими данными (персонажи, словарь, игры) собрать заново."""
        for sid in ("chars", "gloss", "games"):
            if sid in self.sections and sid != self.current:
                self.sections.pop(sid).destroy()
        if self.current in ("chars", "gloss", "games", "hist"):
            self._rebuild(self.current)
        self.refresh()

    def sync_vars(self):
        self.refresh()

    def toggle(self):
        if self.visible:
            self.win.withdraw()
        else:
            self.win.deiconify()
            self.refresh()
        self.visible = not self.visible

    def reset_pos(self):
        x, y = self.default_pos
        self.win.geometry(f"+{x}+{y}")
        core.save_settings(panel_pos=(x, y))

    def _start_move(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _end_move(self, e):
        core.save_settings(panel_pos=(self.win.winfo_x(), self.win.winfo_y()))



class LogColumn:
    """Журнал — колонка справа в главном окне, во всю высоту. Не зависит от выбранного раздела.
    ✕ — убрать колонку (окно становится уже), «Журнал» внизу боковой колонки — вернуть."""

    def __init__(self, shell, win):
        self.shell, self.win = shell, win
        self.frame = tk.Frame(win, bg=K.SIDEBAR, width=LOG_W)
        self.frame.pack_propagate(False)
        self.line = tk.Frame(win, bg=K.LINE, width=1)
        head = tk.Frame(self.frame, bg=K.SIDEBAR)
        head.pack(fill="x", padx=(14, 6), pady=(16, 8))
        title = K.label(head, "Журнал", 12, K.TEXT, "bold")
        title.pack(side="left")
        close = tk.Label(head, text="✕", bg=K.SIDEBAR, fg=K.MUTED, font=K.f(10), cursor="hand2", padx=8)
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.toggle())
        clear = tk.Label(head, text="Очистить", bg=K.SIDEBAR, fg=K.ACCENT_TEXT, font=K.f(9), cursor="hand2")
        clear.pack(side="right", padx=(0, 6))
        clear.bind("<Button-1>", lambda e: self.clear())
        for w_ in (head, title):
            w_.bind("<ButtonPress-1>", shell._start_move)
            w_.bind("<B1-Motion>", shell._move)
            w_.bind("<ButtonRelease-1>", shell._end_move)
        self.text = tk.Text(self.frame, bg=K.SIDEBAR, fg=K.MUTED, font=(K.MONO, 9), relief="flat",
                            highlightthickness=0, wrap="word", padx=14, pady=4, state="disabled", cursor="arrow",
                            spacing1=1, spacing3=3)
        self.text.pack(fill="both", expand=True, pady=(0, 10))
        for tag, color in LOG_COLORS.items():
            self.text.tag_config(tag, foreground=color)
        self.text.tag_config("time", foreground=K.FAINT)
        self.visible = shell.log_on
        if self.visible:
            self._pack()

    def _pack(self):
        before = getattr(self.shell, "content", None)     # колонка встаёт справа от уже показанного раздела
        kw = {"before": before} if before is not None else {}
        self.frame.pack(side="right", fill="y", **kw)
        self.line.pack(side="right", fill="y", **kw)

    def add(self, t, msg, level):
        self.text.config(state="normal")
        self.text.insert("end", f"{t}  ", "time")
        self.text.insert("end", f"{msg}\n", level)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > 300:
            self.text.delete("1.0", f"{lines - 300}.0")
        self.text.see("end")
        self.text.config(state="disabled")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def toggle(self):
        self.visible = not self.visible
        w = W + (LOG_W if self.visible else 0)
        x, y = self.win.winfo_x(), self.win.winfo_y()
        sw = self.win.winfo_screenwidth()
        if self.visible:
            self._pack()
            x = max(0, min(x, sw - w))      # не уезжать за правый край экрана
        else:
            self.frame.pack_forget()
            self.line.pack_forget()
        self.win.geometry(f"{w}x{self.shell.height}+{x}+{y}")
        core.save_settings(log_visible=self.visible)
        self.shell.log_on = self.visible
