import logging
import random
import shutil
from pathlib import Path

from app.config import Settings
from app.media.base import Media
from app.video.ffmpeg_utils import check_ffmpeg, command, probe


class VideoComposer:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def compose(
        self,
        media: list[Media],
        durations: list[float],
        audio: Path,
        subtitles: Path,
        destination: Path,
        temporary: Path,
        speed: float,
        total_duration: float,
    ) -> Path:
        s = self.settings
        s.require_cloud()
        check_ffmpeg()
        logging.getLogger(__name__).info("FFmpeg: normalizing %s scenes", len(media))
        for index, (item, duration) in enumerate(zip(media, durations, strict=True)):
            source = ["-loop", "1"] if item.is_image else ["-stream_loop", "-1"]
            filters = (
                f"scale={s.video_width}:{s.video_height}:force_original_aspect_ratio=increase,"
                f"crop={s.video_width}:{s.video_height},setsar=1,fps={s.video_fps},format=yuv420p"
            )
            if item.is_image:
                filters = (
                    f"scale={s.video_width}:{s.video_height}:force_original_aspect_ratio=increase,"
                    f"crop={s.video_width}:{s.video_height},"
                    f"zoompan=z='min(zoom+0.0003,1.08)':x='iw/2-iw/zoom/2':"
                    f"y='ih/2-ih/zoom/2':d=1:s={s.video_width}x{s.video_height}:fps={s.video_fps},"
                    "setsar=1,format=yuv420p"
                )
            await command(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    *source,
                    "-i",
                    str(item.path),
                    "-t",
                    f"{duration:.6f}",
                    "-an",
                    "-vf",
                    filters,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "21",
                    "-threads",
                    "2",
                    str(temporary / f"segment_{index:02}.mp4"),
                ]
            )
        (temporary / "concat.txt").write_text(
            "".join(f"file 'segment_{i:02}.mp4'\n" for i in range(len(media))), encoding="utf-8"
        )
        # Only a constant relative name reaches the FFmpeg filter parser.
        shutil.copyfile(subtitles, temporary / "captions.ass")
        music = [
            p
            for p in s.path("assets/music").glob("*")
            if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}
        ]
        inputs = ["-f", "concat", "-safe", "1", "-i", "concat.txt", "-i", str(audio)]
        filters = f"[1:a]atempo={speed:.6f},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[voice];"
        if music:
            inputs += ["-stream_loop", "-1", "-i", str(random.choice(music))]
            filters += (
                f"[2:a]loudnorm=I=-16:TP=-1.5:LRA=11,volume={s.music_volume},"
                f"afade=t=in:st=0:d=1,afade=t=out:st={max(0, total_duration - 2):.3f}:d=2[music];"
                "[voice][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
            )
        else:
            filters += "[voice]anull[a]"
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name("reel.partial.mp4")
        await command(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                *inputs,
                "-filter_complex",
                filters,
                "-vf",
                "ass=captions.ass",
                "-map",
                "0:v:0",
                "-map",
                "[a]",
                "-t",
                f"{total_duration:.6f}",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "21",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(s.video_fps),
                "-threads",
                "2",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(partial),
            ],
            cwd=temporary,
        )
        info = await probe(partial)
        video = next(x for x in info["streams"] if x["codec_type"] == "video")
        sound = next(x for x in info["streams"] if x["codec_type"] == "audio")
        duration = float(info["format"]["duration"])
        if (video["width"], video["height"], video["codec_name"], sound["codec_name"]) != (
            s.video_width,
            s.video_height,
            "h264",
            "aac",
        ):
            raise RuntimeError("Output format validation failed")
        if not s.video_min_duration - 0.1 <= duration <= s.video_max_duration + 0.1:
            raise RuntimeError("Output duration validation failed")
        partial.replace(destination)
        return destination
