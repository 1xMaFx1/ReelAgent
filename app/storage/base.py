from pathlib import Path
from typing import Protocol


class StorageProvider(Protocol):
    async def upload(self, path: Path, public_id: str) -> str: ...
