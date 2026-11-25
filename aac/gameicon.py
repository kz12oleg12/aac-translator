"""Значок игры из её .exe (Windows): сохраняется в папку пресета как icon.png и показывается в панели."""
import ctypes
import os
import threading

from . import core

SIZE = 128
_busy = set()


def path(pid):
    from . import profiles
    return os.path.join(profiles.folder(pid), "icon.png")


def _extract(exe_path, out):
    from ctypes import wintypes
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hicon = wintypes.HICON()
    got = user32.PrivateExtractIconsW(exe_path, 0, SIZE, SIZE, ctypes.byref(hicon), None, 1, 0)
    if got < 1 or not hicon:
        return False

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    bmi = BMI(ctypes.sizeof(BMI), SIZE, -SIZE, 1, 32, 0, 0, 0, 0, 0, 0)
    hdc = gdi32.CreateCompatibleDC(None)
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(hdc, hbmp)
    try:
        user32.DrawIconEx(hdc, 0, 0, hicon, SIZE, SIZE, 0, None, 3)        # DI_NORMAL
        raw = ctypes.string_at(bits, SIZE * SIZE * 4)
        img = Image.frombuffer("RGBA", (SIZE, SIZE), raw, "raw", "BGRA", 0, 1)
        if img.getextrema()[3][1] == 0:                                   # старый значок без прозрачности
            img = img.convert("RGB").convert("RGBA")
        bbox = img.getbbox()
        if not bbox:
            return False
        os.makedirs(os.path.dirname(out), exist_ok=True)
        img.save(out)
        return True
    finally:
        gdi32.SelectObject(hdc, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc)
        user32.DestroyIcon(hicon)


def ensure(prof, proc_pid):
    """Игра на экране: если у пресета ещё нет значка — достать из её .exe (в фоне)."""
    if not prof or prof == core.DEFAULT_PROFILE or prof in _busy or os.name != "nt":
        return
    if os.path.exists(path(prof)):
        return
    from . import game
    exe_path = game._path_of(proc_pid) if proc_pid else None
    if not exe_path:
        return
    _busy.add(prof)

    def run():
        try:
            _extract(exe_path, path(prof))
        except Exception as e:
            print("icon:", e)
    threading.Thread(target=run, daemon=True).start()


_urls = {}


def data_url(prof):
    """Значок для панели (data:image/png) или "". Кэшируется, пока файл не поменялся."""
    import base64
    if not prof:
        return ""
    p = path(prof)
    try:
        if not os.path.exists(p):
            return ""
        mt = os.path.getmtime(p)
        hit = _urls.get(prof)
        if hit and hit[0] == mt:
            return hit[1]
        from PIL import Image
        import io
        im = Image.open(p)
        im.thumbnail((72, 72))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        _urls[prof] = (mt, url)
        return url
    except Exception:
        return ""
