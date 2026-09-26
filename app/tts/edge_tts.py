from pathlib import Path

import aiohttp
import edge_tts
from mutagen.mp3 import MP3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.tts.base import Speech, Word


class EdgeTTSProvider:
    def __init__(self, voice: str):
        self.voice = voice

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(max=8),
        retry=retry_if_exception_type(
            (aiohttp.ClientError, TimeoutError, edge_tts.exceptions.NoAudioReceived)
        ),
        reraise=True,
    )
    async def synthesize(self, text: str, destination: Path) -> Speech:
        destination.parent.mkdir(parents=True, exist_ok=True)
        words: list[Word] = []
        communicate = edge_tts.Communicate(text, self.voice, boundary="WordBoundary")
        with destination.open("wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 10_000_000
                    words.append(Word(chunk["text"], start, start + chunk["duration"] / 10_000_000))
        duration = MP3(destination).info.length
        if duration <= 0:
            raise ValueError("TTS returned empty audio")
        return Speech(destination, duration, words)
