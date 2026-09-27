"""Small synthetic cloud-only render to verify FFmpeg filters and codecs, without API keys."""

import asyncio
import tempfile
from pathlib import Path

from app.config import Settings
from app.media.base import Media
from app.subtitles.generator import SubtitleGenerator
from app.video.composer import VideoComposer
from app.video.ffmpeg_utils import command


async def main() -> None:
    s = Settings(
        _env_file=None,
        video_width=360,
        video_height=640,
        video_min_duration=10,
        video_max_duration=12,
        subtitle_font_size=24,
        subtitle_margin_v=100,
    )
    s.require_cloud()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        source, audio = work / "source.mp4", work / "voice.wav"
        await command(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=360x640:rate=30",
                "-t",
                "1",
                "-c:v",
                "libx264",
                str(source),
            ]
        )
        await command(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "11",
                str(audio),
            ]
        )
        captions = SubtitleGenerator(s).generate(
            ["Проверка облачного монтажа и русских субтитров."], 11, work / "subtitles.ass"
        )
        photo = work / "photo.jpg"
        await command(
            ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-frames:v", "1", str(photo)]
        )
        await VideoComposer(s).compose(
            [Media(source, "synthetic", "", ""), Media(photo, "still", "", "", True)],
            [5, 6],
            audio,
            captions,
            work / "reel.mp4",
            work,
            1,
            11,
        )
        print("Cloud smoke render passed: H.264/AAC, vertical MP4, ASS, duration")


if __name__ == "__main__":
    asyncio.run(main())
