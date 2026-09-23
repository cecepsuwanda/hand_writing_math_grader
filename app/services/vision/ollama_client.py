"""HTTP client for Ollama vision and chat APIs."""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.exceptions import OllamaTimeoutError, OllamaUnavailableError

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)
        self._transport = transport

    def generate(self, prompt: str, model: str) -> str:
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            # Gemma4+/thinking models can exhaust the output budget on
            # reasoning and leave message.content empty; force final answer.
            "think": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }
        return self._chat(payload, model)

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        image_path = Path(image_path)
        if not image_path.is_file():
            raise OllamaUnavailableError(f"image not found: {image_path}")

        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "think": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
        }
        return self._chat(payload, model)

    def _chat(self, payload: dict[str, Any], model: str) -> str:
        url = f"{self._base_url}/api/chat"
        attempts = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                with httpx.Client(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = client.post(url, json=payload)
                elapsed = time.perf_counter() - started
                logger.info(
                    "ollama chat model=%s attempt=%s status=%s elapsed=%.2fs",
                    model,
                    attempt,
                    response.status_code,
                    elapsed,
                )
                if response.status_code >= 500:
                    raise OllamaUnavailableError(
                        f"server error {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    raise OllamaUnavailableError(
                        f"request failed {response.status_code}: {response.text[:200]}"
                    )
                data = response.json()
                content = self._message_text(data)
                if not content.strip():
                    done_reason = data.get("done_reason")
                    raise OllamaUnavailableError(
                        "empty message content from Ollama"
                        + (f" (done_reason={done_reason})" if done_reason else "")
                    )
                return content
            except httpx.TimeoutException as exc:
                last_error = OllamaTimeoutError(model, self._timeout_seconds)
                logger.warning(
                    "ollama timeout model=%s attempt=%s/%s",
                    model,
                    attempt,
                    attempts,
                )
                if attempt >= attempts:
                    raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = OllamaUnavailableError(str(exc))
                logger.warning(
                    "ollama http error model=%s attempt=%s/%s error=%s",
                    model,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt >= attempts:
                    raise last_error from exc
            except OllamaUnavailableError as exc:
                last_error = exc
                if attempt >= attempts:
                    raise
                logger.warning(
                    "ollama unavailable model=%s attempt=%s/%s error=%s",
                    model,
                    attempt,
                    attempts,
                    exc,
                )
            time.sleep(min(2 ** (attempt - 1), 8))

        if isinstance(last_error, Exception):
            raise last_error
        raise OllamaUnavailableError("unknown Ollama failure")

    @staticmethod
    def _message_text(data: dict[str, Any]) -> str:
        """Prefer assistant content; fall back to thinking if content is empty.

        Some vision+think responses spend the whole token budget on
        ``message.thinking`` and leave ``content`` blank (Ollama #16184).
        """
        message = data.get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking.strip():
            logger.warning(
                "ollama content empty; using message.thinking (%s chars)",
                len(thinking),
            )
            return thinking
        return content if isinstance(content, str) else ""
