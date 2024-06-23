
from resources.lib.os.model.request.abstract import OpenSubtitlesRequest


class OpenSubtitlesGuessItRequest(OpenSubtitlesRequest):
    def __init__(self, filename="", **catch_overflow):
        self._filename = filename

        super().__init__()

        # ordered request params with defaults
        self.DEFAULT_LIST = dict(filename="")

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value
