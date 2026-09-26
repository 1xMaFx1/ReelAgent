import asyncio
from pathlib import Path

import pytest

import app.video.composer as module
from app.config import Settings
from app.media.base import Media
from app.video.composer import VideoComposer


@pytest.mark.parametrize("with_music", [False, True])
def test_composer_commands_and_atomic_output(tmp_path, monkeypatch, with_music):
    commands = []
    monkeypatch.setattr(Settings, "require_cloud", lambda self: None)
    monkeypatch.setattr(module, "check_ffmpeg", lambda: None)

    async def fake_command(args, cwd=None):
        commands.append(args)
        if "-movflags" in args:
            Path(args[-1]).write_bytes(b"unit-test-not-a-real-mp4")
        return ""

    async def fake_probe(path):
        return {
            "format": {"duration": "36"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }

    monkeypatch.setattr(module, "command", fake_command)
    monkeypatch.setattr(module, "probe", fake_probe)
    settings = Settings(_env_file=None, base_dir=tmp_path)
    if with_music:
        directory = tmp_path / "assets/music"
        directory.mkdir(parents=True)
        (directory / "music.mp3").write_bytes(b"unit-test")
    captions = tmp_path / "subtitles.ass"
    captions.write_text("ASS unit test")
    destination = tmp_path / "output/reel.mp4"
    media = [
        Media(tmp_path / "clip.mp4", "one", "", ""),
        Media(tmp_path / "photo.jpg", "two", "", "", True),
    ]
    result = asyncio.run(
        VideoComposer(settings).compose(
            media, [18, 18], tmp_path / "voice.mp3", captions, destination, tmp_path, 1, 36
        )
    )
    assert result.exists() and not (destination.parent / "reel.partial.mp4").exists()
    assert "-stream_loop" in commands[0] and "-loop" in commands[1]
    assert (tmp_path / "concat.txt").read_text().splitlines() == [
        "file 'segment_00.mp4'",
        "file 'segment_01.mp4'",
    ]
    final = commands[-1]
    filters = final[final.index("-filter_complex") + 1]
    assert ("amix" in filters) == with_music
    assert "loudnorm" in filters and "ass=captions.ass" in final
