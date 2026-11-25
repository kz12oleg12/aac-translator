"""
Экранный ИИ-переводчик для ArcheAge Chronicles (и любых других игр). Версия 15.32

Горячие клавиши:
  F9           — выделить область СУБТИТРОВ (запоминается навсегда, даже после перезапуска)
  Shift+F9     — выделить область ВАРИАНТОВ ОТВЕТА (переводятся вместе с субтитрами, с учётом реплики NPC)
  F8           — ВКЛ/ВЫКЛ автоперевод субтитров: каждая новая реплика переводится сама
  F7           — обвести мышкой задание/текст и перевести один раз (в отдельном окне,
                 область субтитров при этом не меняется)
  F10          — скрыть / показать окна перевода (правый клик по окну тоже скрывает)
  F11          — вернуть окна на место (субтитры и ответы снова прилипают к своим областям)
  Ctrl+Shift+L — режим расстановки: показать окна перевода, чтобы перетащить их мышкой.
                 Ширина — тянуть за правый край окна (или колесо мыши). Всё запоминается.
  F6           — скрыть / показать системную панель (статус, клавиши, ошибки)
  Ctrl+Shift+Q — выйти

Установка (один раз):
  py -m pip install mss pillow keyboard requests pynput pystray
  Для режима «распознать + перевести» (Google / DeepL) дополнительно:
  py -m pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Globalization winrt-Windows.Foundation winrt-Windows.Storage.Streams

Ключ Gemini (бесплатно): https://aistudio.google.com/apikey
  Вставьте его в API_KEY в файле aac/config.py или задайте переменную окружения GEMINI_API_KEY.

Игру запускайте в режиме «Оконный без рамки» (Borderless),
иначе в полноэкранном режиме скриншот может быть чёрным, а окно перевода — не видно.
"""

# Это короткий файл запуска. Сама программа — в папке aac (по модулям).
import ctypes
import os
import sys

# папка программы: рядом с AAC Translator.exe (собранная версия) или с этим файлом
_HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

if "--selftest" in sys.argv:
    # проверка сборки: все модули программы загружаются (без окон и клавиатуры); код выхода 0 — всё хорошо
    import importlib
    import pkgutil
    import traceback
    sys.path.insert(0, _HERE)
    try:
        import aac
        bad = []
        for m in pkgutil.iter_modules(aac.__path__):
            try:
                importlib.import_module("aac." + m.name)
            except Exception:
                bad.append(m.name + ": " + traceback.format_exc(limit=1).strip().splitlines()[-1])
        for opt in ("PIL", "mss", "requests", "keyboard", "pynput", "pystray", "edge_tts",
                    "winrt.windows.media.ocr"):
            try:
                importlib.import_module(opt)
            except Exception as e:
                bad.append(f"{opt}: {e}")
        with open(os.path.join(_HERE, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write("OK\n" if not bad else "\n".join(bad))
        sys.exit(1 if bad else 0)
    except SystemExit:
        raise
    except Exception:
        with open(os.path.join(_HERE, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        sys.exit(2)

if "--selftest-voices" in sys.argv:
    # проверка пакета офлайн-голосов: подключается, PyTorch грузится, модель говорит фразу; код 0 — всё хорошо
    import traceback
    sys.path.insert(0, _HERE)
    out = []
    try:
        from aac import voicepack, tts_silero
        out.append(f"пакет: {voicepack.activate()}")
        import torch
        out.append(f"torch {torch.__version__}: {float(torch.ones(2).sum())}")
        tts_silero.load()
        path = os.path.join(_HERE, "selftest_voice.wav")
        tts_silero.synth_to_wav("Привет! Проверка офлайн-голоса.", path, tts_silero.VOICES[0][0])
        out.append(f"голос: {os.path.getsize(path)} байт")
        code = 0 if os.path.getsize(path) > 10000 else 1
    except Exception:
        out.append(traceback.format_exc())
        code = 2
    with open(os.path.join(_HERE, "selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    sys.exit(code)

if "--webpanel" in sys.argv:      # окно новой панели — отдельный процесс, свой журнал не ведёт
    if sys.stdout is None or sys.stderr is None:
        sys.stdout = sys.stderr = open(os.devnull, "w")
    sys.path.insert(0, _HERE)
    from aac import web_window
    _a = sys.argv
    web_window.run(_a[_a.index("--webpanel") + 1],
                   int(_a[_a.index("--parent") + 1]) if "--parent" in _a else None)
    sys.exit(0)

if sys.stdout is None or sys.stderr is None:
    _log_path = os.path.join(_HERE, "translator.log")
    try:
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 2_000_000:
            os.replace(_log_path, _log_path + ".old")  # не даём файлу журнала разрастись
        _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _log_file
    except Exception:
        pass

# Чтобы координаты окон и скриншотов совпадали при масштабировании Windows (125%, 150%...)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

sys.path.insert(0, _HERE)
from aac.main import main  # noqa: E402

if __name__ == "__main__":
    main()
