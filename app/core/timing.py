import bisect
import re

from app.core.models import Script
from app.tts.base import Speech


def letter_count(text: str) -> int:
    return len(re.sub(r"[^\w]", "", text))


def fit_timing(
    script: Script, speech: Speech, minimum: float, maximum: float
) -> tuple[float, float, list[float]]:
    target = min(maximum - 0.15, max(minimum + 0.15, speech.duration))
    speed = speech.duration / target
    if not 0.75 <= speed <= 1.35:
        raise ValueError("Narration is too short/long: regenerate a script with 75–90 words")
    segments = script.segments
    weights = [letter_count(text) for text in segments]
    total = sum(weights)
    cuts = [0.0]
    accumulated = 0
    word_ends = []
    count = 0
    for word in speech.words:
        count += letter_count(word.text)
        word_ends.append(count)
    exact = count == total and bool(word_ends)
    for weight in weights[:-1]:
        accumulated += weight
        index = bisect.bisect_left(word_ends, accumulated) + 1 if exact else 0
        cut = (
            speech.words[index].start / speed
            if exact and index < len(speech.words)
            else target * accumulated / total
        )
        cuts.append(cut)
    cuts.append(target)
    intervals = [b - a for a, b in zip(cuts, cuts[1:])]
    durations = intervals[1:-1]
    durations[0] += intervals[0]
    durations[-1] += intervals[-1]
    return target, speed, durations
