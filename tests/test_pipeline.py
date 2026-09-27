from app.media.base import Media
from app.tts.base import Speech


class FakeTTS:
    def __init__(self, *args):
        pass

    async def synthesize(self, text, path):
        path.write_bytes(b"fake-audio")
        return Speech(path, 36, [])


class FakeMedia:
    def __init__(self, *args):
        pass

    async def fetch(self, query, destination, used):
        destination.write_bytes(b"fake-media")
        return Media(destination, str(destination), "https://example.com/stock", "test")


class FakeComposer:
    calls = 0

    def __init__(self, *args):
        pass

    async def compose(self, media, durations, audio, captions, video, *args):
        self.__class__.calls += 1
        video.write_bytes(b"fake-mp4-for-unit-test")
        return video
