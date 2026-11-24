"""Несколько мониторов. Координаты — как у Windows: основной монитор начинается в (0, 0), второй может быть
левее (x < 0) или выше (y < 0). «Виртуальный экран» — прямоугольник, охватывающий все мониторы."""
import ctypes

_fallback = {"w": 1920, "h": 1080}     # не Windows (проверки) — один экран такого размера


def set_fallback(w, h):
    _fallback.update(w=int(w), h=int(h))


def virtual():
    """(x, y, ширина, высота) прямоугольника, охватывающего все мониторы."""
    try:
        u = ctypes.windll.user32
        w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
        if w > 0 and h > 0:
            return u.GetSystemMetrics(76), u.GetSystemMetrics(77), w, h
    except Exception:
        pass
    return 0, 0, _fallback["w"], _fallback["h"]


class _RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class _MONINFO(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("mon", _RECT), ("work", _RECT), ("flags", ctypes.c_ulong)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def monitor_at(x, y):
    """(left, top, right, bottom) монитора, на котором точка (или ближайшего к ней)."""
    try:
        u = ctypes.windll.user32
        u.MonitorFromPoint.argtypes = [_POINT, ctypes.c_ulong]
        u.MonitorFromPoint.restype = ctypes.c_void_p
        u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONINFO)]
        hmon = u.MonitorFromPoint(_POINT(int(x), int(y)), 2)       # MONITOR_DEFAULTTONEAREST
        mi = _MONINFO()
        mi.cb = ctypes.sizeof(_MONINFO)
        if hmon and u.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            m = mi.mon
            return m.l, m.t, m.r, m.b
    except Exception:
        pass
    return 0, 0, _fallback["w"], _fallback["h"]


def on_screen(x, y, margin_w=100, margin_h=60):
    """Точка (левый верх окна) на каком-нибудь мониторе — окно не потерялось за краем."""
    vx, vy, vw, vh = virtual()
    if not (vx <= x <= vx + vw - margin_w and vy <= y <= vy + vh - margin_h):
        return False
    l, t, r, b = monitor_at(x + 10, y + 10)
    return l <= x + 10 < r and t <= y + 10 < b


def clamp(x, y, w, h, near=None):
    """Окно w×h в точке (x, y) — целиком на мониторе (на котором точка near или само окно)."""
    px, py = near if near else (x + w // 2, y + h // 2)
    l, t, r, b = monitor_at(px, py)
    x = max(l, min(int(x), r - int(w)))
    y = max(t, min(int(y), b - int(h)))
    return x, y
