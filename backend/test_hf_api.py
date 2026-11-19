import requests
import base64

API_URL = "https://api-inference.huggingface.co/models/microsoft/Florence-2-base"

with open("storage/documents/133b4d91-8d8c-4733-8c03-67fe8c7f7de1.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "inputs": {
        "image": img_b64,
        "text": "<OCR>"
    }
}
response = requests.post(API_URL, json=payload)
print(response.json())
