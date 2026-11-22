"""
Установщик AAC Translator.
- копирует программу в папку  %USERPROFILE%\\AAC Translator
- переносит ваши настройки (области, клавиши, окна, выбранный переводчик) из «Загрузок»
- устанавливает нужные библиотеки Python
- создаёт ярлыки на рабочем столе и в меню «Пуск»
Запуск: двойной щелчок по install.bat (или: py install.py)

Автообновление: программа сама скачивает новую версию и запускает
    install.py --update --wait-pid <номер процесса программы>
— установщик ждёт, пока программа закроется, тихо обновляет файлы (вывод — в update.log)
и снова запускает программу.
"""
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = Path.home() / "AAC Translator"
DOWNLOADS = Path.home() / "Downloads"
SETTINGS = "aac_translator_settings.json"
PACKAGES = [
    "mss", "pillow", "keyboard", "requests", "pynput", "pystray",
    "winrt-Windows.Media.Ocr", "winrt-Windows.Graphics.Imaging", "winrt-Windows.Globalization",
    "winrt-Windows.Foundation", "winrt-Windows.Storage.Streams",
]


UPDATE = "--update" in sys.argv
NO_WINDOW = 0x08000000 if (UPDATE and os.name == "nt") else 0   # при автообновлении — без чёрных окон


def run(cmd):
    if UPDATE:   # вывод pip и PowerShell — тоже в update.log
        sys.stdout.flush()
        return subprocess.run(cmd, creationflags=NO_WINDOW, stdout=sys.stdout, stderr=subprocess.STDOUT)
    return subprocess.run(cmd)


def wait_pid(pid, timeout=60):
    """Подождать, пока старая копия программы закроется (иначе файлы могут быть заняты)."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
        if h:
            k.WaitForSingleObject(h, int(timeout * 1000))
            k.CloseHandle(h)
    except Exception:
        import time
        time.sleep(3)


def step(text):
    print(f"\n=== {text}")


def main():
    print("Установка AAC Translator")
    print(f"Папка программы: {TARGET}")

    step("1/4 Копирую файлы")
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "tests").mkdir(exist_ok=True)
    for name in ("aac_translator.py", "start_with_console.bat", "README.txt", "icon.ico", "icon_22.png", "logo.svg",
                 "install_silero.py", "install_silero.bat"):
        if (HERE / name).exists() and HERE != TARGET:
            shutil.copy2(HERE / name, TARGET / name)
            print("  ", name)
    for f in (HERE / "tests").glob("*.py"):
        if HERE != TARGET:
            shutil.copy2(f, TARGET / "tests" / f.name)
            print("   tests\\" + f.name)
    # сама программа — папка aac (модули). Старую папку заменяем целиком, чтобы не остались устаревшие файлы.
    if (HERE / "aac").is_dir() and HERE != TARGET:
        if (TARGET / "aac").exists():
            shutil.rmtree(TARGET / "aac")
        shutil.copytree(HERE / "aac", TARGET / "aac", ignore=shutil.ignore_patterns("__pycache__"))
        print("   aac\\  (" + str(len(list((TARGET / "aac").glob("*.py")))) + " модулей)")

    step("2/4 Переношу ваши настройки")
    if (TARGET / SETTINGS).exists():
        print("   Настройки уже есть в папке программы — оставляю их.")
    elif (DOWNLOADS / SETTINGS).exists():
        shutil.copy2(DOWNLOADS / SETTINGS, TARGET / SETTINGS)
        print("   Перенёс области, клавиши, положение окон и выбор переводчика из «Загрузок».")
    else:
        print("   Старых настроек не нашёл — начнёте с чистого листа.")

    step("3/4 Устанавливаю библиотеки (может занять минуту)")
    r = run([sys.executable, "-m", "pip", "install", *([] if UPDATE else ["--upgrade"]), "--disable-pip-version-check", *PACKAGES])
    if r.returncode != 0:
        print("   ! Не все библиотеки установились. Программа может не запуститься — пришлите текст ошибки.")
    # нейроголоса для озвучки — отдельно: если не встанут, программа всё равно работает (голос Windows)
    r = run([sys.executable, "-m", "pip", "install", *([] if UPDATE else ["--upgrade"]), "--disable-pip-version-check", "edge-tts"])
    if r.returncode != 0:
        print("   ! Нейроголоса (edge-tts) не установились — озвучка будет голосом Windows.")
    # если стоят офлайн-голоса Silero (PyTorch) — ставим и расстановку ударений для доп. голосов
    try:
        import importlib.util
        has_torch = importlib.util.find_spec("torch") is not None
    except Exception:
        has_torch = False
    if has_torch:
        r = run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "silero-stress"])
        if r.returncode != 0:
            print("   ! Доп. голоса Silero (silero-stress) не установились — останутся основные голоса.")

    step("4/4 Создаю ярлыки")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = TARGET / "aac_translator.py"
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
    $lnk = $ws.CreateShortcut((Join-Path $dir 'AAC Translator.lnk'))
    $lnk.TargetPath = '{pythonw}'
    $lnk.Arguments = '"{script}"'
    $lnk.WorkingDirectory = '{TARGET}'
    $lnk.IconLocation = '{TARGET / "icon.ico"},0'
    $lnk.Description = 'Переводчик субтитров для ArcheAge Chronicles'
    $lnk.Save()
    Write-Output ('   ' + $lnk.FullName)
}}
"""
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode()
    r = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded])
    if r.returncode != 0:
        print("   ! Ярлыки создать не удалось. Запускайте файл start_with_console.bat в папке программы.")

    if UPDATE:
        print("\nОбновление установлено, запускаю программу.")
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([str(pythonw), str(script)], cwd=str(TARGET), creationflags=flags, close_fds=True)
        return
    # старые файлы в «Загрузках»
    old = sorted(p.name for p in DOWNLOADS.glob("aac_translator*.py")) + \
        [n for n in ("start_translator.bat", "groq_test.py", "mistral_test.py", SETTINGS)
         if (DOWNLOADS / n).exists()]
    print("\nГотово! Запускайте переводчик ярлыком «AAC Translator» на рабочем столе или в меню «Пуск».")
    print(f"Папка программы: {TARGET}")
    if old:
        print("\nСтарые файлы в «Загрузках» больше не нужны, их можно удалить:")
        for n in old:
            print("   ", n)
    print("\nКлючи (setx ...) переустанавливать не нужно — они хранятся в Windows, а не в файлах.")
    print("Проверить, что всё в порядке:  py tests\\test_translator.py  (в папке программы)")
    os.startfile(TARGET)  # открыть папку программы


if __name__ == "__main__":
    if UPDATE:
        # тихий режим: всё пишем в update.log в папке программы
        TARGET.mkdir(parents=True, exist_ok=True)
        log = open(TARGET / "update.log", "w", encoding="utf-8")
        sys.stdout = sys.stderr = log
        if "--wait-pid" in sys.argv:
            wait_pid(sys.argv[sys.argv.index("--wait-pid") + 1])
        try:
            main()
        except Exception as e:
            print("\n! Ошибка обновления:", repr(e))
            # программа должна запуститься в любом случае — хотя бы старая версия
            try:
                pw = Path(sys.executable).with_name("pythonw.exe")
                subprocess.Popen([str(pw if pw.exists() else sys.executable), str(TARGET / "aac_translator.py")],
                                 cwd=str(TARGET), creationflags=0x00000008 if os.name == "nt" else 0)
            except Exception:
                pass
        log.close()
    else:
        try:
            main()
        except Exception as e:
            print("\n! Ошибка установки:", repr(e))
        input("\nНажмите Enter, чтобы закрыть...")
