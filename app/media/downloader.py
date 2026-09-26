from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.utils.retry import network_retry


@network_retry
async def download(client: httpx.AsyncClient, url: str, path: Path) -> Path:
    if urlparse(url).scheme != "https":
        raise ValueError("Media download requires HTTPS")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    total = 0
    try:
        async with client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > 250 * 1024 * 1024:
                        raise ValueError("Stock clip exceeds 250 MB limit")
                    handle.write(chunk)
        if total == 0:
            raise ValueError("Empty media download")
        temporary.replace(path)
        return path
    finally:
        temporary.unlink(missing_ok=True)
