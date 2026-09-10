"""FFmpeg/ffprobe version parsing, execution, caching and UI status tests."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from app.core.ffmpeg import (
    MINIMUM_LABEL, _inspect_cached, compatibility, detect, inspect_binary,
    parse_version_line, version_status)
from app.services.settings import Settings
from app.ui.dialogs import SettingsDialog


class FFmpegVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        _inspect_cached.cache_clear()

    def test_release_date_and_unknown_parsing(self):
        cases = [
            ("ffmpeg version 7.1.1 Copyright", "7.1.1", (7, 1, 1), "release", True),
            ("ffprobe version n4.4.5-static", "n4.4.5-static", (4, 4, 5), "release", True),
            ("ffmpeg version 4.3.6-ubuntu", "4.3.6-ubuntu", (4, 3, 6), "release", False),
            ("ffmpeg version 2026-08-23-git-full", "2026-08-23-git-full", (2026, 8, 23), "date", True),
            ("ffmpeg version git-2020-01-02", "git-2020-01-02", (2020, 1, 2), "old-date", False),
            ("ffmpeg version N-123456-gabcdef", "N-123456-gabcdef", None, "unknown", None),
        ]
        for line, display, parsed, strategy, supported in cases:
            with self.subTest(line=line):
                self.assertEqual(parse_version_line(line), (display, parsed, strategy))
                self.assertEqual(compatibility(parsed, strategy), supported)
        self.assertEqual(parse_version_line("unrelated output"), (None, None, "unknown"))

    def test_inspection_invocation_cache_and_refresh_on_file_change(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "ffmpeg.exe"
            executable.write_bytes(b"one")
            result = SimpleNamespace(stdout="ffmpeg version 6.1.2\nbuilt test\n", returncode=0)
            with patch("app.core.ffmpeg.subprocess.run", return_value=result) as run:
                first = inspect_binary(str(executable))
                second = inspect_binary(str(executable))
                self.assertEqual(run.call_count, 1)
                self.assertEqual(first, second)
                args, kwargs = run.call_args
                self.assertEqual(args[0], [str(executable), "-version"])
                self.assertEqual(kwargs["timeout"], 5)
                self.assertFalse(kwargs["shell"] if "shell" in kwargs else False)
                executable.write_bytes(b"changed size")
                inspect_binary(str(executable))
                self.assertEqual(run.call_count, 2)
            self.assertTrue(first["compatible"])
            self.assertEqual(first["version"], "6.1.2")

    def test_timeout_start_failure_exit_and_bad_output(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "ffmpeg.exe"
            executable.write_bytes(b"x")
            failures = [
                (subprocess.TimeoutExpired("ffmpeg", 5), "timed out"),
                (OSError("denied"), "could not be started"),
            ]
            for error, message in failures:
                _inspect_cached.cache_clear()
                with patch("app.core.ffmpeg.subprocess.run", side_effect=error):
                    self.assertIn(message, inspect_binary(str(executable))["error"])
            for output, code, message in (("ffmpeg version 7.0", 3, "code 3"), ("garbage", 0, "not recognized")):
                _inspect_cached.cache_clear()
                with patch("app.core.ffmpeg.subprocess.run", return_value=SimpleNamespace(stdout=output, returncode=code)):
                    self.assertIn(message, inspect_binary(str(executable))["error"])

    def test_detect_both_tools_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("ffmpeg.exe", "ffprobe.exe"):
                (Path(directory) / name).write_bytes(b"x")
            with patch("app.core.ffmpeg.inspect_binary", side_effect=[
                    {"version": "7.1", "version_tuple": (7, 1, 0), "strategy": "release", "compatible": True, "error": None},
                    {"version": "N-custom", "version_tuple": None, "strategy": "unknown", "compatible": None, "error": None}]):
                info = detect(directory)
            self.assertEqual(info["minimum_version"], MINIMUM_LABEL)
            self.assertIn("Compatible", version_status(info))
            self.assertIn("unknown", version_status(info, "ffprobe").lower())
        self.assertEqual(version_status({"ffmpeg": None}), "Not found")

    def test_settings_dialog_displays_version_and_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            fake = {
                "minimum_version": "4.4", "ffmpeg": "C:/ffmpeg.exe", "ffprobe": "C:/ffprobe.exe",
                "ffmpeg_version": "7.1", "ffprobe_version": "7.1", "ffmpeg_compatible": True,
                "ffprobe_compatible": True, "ffmpeg_error": None, "ffprobe_error": None,
            }
            with patch("app.ui.dialogs.detect", return_value=fake):
                dialog = SettingsDialog(settings)
                self.assertIn("Required baseline: FFmpeg 4.4+", dialog.ff_status.text())
                self.assertIn("7.1 — Compatible", dialog.ff_status.text())
                dialog.deleteLater()
