import json
import os

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

client = None

if OpenAI is not None and DEEPSEEK_API_KEY:
    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )


def classify_with_deepseek(message: str):
    if OpenAI is None:
        raise RuntimeError("openai package is not installed")

    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    if client is None:
        raise RuntimeError("DeepSeek client is not initialized")

    prompt = f"""
Classify this enterprise request.

Allowed intents:
- odoo
- support
- knowledge
- development
- security
- server
- general

Return JSON only with this exact structure:
{{
  "intent": "one_allowed_intent",
  "confidence": 0.0,
  "requires_approval": false
}}

Request:
{message}
"""

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are an enterprise intent classifier. Return valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    allowed_intents = {
        "odoo",
        "support",
        "knowledge",
        "development",
        "security",
        "server",
        "general",
    }

    intent = data.get("intent", "general")

    if intent not in allowed_intents:
        intent = "general"

    return {
        "intent": intent,
        "confidence": float(data.get("confidence", 0.7)),
        "requires_approval": bool(data.get("requires_approval", False)),
        "classifier_source": "deepseek",
        "classifier_error": None,
    }