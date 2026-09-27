"""Render reviewed, manually supplied weekly prompts without an LLM subscription."""

import io
import json
import os
import shutil
import textwrap
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.models import Status
from app.core.prompt_queue import WeeklyPlan
from app.core.timing import fit_timing
from app.media.base import Media
from app.media.commons import CommonsProvider
from app.media.nasa import NasaVideoProvider
from app.subtitles.generator import SubtitleGenerator, timestamp
from app.tts.edge_tts import EdgeTTSProvider
from app.utils.files import save_json
from app.video.composer import VideoComposer
from app.video.ffmpeg_utils import command


def cache_path(settings, plan, entry):
    return settings.path(f"data/week-cache/{plan.id}/{entry.key}.mp4")


async def cache_clip(source, destination, *, concat=False):
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".partial.mp4")
    inputs = ["-f", "concat", "-safe", "1"] if concat else ["-ss", "3"]
    await command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-i",
            str(source),
            "-t",
            "12",
            "-an",
            "-vf",
            "scale=540:960",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-b:v",
            "500k",
            "-maxrate",
            "600k",
            "-bufsize",
            "1200k",
            "-threads",
            "2",
            str(partial),
        ]
    )
    partial.replace(destination)


async def anchor_file(settings, entry, client):
    local = settings.path(f"output/{entry.anchor_date}/reel.mp4")
    if local.is_file():
        return local
    repo = os.environ["GITHUB_REPOSITORY"]
    headers = {"Authorization": "Bearer " + os.environ["GH_TOKEN"]}
    response = await client.get(
        f"https://api.github.com/repos/{repo}/actions/runs/{entry.anchor_run_id}/artifacts",
        headers=headers,
    )
    response.raise_for_status()
    candidates = [
        a
        for a in response.json()["artifacts"]
        if a["name"] == "reelagent-state" and not a["expired"]
    ]
    if not candidates:
        raise ValueError(
            "Первый ролик отсутствует в облаке. Восстановите его из сохранённой копии."
        )
    response = await client.get(candidates[0]["archive_download_url"], headers=headers)
    if response.is_redirect:
        response = await client.get(response.headers["location"], follow_redirects=True)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        payload = archive.read(f"output/{entry.anchor_date}/reel.mp4")
    # Keep imported anchors out of today's downloadable output.
    local = settings.path(f"data/tmp/anchor-{entry.key}.mp4")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(payload)
    return local


