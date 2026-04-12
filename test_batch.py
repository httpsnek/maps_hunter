import requests

MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/9jyok9g8fqrwsdpioxlo0vvjrczylivu"

payload = {
    "batch_id": "req_777",
    "leads": [
        {
            "name": "Barbershop u Nikity",
            "category": "barbershop",
            "rating": 4.9,
            "reviews_summary": "Great haircut, nice atmosphere, professional staff."
        },
        {
            "name": "Kadeřnictví Jana",
            "category": "hair salon",
            "rating": 4,
            "reviews_summary": "Okay service, but a bit slow and expensive."
        },
        {
            "name": "Nový Salon",
            "category": "beauty salon",
            "rating": 3,
            "reviews_summary": ""
        }
    ]
}

print("Sending...")
response = requests.post(MAKE_WEBHOOK_URL, json=payload)

if response.status_code == 200:
    print("Succesfully")
else:
    print(f"Error: {response.status_code}")