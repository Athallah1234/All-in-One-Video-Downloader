import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QObject, Signal
from utils.paths import LOG_DIR
from utils.security import redact

class LogEmitter(QObject):
    message = Signal(str, str)

class QtLogHandler(logging.Handler):
    def __init__(self, emitter: LogEmitter):
        super().__init__(); self.emitter = emitter
    def emit(self, record: logging.LogRecord) -> None:
        try:self.emitter.message.emit(record.levelname, self.format(record))
        except RuntimeError:
            # The application can close while a yt-dlp worker is still
            # unwinding. A deleted Qt receiver must never break logging or be
            # raised back into yt-dlp as an extraction failure.
            pass

class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))

def setup_logging() -> tuple[logging.Logger, LogEmitter]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("video_downloader")
    logger.setLevel(logging.DEBUG)
    emitter = LogEmitter()
    formatter = RedactingFormatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    if not logger.handlers:
        file_handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        qt_handler = QtLogHandler(emitter)
        for handler in (file_handler, qt_handler): handler.setFormatter(formatter); logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            if isinstance(handler, QtLogHandler): handler.emitter = emitter
    return logger, emitter
