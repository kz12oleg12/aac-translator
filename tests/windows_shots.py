"""Снимки окон на настоящем Windows (запускается в проверках GitHub; картинки — в «артефактах» запуска)."""
import os
import sys
import tempfile
import time
import types

sys.modules["keyboard"] = types.ModuleType("keyboard")
sys.modules["keyboard"].add_hotkey = lambda *a, **k: 0
sys.modules["keyboard"].remove_hotkey = lambda *a: 0
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "shots")
os.makedirs(OUT, exist_ok=True)

from aac import config, core  # noqa: E402
d = tempfile.mkdtemp()
config.APP_DIR = d
config.SETTINGS_FILE = os.path.join(d, "s.json")
core.SETTINGS = core.load_settings() or {}
from aac import profiles, style, appwin  # noqa: E402
import tkinter as tk  # noqa: E402
from PIL import ImageGrab  # noqa: E402

pid = profiles.create("deadcells.exe", "Dead Cells")
profiles.activate(pid, announce=False, hold=True)
app = appwin.App()


def pump(n=20):
    for _ in range(n):
        app.root.update()
        time.sleep(0.03)


pump()
app.panel.win.withdraw()
g = tk.Toplevel(app.root)
g.overrideredirect(True)
g.geometry("760x240+100+100")
c = tk.Canvas(g, width=760, height=240, highlightthickness=0)
c.pack()
for i in range(0, 760, 20):
    c.create_rectangle(i, 0, i + 20, 240, fill=["#5a7d9a", "#8fb3c9", "#c9d7a0", "#e8e2b0"][i // 20 % 4], outline="")
pump()
for mode in ("outline", "box"):
    style.save(text_mode=mode, text_color="#fff3b0", font_size=20)
    app.apply_game_style()
    app.subs.manual = True
    app.subs.width = 680
    app.subs.push("Коллекционер: Ты снова здесь? Клетки сами себя не соберут.")
    app.subs.win.geometry("+130+140")
    pump()
    app.subs.win.lift()
    pump()
    ImageGrab.grab(bbox=(100, 100, 860, 340), all_screens=True).save(os.path.join(OUT, f"subs_{mode}.png"))
app.panel.win.deiconify()
app.panel.win.geometry("+0+0")
app.panel.show("win")
pump()
w = app.panel.win
ImageGrab.grab(bbox=(0, 0, w.winfo_width(), w.winfo_height()), all_screens=True).save(os.path.join(OUT, "panel_win.png"))
print("готово:", os.listdir(OUT))
os._exit(0)
