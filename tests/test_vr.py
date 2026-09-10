"""Strict equirectangular format selection, validation, worker and UI tests."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox
from yt_dlp import YoutubeDL

from app.core.format_builder import build_options
from app.core.models import Task
from app.core.vr import format_is_equirectangular, is_equirectangular, validate_vr_info, vr_selector
from app.services.settings import DEFAULTS, Settings
from app.ui.downloader import DownloaderTab, MODES
from app.workers.jobs import DownloadWorker


class VRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_projection_detection_is_strict(self):
        for value in ("2160s, equi", "equirect", "EQUIRECTANGULAR", "4K / equi / spatial"):
            self.assertTrue(is_equirectangular(value))
        for value in ("2160p", "rectangular", "equi-angular cubemap", "360p", "3D", "flat", None):
            self.assertFalse(is_equirectangular(value))
        self.assertTrue(format_is_equirectangular({"projection_type": "equirectangular"}))

    def test_info_validation_never_guesses_from_title(self):
        validate_vr_info({"formats": [{"format_id": "401", "format_note": "2160s, equi"}]})
        validate_vr_info({"requested_formats": [{"projection": "equirectangular"}]})
        with self.assertRaisesRegex(ValueError, "No equirectangular"):
            validate_vr_info({"title": "Amazing 360 VR equirectangular video", "tags": ["360"],
                              "formats": [{"format_note": "2160p"}]})

    def test_selector_quality_ffmpeg_and_yt_dlp_parser(self):
        expected = "bestvideo[height<=2160][format_note*=equi]+bestaudio/best[height<=2160][format_note*=equi]"
        self.assertEqual(vr_selector(DEFAULTS | {"quality": "2160p"}), expected)
        self.assertEqual(vr_selector(DEFAULTS, False), "best[format_note*=equi]")
        with YoutubeDL({"quiet": True}) as ydl:
            self.assertIsNotNone(ydl.build_format_selector(expected))
            self.assertIsNotNone(ydl.build_format_selector(vr_selector(DEFAULTS, False)))

    def test_build_options_for_analysis_download_and_aria(self):
        prefs = DEFAULTS | {"mode": "360° / VR", "quality": "Best Available"}
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}), \
                patch("app.core.aria2.detect_aria2c", return_value="aria2c"):
            opts = build_options(prefs | {"use_aria2c": True})
            self.assertEqual(opts["format"], "bestvideo[format_note*=equi]+bestaudio/best[format_note*=equi]")
            self.assertEqual(opts["external_downloader"], {"default": "aria2c"})
            analyzed = build_options(prefs, analyze=True)
            self.assertTrue(analyzed["skip_download"])

    def test_worker_rejects_flat_media_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Task("https://example.test/video", DEFAULTS | {"mode": "360° / VR", "output": directory}, media_type="360° / VR")
            worker = DownloadWorker(task)
            errors = []
            worker.failed.connect(lambda identifier, error: errors.append(error))
            flat = {"has_drm": False, "formats": [{"format_note": "1080p"}]}
            with patch("app.workers.jobs.build_options", return_value={"paths": {"home": directory}}), patch("app.workers.jobs.YoutubeDL") as factory:
                ydl = factory.return_value.__enter__.return_value
                def extract(url, download=True):
                    factory.call_args.args[0]["match_filter"](flat, incomplete=False)
                ydl.extract_info.side_effect = extract
                worker.run()
            self.assertEqual(len(errors), 1)
            self.assertIn("equirectangular", errors[0])

    def test_ui_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            tab = DownloaderTab(settings)
            tab.modes.setCurrentIndex(MODES.index("360° / VR"))
            self.assertEqual(tab.download_button.text(), "◎  Download 360°")
            self.assertFalse(tab.format.isEnabled())
            self.assertTrue(tab.quality.isEnabled())
            tab.info = None
            with patch.object(QMessageBox, "warning") as warning:
                tab.analyzed({"title": "Flat 360 claim", "formats": [{"format_note": "1080p"}]},
                             tab.url.text().strip(), "360° / VR")
                warning.assert_called_once()
            tab.deleteLater()
