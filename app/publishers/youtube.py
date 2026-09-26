import asyncio
from pathlib import Path

import httpx

from app.config import Settings
from app.core.models import Metadata
from app.utils.retry import request, transient


class YouTubePublisher:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    @property
    def configured(self) -> bool:
        s = self.settings
        return all(
            x.get_secret_value()
            for x in (s.youtube_client_id, s.youtube_client_secret, s.youtube_refresh_token)
        )

    async def publish(self, path: Path, metadata: Metadata) -> str:
        s = self.settings
        token = await request(
            self.client,
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": s.youtube_client_id.get_secret_value(),
                "client_secret": s.youtube_client_secret.get_secret_value(),
                "refresh_token": s.youtube_refresh_token.get_secret_value(),
                "grant_type": "refresh_token",
            },
        )
        headers = {"Authorization": "Bearer " + token.json()["access_token"]}
        size = path.stat().st_size
        response = await request(
            self.client,
            "POST",
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                **headers,
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": "video/mp4",
            },
            json={
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description + "\n\n" + " ".join(metadata.hashtags),
                    "tags": [tag.lstrip("#") for tag in metadata.hashtags],
                    "categoryId": "28",
                },
                "status": {
                    "privacyStatus": s.youtube_privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            },
        )
        location = response.headers["Location"]
        offset = 0
        # Resume the same upload session after an ambiguous response; never create a second video.
        for attempt in range(3):
            try:
                if attempt:
                    status = await self.client.put(
                        location,
                        headers={
                            **headers,
                            "Content-Length": "0",
                            "Content-Range": f"bytes */{size}",
                        },
                        content=b"",
                    )
                    if status.status_code in (200, 201):
                        return status.json()["id"]
                    if status.status_code != 308:
                        status.raise_for_status()
                        raise RuntimeError("Unexpected YouTube upload status")
                    received = status.headers.get("Range")
                    offset = int(received.rsplit("-", 1)[1]) + 1 if received else 0

                async def chunks():
                    with path.open("rb") as handle:
                        handle.seek(offset)
                        while chunk := handle.read(1024 * 1024):
                            yield chunk

                result = await self.client.put(
                    location,
                    headers={
                        **headers,
                        "Content-Type": "video/mp4",
                        "Content-Length": str(size - offset),
                        "Content-Range": f"bytes {offset}-{size - 1}/{size}",
                    },
                    content=chunks(),
                    timeout=300,
                )
                if result.status_code in (200, 201):
                    return result.json()["id"]
                if result.status_code != 308:
                    result.raise_for_status()
            except httpx.HTTPError as error:
                if not transient(error):
                    raise
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        raise RuntimeError(
            "YouTube upload uncertain after 3 attempts; check Studio before retrying"
        )
