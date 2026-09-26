import hashlib
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import Settings
from app.utils.retry import network_retry


class CloudinaryStorageProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(
            s.cloudinary_cloud_name
            and s.cloudinary_api_key.get_secret_value()
            and s.cloudinary_api_secret.get_secret_value()
        )

    @network_retry
    async def upload(self, path: Path, public_id: str) -> str:
        s = self.settings
        if path.stat().st_size > 95 * 1024 * 1024:
            raise ValueError("Video exceeds MVP Cloudinary upload limit (95 MB)")
        params = {"overwrite": "true", "public_id": public_id, "timestamp": str(int(time.time()))}
        signing = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
        signature = hashlib.sha1(
            (signing + s.cloudinary_api_secret.get_secret_value()).encode()
        ).hexdigest()
        with path.open("rb") as video:
            response = await self.client.post(
                f"https://api.cloudinary.com/v1_1/{quote(s.cloudinary_cloud_name, safe='')}/video/upload",
                data={
                    **params,
                    "signature": signature,
                    "api_key": s.cloudinary_api_key.get_secret_value(),
                },
                files={"file": (path.name, video, "video/mp4")},
                timeout=300,
            )
        response.raise_for_status()
        return response.json()["secure_url"]
