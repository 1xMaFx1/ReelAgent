import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.core.models import Topic
from app.llm.gemini import GeminiProvider
from app.media.pexels import PexelsVideoProvider


def test_gemini_schema_and_two_repairs(monkeypatch):
    count = 0

    async def no_sleep(*args):
        pass

    monkeypatch.setattr("app.llm.gemini.asyncio.sleep", no_sleep)

    def handler(request):
        nonlocal count
        count += 1
        assert "responseJsonSchema" in json.loads(request.content)["generationConfig"]
        text = "bad json" if count < 3 else '{"topic":"Почему звёзды мерцают","category":"космос"}'
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await GeminiProvider(
                Settings(_env_file=None, gemini_api_key="test"), client
            ).ask("topic", Topic)

    assert asyncio.run(check()).category == "космос"
    assert count == 3


def test_gemini_fails_after_three(monkeypatch):
    count = 0

    async def no_sleep(*args):
        pass

    monkeypatch.setattr("app.llm.gemini.asyncio.sleep", no_sleep)

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={})

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await GeminiProvider(Settings(_env_file=None, gemini_api_key="test"), client).ask(
                "topic", Topic
            )

    with pytest.raises(RuntimeError, match="3 attempts"):
        asyncio.run(check())
    assert count == 3


def test_pexels_unique_photo_fallback(tmp_path):
    def handler(request):
        if "videos/search" in request.url.path:
            return httpx.Response(200, json={"videos": []})
        if request.url.path == "/v1/search":
            return httpx.Response(
                200,
                json={
                    "photos": [
                        {
                            "id": i,
                            "url": "https://example.com/photo",
                            "photographer": "Test",
                            "src": {"large2x": f"https://images.example.com/{i}.jpg"},
                        }
                        for i in (1, 2)
                    ]
                },
            )
        return httpx.Response(200, content=b"photo")

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = PexelsVideoProvider(Settings(_env_file=None), client)
            used = set()
            a = await provider.fetch("stars", tmp_path / "one", used)
            b = await provider.fetch("stars", tmp_path / "two", used)
            assert a.source_id != b.source_id and a.is_image and b.is_image

    asyncio.run(check())
