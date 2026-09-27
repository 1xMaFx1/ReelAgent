import asyncio
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.publishers.buffer_instagram import BufferInstagramPublisher


def test_only_authorized_instagram_and_keywords():
    settings = Settings(_env_file=None, buffer_api_key="test", buffer_channel_id="channel")
    publisher = BufferInstagramPublisher(settings, None)
    calls = []

    async def query(text, variables):
        calls.append(variables)
        if text.startswith("query"):
            return {
                "channel": {
                    "service": "instagram",
                    "name": "mateushstameska",
                    "externalLink": "",
                    "isDisconnected": False,
                    "isLocked": False,
                    "isQueuePaused": False,
                }
            }
        return {
            "createPost": {
                "__typename": "PostActionSuccess",
                "post": {
                    "id": "post",
                    "dueAt": "2026-09-28T05:00:00Z",
                    "status": "buffer",
                    "schedulingType": "automatic",
                },
            }
        }

    publisher.query = query
    meta = {
        "description": "космос, наука",
        "title": "Короткое название",
        "hashtags": ["#космос"],
        "public_video_url": "https://github.com/a/b/releases/download/reel/reel.mp4",
    }
    result = asyncio.run(
        publisher.schedule("2026-09-28-08", meta, datetime(2026, 9, 28, 4, tzinfo=timezone.utc))
    )
    assert result["id"] == "post"
    payload = calls[-1]["input"]
    assert payload["text"] == "космос, наука\n#космос"
    assert payload["dueAt"] == "2026-09-28T05:00:00+00:00"
    assert payload["metadata"]["instagram"]["type"] == "reel"
    assert payload["schedulingType"] == "automatic"
    with pytest.raises(ValueError, match="пропущено"):
        asyncio.run(
            publisher.schedule("2026-09-28-08", meta, datetime(2026, 9, 28, 6, tzinfo=timezone.utc))
        )


def test_wrong_channel_blocked():
    publisher = BufferInstagramPublisher(
        Settings(_env_file=None, buffer_channel_id="channel"), None
    )

    async def query(*args):
        return {
            "channel": {
                "service": "instagram",
                "name": "someone_else",
                "externalLink": "https://instagram.com/other/",
            }
        }

    publisher.query = query
    with pytest.raises(ValueError, match="разрешённому"):
        asyncio.run(publisher.validate_channel())
