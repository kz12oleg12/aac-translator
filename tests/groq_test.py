"""
Проверка ключа Groq: какие модели с картинками отвечают и какие у них лимиты.
Запуск:  py groq_test.py
Ключ берётся из переменной окружения GROQ_API_KEY (как в переводчике).
"""
import base64
import io
import os
import time

import requests
from PIL import Image, ImageDraw

KEY = os.environ.get("GROQ_API_KEY", "")
URL = "https://api.groq.com/openai/v1/chat/completions"
CANDIDATES = ["qwen/qwen3.8-27b"]

if not KEY:
    print('Ключ не найден. Выполните: setx GROQ_API_KEY "ваш_ключ" и откройте командную строку заново.')
    input("Enter — закрыть...")
    raise SystemExit

print(f"Ключ найден: {KEY[:4]}...{KEY[-4:]}\n")
headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

img = Image.new("RGB", (420, 60), "black")
ImageDraw.Draw(img).text((10, 20), "Where do the pirates gather?", fill="white")
buf = io.BytesIO()
img.save(buf, format="JPEG")
img_b64 = base64.b64encode(buf.getvalue()).decode()

# Список моделей аккаунта
r = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=30)
print(f"--- список моделей: код {r.status_code}")
if r.status_code == 200:
    ids = sorted(m["id"] for m in r.json().get("data", []))
    print("    " + ", ".join(ids))
    # пробуем все модели, которые могут понимать картинки (кроме речи и фильтров)
    skip = ("whisper", "orpheus", "guard", "safeguard", "allam")
    extra = [m for m in ids if not any(w in m for w in skip) and m not in CANDIDATES]
    CANDIDATES += extra
else:
    print("    сервер:", r.text[:300])
print()

for model in CANDIDATES:
    body = {"model": model, "max_tokens": 80, "temperature": 0.2, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Переведи текст на картинке на русский. Выведи только перевод."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}]}
    if "qwen" in model:
        body["reasoning_effort"] = "none"
    t0 = time.time()
    r = requests.post(URL, headers=headers, json=body, timeout=60)
    if r.status_code == 400 and "reasoning" in r.text.lower():
        body.pop("reasoning_effort")
        r = requests.post(URL, headers=headers, json=body, timeout=60)
    print(f"--- {model}: код {r.status_code} за {time.time() - t0:.1f} с")
    for k, v in r.headers.items():
        if "ratelimit" in k.lower() or k.lower() == "retry-after":
            print(f"    {k}: {v}")
    if r.status_code == 200:
        print("    перевод:", (r.json()["choices"][0]["message"].get("content") or "")[:150].replace("\n", " "))
    else:
        print("    сервер:", r.text[:300])
    print()
    time.sleep(1.5)

input("Готово. Нажмите Enter, чтобы закрыть...")
