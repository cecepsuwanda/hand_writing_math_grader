import json
from pathlib import Path

import httpx
import pytest

from app.exceptions import OllamaTimeoutError, OllamaUnavailableError
from app.services.vision.ollama_client import OllamaClient


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "page.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


def test_generate_with_image_success(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content.decode())
        assert body["model"] == "vision-test"
        assert body["format"] == "json"
        assert body["stream"] is False
        assert body["messages"][0]["images"]
        return httpx.Response(
            200,
            json={"message": {"content": '{"page_number": 1, "questions": []}'}},
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=5,
        max_retries=0,
        transport=transport,
    )
    content = client.generate_with_image("prompt", _image(tmp_path), "vision-test")
    assert "page_number" in content


def test_generate_retries_on_timeout_then_succeeds(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(
            200,
            json={"message": {"content": '{"ok": true}'}},
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=1,
        max_retries=1,
        transport=transport,
    )
    content = client.generate_with_image("prompt", _image(tmp_path), "vision-test")
    assert content == '{"ok": true}'
    assert calls["n"] == 2


def test_generate_timeout_exhausted(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=1,
        max_retries=1,
        transport=transport,
    )
    with pytest.raises(OllamaTimeoutError):
        client.generate_with_image("prompt", _image(tmp_path), "vision-test")


def test_generate_connection_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://ollama.test",
        timeout_seconds=1,
        max_retries=0,
        transport=transport,
    )
    with pytest.raises(OllamaUnavailableError):
        client.generate_with_image("prompt", _image(tmp_path), "vision-test")
