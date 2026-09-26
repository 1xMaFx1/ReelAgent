from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    path: Path
    duration: float
    words: list[Word]


class TTSProvider(Protocol):
    async def synthesize(self, text: str, destination: Path) -> Speech: ...
