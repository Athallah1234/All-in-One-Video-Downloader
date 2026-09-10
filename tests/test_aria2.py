"""aria2c detection, yt-dlp configuration, command and UI regressions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from yt_dlp import YoutubeDL
from yt_dlp.downloader.external import Aria2cFD

from app.core.aria2 import (_inspect_cached, aria2_options, aria2_version_status,
                            detect_aria2c, inspect_aria2c, parse_aria2_version)
from app.core.format_builder import build_options
from app.services.settings import DEFAULTS, Settings
from app.ui.dialogs import SettingsDialog


class Aria2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name) / "aria2c.exe"
        self.executable.write_bytes(b"test executable placeholder")
        self.inspect_patch = patch("app.core.aria2._inspect_cached", return_value={
            "version": "1.37.0", "version_tuple": (1, 37, 0), "valid": True, "error": None})
        self.inspect_patch.start()
        self.addCleanup(self.inspect_patch.stop)
        self.preferences = DEFAULTS | {
            "use_aria2c": True, "aria2c_path": str(self.executable),
            "aria2c_connections": 8, "aria2c_splits": 12,
            "aria2c_min_split_mib": 4, "aria2c_disable_ipv6": True,
        }

    def test_detection_file_folder_path_and_wrong_name(self):
        expected = str(self.executable.resolve())
        self.assertEqual(detect_aria2c(str(self.executable)), expected)
        self.assertEqual(detect_aria2c(self.temp.name), expected)
        with patch("app.core.aria2.shutil.which", return_value=expected):
            self.assertEqual(detect_aria2c(), expected)
        wrong = Path(self.temp.name) / "download.exe"
        wrong.write_bytes(b"x")
        self.assertIsNone(detect_aria2c(str(wrong)))
        self.assertIsNone(detect_aria2c(str(Path(self.temp.name) / "missing.exe")))

    def test_options_for_every_mode_and_analysis(self):
        expected = str(self.executable.resolve())
        args = ["--max-connection-per-server=8", "--split=12", "--min-split-size=4M", "--disable-ipv6=true"]
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg"}):
            for mode in ("Video", "Audio", "Playlist", "Channel", "Subtitle", "Metadata", "Batch URL"):
                for analyze in (False, True):
                    opts = build_options(self.preferences | {"mode": mode}, analyze=analyze)
                    self.assertEqual(opts["external_downloader"], {"default": expected})
                    self.assertEqual(opts["external_downloader_args"], {"aria2c": args})

    def test_real_yt_dlp_aria_command(self):
        opts = build_options(self.preferences)
        with YoutubeDL(opts) as ydl:
            downloader = Aria2cFD(ydl, opts)
            # get_suitable_downloader validates the configured binary and stores
            # this path before constructing Aria2cFD during a real download.
            downloader.__dict__["exe"] = str(self.executable.resolve())
            with patch.object(downloader, "_write_cookies", return_value="cookies.txt"):
                command = downloader._make_cmd("video.part", {
                    "url": "https://example.test/video", "http_headers": {"Referer": "https://example.test/"},
                })
        self.assertEqual(command[0], str(self.executable.resolve()))
        for argument in opts["external_downloader_args"]["aria2c"]:
            self.assertIn(argument, command)
        self.assertIn("--header", command)
        self.assertIn("Referer: https://example.test/", command)
        self.assertEqual(command[-1], "https://example.test/video")

    def test_disabled_missing_invalid_and_socks_conflict(self):
        self.assertEqual(aria2_options(DEFAULTS), {})
        with self.assertRaisesRegex(ValueError, "not found"):
            aria2_options(self.preferences | {"aria2c_path": "missing"})
        for key, values in {
            "aria2c_connections": (0, 17, "bad"),
            "aria2c_splits": (0, 17, None),
            "aria2c_min_split_mib": (0, 1025, "bad"),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    aria2_options(self.preferences | {key: value})
        for proxy in ("socks4://host:1", "socks5://host:1", "socks5h://host:1"):
            with self.assertRaisesRegex(ValueError, "does not support SOCKS"):
                aria2_options(self.preferences, proxy)
        self.assertTrue(aria2_options(self.preferences, "http://proxy:8080"))

    def test_settings_clamping_and_ui(self):
        path = Path(self.temp.name) / "settings.json"
        path.write_text('{"aria2c_connections": 999, "aria2c_splits": 0, "aria2c_min_split_mib": 9999}')
        settings = Settings(path)
        self.assertEqual(settings["aria2c_connections"], 16)
        self.assertEqual(settings["aria2c_splits"], 1)
        self.assertEqual(settings["aria2c_min_split_mib"], 1024)
        dialog = SettingsDialog(settings)
        self.assertFalse(dialog.fields["aria2c_path"].isEnabled())
        dialog.fields["use_aria2c"].setChecked(True)
        dialog.fields["aria2c_path"].setText(str(self.executable))
        self.assertTrue(dialog.fields["aria2c_connections"].isEnabled())
        self.assertIn(str(self.executable.resolve()), dialog.aria_status.text())
        self.assertIn("1.37.0 — Valid aria2c executable", dialog.aria_status.text())
        dialog.fields["aria2c_connections"].setValue(8)
        dialog.fields["aria2c_splits"].setValue(8)
        dialog.fields["aria2c_min_split_mib"].setValue(2)
        dialog.save()
        self.assertTrue(settings["use_aria2c"])
        dialog.deleteLater()

    def test_version_parsing_validation_and_status(self):
        for output, display, parsed in (
            ("aria2 version 1.37.0\nCopyright", "1.37.0", (1, 37, 0)),
            ("ARIA2 VERSION 1.36.0", "1.36.0", (1, 36, 0)),
            ("aria2 version 1.35.0-custom", "1.35.0", (1, 35, 0)),
        ):
            with self.subTest(output=output):
                self.assertEqual(parse_aria2_version(output), (display, parsed))
        for output in ("", "aria2c 1.37.0", "not aria2", None):
            self.assertEqual(parse_aria2_version(output), (None, None))
        info = {"path": str(self.executable), "version": "1.37.0", "valid": True, "error": None}
        self.assertIn("Valid", aria2_version_status(info))
        self.assertEqual(aria2_version_status({"path": None}), "Not found")

    def test_real_version_invocation_cache_refresh_and_failures(self):
        self.inspect_patch.stop()
        _inspect_cached.cache_clear()
        successful = SimpleNamespace(stdout="aria2 version 1.37.0\nCopyright", returncode=0)
        with patch("app.core.aria2.subprocess.run", return_value=successful) as run:
            first = inspect_aria2c(str(self.executable))
            second = inspect_aria2c(str(self.executable))
            self.assertEqual(first, second)
            self.assertEqual(run.call_count, 1)
            args, kwargs = run.call_args
            self.assertEqual(args[0], [str(self.executable.resolve()), "--version"])
            self.assertEqual(kwargs["timeout"], 5)
            self.assertFalse(kwargs.get("shell", False))
            self.executable.write_bytes(b"changed executable size")
            inspect_aria2c(str(self.executable))
            self.assertEqual(run.call_count, 2)
        self.assertTrue(first["valid"])
        self.assertEqual(first["version"], "1.37.0")

        for outcome, message in (
            (subprocess.TimeoutExpired("aria2c", 5), "timed out"),
            (OSError("denied"), "could not be started"),
            (SimpleNamespace(stdout="garbage", returncode=0), "not recognized"),
            (SimpleNamespace(stdout="aria2 version 1.37.0", returncode=3), "code 3"),
        ):
            _inspect_cached.cache_clear()
            with self.subTest(message=message), patch("app.core.aria2.subprocess.run", side_effect=outcome if isinstance(outcome, Exception) else None, return_value=None if isinstance(outcome, Exception) else outcome):
                info = inspect_aria2c(str(self.executable))
                self.assertFalse(info["valid"])
                self.assertIn(message, info["error"])
                self.assertIsNone(detect_aria2c(str(self.executable)))
