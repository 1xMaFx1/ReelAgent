"""Schedule a YouTube Short using Buffer's documented GraphQL API."""

from datetime import date
from pathlib import Path

import httpx

from app.config import Settings
from app.core.models import Metadata
from app.core.schedule import publication_time
from app.storage.cloudinary import CloudinaryStorageProvider


class BufferYouTubePublisher:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.storage = CloudinaryStorageProvider(settings, client)

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(
            s.buffer_api_key.get_secret_value()
            and s.buffer_channel_id
            and s.cloudinary_cloud_name
            and s.cloudinary_api_key.get_secret_value()
            and s.cloudinary_api_secret.get_secret_value()
        )

    async def query(self, query: str, variables: dict) -> dict:
        # Never blindly retry a mutation after an ambiguous response.
        response = await self.client.post(
            "https://api.buffer.com",
            headers={"Authorization": "Bearer " + self.settings.buffer_api_key.get_secret_value()},
            json={"query": query, "variables": variables},
            timeout=120,
        )
        response.raise_for_status()
        value = response.json()
        if value.get("errors"):
            raise RuntimeError("Buffer rejected request; check permissions, input and free quota")
        return value["data"]

    async def validate_channel(self) -> None:
        result = await self.query(
            "query($input:ChannelInput!){channel(input:$input){service serviceId "
            "isDisconnected isLocked isQueuePaused}}",
            {"input": {"id": self.settings.buffer_channel_id}},
        )
        channel = result["channel"]
        if (
            channel["service"] != "youtube"
            or channel["serviceId"] != self.settings.youtube_channel_id
        ):
            raise ValueError("Buffer channel does not match the authorized YouTube channel")
        if any(channel[name] for name in ("isDisconnected", "isLocked", "isQueuePaused")):
            raise ValueError("Buffer channel disconnected, locked or paused")

    async def publish(self, path: Path, metadata: Metadata) -> str:
        target = publication_time(path.parent.name, self.settings)
        await self.validate_channel()
        slot = date.fromisoformat(path.parent.name).toordinal() % 7
        url = await self.storage.upload(path, f"reelagent/source-slot-{slot}")
        result = await self.query(
            "mutation($input:CreatePostInput!){createPost(input:$input){__typename "
            "... on PostActionSuccess{post{id dueAt status schedulingType}}}}",
            {
                "input": {
                    "channelId": self.settings.buffer_channel_id,
                    "text": metadata.description + "\n\n" + " ".join(metadata.hashtags),
                    "assets": [{"video": {"url": url}}],
                    "mode": "customScheduled",
                    "dueAt": target.isoformat(),
                    "schedulingType": "automatic",
                    "needsApproval": False,
                    "saveToDraft": False,
                    "aiAssisted": True,
                    "metadata": {
                        "youtube": {
                            "title": metadata.title,
                            "categoryId": "28",
                            "privacy": "public",
                            "madeForKids": False,
                            "isAiGenerated": True,
                        }
                    },
                }
            },
        )
        outcome = result["createPost"]
        if outcome["__typename"] != "PostActionSuccess":
            raise RuntimeError("Buffer scheduling failed: " + outcome["__typename"])
        post = outcome["post"]
        if post["schedulingType"] != "automatic" or not post.get("dueAt"):
            raise RuntimeError("Buffer did not confirm automatic scheduling; inspect queue")
        return "buffer:" + post["id"]
