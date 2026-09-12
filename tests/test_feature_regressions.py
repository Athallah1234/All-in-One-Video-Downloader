"""Cross-feature regressions found during the full application audit."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from app.core.existing_files import predicted_output_paths
from app.core.format_builder import build_options, extra_options
from app.core.models import Status
from app.core.queue_manager import QueueManager
from app.services.settings import DEFAULTS, Settings
from app.ui.downloader import DownloaderTab
from app.ui.library import QueueView
from app.ui.main_window import MainWindow


class FeatureRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(Path(self.temp.name) / "settings.json")
        self.settings.values["output"] = self.temp.name

    def test_settings_non_object_json_recovers(self):
        for value in (None, 42, True, [], "proxy_type"):
            with self.subTest(value=value):
                self.settings.path.write_text(json.dumps(value), encoding="utf-8")
                loaded = Settings(self.settings.path)
                self.assertEqual(loaded.values, DEFAULTS)

    def test_non_finite_network_arguments_rejected(self):
        for option in ("--socket-timeout", "--sleep-interval", "--max-sleep-interval"):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(option=option, value=value), self.assertRaises(ValueError):
                    extra_options(f"{option} {value}")

    def test_audio_only_does_not_remux_to_video_container(self):
        opts = build_options(DEFAULTS | {"format": "Audio Only", "container": "MKV"})
        self.assertNotIn("merge_output_format", opts)
        self.assertNotIn("FFmpegVideoRemuxer", [p["key"] for p in opts["postprocessors"]])
        self.assertEqual(opts["final_ext"], "mp3")

    def test_metadata_ignores_audio_conversion_selection(self):
        opts = build_options(DEFAULTS | {"mode": "Metadata", "format": "Audio Only"})
        self.assertNotIn("final_ext", opts)
        self.assertEqual(opts["postprocessors"], [])

    def test_automatic_only_subtitles_override_shared_video_flag(self):
        opts = build_options(DEFAULTS | {"mode": "Subtitle", "subtitles": True,
            "manual_subtitles": False, "auto_subtitles": True})
        self.assertFalse(opts["writesubtitles"])
        self.assertTrue(opts["writeautomaticsub"])

    def test_embedding_alone_runs_subtitle_conversion_first(self):
        opts = build_options(DEFAULTS | {"embed_subtitle": True, "convert_srt": True})
        keys = [p["key"] for p in opts["postprocessors"]]
        self.assertLess(keys.index("FFmpegSubtitlesConvertor"), keys.index("FFmpegEmbedSubtitle"))

    def test_preflight_does_not_select_processed_playlist_twice(self):
        info = {"entries": [{"id": "two", "title": "Two", "ext": "mp4", "playlist_index": 2}]}
        paths = predicted_output_paths(info, DEFAULTS | {"mode": "Playlist", "items": "2"}, already_selected=True)
        self.assertEqual([p.name for p in paths], ["Two [two].mp4"])

    def test_video_preflight_ignores_old_playlist_selection_and_keeps_dots(self):
        info = {"id": "one", "title": "Part.1", "ext": "mp4"}
        paths = predicted_output_paths(info, DEFAULTS | {"mode": "Video", "items": "5", "description": True})
        self.assertEqual([p.name for p in paths], ["Part.1 [one].mp4", "Part.1 [one].description"])

    def test_batch_worker_cannot_replace_edited_input(self):
        tab = DownloaderTab(self.settings)
        self.addCleanup(tab.deleteLater)
        tab.batch.setPlainText("https://example.com/new")
        with patch.object(tab, "show_batch_validation") as show:
            tab.batch_urls_expanded((["https://example.com/resolved"], []), ["https://bit.ly/old"])
        self.assertEqual(tab.batch.toPlainText(), "https://example.com/new")
        show.assert_not_called()

    def test_shutdown_waits_for_each_background_worker(self):
        downloader = SimpleNamespace(worker=None, resolution_worker=None, batch_validation_worker=None)
        window = SimpleNamespace(manager=SimpleNamespace(workers={}), downloader=downloader, sites_dialog=None)
        self.assertFalse(MainWindow.busy(window))
        for key in ("worker", "resolution_worker", "batch_validation_worker"):
            setattr(downloader, key, object())
            self.assertTrue(MainWindow.busy(window))
            setattr(downloader, key, None)

    def test_queue_selection_tracks_task_after_row_removal(self):
        with patch("app.core.queue_manager.QTimer.singleShot"):
            manager = QueueManager(Mock())
            first = manager.add("https://example.com/first", DEFAULTS, "Video")
            second = manager.add("https://example.com/second", DEFAULTS, "Video")
            view = QueueView(manager)
            self.addCleanup(view.deleteLater)
            view.refresh()
            view.table.selectRow(1)
            first.status = Status.COMPLETED
            manager.remove([first.id])
            self.assertEqual(view.selected_ids(), [second.id])
            second.status = Status.COMPLETED
            manager.remove([second.id])
            self.assertEqual(view.selected_ids(), [])

    def test_corrupt_history_retry_shows_error_without_queueing(self):
        window = SimpleNamespace(settings=self.settings, manager=Mock())
        for preferences in ("{broken", "null", "[]"):
            record = {"preferences": preferences, "source_url": "https://example.com/video", "media_type": "Video"}
            with patch("app.ui.main_window.QMessageBox.warning") as warning:
                MainWindow.retry_history(window, record)
                warning.assert_called_once()
        window.manager.add.assert_not_called()

    def test_unavailable_playlist_entry_does_not_shift_selection(self):
        info = {"entries": [None, {"id": "two", "title": "Two", "ext": "mp4"}]}
        paths = predicted_output_paths(info, DEFAULTS | {"mode": "Playlist", "items": "2"})
        self.assertEqual([p.name for p in paths], ["Two [two].mp4"])

    def test_late_preflight_cannot_queue_after_shutdown(self):
        repository = Mock()
        manager = QueueManager(repository)
        manager.shutdown()
        self.assertIsNone(manager.add("https://example.com/video", DEFAULTS, "Video"))
        self.assertEqual(manager.tasks, {})
        repository.save.assert_not_called()
