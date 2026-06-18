import json
import os

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - requirements.txt should install this
    OpenAI = None


load_dotenv()

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT_SECONDS = 20.0


def _get_api_key() -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return None

    return api_key.strip() or None


def _get_model(model: str | None = None) -> str:
    return model or os.getenv("OPENAI_DEFAULT_MODEL") or DEFAULT_MODEL


def _get_timeout() -> float:
    raw_timeout = os.getenv("OPENAI_TIMEOUT_SECONDS")

    if not raw_timeout:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        return float(raw_timeout)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def is_openai_configured() -> bool:
    return bool(_get_api_key()) and OpenAI is not None


def get_openai_status() -> dict:
    configured = is_openai_configured()

    return {
        "configured": configured,
        "model": _get_model(),
        "status": "ready" if configured else "missing_api_key",
    }


def _extract_text(response) -> str:
    output_text = getattr(response, "output_text", None)

    if output_text:
        return output_text

    output = getattr(response, "output", None)

    if not output:
        return ""

    chunks = []

    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)

            if text:
                chunks.append(text)

    return "\n".join(chunks).strip()


def generate_response(
    prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    selected_model = _get_model(model)

    if not _get_api_key() or OpenAI is None:
        return {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "content": "",
            "error": "missing_api_key",
        }

    try:
        client = OpenAI(
            api_key=_get_api_key(),
            timeout=_get_timeout(),
        )

        request = {
            "model": selected_model,
            "input": prompt,
        }

        if system_prompt:
            request["instructions"] = system_prompt

        response = client.responses.create(**request)
        content = _extract_text(response)

        return {
            "provider": "openai",
            "model": selected_model,
            "success": True,
            "content": content,
            "error": None,
        }

    except Exception as error:
        return {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "content": "",
            "error": error.__class__.__name__,
        }


def generate_structured_response(
    prompt: str,
    schema: dict,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    selected_model = _get_model(model)

    if not _get_api_key() or OpenAI is None:
        return {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "content": "",
            "parsed": None,
            "error": "missing_api_key",
        }

    try:
        client = OpenAI(
            api_key=_get_api_key(),
            timeout=_get_timeout(),
        )

        request = {
            "model": selected_model,
            "input": prompt,
            "text": {
                "format": schema,
            },
        }

        if system_prompt:
            request["instructions"] = system_prompt

        response = client.responses.create(**request)
        content = _extract_text(response)
        parsed = json.loads(content) if content else None

        return {
            "provider": "openai",
            "model": selected_model,
            "success": isinstance(parsed, dict),
            "content": content,
            "parsed": parsed if isinstance(parsed, dict) else None,
            "error": None if isinstance(parsed, dict) else "invalid_json",
        }

    except Exception as error:
        return {
            "provider": "openai",
            "model": selected_model,
            "success": False,
            "content": "",
            "parsed": None,
            "error": error.__class__.__name__,
        }


def ask_gpt(prompt: str):
    result = generate_response(prompt)

    if result["success"]:
        return result["content"]

    return "OpenAI response unavailable."
