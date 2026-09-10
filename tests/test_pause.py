"""Queue state and cooperative pause regressions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from app.core.models import Task, Status
from app.core.queue_manager import QueueManager
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS
from app.workers.jobs import DownloadWorker, Cancelled
from app.ui.library import QueueView


class PauseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.db"
        self.repo = HistoryRepository(self.path)
        self.addCleanup(self.repo.close)
        self.manager = QueueManager(self.repo)
        self.addCleanup(self.manager.shutdown)
        # Run scheduling explicitly in these state-machine tests.
        self.timer = patch("app.core.queue_manager.QTimer.singleShot")
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.task = self.manager.add("https://example.test/video", DEFAULTS, "Video")

    def test_waiting_pause_resume_cancel_ui(self):
        view = QueueView(self.manager)
        view.refresh()
        view.table.selectRow(0)
        self.assertTrue(view.pause_button.isEnabled())
        view.pause_button.click()
        self.assertEqual(self.task.status, Status.PAUSED)
        self.manager.pump()
        self.assertFalse(self.manager.workers)
        self.assertTrue(view.resume_button.isEnabled())
        view.resume_button.click()
        self.assertEqual(self.task.status, Status.WAITING)
        self.manager.pause(self.task.id)
        self.manager.cancel(self.task.id)
        self.assertEqual(self.task.status, Status.CANCELLED)
        self.assertFalse(view.resume_button.isEnabled())
        view.deleteLater()

    def test_acknowledgment_stale_signals_and_slots(self):
        worker = DownloadWorker(self.task)
        self.manager.workers[self.task.id] = worker
        self.task.status = Status.DOWNLOADING
        self.manager.pause(self.task.id)
        first = worker.pause_generation
        self.assertEqual(self.task.status, Status.PAUSING)
        self.manager.progress(self.task.id, {"status": Status.DOWNLOADING, "speed": 50, "eta": 9})
        self.assertEqual(self.task.status, Status.PAUSING)
        self.assertEqual(self.task.speed, 0)
        self.manager.resume(self.task.id)
        self.manager.pause(self.task.id)
        self.manager.paused(self.task.id, first)
        self.assertEqual(self.task.status, Status.PAUSING)
        self.manager.paused(self.task.id, worker.pause_generation)
        self.assertEqual(self.task.status, Status.PAUSED)
        second = self.manager.add("https://example.test/second", DEFAULTS, "Video")
        self.manager.pump()
        self.assertEqual(second.status, Status.WAITING)
        self.assertEqual(len(self.manager.workers), 1)
        self.manager.complete(self.task.id, {})
        self.manager.paused(self.task.id, worker.pause_generation)
        self.assertEqual(self.task.status, Status.COMPLETED)
        self.assertFalse(self.manager.can_resume(self.task.id))
        self.manager.workers.clear()
        worker.cancel()

    def test_worker_resume_and_cancel_wake_waiters(self):
        worker = DownloadWorker(self.task)
        for cancel in (False, True):
            worker.pause()
            finished = threading.Event()
            outcomes = []
            def checkpoint():
                try:
                    worker.check()
                    outcomes.append("resumed")
                except Cancelled:
                    outcomes.append("cancelled")
                finally:
                    finished.set()
            thread = threading.Thread(target=checkpoint, daemon=True)
            thread.start()
            self.assertFalse(finished.wait(.1))
            worker.cancel() if cancel else worker.resume()
            self.assertTrue(finished.wait(2))
            thread.join(2)
            self.assertEqual(outcomes, ["cancelled" if cancel else "resumed"])

    def test_restart_marks_paused_history_failed(self):
        self.manager.pause(self.task.id)
        repo = HistoryRepository(self.path)
        try:
            self.assertEqual(repo.list()[0]["status"], Status.FAILED)
        finally:
            repo.close()

    def test_shutdown_cancels_waiting_paused(self):
        self.manager.pause(self.task.id)
        self.manager.shutdown()
        self.assertEqual(self.task.status, Status.CANCELLED)
        self.assertFalse(self.manager.can_resume(self.task.id))
