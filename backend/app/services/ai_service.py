"""
AI service — supports Ollama (local) and Google Gemini.

Provider is selected by AI_PROVIDER in .env:
  AI_PROVIDER=gemini   → Google Gemini REST API (recommended, fast)
  AI_PROVIDER=ollama   → local Ollama (default if not set)

Gemini setup:
  AI_PROVIDER=gemini
  AI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent
  AI_MODEL=gemini-2.5-flash
  AI_API_KEY=<your key>

Ollama setup:
  AI_PROVIDER=ollama   (or leave AI_PROVIDER unset)
  AI_ENDPOINT=http://localhost:11434/api/generate
  AI_MODEL=llama3
"""
import json
import logging
import re
import httpx
from app.config import settings

log = logging.getLogger("aurum.ai")


def _provider() -> str:
    """Return 'gemini' or 'ollama' based on config."""
    p = getattr(settings, "AI_PROVIDER", "") or ""
    if p.lower() == "gemini":
        return "gemini"
    endpoint = settings.AI_ENDPOINT or ""
    if "googleapis" in endpoint or "generativelanguage" in endpoint:
        return "gemini"
    return "ollama"


async def call_ai(prompt: str) -> str:
    """Call the configured AI model and return the raw text response."""
    provider = _provider()

    if provider == "gemini":
        return await _call_gemini(prompt)
    else:
        return await _call_ollama(prompt)


async def _call_gemini(prompt: str) -> str:
    """Call Google Gemini REST API."""
    api_key  = settings.AI_API_KEY
    endpoint = settings.AI_ENDPOINT  # e.g. .../gemini-2.5-flash:generateContent

    if not api_key:
        raise RuntimeError("AI_API_KEY is not set. Add it to backend/.env")

    url = f"{endpoint}?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are a data engineering assistant. "
                            "You always respond with valid JSON only. "
                            "No markdown fences, no explanation, no extra text — just the JSON object.\n\n"
                            + prompt
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature":     0.1,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",   # forces JSON output
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload)
        if not r.is_success:
            raise RuntimeError(
                f"Gemini API error {r.status_code}: {r.text[:400]}"
            )
        data = r.json()

    # Extract text from Gemini response structure
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response structure: {data}") from e


async def _call_ollama(prompt: str) -> str:
    """Call local Ollama via /api/chat."""
    endpoint = settings.AI_ENDPOINT
    model    = settings.AI_MODEL

    chat_endpoint = endpoint.replace("/api/generate", "/api/chat").replace("/api/tags", "/api/chat")
    if not chat_endpoint.endswith("/api/chat"):
        chat_endpoint = chat_endpoint.rstrip("/") + "/api/chat"

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            chat_endpoint,
            json={
                "model":  model,
                "format": "json",
                "stream": False,
                "messages": [
                    {
                        "role":    "system",
                        "content": "You are a data engineering assistant. You always respond with valid JSON only. No markdown, no explanation, no extra text — just the JSON object.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": 0.1,
                    "num_predict": 2048,
                },
            },
        )
        r.raise_for_status()
        data = r.json()

    return data.get("message", {}).get("content", "")


async def call_ai_json(prompt: str) -> dict:
    """
    Call the AI and parse JSON from the response.
    Falls back to regex extraction, then retries once with a correction prompt.
    """
    try:
        raw = await call_ai(prompt)
    except Exception as e:
        raise RuntimeError(
            f"AI model unavailable: {e}. "
            "Check AI_PROVIDER and AI_API_KEY in backend/.env"
        ) from e

    log.debug(f"[ai] raw response (first 300): {raw[:300]}")

    parsed = _try_parse_json(raw)
    if parsed is not None:
        return parsed

    log.warning("[ai] first response was not valid JSON, retrying with correction prompt")
    correction = (
        "Your previous response was not valid JSON. "
        "Return ONLY a valid JSON object with no markdown, no explanation, no extra text.\n\n"
        f"Original request:\n{prompt}"
    )

    try:
        raw2 = await call_ai(correction)
    except Exception as e:
        raise RuntimeError(f"AI retry failed: {e}") from e

    log.debug(f"[ai] retry response (first 300): {raw2[:300]}")

    parsed2 = _try_parse_json(raw2)
    if parsed2 is not None:
        return parsed2

    raise ValueError(
        f"AI did not return valid JSON after two attempts.\n"
        f"Last response (first 500 chars):\n{raw2[:500]}"
    )


def _try_parse_json(text: str) -> dict | None:
    """Try several strategies to extract JSON from a model response."""
    if not text or not text.strip():
        return None

    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*",     "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", cleaned)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None
