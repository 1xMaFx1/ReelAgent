"""Keyless public-domain photographs, with an explicit graphic fallback."""

import html
import re
from urllib.parse import urlparse

import httpx

from app.media.base import Media
from app.media.downloader import download

USER_AGENT = "ReelAgent/2.0 (https://github.com/1xMaFx1/ReelAgent)"


def public_domain(info):
    metadata = info.get("extmetadata", {})
    license_name = metadata.get("LicenseShortName", {}).get("value", "").lower()
    return license_name in {"public domain", "cc0", "cc-zero", "cc0 1.0"}


class CommonsProvider:
    def __init__(self, settings, client):
        self.client = client
        self.fallback = ""
        self.cache = {}

    async def search(self, query):
        if query not in self.cache:
            response = await self.client.get(
                "https://commons.wikimedia.org/w/api.php",
                headers={"User-Agent": USER_AGENT},
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": query + " filetype:bitmap",
                    "gsrnamespace": 6,
                    "gsrlimit": 30,
                    "prop": "imageinfo",
                    "iiprop": "url|mime|extmetadata",
                    "iiurlwidth": 1280,
                },
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {}).values()
            self.cache[query] = [
                p
                for p in sorted(pages, key=lambda p: p.get("index", 0))
                if p.get("imageinfo") and public_domain(p["imageinfo"][0])
            ]
        return self.cache[query]

    async def fetch(self, query, destination, used):
        try:
            candidates = await self.search(query)
        except (httpx.HTTPError, ValueError):
            candidates = []
        for page in candidates:
            identifier = str(page["pageid"])
            info = page["imageinfo"][0]
            url = info.get("thumburl") or info.get("url", "")
            parsed = urlparse(url)
            if (
                identifier in used
                or parsed.scheme != "https"
                or parsed.hostname != "upload.wikimedia.org"
                or info.get("mime") not in {"image/jpeg", "image/png"}
            ):
                continue
            path = destination.with_suffix(".jpg" if info["mime"] == "image/jpeg" else ".png")
            try:
                await download(self.client, url, path)
            except (httpx.HTTPError, ValueError):
                continue
            used.add(identifier)
            artist = info.get("extmetadata", {}).get("Artist", {}).get("value", "Public domain")
            artist = html.unescape(re.sub("<[^>]+>", "", artist))[:300]
            return Media(path, identifier, info.get("descriptionurl", ""), artist, True)
        # Abstract artwork is generated locally in the cloud, never unrelated stock footage.
        path = destination.with_suffix(".ppm")
        path.parent.mkdir(parents=True, exist_ok=True)
        palette = [(14, 24, 60), (35, 15, 54), (7, 43, 48), (53, 28, 18)]
        rgb = palette[len(used) % len(palette)]
        with path.open("wb") as handle:
            handle.write(b"P6\n540 960\n255\n")
            for y in range(960):
                row = bytearray()
                for x in range(540):
                    glow = max(0, 1 - ((x - 350) ** 2 + (y - 250) ** 2) / 300000)
                    row.extend(min(255, int(c + glow * 35)) for c in rgb)
                handle.write(row)
        identifier = "graphic-" + str(len(used))
        used.add(identifier)
        return Media(path, identifier, "generated:abstract-gradient", "ReelAgent", True)
