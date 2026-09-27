from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Media:
    path: Path
    source_id: str
    source_url: str
    author: str
    is_image: bool = False
    zoom_out: bool = False
    mask_captions: bool = False


class VideoProvider(Protocol):
    async def fetch(self, query: str, destination: Path, used: set[str]) -> Media: ...
