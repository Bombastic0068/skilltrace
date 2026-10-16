import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Free-tier Gemini Flash models. Try these in order if one is unavailable.
GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
)
MAX_ROUNDS = 3
RETRY_WAIT_SECONDS = 4


def _client() -> genai.Client:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is missing. Put it in your .env file.")
    return genai.Client(api_key=api_key)


def _parse_json(text: str):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def generate_json(prompt: str):
    """Call Gemini and parse a JSON response. Retries on failure."""
    client = _client()
    last_error: Exception | None = None

    for round_number in range(1, MAX_ROUNDS + 1):
        for model in GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                )
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError(f"{model} returned an empty response.")
                return _parse_json(text)
            except Exception as error:
                last_error = error
        time.sleep(RETRY_WAIT_SECONDS * round_number)

    raise RuntimeError(f"Gemini API failed after retries: {last_error}") from last_error
