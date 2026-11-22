"""Установка офлайн-голосов Silero для AAC Translator.

1) ставит PyTorch (версия для процессора, ~200 МБ загрузки, ~1 ГБ на диске);
2) скачивает модель русских голосов (~100 МБ) в папку models;
3) говорит проверочную фразу и показывает, сколько занял синтез.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def pip(*args):
    return subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade",
                           "--disable-pip-version-check", *args]).returncode == 0


def main():
    print("Установка офлайн-голосов Silero\n")
    print("=== 1/3 PyTorch (может занять несколько минут)")
    try:
        import torch  # noqa: F401
        print("   PyTorch уже установлен.")
    except Exception:
        ok = pip("torch", "--index-url", "https://download.pytorch.org/whl/cpu")
        if not ok:
            print("   Версия для процессора не встала, пробую обычную…")
            ok = pip("torch")
        if not ok:
            print("\n   ! PyTorch не установился. Пришлите текст ошибки выше.")
            print(f"   (Python {sys.version.split()[0]})")
            return 1

    pip("numpy", "silero-stress")   # numpy нужен модели v5; silero-stress — ударения для доп. голосов
    print("\n=== 2/3 Модель голосов (~100 МБ, один раз)")
    from aac import tts_silero
    t0 = time.time()
    try:
        tts_silero.load()
    except Exception as e:
        print(f"\n   ! Не удалось загрузить модель: {e}")
        return 1
    print(f"   Готово за {time.time() - t0:.1f} с")

    print("\n=== 3/3 Проверка голоса")
    path = os.path.join(tts_silero.MODEL_DIR, "test.wav")
    for voice, label in tts_silero.VOICES[:1] + tts_silero.VOICES[3:4]:
        t0 = time.time()
        tts_silero.synth_to_wav("Привет! Так звучит офлайн-голос для перевода субтитров.", path, voice)
        print(f"   {label}: синтез {time.time() - t0:.2f} с")
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
        except Exception:
            pass
    print("\nВсё готово. В программе: ⚙ Настройки → Голоса → «Silero».")
    return 0


if __name__ == "__main__":
    code = main()
    input("\nНажмите Enter, чтобы закрыть…")
    sys.exit(code)
