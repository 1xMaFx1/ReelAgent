from pathlib import Path
from typing import Protocol

from app.core.models import Metadata


class Publisher(Protocol):
    @property
    def configured(self) -> bool: ...
    async def publish(self, path: Path, metadata: Metadata) -> str: ...
