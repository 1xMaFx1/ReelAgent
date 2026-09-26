import asyncio
from pathlib import Path

import httpx

from app.config import Settings
from app.core.models import Metadata
from app.storage.cloudinary import CloudinaryStorageProvider
from app.utils.retry import request, transient


class InstagramPublisher:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient, storage: CloudinaryStorageProvider
    ):
        self.settings, self.client, self.storage = settings, client, storage
        self.base = f"https://graph.facebook.com/{settings.instagram_api_version}"
        self.headers = {
            "Authorization": "Bearer " + settings.instagram_access_token.get_secret_value()
        }

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.instagram_access_token.get_secret_value()
            and self.settings.instagram_account_id
            and self.storage.configured
        )

    async def container_status(self, container: str) -> str:
        response = await request(
            self.client,
            "GET",
            f"{self.base}/{container}",
            headers=self.headers,
            params={"fields": "status_code"},
        )
        return response.json()["status_code"]

    async def publish(self, path: Path, metadata: Metadata) -> str:
        account = self.settings.instagram_account_id
        url = await self.storage.upload(path, "reelagent/" + path.parent.name)
        caption = (
            metadata.title + "\n\n" + metadata.description + "\n" + " ".join(metadata.hashtags)
        )
        response = await request(
            self.client,
            "POST",
            f"{self.base}/{account}/media",
            headers=self.headers,
            data={
                "media_type": "REELS",
                "video_url": url,
                "caption": caption[:2200],
                "share_to_feed": "true",
            },
        )
        container = response.json()["id"]
        for _ in range(60):
            status = await self.container_status(container)
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError("Instagram video processing failed")
            await asyncio.sleep(5)
        else:
            raise RuntimeError("Instagram processing timed out after 5 minutes")
        for attempt in range(3):
            if attempt:
                status = await self.container_status(container)
                if status == "PUBLISHED":
                    raise RuntimeError(
                        "Instagram published but response ID lost; verify account manually"
                    )
                if status != "FINISHED":
                    raise RuntimeError("Instagram publish state uncertain; verify account manually")
            try:
                result = await self.client.post(
                    f"{self.base}/{account}/media_publish",
                    headers=self.headers,
                    data={"creation_id": container},
                )
                result.raise_for_status()
                return result.json()["id"]
            except httpx.HTTPError as error:
                if not transient(error):
                    raise
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError("Instagram publication uncertain; verify account before retrying")
