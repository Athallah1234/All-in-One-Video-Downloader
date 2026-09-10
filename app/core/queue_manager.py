"""Bounded queue. All task mutations and persistence happen on the GUI thread."""
from datetime import datetime, timedelta, timezone
import logging
from PySide6.QtCore import QObject, Signal, QTimer
from app.core.models import Task, Status, TERMINAL
from app.workers.jobs import DownloadWorker

logger = logging.getLogger(__name__)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class QueueManager(QObject):
    changed = Signal()
    ended = Signal(object)

    def __init__(self, repository, concurrency=1, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.concurrency = concurrency
        self.tasks = {}
        self.workers = {}
        self.closing = False
        self.pause_states = {}
        self.pause_tokens = {}
        self.retry_timers = {}

    def add(self, url: str, options: dict, mode: str):
        task = Task(url=url, options=options.copy(), media_type=mode)
        task.options.setdefault("_temp_id", task.id)
        self.tasks[task.id] = task
        task.history_id = self.repository.save(task)
        logger.info("Download queued (%s)", mode)
        self.changed.emit()
        QTimer.singleShot(0, self.pump)
        return task

    def pump(self):
        if self.closing:
            return
        for task in list(self.tasks.values()):
            if len(self.workers) >= max(1, min(3, self.concurrency)):
                break
            # Archive writes must not race across separate YoutubeDL instances.
            if task.status != Status.WAITING:
                continue
            if any(self.tasks[i].url == task.url and self.tasks[i].options["output"] == task.options["output"] for i in self.workers):
                continue
            if self.workers and (task.options.get("archive") or any(self.tasks[i].options.get("archive") for i in self.workers)):
                continue
            worker = DownloadWorker(task, self)
            self.workers[task.id] = worker
            task.status = Status.ANALYZING
            task.started_at = now()
            worker.progress.connect(self.progress)
            worker.metadata.connect(self.metadata)
            worker.completed.connect(self.complete)
            worker.failed.connect(self.fail)
            worker.cancelled.connect(self.cancelled)
            worker.paused.connect(self.paused)
            worker.finished.connect(lambda identifier=task.id: self.cleanup(identifier))
            self.repository.save(task)
            logger.info("Download started")
            worker.start()
        self.changed.emit()

    def cleanup(self, identifier):
        worker = self.workers.pop(identifier)
        worker.deleteLater()
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def retry_delay(self, task):
        base = self.bounded_int(task.options.get("auto_retry_base_delay"), 2, 1, 3600)
        maximum = self.bounded_int(task.options.get("auto_retry_max_delay"), 60, base, 86400)
        return min(maximum, base * (2 ** task.retry_attempt))

    def retry_limit(self, task):
        return self.bounded_int(task.options.get("auto_retry_attempts"), 3, 1, 20)

    @staticmethod
    def bounded_int(value, default, minimum, maximum):
        try:
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            value = default
        return max(minimum, min(maximum, value))

    def schedule_retry(self, identifier, error):
        task = self.tasks[identifier]
        task.retry_limit = self.retry_limit(task)
        delay = self.retry_delay(task)
        task.retry_attempt += 1
        task.retry_delay = delay
        task.next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
        task.status, task.error, task.completed_at = Status.RETRYING, error, ""
        task.speed, task.eta = 0, None
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda i=identifier: self.retry_ready(i))
        self.retry_timers[identifier] = timer
        timer.start(delay * 1000)
        self.repository.save(task)
        logger.info("Download retry %d/%d scheduled in %d seconds", task.retry_attempt, task.retry_limit, delay)
        self.changed.emit()

    def retry_ready(self, identifier):
        timer = self.retry_timers.pop(identifier, None)
        if timer:
            timer.deleteLater()
        task = self.tasks.get(identifier)
        if self.closing or not task or task.status != Status.RETRYING:
            return
        if identifier in self.workers:
            QTimer.singleShot(50, lambda i=identifier: self.retry_ready(i))
            return
        task.status, task.error, task.next_retry_at = Status.WAITING, "", ""
        task.retry_delay = 0
        self.repository.save(task)
        self.changed.emit()
        self.pump()

    def retry_now(self, identifier):
        task = self.tasks.get(identifier)
        if not task or task.status != Status.RETRYING or self.closing:
            return
        timer = self.retry_timers.pop(identifier, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        task.next_retry_at, task.retry_delay = "", 0
        task.status, task.error = Status.WAITING, ""
        self.repository.save(task)
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def progress(self, identifier, values):
        task = self.tasks[identifier]
        for key, value in values.items():
            if task.status in {Status.PAUSING, Status.PAUSED} and key in {"status", "speed", "eta"}:
                if key == "status":
                    self.pause_states[identifier] = value
                continue
            if key != "file_path" or value:
                setattr(task, key, value)
        self.changed.emit()

    def metadata(self, identifier, values):
        task = self.tasks[identifier]
        for key in ("title", "extractor"):
            if values.get(key):
                setattr(task, key, values[key])
        if values.get("playlist_index"):
            task.item = f"{values['playlist_index']} / {values.get('playlist_count') or values.get('n_entries') or '?'}"
        self.changed.emit()

    def finish(self, identifier, status, error=""):
        task = self.tasks[identifier]
        self.pause_states.pop(identifier, None)
        self.pause_tokens.pop(identifier, None)
        timer = self.retry_timers.pop(identifier, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        task.status, task.error, task.completed_at = status, error, now()
        task.speed, task.eta = 0, None
        task.retry_delay, task.next_retry_at = 0, ""
        if status == Status.COMPLETED:
            task.progress = 100
        self.repository.save(task)
        logger.info("Download %s", str(status).lower())
        self.changed.emit()
        self.ended.emit(task)

    def complete(self, identifier, values):
        self.progress(identifier, values)
        self.finish(identifier, Status.COMPLETED)

    def fail(self, identifier, error):
        task = self.tasks[identifier]
        if (not self.closing and task.options.get("auto_retry")
                and task.retry_attempt < self.retry_limit(task)):
            self.schedule_retry(identifier, error)
        else:
            self.finish(identifier, Status.FAILED, error)

    def cancelled(self, identifier):
        self.finish(identifier, Status.CANCELLED)

    def can_pause(self, identifier):
        return not self.closing and self.tasks[identifier].status in {
            Status.WAITING, Status.ANALYZING, Status.DOWNLOADING, Status.PROCESSING}

    def can_resume(self, identifier):
        return not self.closing and self.tasks[identifier].status in {Status.PAUSING, Status.PAUSED}

    def pause(self, identifier):
        if not self.can_pause(identifier):
            return
        task = self.tasks[identifier]
        self.pause_states[identifier] = task.status
        if identifier in self.workers:
            self.pause_tokens[identifier] = self.workers[identifier].pause()
            task.status = Status.PAUSING
        else:
            task.status = Status.PAUSED
        task.speed, task.eta = 0, None
        self.repository.save(task)
        self.changed.emit()

    def paused(self, identifier, generation):
        task = self.tasks[identifier]
        if task.status == Status.PAUSING and self.pause_tokens.get(identifier) == generation:
            task.status = Status.PAUSED
            self.repository.save(task)
            self.changed.emit()

    def resume(self, identifier):
        if not self.can_resume(identifier):
            return
        task = self.tasks[identifier]
        task.status = self.pause_states.pop(identifier, Status.WAITING)
        self.pause_tokens.pop(identifier, None)
        if identifier in self.workers:
            self.workers[identifier].resume()
        else:
            task.status = Status.WAITING
        self.repository.save(task)
        self.changed.emit()
        QTimer.singleShot(0, self.pump)

    def cancel(self, identifier):
        if self.tasks[identifier].status == Status.RETRYING:
            self.finish(identifier, Status.CANCELLED)
        elif identifier in self.workers:
            self.workers[identifier].cancel()
        elif self.tasks[identifier].status in {Status.WAITING, Status.PAUSED}:
            self.finish(identifier, Status.CANCELLED)

    def retry(self, identifier):
        task = self.tasks[identifier]
        if task.status in TERMINAL and identifier not in self.workers:
            return self.add(task.url, task.options, task.media_type)

    def remove(self, identifiers):
        for identifier in identifiers:
            if identifier in self.tasks and self.tasks[identifier].status in TERMINAL and identifier not in self.workers:
                del self.tasks[identifier]
        self.changed.emit()

    def shutdown(self):
        self.closing = True
        for identifier in list(self.tasks):
            self.cancel(identifier)
