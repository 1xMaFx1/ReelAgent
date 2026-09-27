"""Instagram automatic scheduling through the official Buffer API."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.core.slots import target_time
from app.publishers.buffer import BufferYouTubePublisher


class BufferInstagramPublisher(BufferYouTubePublisher):
    @property
    def configured(self):
        return bool(
            self.settings.buffer_api_key.get_secret_value() and self.settings.buffer_channel_id
        )

    async def validate_channel(self):
        data = await self.query(
            "query($input:ChannelInput!){channel(input:$input){service name externalLink "
            "serviceId isDisconnected isLocked isQueuePaused}}",
            {"input": {"id": self.settings.buffer_channel_id}},
        )
        channel = data["channel"]
        expected = self.settings.instagram_username.lower().lstrip("@")
        link = urlparse(channel.get("externalLink") or "")
        handle = link.path.strip("/").split("/")[0].lower()
        if (
            channel["service"] != "instagram"
            or not expected
            or (
                channel["name"].lower().lstrip("@") != expected
                and not (
                    link.hostname in {"instagram.com", "www.instagram.com"} and handle == expected
                )
            )
        ):
            raise ValueError("Buffer подключён не к разрешённому Instagram-аккаунту")
        if any(channel[key] for key in ("isDisconnected", "isLocked", "isQueuePaused")):
            raise ValueError("Instagram в Buffer отключён, заблокирован или поставлен на паузу")
        return channel

    async def schedule(self, slot: str, meta: dict, now=None):
        target = target_time(slot).astimezone(timezone.utc)
        if target <= (now or datetime.now(timezone.utc)) + timedelta(minutes=2):
            raise ValueError(
                "Время выпуска пропущено. MP4 сохранён, поздняя публикация не выполняется."
            )
        await self.validate_channel()
        url = meta["public_video_url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ValueError("Ожидалась согласованная публичная копия на GitHub")
        result = await self.query(
            "mutation($input:CreatePostInput!){createPost(input:$input){__typename "
            "... on PostActionSuccess{post{id dueAt status schedulingType}} "
            "... on MutationError{message}}}",
            {
                "input": {
                    "channelId": self.settings.buffer_channel_id,
                    "text": meta["description"] + "\n" + " ".join(meta["hashtags"]),
                    "assets": [{"video": {"url": url, "metadata": {"title": meta["title"]}}}],
                    "mode": "customScheduled",
                    "dueAt": target.isoformat(),
                    "schedulingType": "automatic",
                    "needsApproval": False,
                    "saveToDraft": False,
                    "aiAssisted": True,
                    "metadata": {
                        "instagram": {
                            "type": "reel",
                            "shouldShareToFeed": True,
                            "isAiGenerated": True,
                        }
                    },
                }
            },
        )
        outcome = result["createPost"]
        if outcome["__typename"] != "PostActionSuccess":
            raise RuntimeError(
                "Buffer не принял публикацию; проверьте подключение и бесплатную квоту"
            )
        post = outcome["post"]
        if post["schedulingType"] != "automatic" or not post.get("dueAt"):
            raise RuntimeError("Автоматическая публикация не подтверждена Buffer")
        return post

    async def status(self, post_id: str):
        result = await self.query(
            "query($input:PostInput!){post(input:$input){id status sentAt dueAt externalLink}}",
            {"input": {"id": post_id}},
        )
        return result["post"]
