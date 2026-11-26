from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from .errors import LLMError

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
# Free-tier Gemini limits are per minute, so a 429 needs a long pause.
RATE_LIMIT_DEFAULT_WAIT = 30.0
MAX_WAIT_SECONDS = 90.0


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 180,
        max_retries: int = 5,
        sleep=time.sleep,
    ) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY не задан. Создайте .env на основе .env.example и впишите ключ.")
        if max_retries < 1:
            raise ValueError("GEMINI_MAX_RETRIES must be at least 1")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self._sleep = sleep

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

        last_error = "неизвестная ошибка"
        for attempt in range(1, self.max_retries + 1):
            is_last = attempt == self.max_retries
            try:
                response = self.session.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": self.api_key},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = f"сетевая ошибка: {exc}"
                if not is_last:
                    self._sleep(_backoff(attempt))
                continue

            if response.status_code in RETRYABLE_STATUSES:
                last_error = f"HTTP {response.status_code}: {_error_message(response)}"
                if not is_last:
                    wait = _retry_after(response) if response.status_code == 429 else None
                    if response.status_code == 429 and wait is None:
                        wait = RATE_LIMIT_DEFAULT_WAIT
                    wait = min(wait if wait is not None else _backoff(attempt), MAX_WAIT_SECONDS)
                    print(f"    Gemini: {last_error}. Повтор через {wait:.0f} с ({attempt}/{self.max_retries})", flush=True)
                    self._sleep(wait)
                continue

            if response.status_code >= 400:
                # 400/401/403/404 will not fix themselves: fail fast with the API's reason.
                raise LLMError(
                    f"Gemini API вернул HTTP {response.status_code}: {_error_message(response)}. "
                    "Проверьте GEMINI_API_KEY и имя модели GEMINI_MODEL."
                )

            try:
                return _parse_gemini_json(response.json())
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = f"некорректный JSON в ответе модели: {exc}"
                if not is_last:
                    self._sleep(_backoff(attempt))
                continue

        raise LLMError(f"Gemini API не вернул корректный ответ после {self.max_retries} попыток: {last_error}")


def _backoff(attempt: int) -> float:
    return float(min(2 ** attempt, 30))


def _error_message(response) -> str:
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message")
        if message:
            return str(message)[:300]
    except ValueError:
        pass
    return (response.text or "").strip()[:300] or "без описания"


def _retry_after(response) -> float | None:
    header = response.headers.get("Retry-After") if response.headers else None
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        return None
    for detail in details or []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", delay.strip())
            if match:
                return float(match.group(1)) + 1.0
    return None


def _parse_gemini_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback", {})
        raise LLMError(f"Gemini не вернул результат (возможно, сработал фильтр). Детали: {feedback}")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not raw:
        raise ValueError(f"пустой ответ, finishReason={candidate.get('finishReason')}")
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("корневое значение JSON не является объектом")
    return value
