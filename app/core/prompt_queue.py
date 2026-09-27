"""A dated, immutable-on-first-attempt weekly plan supplied by the owner."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.models import Script, SocialCopy


class PromptEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    day: int = Field(ge=1, le=7)
    hour: Literal[8, 12, 17] = 8
    prompt: str = Field(min_length=10, max_length=16000)
    topic: str = Field(min_length=5, max_length=200)
    mode: Literal["generate", "anchor", "recap"] = "generate"
    facts: str = Field(default="", max_length=12000)
    sources: list[HttpUrl] = Field(default_factory=list)
    script: Script | None = None
    social: SocialCopy | None = Field(default=None, alias="copy")
    overlays: list[str] = Field(default_factory=list)
    zoom_out: bool = False
    min_seconds: float = Field(default=30, ge=10, le=44)
    max_seconds: float = Field(default=45, gt=10, le=60)
    recap_days: list[int] = Field(default_factory=list)
    anchor_run_id: int | None = Field(default=None, gt=0)
    anchor_date: date | None = None

    @model_validator(mode="after")
    def validate_entry(self):
        if self.min_seconds >= self.max_seconds:
            raise ValueError("Invalid duration range")
        if self.script and not self.social:
            raise ValueError("Reviewed script requires title, keywords and hashtags")
        if self.overlays and (not self.script or len(self.overlays) != len(self.script.scenes)):
            raise ValueError("One overlay is required per reviewed scene")
        if self.mode == "anchor" and not (self.anchor_run_id and self.anchor_date):
            raise ValueError("Anchor needs its existing cloud run and date")
        if self.mode == "recap":
            if not self.script or len(self.recap_days) != len(self.script.scenes):
                raise ValueError("Recap requires one existing day per scene")
            if len(set(self.recap_days)) != len(self.recap_days) or any(
                not 1 <= d < self.day for d in self.recap_days
            ):
                raise ValueError("Recap can reference distinct earlier days only")
        return self

    @property
    def key(self) -> str:
        value = self.model_dump(mode="json", exclude={"day"})
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:16]


class WeeklyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    start_date: date
    entries: list[PromptEntry] = Field(min_length=7, max_length=21)

    @model_validator(mode="after")
    def seven_days(self):
        expected = [(day, hour) for day in range(1, 8) for hour in (8, 12, 17)]
        actual = [(entry.day, entry.hour) for entry in self.entries]
        if actual != expected and actual != [(day, 8) for day in range(1, 8)]:
            raise ValueError("Expected 7 daily entries or 21 entries ordered by day and 08/12/17")
        for day in range(1, 8):
            texts = [e.script.text for e in self.entries if e.day == day and e.script]
            if len(texts) != len(set(texts)):
                raise ValueError("Duplicate scripts within one day")
        if len({entry.key for entry in self.entries}) != len(self.entries):
            raise ValueError("Duplicate prompts in weekly plan")
        return self

    @classmethod
    def load(cls, path: Path):
        if not path.is_file():
            raise ValueError("Нужен новый пакет из семи промптов Claude: " + str(path))
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def for_date(self, day: str, hour: int = 8) -> PromptEntry:
        index = (date.fromisoformat(day) - self.start_date).days
        if not 0 <= index < 7:
            raise ValueError(
                "На эту дату нет промпта. Передайте новый недельный пакет; случайная тема не выбирается."
            )
        return self.entry(index + 1, hour)

    def entry(self, day: int, hour: int = 8) -> PromptEntry:
        for entry in self.entries:
            if entry.day == day and entry.hour == hour:
                return entry
        raise ValueError("На этот час нет подготовленного сценария")

    def date_for(self, entry: PromptEntry) -> str:
        return (self.start_date + timedelta(days=entry.day - 1)).isoformat()
