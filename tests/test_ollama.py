import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.llm.ollama import OllamaProvider


def test_cloud_model_schema_repair_and_no_credentials(monkeypatch):
    monkeypatch.setattr(Settings, "require_cloud", lambda self: None)
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers
        assert body["stream"] is False and body["think"] is False
        assert body["format"]["type"] == "object"
        value = "{}" if len(calls) < 3 else '{"topic":"Почему звёзды мерцают","category":"космос"}'
        return httpx.Response(200, json={"response": value})

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await OllamaProvider(Settings(_env_file=None), client).generate_topic([])

    assert asyncio.run(check()).category == "космос"
    assert len(calls) == 3


def test_cloud_model_cannot_run_locally():
    async def check():
        async with httpx.AsyncClient() as client:
            await OllamaProvider(Settings(_env_file=None), client).generate_topic([])

    with pytest.raises(ValueError, match="cloud-only"):
        asyncio.run(check())


def test_ollama_does_not_require_gemini():
    Settings(_env_file=None, llm_provider="ollama", pexels_api_key="test").require_generation_keys()
