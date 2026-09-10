"""Bounded rotating, redacted logs with a Qt signal bridge."""
import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QObject, Signal
from app.core.utils import redact
from app.services.settings import ROOT


class LogBus(QObject):
    message = Signal(str, str)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


class QtHandler(logging.Handler):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus

    def emit(self, record):
        self.bus.message.emit(record.levelname, self.format(record))


def initialize() -> LogBus:
    (ROOT / "logs").mkdir(exist_ok=True)
    bus = LogBus()
    formatter = SafeFormatter("%(asctime)s  %(levelname)-7s  %(name)s  %(message)s")
    handlers = [RotatingFileHandler(ROOT / "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"), QtHandler(bus)]
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    return bus
