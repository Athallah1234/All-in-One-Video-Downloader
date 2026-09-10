"""Offline regressions for session site authentication."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.core.format_builder import build_options, authentication_options
from app.core.models import Task
from app.core.utils import redact
from app.database.history import HistoryRepository
from app.services.settings import Settings, DEFAULTS
from app.workers.jobs import analyze, YDLLogger, DownloadWorker

AUTH = {"site_login": True, "username": "member@example.test", "password": " p@ss word! "}

class AuthenticationTests(unittest.TestCase):
    def test_all_modes_and_analysis(self):
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg"}):
            for mode in ("Video", "Audio", "Playlist", "Channel", "Subtitle", "Metadata", "Batch URL"):
                for analysis in (False, True):
                    opts = build_options(DEFAULTS | AUTH | {"mode": mode}, analyze=analysis)
                    self.assertEqual(opts["username"], AUTH["username"])
                    self.assertEqual(opts["password"], AUTH["password"])
            opts = build_options(DEFAULTS | AUTH | {"site_login": False})
            self.assertNotIn("password", opts)
            self.assertNotIn("username", opts)

    def test_validation(self):
        for changed in ({"username": " "}, {"password": ""}, {"password": "x\n"}, {"username": None}):
            with self.assertRaises(ValueError):
                authentication_options(AUTH | changed)

    def test_no_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(path)
            settings.values.update(AUTH)
            settings.save()
            for key in AUTH:
                self.assertNotIn(key, json.loads(path.read_text()))
            path.write_text(json.dumps(DEFAULTS | AUTH))
            self.assertFalse(Settings(path)["site_login"])
            self.assertEqual(Settings(path)["password"], "")
            repo = HistoryRepository(Path(directory) / "history.db")
            try:
                task = Task("https://example.test/video", DEFAULTS | AUTH, error=AUTH["password"])
                repo.save(task)
                record = repo.list()[0]
                for key in AUTH:
                    self.assertNotIn(key, json.loads(record["preferences"]))
                self.assertNotIn(AUTH["password"], record["error_message"])
                self.assertNotIn(AUTH["password"], repr(task))
            finally:
                repo.close()

    def test_diagnostics(self):
        from urllib.parse import quote
        ylog = YDLLogger(AUTH)
        for message in (AUTH["password"], quote(AUTH["password"], safe=""), AUTH["username"]):
            self.assertNotIn(message, ylog.clean("Rejected " + message))
        with patch("app.workers.jobs.YoutubeDL") as factory:
            factory.return_value.__enter__.return_value.extract_info.side_effect = RuntimeError("Rejected " + AUTH["password"])
            with self.assertRaises(ValueError) as raised:
                analyze("https://example.test/video", DEFAULTS | AUTH)
            self.assertNotIn(AUTH["password"], str(raised.exception))

    def test_download_failure_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Task("https://example.test/video", DEFAULTS | AUTH | {"output": directory})
            worker = DownloadWorker(task)
            failures = []
            worker.failed.connect(lambda identifier, message: failures.append(message))
            with patch("app.workers.jobs.YoutubeDL") as factory:
                factory.return_value.__enter__.return_value.extract_info.side_effect = RuntimeError("Rejected " + AUTH["password"])
                worker.run()
                self.assertEqual(factory.call_args.args[0]["password"], AUTH["password"])
            self.assertEqual(len(failures), 1)
            self.assertNotIn(AUTH["password"], failures[0])

    def test_settings_ui(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QLineEdit
        from app.ui.dialogs import SettingsDialog
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            dialog = SettingsDialog(settings)
            self.assertEqual(dialog.fields["password"].echoMode(), QLineEdit.EchoMode.Password)
            self.assertFalse(dialog.fields["password"].isEnabled())
            dialog.fields["site_login"].setChecked(True)
            dialog.fields["username"].setText(AUTH["username"])
            dialog.fields["password"].setText(AUTH["password"])
            dialog.save()
            self.assertEqual(settings["password"], AUTH["password"])
            self.assertTrue(settings["site_login"])
            dialog.deleteLater()
