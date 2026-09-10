"""State-machine coverage for whole-job automatic retries."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from app.core.models import Status
from app.core.queue_manager import QueueManager
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS, Settings
from app.ui.dialogs import SettingsDialog
from app.ui.library import QueueView


class FakeTimer:
    instances = []

    def __init__(self, parent=None):
        self.callback = None
        self.interval = None
        self.active = False
        self.timeout = self
        self.instances.append(self)

    @staticmethod
    def singleShot(interval, callback):
        pass

    def connect(self, callback):
        self.callback = callback

    def setSingleShot(self, value):
        pass

    def start(self, interval):
        self.interval = interval
        self.active = True

    def stop(self):
        self.active = False

    def deleteLater(self):
        pass

    def fire(self):
        self.active = False
        self.callback()


class AutoRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        FakeTimer.instances.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = HistoryRepository(Path(self.temp.name) / "history.db")
        self.addCleanup(self.repo.close)
        self.timer_patch = patch("app.core.queue_manager.QTimer", FakeTimer)
        self.timer_patch.start()
        self.addCleanup(self.timer_patch.stop)
        self.single_patch = patch("app.core.queue_manager.QTimer.singleShot")
        self.single_patch.start()
        self.addCleanup(self.single_patch.stop)
        self.manager = QueueManager(self.repo)
        self.manager.pump = Mock()
        self.options = DEFAULTS | {
            "auto_retry": True, "auto_retry_attempts": 3,
            "auto_retry_base_delay": 2, "auto_retry_max_delay": 5,
        }
        self.task = self.manager.add("https://example.test/video", self.options, "Video")

    def test_exponential_cap_success_and_history(self):
        for attempt, delay in ((1, 2), (2, 4), (3, 5)):
            self.manager.fail(self.task.id, f"failure {attempt}")
            self.assertEqual(self.task.status, Status.RETRYING)
            self.assertEqual(self.task.retry_attempt, attempt)
            self.assertEqual(self.task.retry_delay, delay)
            self.assertEqual(FakeTimer.instances[-1].interval, delay * 1000)
            self.assertNotIn(self.task.id, self.manager.workers)
            FakeTimer.instances[-1].fire()
            self.assertEqual(self.task.status, Status.WAITING)
        self.manager.fail(self.task.id, "final failure")
        self.assertEqual(self.task.status, Status.FAILED)
        self.assertEqual(self.repo.list()[0]["status"], Status.FAILED)

    def test_cancel_and_retry_now(self):
        self.manager.fail(self.task.id, "temporary")
        timer = FakeTimer.instances[-1]
        self.manager.retry_now(self.task.id)
        self.assertFalse(timer.active)
        self.assertEqual(self.task.status, Status.WAITING)
        self.manager.fail(self.task.id, "again")
        timer = FakeTimer.instances[-1]
        self.manager.cancel(self.task.id)
        self.assertFalse(timer.active)
        self.assertEqual(self.task.status, Status.CANCELLED)
        timer.fire()
        self.assertEqual(self.task.status, Status.CANCELLED)

    def test_disabled_and_shutdown(self):
        self.task.options["auto_retry"] = False
        self.manager.fail(self.task.id, "no retry")
        self.assertEqual(self.task.status, Status.FAILED)
        other = self.manager.add("https://example.test/other", self.options, "Video")
        self.manager.fail(other.id, "temporary")
        self.manager.shutdown()
        self.assertEqual(other.status, Status.CANCELLED)
        self.assertFalse(FakeTimer.instances[-1].active)

    def test_ui_and_settings_validation(self):
        settings = Settings(Path(self.temp.name) / "settings.json")
        dialog = SettingsDialog(settings)
        self.assertFalse(dialog.fields["auto_retry_attempts"].isEnabled())
        dialog.fields["auto_retry"].setChecked(True)
        self.assertTrue(dialog.fields["auto_retry_attempts"].isEnabled())
        dialog.fields["auto_retry_base_delay"].setValue(10)
        dialog.fields["auto_retry_max_delay"].setValue(5)
        with patch("app.ui.dialogs.QMessageBox.warning") as warning:
            dialog.save()
            warning.assert_called_once()
            self.assertEqual(dialog.result(), 0)
        dialog.fields["auto_retry_max_delay"].setValue(20)
        dialog.save()
        self.assertTrue(settings["auto_retry"])
        view = QueueView(self.manager)
        self.manager.tasks[self.task.id].status = Status.RETRYING
        self.manager.tasks[self.task.id].retry_attempt = 1
        self.manager.tasks[self.task.id].retry_limit = 3
        self.manager.tasks[self.task.id].next_retry_at = "2999-01-01T00:00:00+00:00"
        view.refresh()
        self.assertIn("Retrying in", view.table.item(0, 2).text())
        view.deleteLater()

    def test_corrupt_ranges_are_clamped(self):
        path = Path(self.temp.name) / "settings.json"
        path.write_text('{"auto_retry_attempts": 999999, "auto_retry_base_delay": 0, "auto_retry_max_delay": 999999}')
        settings = Settings(path)
        self.assertEqual(settings["auto_retry_attempts"], 20)
        self.assertEqual(settings["auto_retry_base_delay"], 1)
        self.assertEqual(settings["auto_retry_max_delay"], 86400)
        self.task.options.update(auto_retry_attempts="invalid", auto_retry_base_delay=None,
                                 auto_retry_max_delay=10**100)
        self.assertEqual(self.manager.retry_limit(self.task), 3)
        self.assertEqual(self.manager.retry_delay(self.task), 2)
