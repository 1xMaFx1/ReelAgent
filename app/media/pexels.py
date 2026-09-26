import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.media.base import Media
from app.media.downloader import download
from app.utils.retry import request


class PexelsVideoProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.client = client
        self.headers = {"Authorization": settings.pexels_api_key.get_secret_value()}

    async def search(self, query: str, *, photos: bool = False) -> list[dict]:
        endpoint = (
            "https://api.pexels.com/v1/search"
            if photos
            else "https://api.pexels.com/v1/videos/search"
        )
        response = await request(
            self.client,
            "GET",
            endpoint,
            headers=self.headers,
            params={"query": query, "per_page": 20, "orientation": "portrait"},
        )
        return response.json().get("photos" if photos else "videos", [])

    async def fetch(self, query: str, destination: Path, used: set[str]) -> Media:
        queries = list(dict.fromkeys([query, " ".join(query.split()[:2]), query.split()[0]]))
        for candidate in queries:
            for video in await self.search(candidate):
                source_id = f"video:{video['id']}"
                if source_id in used:
                    continue
                files = [
                    f
                    for f in video.get("video_files", [])
                    if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
                ]
                files.sort(
                    key=lambda f: (
                        abs(f["height"] - 1920) + abs(f["width"] / f["height"] - 9 / 16) * 2000
                    )
                )
                if not files:
                    continue
                try:
                    path = await download(
                        self.client, files[0]["link"], destination.with_suffix(".mp4")
                    )
                except (httpx.HTTPError, ValueError):
                    logging.getLogger(__name__).warning(
                        "Stock download failed; trying next candidate"
                    )
                    continue
                used.add(source_id)
                return Media(
                    path, source_id, video.get("url", ""), video.get("user", {}).get("name", "")
                )
        for candidate in queries:
            for photo in await self.search(candidate, photos=True):
                source_id = f"photo:{photo['id']}"
                if source_id in used:
                    continue
                try:
                    path = await download(
                        self.client, photo["src"]["large2x"], destination.with_suffix(".jpg")
                    )
                except (httpx.HTTPError, ValueError):
                    continue
                used.add(source_id)
                return Media(
                    path, source_id, photo.get("url", ""), photo.get("photographer", ""), True
                )
        raise RuntimeError(f"No unique stock video or photo for query: {query}")
