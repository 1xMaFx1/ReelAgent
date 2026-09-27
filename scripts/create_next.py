"""One request creates exactly one next reel. No clock, cron or social publishing."""

import asyncio
import json
import os
import shutil

import httpx

from app.config import Settings
from app.core.pipeline import Pipeline
from app.core.prompt_queue import WeeklyPlan
from app.core.weekly_pipeline import cache_path
from app.media.downloader import download
from scripts.library import gh, ready_releases, repository


def select_entry(plan, ready, request_id):
    for item in ready:
        if item.get("request_id") == request_id:
            return None, item
    done = {item["prompt_key"] for item in ready}
    return next((entry for entry in plan.entries if entry.key not in done), None), None


def release_body(entry, plan, request_id):
    marker = {
        "prompt_key": entry.key,
        "plan_id": plan.id,
        "request_id": request_id,
        "day": entry.day,
        "variant": (8, 12, 17).index(entry.hour) + 1,
    }
    return (
        "Готовый ролик. Нажмите **reel.mp4** в разделе Assets, чтобы скачать.\n\n"
        "Описание, ключевые слова и источники — в metadata.json.\n\n"
        "<!-- reelagent:" + json.dumps(marker, ensure_ascii=False) + " -->"
    )


async def main():
    settings = Settings()
    settings.require_cloud()
    plan = WeeklyPlan.load(settings.path(str(settings.prompt_queue_file)))
    repo = repository()
    request_id = os.environ.get("REQUEST_ID") or os.environ["GITHUB_RUN_ID"]
    ready = ready_releases(repo)
    previous = next((r for r in ready if r.get("request_id") == request_id), None)
    if previous:
        print("Этот запрос уже выполнен: " + previous["url"])
        return
    prompt = os.environ.get("CUSTOM_PROMPT", "").strip()
    if prompt:
        from scripts.custom_prompt import prepare_prompt

        settings, plan = await prepare_prompt(settings, prompt, request_id)
    entry, previous = select_entry(plan, ready, request_id)
    if previous:
        print("Этот запрос уже выполнен: " + previous["url"])
        return
    if entry is None:
        raise ValueError("Все промпты использованы. Добавьте новый пакет сценариев.")
    identifier = plan.date_for(entry) + f"-{entry.hour:02}"
    settings = settings.model_copy(update={"run_slot": identifier})
    if entry.mode == "recap":
        by_key = {item["prompt_key"]: item for item in ready}
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            for day in entry.recap_days:
                earlier = plan.entry(day, entry.hour)
                source = by_key.get(earlier.key)
                if source is None:
                    raise ValueError(f"Для подборки не хватает выпуска по теме {day}")
                target = cache_path(settings, plan, earlier)
                target.parent.mkdir(parents=True, exist_ok=True)
                await download(
                    client, source["assets"]["recap.mp4"]["browser_download_url"], target
                )
    video = await Pipeline(settings).run()
    if video is None:
        raise ValueError(
            "Для режима по кнопке нужен самостоятельный сценарий, а не ссылка на старый выпуск"
        )
    tag = "reel-" + entry.key
    notes = settings.path("data/release-notes.md")
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(release_body(entry, plan, request_id), encoding="utf-8")
    try:
        gh("release", "view", tag, "--repo", repo)
    except RuntimeError:
        gh(
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--target",
            os.environ["GITHUB_SHA"],
            "--title",
            entry.social.title,
            "--notes-file",
            str(notes),
        )
    gh(
        "release",
        "edit",
        tag,
        "--repo",
        repo,
        "--title",
        entry.social.title,
        "--notes-file",
        str(notes),
    )
    # metadata.json is the completion marker and is uploaded last.
    gh("release", "upload", tag, str(video), "--repo", repo, "--clobber")
    recap = video.with_name("recap.mp4")
    shutil.copyfile(cache_path(settings, plan, entry), recap)
    gh(
        "release",
        "upload",
        tag,
        str(recap),
        "--repo",
        repo,
        "--clobber",
    )
    gh("release", "upload", tag, str(video.with_name("subtitles.ass")), "--repo", repo, "--clobber")
    gh("release", "upload", tag, str(video.with_name("metadata.json")), "--repo", repo, "--clobber")
    url = f"https://github.com/{repo}/releases/tag/{tag}"
    print("Готово: " + url)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(
                f"## Ролик готов: {entry.social.title}\n\n[Скачать MP4]"
                f"(https://github.com/{repo}/releases/download/{tag}/reel.mp4)\n\n"
                f"[Все файлы выпуска]({url})\n\nДля сохранения на рабочий стол откройте ReelAgent и нажмите «Скачать».\n"
            )


if __name__ == "__main__":
    asyncio.run(main())
