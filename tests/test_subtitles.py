from app.config import Settings
from app.subtitles.generator import SubtitleGenerator, escape_ass, timestamp
from app.tts.base import Word


def test_timestamp_roundover():
    assert timestamp(59.999) == "0:01:00.00"
    assert timestamp(3600) == "1:00:00.00"


def test_escape():
    assert "{" not in escape_ass(r"{\pos(1,2)} текст")
    assert "\\" not in escape_ass(r"{\pos(1,2)} текст")


def test_two_lines_and_utf8(tmp_path):
    path = SubtitleGenerator(Settings(_env_file=None)).generate(
        ["Оченьдлинноеслово" * 8, "Привет, это проверка субтитров. " * 15], 35, tmp_path / "s.ass"
    )
    result = path.read_text()
    assert "DejaVu Sans" in result
    events = [line for line in result.splitlines() if line.startswith("Dialogue:")]
    assert len(events) > 1
    assert all(line.count(r"\N") <= 1 for line in events)


def test_speed_adjustment(tmp_path):
    path = SubtitleGenerator(Settings(_env_file=None)).generate(
        ["Привет"], 10, tmp_path / "s.ass", [Word("Привет", 2, 4)], speed=2
    )
    assert "0:00:01.00,0:00:02.00" in path.read_text()
