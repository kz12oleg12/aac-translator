"""История переводов: память сессии и файлы по дням."""


import os


import threading
import time


from . import config, core


HISTORY_DIR = os.path.join(config.APP_DIR, "history")
translation_history = []   # [(время, вид, оригинал, перевод)] за эту сессию
_last_src = {}             # поток -> распознанный оригинал последнего перевода


def last_source():
    return _last_src.get(threading.get_ident())


def history_add(kind, original, translation):
    if not translation:
        return
    entry = (time.strftime("%H:%M:%S"), kind, original or "", translation)
    translation_history.append(entry)
    del translation_history[:-3000]
    if config.SAVE_HISTORY:
        try:
            os.makedirs(HISTORY_DIR, exist_ok=True)
            path = os.path.join(HISTORY_DIR, time.strftime("%Y-%m-%d") + ".txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{entry[0]}] {kind}\n")
                if original:
                    f.write("EN: " + original.replace("\n", " / ") + "\n")
                f.write("RU: " + translation.replace("\n", " / ") + "\n\n")
        except Exception as e:
            print("history:", e)
    core.events.put(("history_new", entry))
