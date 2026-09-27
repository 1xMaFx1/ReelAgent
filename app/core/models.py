from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Topic(Model):
    topic: str = Field(min_length=5, max_length=200)
    category: str = Field(min_length=2, max_length=60)


class Scene(Model):
    id: int = Field(ge=1)
    narration: str = Field(min_length=3, max_length=350)
    visual_query: str = Field(min_length=2, max_length=150)
    duration: float = Field(gt=0, le=15)


class Script(Model):
    topic: str = Field(min_length=5, max_length=200)
    hook: str = Field(min_length=3, max_length=100)
    scenes: list[Scene] = Field(min_length=4, max_length=7)
    ending: str = Field(min_length=3, max_length=180)

    @model_validator(mode="after")
    def scene_ids(self):
        if [s.id for s in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("Scene IDs must be consecutive, starting at 1")
        return self

    @property
    def segments(self) -> list[str]:
        return [self.hook, *(s.narration for s in self.scenes), self.ending]

    @property
    def text(self) -> str:
        return " ".join(self.segments)


class GeneratedScript(Script):
    @model_validator(mode="after")
    def narration_length(self):
        words = len(self.text.split())
        if not 65 <= words <= 100:
            raise ValueError(
                f"Narration has {words} words; write 65–100 Russian words across hook, scenes and ending"
            )
        return self


class NarrationDraft(Model):
    hook: str = Field(min_length=3, max_length=100)
    body: str = Field(min_length=350, max_length=1200)
    ending: str = Field(min_length=3, max_length=150)
    visual_query: str = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def length(self):
        words = len((self.hook + " " + self.body + " " + self.ending).split())
        if not 55 <= words <= 100:
            raise ValueError(
                f"Text has {words} words. Required total: 55–100 words. Expand body to 70 words."
            )
        return self


class Metadata(Model):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10, max_length=3000)
    hashtags: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def tags(self):
        if any(not tag.startswith("#") or any(c.isspace() for c in tag) for tag in self.hashtags):
            raise ValueError("Hashtags must start with # and contain no whitespace")
        return self


class SocialCopy(Model):
    title: str = Field(min_length=3, max_length=55)
    keywords: list[str] = Field(min_length=3, max_length=8)
    hashtags: list[str] = Field(min_length=3, max_length=6)

    @field_validator("hashtags", mode="before")
    @classmethod
    def normalize_tags(cls, values):
        import re

        if not isinstance(values, list):
            return values
        normalized = []
        for value in values:
            if not isinstance(value, str):
                return values
            tag = re.sub(r"[^\w]", "", value)[:40]
            if len(tag) >= 2 and "#" + tag not in normalized:
                normalized.append("#" + tag)
        for tag in ("#космос", "#наука", "#NASA"):
            if len(normalized) < 3 and tag not in normalized:
                normalized.append(tag)
        return normalized[:6]

    @model_validator(mode="after")
    def validate_copy(self):
        import re

        if any(not re.fullmatch(r"[\w\- ]{2,60}", word) for word in self.keywords):
            raise ValueError("Keywords must be short words or phrases without links")
        if any(not re.fullmatch(r"#\w{2,40}", tag) for tag in self.hashtags):
            raise ValueError("Invalid hashtag")
        return self


class SceneQueries(Model):
    queries: list[str] = Field(min_length=4, max_length=7)


class SafetyReview(Model):
    safe: bool
    reason: str


class Status(StrEnum):
    CREATED = "CREATED"
    GENERATING = "GENERATING"
    RENDERING = "RENDERING"
    READY = "READY"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    PARTIALLY_PUBLISHED = "PARTIALLY_PUBLISHED"
    FAILED = "FAILED"
