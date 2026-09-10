"""Netrc integration with real yt-dlp credential lookup, without network access."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from yt_dlp import YoutubeDL
from yt_dlp.extractor.common import InfoExtractor
from app.core.format_builder import build_options, authentication_options
from app.core.netrc_auth import read_netrc
from app.core.models import Task
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS, Settings
from app.workers.jobs import analyze, DownloadWorker, YDLLogger


class NetrcTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / ".netrc"
        self.path.write_text('# test accounts\nmachine example login "test user" password "sensitive password"\nmachine second login seconduser password secondsecret\ndefault login fallback password fallbacksecret\n', encoding="utf-8")
        self.prefs = DEFAULTS | {"use_netrc": True, "netrc_location": str(self.path), "output": self.temp.name}

    def test_real_extractor_lookup_and_all_modes(self):
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg"}):
            for mode in ("Video", "Audio", "Playlist", "Channel", "Subtitle", "Metadata", "Batch URL"):
                for analysis in (False, True):
                    opts = build_options(self.prefs | {"mode": mode}, analyze=analysis)
                    self.assertTrue(opts["usenetrc"])
                    self.assertNotIn("password", opts)
                    with YoutubeDL(opts) as ydl:
                        ie = InfoExtractor(ydl)
                        self.assertEqual(ie._get_login_info(netrc_machine="example"), ("test user", "sensitive password"))
                        self.assertEqual(ie._get_login_info(netrc_machine="second"), ("seconduser", "secondsecret"))
                        self.assertEqual(ie._get_login_info(netrc_machine="unknown"), ("fallback", "fallbacksecret"))

    def test_missing_entry(self):
        self.path.write_text("machine example login user password secret\n")
        with YoutubeDL(authentication_options(self.prefs)) as ydl:
            self.assertEqual(InfoExtractor(ydl)._get_login_info(netrc_machine="unknown"), (None, None))

    def test_paths_and_disabled(self):
        expected = str(self.path.resolve())
        self.assertEqual(read_netrc(self.prefs | {"netrc_location": self.temp.name})[0], expected)
        with patch("app.core.netrc_auth.Path.home", return_value=Path(self.temp.name)):
            self.assertEqual(read_netrc(self.prefs | {"netrc_location": ""})[0], expected)
        self.assertEqual(authentication_options(self.prefs | {"use_netrc": False, "netrc_location": "missing"}), {})
        with self.assertRaisesRegex(ValueError, "either"):
            authentication_options(self.prefs | {"site_login": True})

    def test_invalid_and_unreadable_do_not_leak(self):
        self.path.write_text("machine example login user password secret UnexpectedSecret\n")
        with self.assertRaises(ValueError) as caught:
            read_netrc(self.prefs)
        self.assertNotIn("UnexpectedSecret", str(caught.exception))
        with patch("app.core.netrc_auth.netrc.netrc", side_effect=PermissionError("private-path")):
            with self.assertRaisesRegex(ValueError, "Cannot read"):
                read_netrc(self.prefs)
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "not found"):
            read_netrc(self.prefs)

    def test_settings_and_history(self):
        settings = Settings(Path(self.temp.name) / "settings.json")
        settings.values.update(self.prefs)
        settings.save()
        loaded = Settings(settings.path)
        self.assertTrue(loaded["use_netrc"])
        self.assertEqual(loaded["netrc_location"], str(self.path))
        self.assertNotIn("sensitive password", settings.path.read_text())
        repo = HistoryRepository(Path(self.temp.name) / "history.db")
        self.addCleanup(repo.close)
        repo.save(Task("https://example.test", self.prefs))
        prefs = json.loads(repo.list()[0]["preferences"])
        self.assertNotIn("netrc_location", prefs)
        self.assertNotIn("use_netrc", prefs)

    def test_worker_failure_privacy(self):
        with patch("app.workers.jobs.YoutubeDL") as factory:
            factory.return_value.__enter__.return_value.extract_info.side_effect = RuntimeError("sensitive password")
            with self.assertRaises(ValueError) as caught:
                analyze("https://example.test", self.prefs)
            self.assertNotIn("sensitive password", str(caught.exception))
            worker = DownloadWorker(Task("https://example.test", self.prefs))
            errors = []
            worker.failed.connect(lambda identifier, error: errors.append(error))
            worker.run()
            self.assertTrue(factory.call_args.args[0]["usenetrc"])
            self.assertEqual(len(errors), 1)
            self.assertNotIn("sensitive password", errors[0])
        # Changed files and malformed parser tokens must not leak either.
        self.assertNotIn("newsecret", YDLLogger(self.prefs).clean("bad token newsecret"))

    def test_ui_switch_save_cancel_reset(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from app.ui.dialogs import SettingsDialog
        app = QApplication.instance() or QApplication([])
        settings = Settings(Path(self.temp.name) / "settings.json")
        dialog = SettingsDialog(settings)
        dialog.fields["site_login"].setChecked(True)
        dialog.fields["use_netrc"].setChecked(True)
        self.assertFalse(dialog.fields["site_login"].isChecked())
        dialog.fields["netrc_location"].setText(str(self.path))
        dialog.save()
        self.assertTrue(settings["use_netrc"])
        second = SettingsDialog(settings)
        second.reset()
        self.assertFalse(second.fields["use_netrc"].isChecked())
        second.reject()
        self.assertTrue(settings["use_netrc"])
        third = SettingsDialog(settings)
        third.fields["site_login"].setChecked(True)
        self.assertFalse(third.fields["use_netrc"].isChecked())
        for item in (dialog, second, third):
            item.deleteLater()
