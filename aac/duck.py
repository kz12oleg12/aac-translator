"""Приглушение игры, пока звучит озвучка: громкость только процесса игры (микшер Windows), потом — обратно."""
import os
import threading

from . import config, core

_lock = threading.Lock()
_saved = {}          # pid процесса игры → его громкость до приглушения
_on = False


def _game_names():
    from . import profiles
    p = profiles.all_profiles().get(core.active_profile) if core.active_profile else None
    if not p:
        return [], ""
    return [e.lower() for e in p.get("exes", [])], (p.get("match") or "").lower()


def _sessions():
    from pycaw.pycaw import AudioUtilities           # Windows; без pycaw просто не приглушаем
    exes, match = _game_names()
    if not exes and not match:
        return []
    out = []
    for s in AudioUtilities.GetAllSessions():
        pr = s.Process
        if not pr or pr.pid == os.getpid():
            continue
        name = (pr.name() or "").lower()
        if name in exes or (match and match in name):
            out.append(s)
    return out


def _worker(down):
    global _on
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass
    with _lock:
        if down == _on:
            return
        try:
            if down:
                for s in _sessions():
                    v = s.SimpleAudioVolume
                    cur = v.GetMasterVolume()
                    _saved[s.Process.pid] = cur
                    v.SetMasterVolume(cur * config.TTS_DUCK_LEVEL, None)
            else:
                for s in _sessions():
                    pid = s.Process.pid
                    if pid in _saved:
                        s.SimpleAudioVolume.SetMasterVolume(_saved.pop(pid), None)
                _saved.clear()
            _on = down
        except Exception as e:
            print("duck:", e)
            _on = down


def set(down):
    """down=True — приглушить игру, False — вернуть громкость. Не блокирует поток озвучки."""
    if os.name != "nt" or (down and not config.TTS_DUCK):
        return
    if down == _on:
        return
    threading.Thread(target=_worker, args=(bool(down),), daemon=True).start()
