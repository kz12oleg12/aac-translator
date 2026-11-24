"""Мастер первого запуска: четыре шага, каждый сам отмечается, когда сделан. Можно пропустить
и открыть снова с Главной («Мастер настройки»)."""
import tkinter as tk

from . import config, core, hotkeys, profiles, translate
from . import ui_kit as K
from .ui_panel import PROVIDER_NAMES

STEPS = [
    ("tr", "Выберите переводчик",
     "Google работает сразу и без ключа. Нейросеть (Groq — бесплатно) переводит живее и учитывает контекст, "
     "но ей нужен ключ — его можно получить за пару минут."),
    ("game", "Запустите игру",
     "Программа сама узнает игру и заведёт ей пресет — свои области, словарь, персонажей. Ничего нажимать не нужно."),
    ("area", "Обведите субтитры",
     "Обведите мышкой место на экране, где в игре появляются реплики персонажей."),
    ("auto", "Включите автоперевод",
     "Дальше программа сама переводит каждую новую реплику. Можно включать его автоматически при запуске игры."),
]


def needed():
    """Новый пользователь: мастер ещё не пройден и не пропущен, и пресетов игр нет."""
    return not core.SETTINGS.get("wizard_done") and not profiles.game_profiles()


class WizardMixin:
    def _build_start(self):
        sc, b = self._page("Начало работы", "Четыре шага — и программа переводит игру. Шаги отмечаются сами.")
        self.wz = {}
        for n, (key, title, text) in enumerate(STEPS, 1):
            c, ci = K.card(b, padx=16, pady=12)
            c.pack(fill="x", pady=(0, 12))
            top = tk.Frame(ci, bg=K.CARD)
            top.pack(fill="x")
            num = tk.Label(top, text=str(n), width=3, font=K.f(11, "bold"), bg=K.LINE, fg=K.TEXT)
            num.pack(side="left")
            K.label(top, title, 12, K.TEXT, "bold").pack(side="left", padx=(10, 0))
            state = K.label(top, "", 9, K.DIM)
            state.pack(side="right")
            K.label(ci, text, 9, K.DIM, wraplength=560).pack(anchor="w", pady=(6, 8))
            acts = tk.Frame(ci, bg=K.CARD)
            acts.pack(fill="x")
            self.wz[key] = {"num": num, "state": state, "acts": acts}
        a = self.wz["tr"]["acts"]
        K.button(a, "Google — без ключа", lambda: self._wz_provider("google", None), kind="ghost", size=9).pack(
            side="left")
        K.button(a, "Groq — нейросеть", lambda: self._wz_provider("groq_ocr", "groq_ocr"), kind="ghost",
                 size=9).pack(side="left", padx=(8, 0))
        a = self.wz["area"]["acts"]
        K.button(a, f"Обвести субтитры · {hotkeys.K('select')}", lambda: core.events.put(("select", None)),
                 kind="primary", size=9).pack(side="left")
        K.label(a, "или нажмите клавишу прямо в игре", 9, K.FAINT).pack(side="left", padx=(10, 0))
        a = self.wz["auto"]["acts"]
        K.button(a, f"Включить автоперевод · {hotkeys.K('auto')}", lambda: core.events.put(("auto", None)),
                 kind="primary", size=9).pack(side="left")
        self.wz_auto_start = tk.BooleanVar(value=False)
        K.Toggle(a, False, self._wz_auto_start, small=True).pack(side="left", padx=(14, 6))
        K.label(a, "включать сам при запуске игры", 9, K.TEXT2).pack(side="left")
        bottom = tk.Frame(b, bg=K.BG)
        bottom.pack(fill="x", pady=(4, 0))
        self.wz_done_btn = K.button(bottom, "Готово", self._wz_finish, kind="primary")
        self.wz_done_btn.pack(side="right")
        K.button(bottom, "Пропустить", self._wz_finish, kind="flat", size=9).pack(side="right", padx=(0, 8))
        return sc

    def _wz_provider(self, main, need_key):
        config.PROVIDER = main
        config.FALLBACK_PROVIDERS = ["google"] if main != "google" else ["microsoft"]
        core.save_settings(provider=config.PROVIDER, fallback=config.FALLBACK_PROVIDERS)
        core.log(f"Переводчик: {main} (запасной — {config.FALLBACK_PROVIDERS[0]})", "ok")
        if need_key and not translate.provider_has_key(need_key):
            self._ask_key(need_key)
        self.refresh()

    def _wz_auto_start(self, v):
        pid = core.active_profile
        profs = profiles.all_profiles()
        self._wz_auto_wanted = bool(v)
        if pid and pid in profs and not profs[pid].get("free"):
            profs[pid]["auto_start"] = bool(v)
            core.save_settings(profiles=profs)

    def _wz_state(self):
        game_on = bool(core.active_profile) and profiles.is_running() and not profiles.is_free()
        return {
            "tr": (bool(translate.provider_chain()),
                   " → ".join(PROVIDER_NAMES.get(p, p) for p in translate.provider_chain()[:2])
                   or "переводчик без ключа — выберите другой"),
            "game": (game_on, f"✓ {profiles.name()}" if game_on else "ждёт игру…"),
            "area": (bool(core.region), "✓ обведено" if core.region else
                     ("сначала запустите игру" if not game_on else "ещё не обведено")),
            "auto": (core.auto_on.is_set(), "✓ включён" if core.auto_on.is_set() else "выключен"),
        }

    def _refresh_start(self):
        st = self._wz_state()
        for key, (ok, text) in st.items():
            w = self.wz[key]
            txt = ("✓ " if ok and not text.startswith("✓") else "") + text
            if w["state"].cget("text") != txt:
                w["state"].config(text=txt, fg=K.GREEN if ok else K.DIM)
                w["num"].config(bg=K.GREEN if ok else K.LINE, fg="#141413" if ok else K.TEXT)
        # галочка «включать сам» относится к игре — запомнить, когда игра появится
        if getattr(self, "_wz_auto_wanted", False) and core.active_profile:
            profs = profiles.all_profiles()
            p = profs.get(core.active_profile)
            if p is not None and not p.get("free") and not p.get("auto_start"):
                p["auto_start"] = True
                core.save_settings(profiles=profs)

    def _wz_finish(self):
        core.save_settings(wizard_done=True)
        self.show("home")