async def run_weekly(settings, db, client):
    settings.require_cloud()
    day = settings.run_slot or datetime.now(ZoneInfo("Europe/Simferopol")).date().isoformat()
    calendar_day = day[:10]
    hour = int(day[11:]) if len(day) > 10 else 8
    plan = WeeklyPlan.load(settings.path(str(settings.prompt_queue_file)))
    entry = plan.for_date(calendar_day, hour)
    db.assign_prompt(day, entry.key, plan.id, entry.model_dump_json())
    if entry.mode != "anchor" and (entry.script is None or entry.social is None):
        raise ValueError(
            "Промпт принят, но ещё нужен проверенный сценарий. Передайте пакет для подготовки."
        )
    # Bootstrap the existing anchor once; subsequent state artifacts retain its short excerpt.
    for anchor in (e for e in plan.entries if e.mode == "anchor"):
        cached = cache_path(settings, plan, anchor)
        if not cached.exists():
            await cache_clip(await anchor_file(settings, anchor, client), cached)
    if entry.mode == "anchor":
        # Anchor is already created; never overwrite a different existing daily draft.
        return None
    output = settings.path(f"output/{day}")
    video, metadata_path = output / "reel.mp4", output / "metadata.json"
    cached = cache_path(settings, plan, entry)
    if video.exists():
        if not metadata_path.exists():
            raise ValueError("Сохранён MP4 без описания. Нужна проверка перед повторным запуском.")
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        if meta.get("prompt_key") != entry.key:
            raise ValueError("На эту дату уже есть другой ролик; автоматическая замена запрещена.")
        if not cached.exists():
            await cache_clip(video, cached)
        db.update(db.claim(day), status=Status.READY, video_path=str(video), error_message=None)
        return video
    prior = db.today(day)
    if prior and prior["status"] in {Status.READY, Status.PUBLISHED, Status.SCHEDULED}:
        raise ValueError("Готовый ролик утрачен. Восстановите его, чтобы не создавать дубликат.")
    s = settings.model_copy(
        update={"video_min_duration": entry.min_seconds, "video_max_duration": entry.max_seconds}
    )
    temporary = s.path(f"data/tmp/{day}")
    temporary.mkdir(parents=True, exist_ok=True)
    video_id = db.claim(day)
    rendered = False
    try:
        script = entry.script
        db.update(
            video_id,
            status=Status.GENERATING,
            topic=entry.topic,
            title=entry.social.title,
            script=script.model_dump_json(),
            error_message=None,
        )
        speech = await EdgeTTSProvider(s.tts_voice).synthesize(script.text, temporary / "voice.mp3")
        duration, speed, durations = fit_timing(
            script, speech, entry.min_seconds, entry.max_seconds
        )
        subtitles = SubtitleGenerator(s).generate(
            script.segments, duration, temporary / "subtitles.ass", speech.words, speed
        )
        with subtitles.open("a", encoding="utf-8") as handle:
            handle.write(
                f"Dialogue: 1,0:00:00.00,{timestamp(duration)},Default,,0,0,0,,"
                + r"{\an7\pos(70,90)\fs26\bord1}"
                + ("ИЗОБРАЖЕНИЯ: NASA" if entry.media_source == "nasa" else "REELAGENT")
                + "\n"
            )
            cursor = 0.0
            for title, length in zip(entry.overlays, durations):
                title = (
                    title.replace("\\", " ").replace("{", "").replace("}", "").replace("\n", " ")
                )
                title = r"\N".join(textwrap.wrap(title, width=24))
                handle.write(
                    f"Dialogue: 2,{timestamp(cursor)},{timestamp(cursor + length)},Default,,0,0,0,,"
                    + r"{\an8\pos(540,230)\fs60\bord4}"
                    + title
                    + "\n"
                )
                cursor += length
        media, used = [], set()
        provider = (
            NasaVideoProvider(s, client)
            if entry.media_source == "nasa"
            else CommonsProvider(s, client)
        )
        for index, scene in enumerate(script.scenes):
            if entry.mode == "recap":
                earlier = plan.entry(entry.recap_days[index], entry.hour)
                path = cache_path(s, plan, earlier)
                if not path.exists():
                    raise ValueError(
                        f"Для подборки не хватает готового дня {earlier.day}. Восстановите кадры."
                    )
                item = Media(
                    path,
                    earlier.key,
                    f"weekly:{plan.id}/day-{earlier.day}",
                    "NASA",
                    mask_captions=True,
                )
            else:
                provider.fallback = scene.visual_query  # Never fall back to an unrelated topic.
                item = await provider.fetch(
                    scene.visual_query, temporary / f"source_{scene.id}", used
                )
                item.zoom_out = entry.zoom_out
            media.append(item)
        meta = {
            "topic": entry.topic,
            "title": entry.social.title,
            "description": ", ".join(entry.social.keywords),
            "hashtags": entry.social.hashtags,
            "script": script.text,
            "hook": script.hook,
            "ending": script.ending,
            "scenes": [
                {**scene.model_dump(), "render_duration": length}
                for scene, length in zip(script.scenes, durations)
            ],
            "duration": duration,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "content_mode": "prompt_queue",
            "plan_id": plan.id,
            "prompt_key": entry.key,
            "prompt": entry.prompt,
            "plan_day": entry.day,
            "slot": day,
            "fact_sources": [str(url) for url in entry.sources],
            "sources": [
                {"id": m.source_id, "url": m.source_url, "author": m.author} for m in media
            ],
            "youtube": None,
            "instagram": None,
        }
        save_json(metadata_path, meta)
        db.update(video_id, status=Status.RENDERING)
        await VideoComposer(s).compose(
            media, durations, speech.path, subtitles, video, temporary, speed, duration
        )
        rendered = True
        # Archive actual scene footage without old subtitles for the weekly highlight reel.
        await cache_clip(temporary / "concat.txt", cached, concat=True)
        shutil.copyfile(subtitles, output / "subtitles.ass")
        db.update(video_id, status=Status.READY, video_path=str(video))
        shutil.rmtree(temporary)
        return video
    except Exception as error:
        db.update(
            video_id,
            status=Status.READY if rendered else Status.FAILED,
            error_message=type(error).__name__,
        )
        raise
