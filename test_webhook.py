import requests
import json

MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/9jyok9g8fqrwsdpioxlo0vvjrczylivu"

sample_lead = {
    "name": "Barbershop u Nikity",
    "category": "barbershop",
    "rating": 4.8,
    "reviews_count": 120,
    "reviews_summary": "Great haircut, nice atmosphere; slightly expensive"
}

print(f"Отправляем лид {sample_lead['name']} в Make...")

response = requests.post(MAKE_WEBHOOK_URL, json=sample_lead)

if response.status_code == 200:
    print("Успешно! Данные улетели в Make.")
else:
    print(f"Ошибка: {response.status_code}")