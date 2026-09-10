"""Live recording duration, metadata validation, yt-dlp, worker and UI tests."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox
from yt_dlp.downloader import get_suitable_downloader
from yt_dlp.downloader.external import FFmpegFD

from app.core.format_builder import build_options
from app.core.live import live_duration, live_options, validate_live_info
from app.core.models import Task
from app.services.settings import DEFAULTS, Settings
from app.ui.downloader import DownloaderTab, MODES
from app.workers.jobs import DownloadWorker


LIVE = {"mode": "Live Stream", "live_hours": 0, "live_minutes": 1, "live_seconds": 30}


class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_duration_and_download_range(self):
        self.assertEqual(live_duration(DEFAULTS | LIVE), 90)
        opts = live_options(DEFAULTS | LIVE, "ffmpeg")
        self.assertFalse(opts["live_from_start"])
        self.assertEqual(list(opts["download_ranges"]({"is_live": True}, None)), [{"start_time": 0, "end_time": 90}])
        info = {"protocol": "m3u8", "section_start": 0, "section_end": 90, "to_stdout": False}
        self.assertIs(get_suitable_downloader(info, opts), FFmpegFD)
        beginning = live_options(DEFAULTS | LIVE | {"live_from_start": True}, "ffmpeg")
        self.assertTrue(beginning["live_from_start"])

    def test_all_formats_and_aria_is_bypassed(self):
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}):
            for fmt in ("Best Video + Audio", "Best Video", "Best Audio", "MP4", "WebM", "Audio Only"):
                opts = build_options(DEFAULTS | LIVE | {"format": fmt, "use_aria2c": True, "aria2c_path": "missing"})
                self.assertIn("download_ranges", opts)
                self.assertNotIn("external_downloader", opts)
            analyzed = build_options(DEFAULTS | LIVE, analyze=True)
            self.assertTrue(analyzed["skip_download"])

    def test_invalid_duration_ffmpeg_and_proxy(self):
        invalid = [
            {"live_hours": 0, "live_minutes": 0, "live_seconds": 0},
            {"live_hours": 169}, {"live_hours": 168, "live_seconds": 1},
            {"live_minutes": 60}, {"live_seconds": -1}, {"live_seconds": "bad"},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                live_duration(DEFAULTS | LIVE | change)
        with self.assertRaisesRegex(ValueError, "FFmpeg"):
            live_options(DEFAULTS | LIVE, None)
        with self.assertRaisesRegex(ValueError, "SOCKS"):
            live_options(DEFAULTS | LIVE, "ffmpeg", "socks5h://proxy:1080")
        # Metadata analysis remains available before FFmpeg is configured.
        self.assertTrue(live_options(DEFAULTS | LIVE, None, analyze=True))

    def test_live_metadata_states(self):
        validate_live_info({"is_live": True, "live_status": "is_live"})
        for status, message in (("is_upcoming", "not started"), ("was_live", "ended"), ("post_live", "ended"), ("not_live", "not currently")):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, message):
                validate_live_info({"is_live": False, "live_status": status})

    def test_worker_rejects_vod_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Task("https://example.test/video", DEFAULTS | LIVE | {"output": directory}, media_type="Live Stream")
            worker = DownloadWorker(task)
            errors = []
            worker.failed.connect(lambda identifier, error: errors.append(error))
            fake = {"has_drm": False, "is_live": False, "live_status": "not_live"}
            with patch("app.workers.jobs.build_options", return_value={"paths": {"home": directory}}), patch("app.workers.jobs.YoutubeDL") as factory:
                ydl = factory.return_value.__enter__.return_value
                def extract(url, download=True):
                    options = factory.call_args.args[0]
                    options["match_filter"](fake, incomplete=False)
                ydl.extract_info.side_effect = extract
                worker.run()
            self.assertEqual(len(errors), 1)
            self.assertIn("not currently", errors[0])

    def test_ui_mode_duration_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            settings.values["output"] = directory
            tab = DownloaderTab(settings)
            tab.modes.setCurrentIndex(MODES.index("Live Stream"))
            self.assertTrue(tab.live_box.isVisibleTo(tab))
            self.assertEqual(tab.download_button.text(), "●  Record Live")
            tab.live_hours.setValue(1)
            tab.live_minutes.setValue(2)
            tab.live_seconds.setValue(3)
            tab.live_from_start.setChecked(True)
            prefs = tab.preferences()
            self.assertEqual(live_duration(prefs), 3723)
            tab.persist_preferences()
            loaded = Settings(settings.path)
            self.assertEqual(loaded["live_hours"], 1)
            self.assertTrue(loaded["live_from_start"])
            tab.deleteLater()
