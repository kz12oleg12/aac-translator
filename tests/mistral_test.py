"""
Проверка ключа Mistral: какие модели отвечают и что говорит сервер о лимитах.
Запуск:  py mistral_test.py
Ключ берётся из переменной окружения MISTRAL_API_KEY (как в переводчике).
"""
import base64
import io
import os
import time

import requests
from PIL import Image, ImageDraw

KEY = os.environ.get("MISTRAL_API_KEY", "")
URL = "https://api.mistral.ai/v1/chat/completions"
MODELS = ["mistral-small-2603", "mistral-small-latest", "mistral-medium-latest", "mistral-large-4"]

if not KEY:
    print("Ключ не найден. Выполните: setx MISTRAL_API_KEY \"ваш_ключ\" и откройте командную строку заново.")
    raise SystemExit

print(f"Ключ найден: {KEY[:4]}...{KEY[-4:]}\n")

# маленькая картинка с английским текстом
img = Image.new("RGB", (400, 60), "black")
ImageDraw.Draw(img).text((10, 20), "Where do the pirates gather?", fill="white")
buf = io.BytesIO()
img.save(buf, format="JPEG")
img_b64 = base64.b64encode(buf.getvalue()).decode()


def show(title, r):
    print(f"--- {title}: код {r.status_code}")
    limits = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"}
    for k, v in limits.items():
        print(f"    {k}: {v}")
    if r.status_code == 200:
        print("    ответ:", r.json()["choices"][0]["message"]["content"][:120].replace("\n", " "))
    else:
        print("    сервер:", r.text[:300])
    print()


headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# 0. Список моделей, доступных ключу
r = requests.get("https://api.mistral.ai/v1/models", headers=headers, timeout=30)
print(f"--- список моделей: код {r.status_code}")
if r.status_code == 200:
    ids = sorted(m["id"] for m in r.json().get("data", []))
    vision = sorted(m["id"] for m in r.json().get("data", [])
                    if (m.get("capabilities") or {}).get("vision"))
    print(f"    всего моделей: {len(ids)}")
    print(f"    понимают картинки: {', '.join(vision) or '—'}")
else:
    print("    сервер:", r.text[:300])
print()

for model in MODELS:
    # 1. Только текст
    body = {"model": model, "max_tokens": 30,
            "messages": [{"role": "user", "content": "Переведи на русский: Hello, traveler!"}]}
    show(f"{model}, только текст", requests.post(URL, headers=headers, json=body, timeout=30))
    time.sleep(1.5)
    # 2. Картинка
    body = {"model": model, "max_tokens": 60, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Переведи текст на картинке на русский."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}]}
    show(f"{model}, с картинкой", requests.post(URL, headers=headers, json=body, timeout=30))
    time.sleep(1.5)

input("Готово. Нажмите Enter, чтобы закрыть...")
