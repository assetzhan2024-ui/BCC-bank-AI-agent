from __future__ import annotations

import json
import time
from typing import Any

import requests

from .errors import LLMError


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 180,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY не задан. Создайте .env на основе .env.example.")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": self.api_key},
                    timeout=self.timeout,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                response.raise_for_status()
                return _parse_gemini_json(response.json())
            except (requests.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
        raise LLMError(f"Gemini API не вернул корректный JSON после {self.max_retries} попыток: {last_error}")


def _parse_gemini_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback", {})
        raise LLMError(f"Gemini не вернул результат. Детали: {feedback}")
    parts = candidates[0]["content"]["parts"]
    raw = "".join(part.get("text", "") for part in parts).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise LLMError("Gemini вернул JSON, но корневое значение не является объектом.")
    return value
