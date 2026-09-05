import logging

from utils.logger import QtLogHandler
from workers.tasks import safe_emit


class DeletedSignal:
    def emit(self,*_args):
        raise RuntimeError("Signal source has been deleted")


def test_safe_emit_ignores_deleted_qt_signal():
    safe_emit(DeletedSignal(),"value")


def test_qt_log_handler_does_not_raise_when_emitter_is_deleted():
    emitter=type("Emitter",(),{"message":DeletedSignal()})()
    handler=QtLogHandler(emitter)
    handler.emit(logging.LogRecord("test",logging.WARNING,__file__,1,"warning",(),None))
