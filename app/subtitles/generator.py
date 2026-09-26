import textwrap
from pathlib import Path

from app.config import Settings
from app.tts.base import Word


def timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


class SubtitleGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(
        self,
        segments: list[str],
        duration: float,
        path: Path,
        words: list[Word] | None = None,
        speed: float = 1.0,
    ) -> Path:
        s = self.settings
        if not words:
            tokens = " ".join(segments).split()
            total = sum(len(t) for t in tokens)
            cursor = 0.0
            words = []
            for token in tokens:
                end = cursor + duration * len(token) / total
                words.append(Word(token, cursor, end))
                cursor = end
            speed = 1.0
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {s.video_width}
PlayResY: {s.video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s.subtitle_font},{s.subtitle_font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,160,{s.subtitle_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: list[str] = []
        group: list[Word] = []

        def flush() -> None:
            if not group:
                return
            lines = textwrap.wrap(
                escape_ass(" ".join(w.text for w in group)), width=s.subtitle_chars_per_line
            )
            start = group[0].start / speed
            end = min(duration, group[-1].end / speed)
            if end > start:
                body = r"\N".join(lines)
                events.append(
                    f"Dialogue: 0,{timestamp(start)},{timestamp(end)},Default,,0,0,0,,{body}"
                )
            group.clear()

        # Split very long tokens so even a single token cannot create >2 lines.
        expanded: list[Word] = []
        for word in words:
            chunks = textwrap.wrap(word.text, width=s.subtitle_chars_per_line)
            for i, chunk in enumerate(chunks):
                part = (word.end - word.start) / len(chunks)
                expanded.append(Word(chunk, word.start + i * part, word.start + (i + 1) * part))
        for word in expanded:
            candidate = " ".join([*(w.text for w in group), word.text])
            if group and (
                len(textwrap.wrap(candidate, s.subtitle_chars_per_line)) > 2
                or word.end - group[0].start > 2.8 * speed
            ):
                flush()
            group.append(word)
        flush()
        path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        return path
