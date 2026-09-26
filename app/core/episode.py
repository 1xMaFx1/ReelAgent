"""A reviewed first episode can be rendered without any paid API or account keys."""

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, model_validator

from app.core.models import Metadata, Script, Topic
from app.media.base import Media
from app.media.downloader import download


class Clip(BaseModel):
    query: str
    url: str
    credit: str
    source_page: str


class Episode(BaseModel):
    script: Script
    metadata: Metadata
    clips: list[Clip]
    fact_sources: list[str]

    @model_validator(mode="after")
    def validate_clips(self):
        if len(self.clips) != len(self.script.scenes):
            raise ValueError("Each scene needs one unique clip")
        if len({clip.url for clip in self.clips}) != len(self.clips):
            raise ValueError("Episode clips must be unique")
        for clip in self.clips:
            parsed = urlparse(clip.url)
            if parsed.scheme != "https" or not parsed.hostname.endswith(".nasa.gov"):
                raise ValueError("Prepared first episode uses official HTTPS NASA assets only")
        if [c.query for c in self.clips] != [s.visual_query for s in self.script.scenes]:
            raise ValueError("Clip queries must match the script")
        return self

    @classmethod
    def load(cls, path: Path) -> "Episode":
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


class EpisodeScriptProvider:
    def __init__(self, episode: Episode):
        self.episode = episode

    async def generate_topic(self, recent: list[str]) -> Topic:
        if self.episode.script.topic in recent:
            raise ValueError(
                "Prepared episode already used. Configure an LLM or a new reviewed episode."
            )
        return Topic(topic=self.episode.script.topic, category="космос")

    async def generate_script(self, topic: Topic) -> Script:
        return self.episode.script

    async def generate_metadata(self, script: Script) -> Metadata:
        return self.episode.metadata


class EpisodeVideoProvider:
    def __init__(self, episode: Episode, client: httpx.AsyncClient):
        self.episode, self.client = episode, client

    async def fetch(self, query: str, destination: Path, used: set[str]) -> Media:
        clip = next(clip for clip in self.episode.clips if clip.query == query)
        if clip.url in used:
            raise ValueError("Clip already used in this episode")
        result = await download(self.client, clip.url, destination.with_suffix(".webm"))
        used.add(clip.url)
        return Media(result, clip.url, clip.source_page, clip.credit)
