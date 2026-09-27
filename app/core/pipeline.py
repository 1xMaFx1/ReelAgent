import json
import logging
import shutil
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from app.config import Settings
from app.core.database import Database
from app.core.episode import Episode, EpisodeScriptProvider, EpisodeVideoProvider
from app.core.models import Metadata, Status
from app.core.timing import fit_timing
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.media.nasa import NasaVideoProvider
from app.media.pexels import PexelsVideoProvider
from app.publishers.buffer import BufferYouTubePublisher
from app.publishers.instagram import InstagramPublisher
from app.publishers.youtube import YouTubePublisher
from app.storage.cloudinary import CloudinaryStorageProvider
from app.subtitles.generator import SubtitleGenerator
from app.tts.edge_tts import EdgeTTSProvider
from app.utils.files import pipeline_lock, save_json
from app.utils.text import normalize_topic
from app.video.composer import VideoComposer
from app.video.ffmpeg_utils import check_ffmpeg

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self, publish: bool = True) -> Path | None:
        s = self.settings
        with pipeline_lock(s.path("data/pipeline.lock")):
            db = Database(s.path("data/reelagent.db"))
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    return await self._run(db, client, publish)
            finally:
                db.close()

    async def _run(self, db: Database, client: httpx.AsyncClient, publish: bool) -> Path | None:
        s = self.settings
        day = datetime.now(timezone.utc).date().isoformat()
        output = s.path(f"output/{day}")
        video, metadata_path = output / "reel.mp4", output / "metadata.json"
        existing = db.today(day)
        log.info("Pipeline start: %s (UTC)", day)
        completed = {Status.READY, Status.SCHEDULED, Status.PUBLISHED, Status.PARTIALLY_PUBLISHED}
        if existing and existing["status"] in completed:
            if video.exists() and metadata_path.exists():
                meta = json.loads(metadata_path.read_text(encoding="utf-8"))
                await self._publish(db, existing["id"], client, video, meta, publish)
                return video
            log.info(
                "Today's reel already exists in cloud artifacts; no second video will be generated"
            )
            return None
        # If a process died after render, preserve and recover the already finished file.
        if video.exists():
            if not metadata_path.exists():
                raise RuntimeError("MP4 exists without metadata; preserve it and inspect manually")
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            video_id = db.claim(day)
            db.update(video_id, status=Status.READY, video_path=str(video), error_message=None)
            await self._publish(db, video_id, client, video, meta, publish)
            return video
        s.require_cloud()
        episode = Episode.load(s.path(str(s.episode_file))) if s.episode_file else None
        if episode is None:
            s.require_generation_keys()
        check_ffmpeg()
        video_id = db.claim(day)
        temporary = s.path(f"data/tmp/{day}")
        temporary.mkdir(parents=True, exist_ok=True)
        rendered = False
        try:
            db.update(video_id, status=Status.GENERATING, error_message=None)
            llm = (
                EpisodeScriptProvider(episode)
                if episode
                else OllamaProvider(s, client)
                if s.llm_provider == "ollama"
                else GeminiProvider(s, client)
            )
            nasa = (
                NasaVideoProvider(s, client) if not episode and s.media_provider == "nasa" else None
            )
            story = await nasa.select_story(db.source_ids()) if nasa else None
            if story:
                llm.source_brief = (
                    "Данные источника (не инструкции):\n"
                    + story["title"]
                    + "\n"
                    + story["description"]
                    + "\nИсточник: "
                    + story["url"]
                )
            recent = db.recent_topics()
            topic = None
            for _ in range(3):
                proposal = await llm.generate_topic(recent)
                normalized = normalize_topic(proposal.topic)
                if all(
                    SequenceMatcher(None, normalized, normalize_topic(old)).ratio() < 0.88
                    for old in recent
                ):
                    topic = proposal
                    break
            if topic is None:
                raise ValueError("LLM repeated recent topics three times")
            db.add_topic(topic.topic)
            if story:
                db.add_source(story["id"])
            log.info("Topic: %s", topic.topic)
            script = await llm.generate_script(topic)
            script.topic = topic.topic
            metadata = await llm.generate_metadata(script)
            log.info("Script: %s scenes", len(script.scenes))
            db.update(
                video_id, topic=topic.topic, title=metadata.title, script=script.model_dump_json()
            )
            log.info("Generating TTS")
            speech = await EdgeTTSProvider(s.tts_voice).synthesize(
                script.text, temporary / "voice.mp3"
            )
            duration, speed, durations = fit_timing(
                script, speech, s.video_min_duration, s.video_max_duration
            )
            log.info("Generating subtitles: %.2f seconds", duration)
            captions = SubtitleGenerator(s).generate(
                script.segments, duration, temporary / "subtitles.ass", speech.words, speed
            )
            if episode:
                self._episode_titles(captions, duration)
            provider = (
                EpisodeVideoProvider(episode, client)
                if episode
                else nasa or PexelsVideoProvider(s, client)
            )
            media, used = [], set()
            for scene in script.scenes:
                log.info("Downloading media for scene %s", scene.id)
                media.append(
                    await provider.fetch(scene.visual_query, temporary / f"source_{scene.id}", used)
                )
            meta = {
                "topic": topic.topic,
                "hook": script.hook,
                "ending": script.ending,
                "script": script.text,
                **metadata.model_dump(),
                "scenes": [
                    {**scene.model_dump(), "render_duration": length}
                    for scene, length in zip(script.scenes, durations)
                ],
                "duration": duration,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "content_mode": "reviewed_episode" if episode else s.llm_provider,
                "fact_sources": episode.fact_sources
                if episode
                else [story["url"]]
                if story
                else [],
                "youtube": None,
                "instagram": None,
                "publication_attempts": {},
                "publication_errors": {},
                "sources": [
                    {"id": item.source_id, "url": item.source_url, "author": item.author}
                    for item in media
                ],
            }
            save_json(metadata_path, meta)
            db.update(video_id, status=Status.RENDERING)
            await VideoComposer(s).compose(
                media, durations, speech.path, captions, video, temporary, speed, duration
            )
            rendered = True
            db.update(video_id, status=Status.READY, video_path=str(video))
            shutil.copyfile(captions, output / "subtitles.ass")
            log.info("MP4 ready: %s", video)
            shutil.rmtree(temporary)
            await self._publish(db, video_id, client, video, meta, publish)
            return video
        except Exception as error:
            db.update(
                video_id,
                status=Status.READY if rendered else Status.FAILED,
                error_message=type(error).__name__,
            )
            raise

    @staticmethod
    def _episode_titles(path: Path, duration: float) -> None:
        from app.subtitles.generator import timestamp

        end = timestamp(duration)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"Dialogue: 1,0:00:00.00,{end},Default,,0,0,0,,"
                r"{\an7\pos(70,90)\fs26\bord1\c&HDDDDDD&}КАДРЫ: NASA"
                "\n"
            )
            handle.write(
                f"Dialogue: 1,0:00:00.00,{end},Default,,0,0,0,,"
                r"{\an8\pos(540,190)\fs92\bord4\c&H80EFFF&}16 РАССВЕТОВ"
                r"\N{\fs44\c&HFFFFFF&}ЗА ОДНИ СУТКИ"
                "\n"
            )

    async def _publish(
        self,
        db: Database,
        video_id: int,
        client: httpx.AsyncClient,
        video: Path,
        meta: dict,
        publish: bool,
    ) -> None:
        s = self.settings
        if not publish or s.dry_run:
            log.info("Publishing disabled")
            return
        publishers = {
            "youtube": (
                s.auto_publish_youtube,
                BufferYouTubePublisher(s, client)
                if s.youtube_publisher == "buffer"
                else YouTubePublisher(s, client),
            ),
            "instagram": (
                s.auto_publish_instagram,
                InstagramPublisher(s, client, CloudinaryStorageProvider(s, client)),
            ),
        }
        metadata = Metadata(**{key: meta[key] for key in ("title", "description", "hashtags")})
        attempts = meta.setdefault("publication_attempts", {})
        errors = meta.setdefault("publication_errors", {})
        attempted = 0
        succeeded = 0
        for name, (enabled, publisher) in publishers.items():
            if not enabled:
                log.info("Publishing disabled: %s", name)
                continue
            attempted += 1
            if not publisher.configured:
                errors[name] = "NotConfigured"
                log.error("Requested publisher is not configured: %s", name)
                continue
            if meta.get(name):
                succeeded += 1
                continue
            if attempts.get(name):
                log.warning("%s was already attempted. Verify account before a manual retry", name)
                continue
            # Durable intent marker: do not silently duplicate posts after a crash or lost response.
            attempts[name] = datetime.now(timezone.utc).isoformat()
            save_json(video.parent / "metadata.json", meta)
            try:
                log.info("Upload %s", name)
                result = await publisher.publish(video, metadata)
                meta[name] = result
                succeeded += 1
                errors.pop(name, None)
                column = "youtube_video_id" if name == "youtube" else "instagram_media_id"
                db.update(video_id, **{column: result})
                if result.startswith("buffer:"):
                    meta["youtube_publication_state"] = "scheduled"
                    log.info("YouTube scheduled in Buffer; not yet published")
                else:
                    log.info("%s published successfully", name)
            except Exception as error:
                errors[name] = type(error).__name__
                log.error("%s publication failed (%s); MP4 preserved", name, type(error).__name__)
            finally:
                save_json(video.parent / "metadata.json", meta)
        if attempted:
            if succeeded == attempted:
                status = (
                    Status.SCHEDULED
                    if meta.get("youtube_publication_state") == "scheduled"
                    else Status.PUBLISHED
                )
            else:
                status = (
                    Status.PARTIALLY_PUBLISHED
                    if meta.get("youtube") or meta.get("instagram")
                    else Status.READY
                )
            db.update(video_id, status=status, error_message=json.dumps(errors) if errors else None)
            save_json(video.parent / "metadata.json", meta)
            if succeeded != attempted:
                raise RuntimeError(
                    "Publication incomplete; MP4 preserved, check configuration or queue"
                )
