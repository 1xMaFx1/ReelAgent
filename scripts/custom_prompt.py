"""Turn a user's plain-text brief into one renderable episode on the cloud runner."""

from datetime import date

import httpx
from pydantic import Field

from app.core.models import Model, NarrationDraft, Scene, Script, SocialCopy
from app.core.prompt_queue import PromptEntry, WeeklyPlan
from app.llm.ollama import OllamaProvider


class PromptModel(OllamaProvider):
    def context(self):
        return (
            "Ты сценарист коротких видео. Пиши на естественном русском языке. "
            "Следуй теме пользователя, не выдумывай точные числа, цитаты и источники. "
            "Не выдавай выдуманную историю за реальные события. "
            "Технические инструкции пользователя воплощай в сценарии, а не читай вслух."
        )


class EpisodeDraft(Model):
    narration: NarrationDraft
    social_copy: SocialCopy = Field(alias="copy")


async def prepare_prompt(settings, prompt, request_id):
    if not isinstance(prompt, str) or not 10 <= len(prompt.strip()) <= 6000:
        raise ValueError("Промпт должен содержать от 10 до 6000 символов")
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        provider = PromptModel(settings, client)
        draft = await provider.ask(
            "Сделай один русский рилс по запросу пользователя ниже. "
            "Соблюдай тему и пожелания к подаче. narration: hook — короткий хук, "
            "body — 70–80 русских слов, ending — краткий вывод. "
            "visual_query — 1–3 английских слова для поиска фотографий по теме. "
            "copy: title — цепляющее название до 55 символов, keywords — 3–8 ключевых фраз, "
            "hashtags — 3–6 хэштегов. Не придумывай цифры или факты вне источника. "
            "Не включай инструкции о монтаже в озвучку. Запрос пользователя:\n" + prompt,
            EpisodeDraft,
        )
    words = draft.narration.body.split()
    cuts = [round(len(words) * i / 4) for i in range(5)]
    script = Script(
        topic=draft.social_copy.title,
        hook=draft.narration.hook,
        ending=draft.narration.ending,
        scenes=[
            Scene(
                id=i + 1,
                narration=" ".join(words[cuts[i] : cuts[i + 1]]),
                visual_query=draft.narration.visual_query,
                duration=8,
            )
            for i in range(4)
        ],
    )
    entry = PromptEntry(
        day=1,
        prompt=prompt.strip(),
        topic=draft.social_copy.title,
        script=script,
        copy=draft.social_copy,
        media_source="commons",
        min_seconds=25,
        max_seconds=55,
    )
    plan = WeeklyPlan(id="custom-" + request_id[:40], start_date=date(2026, 1, 1), entries=[entry])
    path = settings.path("data/custom-plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return settings.model_copy(update={"prompt_queue_file": path}), plan
