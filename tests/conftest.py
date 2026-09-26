import pytest

from app.core.models import Script


@pytest.fixture
def script():
    return Script(
        topic="Почему звёзды мерцают",
        hook="Почему мерцают звёзды?",
        scenes=[
            {
                "id": i,
                "narration": "Свет звёзд проходит через атмосферу нашей планеты.",
                "visual_query": "night sky stars",
                "duration": 6,
            }
            for i in range(1, 5)
        ],
        ending="За пределами атмосферы мерцание исчезает.",
    )
