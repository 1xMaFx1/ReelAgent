import asyncio
import json
import shutil
from pathlib import Path


async def command(args: list[str], cwd: Path | None = None) -> str:
    process = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=1200)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(f"{args[0]} failed: " + stderr.decode(errors="replace")[-1800:])
    return stdout.decode()


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe are required on the cloud runner")


async def probe(path: Path) -> dict:
    return json.loads(
        await command(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
        )
    )
