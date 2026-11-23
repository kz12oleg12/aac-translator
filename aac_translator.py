"""
Экранный ИИ-переводчик для ArcheAge Chronicles (и любых других игр). Версия 10.1

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

if sys.stdout is None or sys.stderr is None:
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translator.log")
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aac.main import main  # noqa: E402

if __name__ == "__main__":
    main()
