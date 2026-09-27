"""Keyless NASA library: source descriptions and credited science imagery."""

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.media.base import Media
from app.media.downloader import download
from app.utils.retry import request


def nasa_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").endswith(".nasa.gov")


def usable(item: dict) -> bool:
    data = (item.get("data") or [{}])[0]
    text = " ".join(str(value) for value in data.values()).lower()
    return bool(data.get("nasa_id")) and not any(
        marker in text for marker in ("copyright", "©", "all rights reserved", "press conference")
    )


class NasaVideoProvider:
    def __init__(self, settings, client: httpx.AsyncClient):
        self.client = client
        self.fallback = "Earth"

    async def search(self, query: str, kind: str = "image") -> list[dict]:
        response = await request(
            self.client,
            "GET",
            "https://images-api.nasa.gov/search",
            params={"q": query, "media_type": kind, "page_size": 50},
        )
        return [item for item in response.json()["collection"]["items"] if usable(item)]

    async def select_story(self, used: set[str]) -> dict:
        terms = [
            "Jupiter",
            "Saturn",
            "Mars",
            "Moon",
            "Earth ocean",
            "nebula",
            "galaxy",
            "Sun",
            "Venus",
            "Mercury",
            "comet",
            "aurora",
            "Neptune",
            "Uranus",
        ]
        offset = datetime.now(timezone.utc).date().toordinal() % len(terms)
        for term in (terms[offset:] + terms[:offset])[:4]:
            for item in await self.search(term):
                data = item["data"][0]
                description = html.unescape(re.sub("<[^>]+>", " ", data.get("description", "")))
                if data["nasa_id"] in used or len(description) < 600:
                    continue
                self.fallback = term
                return {
                    "id": data["nasa_id"],
                    "title": data["title"],
                    "description": description[:5000],
                    "url": "https://images.nasa.gov/details/" + quote(data["nasa_id"], safe=""),
                }
        raise ValueError("No unused NASA source found")

    async def fetch(self, query: str, destination: Path, used: set[str]) -> Media:
        queries = list(dict.fromkeys([query, self.fallback]))
        # Library photos are reliable, high resolution, and animated by the compositor.
        for search in queries:
            for item in (await self.search(search))[:12]:
                data = item["data"][0]
                identifier = data["nasa_id"]
                if identifier in used:
                    continue
                urls = [
                    link["href"]
                    for link in item.get("links", [])
                    if nasa_url(link.get("href", ""))
                    and urlparse(link["href"]).path.lower().endswith((".jpg", ".jpeg", ".png"))
                ]
                if not urls:
                    continue
                try:
                    manifest = await request(
                        self.client,
                        "GET",
                        "https://images-api.nasa.gov/asset/" + quote(identifier, safe=""),
                    )
                    larger = [
                        entry["href"]
                        for entry in manifest.json()["collection"]["items"]
                        if nasa_url(entry.get("href", "")) and entry["href"].endswith("~medium.jpg")
                    ]
                    if larger:
                        urls = larger
                    path = destination.with_suffix(Path(urlparse(urls[0]).path).suffix)
                    await download(self.client, urls[0], path)
                except (httpx.HTTPError, ValueError):
                    continue
                used.add(identifier)
                return Media(
                    path,
                    identifier,
                    "https://images.nasa.gov/details/" + quote(identifier, safe=""),
                    data.get("secondary_creator") or data.get("photographer") or "NASA",
                    True,
                )
        raise ValueError("No distinct NASA image found for scene")
