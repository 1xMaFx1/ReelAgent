"""Exercise the real free cloud model without publishing or creating a second daily reel."""

import asyncio
import json
from pathlib import Path

import httpx

from app.config import Settings
from app.llm.ollama import OllamaProvider


async def main() -> None:
    async with httpx.AsyncClient() as client:
        provider = OllamaProvider(Settings(), client)
        topic = await provider.generate_topic([])
        print("Topic:", topic.topic, flush=True)
        script = await provider.generate_script(topic)
        metadata = await provider.generate_metadata(script)
        output = Path("model-check")
        output.mkdir(exist_ok=True)
        (output / "draft.json").write_text(
            json.dumps(
                {"script": script.model_dump(), "metadata": metadata.model_dump()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(script.text, flush=True)
        print("Draft validated; nothing was published.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
