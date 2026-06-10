import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print("API key loaded:", bool(api_key))
print("API key starts with:", api_key[:8] if api_key else None)

genai.configure(api_key=api_key)

model = genai.GenerativeModel("models/gemini-2.0-flash")

response = model.generate_content("Return only this JSON: {\"ok\": true}")

print(response.text)