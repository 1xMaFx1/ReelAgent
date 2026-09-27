"""Read-only readiness check: never uploads or publishes a video."""

import asyncio

import httpx

from app.config import Settings
from app.media.pexels import PexelsVideoProvider
from app.publishers.buffer import BufferYouTubePublisher


async def main():
    settings = Settings()
    settings.require_generation_keys()
    async with httpx.AsyncClient(timeout=60) as client:
        publisher = BufferYouTubePublisher(settings, client)
        if not publisher.configured:
            raise ValueError("Missing Buffer or Cloudinary connection")
        await publisher.validate_channel()
        results = await PexelsVideoProvider(settings, client).search("earth space")
        if not results:
            raise ValueError("Pexels search returned no stock videos")
        print("Channel verified; stock search works; storage credentials present. No post created.")


if __name__ == "__main__":
    asyncio.run(main())
