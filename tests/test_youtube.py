import asyncio

import httpx

from app.config import Settings
from app.core.models import Metadata
from app.publishers.youtube import YouTubePublisher


def test_lost_upload_response_resumes_same_session(tmp_path, monkeypatch):
    calls = []

    async def no_sleep(*args):
        pass

    monkeypatch.setattr("app.publishers.youtube.asyncio.sleep", no_sleep)
    path = tmp_path / "reel.mp4"
    path.write_bytes(b"test-video")

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "test"})
        if request.method == "POST":
            return httpx.Response(200, headers={"Location": "https://www.googleapis.com/session"})
        if request.headers.get("Content-Range", "").startswith("bytes */"):
            return httpx.Response(200, json={"id": "saved-id"})
        return httpx.Response(503)

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await YouTubePublisher(Settings(_env_file=None), client).publish(
                path,
                Metadata(title="Test title", description="Test description", hashtags=["#space"]),
            )

    assert asyncio.run(check()) == "saved-id"
    assert sum("upload/youtube" in url for url in calls) == 1
