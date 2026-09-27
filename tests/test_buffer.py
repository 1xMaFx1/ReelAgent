import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from app.config import Settings
from app.core.models import Metadata
from app.publishers.buffer import BufferYouTubePublisher


def test_schedule_matches_channel_and_never_posts_immediately(tmp_path, monkeypatch):
    target = datetime(2026, 9, 27, 5, tzinfo=timezone.utc)
    monkeypatch.setattr("app.publishers.buffer.publication_time", lambda *args: target)
    mutations = []

    async def upload(*args):
        return "https://media.example/reel.mp4"

    monkeypatch.setattr("app.storage.cloudinary.CloudinaryStorageProvider.upload", upload)

    def handler(request):
        payload = json.loads(request.content)
        if "mutation" not in payload["query"]:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "channel": {
                            "service": "youtube",
                            "serviceId": "authorized-channel",
                            "isDisconnected": False,
                            "isLocked": False,
                            "isQueuePaused": False,
                        }
                    }
                },
            )
        data = payload["variables"]["input"]
        mutations.append(data)
        return httpx.Response(
            200,
            json={
                "data": {
                    "createPost": {
                        "__typename": "PostActionSuccess",
                        "post": {
                            "id": "post-1",
                            "dueAt": target.isoformat(),
                            "status": "buffer",
                            "schedulingType": "automatic",
                        },
                    }
                }
            },
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            publisher = BufferYouTubePublisher(
                Settings(
                    _env_file=None,
                    buffer_api_key="fake",
                    buffer_channel_id="buffer-id",
                    youtube_channel_id="authorized-channel",
                ),
                client,
            )
            return await publisher.publish(
                tmp_path / "2026-09-27/reel.mp4",
                Metadata(
                    title="16 рассветов за день?",
                    description="космос, МКС, рассвет",
                    hashtags=["#космос"],
                ),
            )

    assert asyncio.run(check()) == "buffer:post-1"
    assert len(mutations) == 1
    assert mutations[0]["mode"] == "customScheduled"
    assert mutations[0]["dueAt"] == target.isoformat()
    assert mutations[0]["text"] == "космос, МКС, рассвет\n\n#космос"
    assert mutations[0]["metadata"]["youtube"]["privacy"] == "public"


def test_wrong_channel_blocks_before_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.publishers.buffer.publication_time", lambda *args: datetime.now(timezone.utc)
    )

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "channel": {
                        "service": "youtube",
                        "serviceId": "another-channel",
                        "isDisconnected": False,
                        "isLocked": False,
                        "isQueuePaused": False,
                    }
                }
            },
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await BufferYouTubePublisher(Settings(_env_file=None), client).publish(
                tmp_path / "reel.mp4",
                Metadata(title="Title", description="keywords only", hashtags=["#test"]),
            )

    with pytest.raises(ValueError, match="authorized YouTube"):
        asyncio.run(check())
