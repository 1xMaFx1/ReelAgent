from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class Metadata(Model):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=10, max_length=3000)
    hashtags: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def tags(self):
        if any(not tag.startswith("#") or any(c.isspace() for c in tag) for tag in self.hashtags):
            raise ValueError("Hashtags must start with # and contain no whitespace")
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
    PUBLISHED = "PUBLISHED"
    PARTIALLY_PUBLISHED = "PARTIALLY_PUBLISHED"
    FAILED = "FAILED"
