"""Persist intent BEFORE creating a remote post; never retry ambiguous creation."""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.publishers.buffer_instagram import BufferInstagramPublisher
from app.utils.files import save_json


def attempt_id():
    return os.environ["GITHUB_RUN_ID"] + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")


def output(value):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.write("create=" + str(value).lower() + "\n")


async def main(mode):
    settings = Settings()
    path = settings.path(f"output/{settings.run_slot}/metadata.json")
    if not path.exists():
        raise ValueError("Нет готового выпуска для этого часа")
    meta = json.loads(path.read_text())
    async with httpx.AsyncClient(timeout=120) as client:
        publisher = BufferInstagramPublisher(settings, client)
        if not settings.auto_publish_instagram or not publisher.configured:
            meta["instagram_state"] = "not_connected"
            save_json(path, meta)
            output(False)
            print("Видео готово; подключение Instagram ещё не завершено")
            return
        if meta.get("buffer_post_id"):
            post = await publisher.status(meta["buffer_post_id"])
            meta["instagram_state"] = post["status"]
            meta["instagram"] = (
                (post.get("externalLink") or post["id"]) if post["status"] == "sent" else None
            )
            meta["instagram_checked_at"] = datetime.now(timezone.utc).isoformat()
            save_json(path, meta)
            output(False)
            return
        if mode == "verify":
            output(False)
            return
        if mode == "prepare":
            if meta.get("instagram_intent"):
                raise RuntimeError(
                    "Предыдущая отправка не подтверждена: проверьте очередь Buffer перед повтором"
                )
            await publisher.validate_channel()
            meta["instagram_intent"] = attempt_id()
            meta["instagram_state"] = "submitting"
            save_json(path, meta)
            output(True)
            return
        if mode != "submit" or meta.get("instagram_intent") != attempt_id():
            raise RuntimeError("Нет сохранённого разрешения на эту попытку отправки")
        try:
            post = await publisher.schedule(settings.run_slot, meta)
            meta["buffer_post_id"] = post["id"]
            meta["instagram_state"] = "scheduled"
            meta["instagram_due_at"] = post["dueAt"]
            meta["instagram"] = None
            save_json(path, meta)
        except Exception:
            meta["instagram_state"] = "needs_review"
            save_json(path, meta)
            raise


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
