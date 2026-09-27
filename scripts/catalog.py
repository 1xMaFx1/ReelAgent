"""Small durable metadata catalog; MP4 backups live in owner-approved Releases."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import sys

import httpx

from app.config import Settings
from app.media.downloader import download


def save():
    settings = Settings()
    folder = settings.path("data/catalog")
    folder.mkdir(parents=True, exist_ok=True)
    for meta in settings.path("output").glob("*/metadata.json"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}-(08|12|17)", meta.parent.name):
            shutil.copyfile(meta, folder / (meta.parent.name + ".json"))


async def recover():
    settings = Settings()
    slot = settings.run_slot
    catalog = settings.path(f"data/catalog/{slot}.json")
    if not catalog.is_file():
        return
    target = settings.path(f"output/{slot}/reel.mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    meta = json.loads(catalog.read_text())
    if not target.exists():
        expected = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/reel-{slot}/reel.mp4"
        if meta.get("public_video_url") != expected or not meta.get("video_sha256"):
            raise ValueError("Не удалось подтвердить резервную копию MP4")
        partial = target.with_suffix(".recovering.mp4")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            await download(client, expected, partial)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != meta["video_sha256"]:
            partial.unlink()
            raise ValueError("Контрольная сумма резервной копии не совпала")
        partial.replace(target)
    # Preserve the more recent output metadata if state contains it.
    if not target.with_name("metadata.json").exists():
        shutil.copyfile(catalog, target.with_name("metadata.json"))


if __name__ == "__main__":
    if sys.argv[1] == "save":
        save()
    else:
        asyncio.run(recover())
