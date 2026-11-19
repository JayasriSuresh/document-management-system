import os
from groq import Groq
from app.config import settings

client = Groq(api_key=settings.GROQ_API_KEY)
models = client.models.list()
for m in models.data:
    if 'vision' in m.id.lower() or 'llama' in m.id.lower():
        print(m.id)
