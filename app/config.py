from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    app_env: Literal["local", "cloud", "test"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    llm_provider: Literal["gemini", "ollama"] = "gemini"
    ollama_model: str = "qwen2.5:7b"
    content_brief_file: Path | None = None
    pexels_api_key: SecretStr = SecretStr("")
    media_provider: Literal["pexels", "nasa"] = "pexels"
    tts_voice: str = "ru-RU-DmitryNeural"
    video_width: int = Field(default=1080, ge=180)
    video_height: int = Field(default=1920, ge=320)
    video_fps: int = Field(default=30, ge=24, le=60)
    video_min_duration: float = Field(default=30, ge=10)
    video_max_duration: float = Field(default=45, le=60)
    subtitle_font: str = "DejaVu Sans"
    subtitle_font_size: int = Field(default=64, ge=20, le=100)
    subtitle_margin_v: int = Field(default=350, ge=100, le=600)
    subtitle_chars_per_line: int = Field(default=26, ge=12, le=32)
    music_volume: float = Field(default=0.10, ge=0.08, le=0.12)
    youtube_client_id: SecretStr = SecretStr("")
    youtube_client_secret: SecretStr = SecretStr("")
    youtube_refresh_token: SecretStr = SecretStr("")
    youtube_privacy_status: Literal["public", "private", "unlisted"] = "public"
    youtube_publisher: Literal["direct", "buffer"] = "direct"
    youtube_channel_id: str = "UCr74LNUyePqX4CLS9sI5IPg"
    buffer_api_key: SecretStr = SecretStr("")
    buffer_channel_id: str = ""
    publication_timezone: str = "Europe/Simferopol"
    publication_hour: int = Field(default=8, ge=0, le=23)
    publication_minute: int = Field(default=0, ge=0, le=59)
    instagram_access_token: SecretStr = SecretStr("")
    instagram_account_id: str = ""
    instagram_api_version: str = "v24.0"
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: SecretStr = SecretStr("")
    cloudinary_api_secret: SecretStr = SecretStr("")
    auto_publish_youtube: bool = False
    auto_publish_instagram: bool = False
    dry_run: bool = True
    allow_cta: bool = False
    episode_file: Path | None = None
    base_dir: Path = Path(".")

    @field_validator("episode_file", "content_brief_file", mode="before")
    @classmethod
    def empty_episode(cls, value):
        return value or None

    @model_validator(mode="after")
    def validate_video(self):
        if self.video_min_duration >= self.video_max_duration:
            raise ValueError("VIDEO_MIN_DURATION must be below VIDEO_MAX_DURATION")
        if self.video_width % 2 or self.video_height % 2:
            raise ValueError("Video dimensions must be even")
        if self.video_width * 16 != self.video_height * 9:
            raise ValueError("Video aspect ratio must be 9:16")
        if not self.gemini_model.strip():
            raise ValueError("Set GEMINI_MODEL to a model available in AI Studio")
        return self

    def path(self, name: str) -> Path:
        return self.base_dir.resolve() / name

    def require_generation_keys(self) -> None:
        required = []
        if self.llm_provider == "gemini":
            required.append("gemini_api_key")
        if self.media_provider == "pexels":
            required.append("pexels_api_key")
        missing = [name for name in required if not getattr(self, name).get_secret_value()]
        if missing:
            raise ValueError("Missing settings: " + ", ".join(x.upper() for x in missing))

    def require_cloud(self) -> None:
        import sys

        if self.app_env != "cloud" or sys.platform == "darwin":
            raise ValueError(
                "Render is cloud-only. Run GitHub Actions or Docker on a Linux server (APP_ENV=cloud)."
            )
