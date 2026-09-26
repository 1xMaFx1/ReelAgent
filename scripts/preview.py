"""Create a small preview in the cloud alongside the completed MP4."""

import subprocess
from pathlib import Path

from app.config import Settings

Settings().require_cloud()
for video in Path("output").glob("*/reel.mp4"):
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "8",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=540:960",
            str(video.with_name("preview.jpg")),
        ],
        check=True,
    )
