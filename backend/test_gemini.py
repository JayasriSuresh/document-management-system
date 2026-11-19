import os
from google import genai
from app.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)
for model in client.models.list():
    if 'flash' in model.name:
        print(model.name)
