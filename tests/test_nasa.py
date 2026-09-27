import asyncio

import httpx

from app.config import Settings
from app.core.database import Database
from app.media.nasa import NasaVideoProvider, nasa_url, usable


def test_source_filter_and_history(tmp_path):
    assert nasa_url("https://images-assets.nasa.gov/a.jpg")
    assert not nasa_url("https://nasa.gov.evil.example/a.jpg")
    assert not usable({"data": []})
    assert not usable({"data": [{"nasa_id": "x", "description": "Copyright owner"}]})
    db = Database(tmp_path / "history.db")
    db.add_source("a")
    db.add_source("a")
    assert db.source_ids() == {"a"}
    db.close()
    Settings(llm_provider="ollama", media_provider="nasa").require_generation_keys()


def test_skips_used_story():
    asyncio.run(check_unused_story())


async def check_unused_story():
    items = [
        {"data": [{"nasa_id": key, "title": key, "description": "Source facts. " * 60}]}
        for key in ("used", "fresh")
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"collection": {"items": items}})
        )
    ) as client:
        story = await NasaVideoProvider(Settings(), client).select_story({"used"})
        assert story["id"] == "fresh"
