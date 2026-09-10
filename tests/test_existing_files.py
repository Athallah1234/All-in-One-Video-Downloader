"""Existing-output prediction and collision tests."""
import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.existing_files import existing_output_files, predicted_output_paths
from app.services.settings import DEFAULTS
from app.services.settings import Settings
from app.ui.downloader import DownloaderTab


class ExistingFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.preferences = DEFAULTS | {"output": self.temp.name, "mode": "Video"}
        self.info = {"id": "abc", "title": "Example", "ext": "webm", "webpage_url": "https://example.com/v"}

    def test_media_audio_metadata_and_sidecar_predictions(self):
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}):
            video = predicted_output_paths(self.info, self.preferences | {"container": "MKV"})
            audio = predicted_output_paths(self.info, self.preferences | {"mode": "Audio", "audio_format": "MP3"})
            metadata = predicted_output_paths(self.info, self.preferences | {"mode": "Metadata"})
        self.assertEqual(video[0].suffix, ".mkv")
        self.assertEqual(audio[0].suffix, ".mp3")
        self.assertEqual(metadata[0].name, "Example [abc].info.json")

    def test_case_insensitive_existing_file_and_sidecars(self):
        prefs = self.preferences | {"description": True, "info_json": True}
        (Path(self.temp.name) / "EXAMPLE [ABC].WEBM").write_text("existing")
        (Path(self.temp.name) / "Example [abc].description").write_text("existing")
        found = existing_output_files(self.info, prefs)
        self.assertEqual(len(found), 2)

    def test_playlist_selection_limits_collision_scope(self):
        info = {"entries": [
            {"id": "one", "title": "One", "ext": "mp4"},
            {"id": "two", "title": "Two", "ext": "mp4"},
        ]}
        (Path(self.temp.name) / "One [one].mp4").write_text("existing")
        (Path(self.temp.name) / "Two [two].mp4").write_text("existing")
        found = existing_output_files(info, self.preferences | {"mode": "Playlist", "items": "2"})
        self.assertEqual([path.name for path in found], ["Two [two].mp4"])

    def test_playlist_ranges_negative_indices_and_date_range(self):
        entries = [{"id": str(index), "title": str(index), "ext": "mp4", "upload_date": f"2026010{index}"}
                   for index in range(1, 7)]
        info = {"entries": entries}
        names = [path.name for path in predicted_output_paths(
            info, self.preferences | {"mode": "Playlist", "items": "1,3:5:2,-1"})]
        self.assertEqual(names, ["1 [1].mp4", "3 [3].mp4", "5 [5].mp4", "6 [6].mp4"])
        dated = [path.name for path in predicted_output_paths(info, self.preferences | {
            "mode": "Channel", "channel_selection": "Date Range", "date_from": "20260102", "date_to": "20260104"})]
        self.assertEqual(dated, ["2 [2].mp4", "3 [3].mp4", "4 [4].mp4"])

    def test_ui_warns_then_queues_only_after_explicit_continue(self):
        settings = Settings(Path(self.temp.name) / "settings.json")
        settings.values["output"] = self.temp.name
        tab = DownloaderTab(settings)
        tab.url.setText("https://example.com/video")
        queued = []
        tab.request_download.connect(lambda url, preferences, mode: queued.append((url, mode)))
        preferences = tab.preferences()
        conflict = Path(self.temp.name) / "Example [abc].mp4"
        conflict.write_text("existing")
        prompt = unittest.mock.Mock()
        proceed = object()
        prompt.addButton.side_effect = [proceed, object()]
        prompt.clickedButton.return_value = proceed
        with patch("app.ui.downloader.existing_output_files", return_value=[conflict]), \
                patch("app.ui.downloader.QMessageBox", return_value=prompt):
            tab.finish_existing_file_preflight([("https://example.com/video", self.info)],
                                               ["https://example.com/video"], preferences, "Video")
        self.assertEqual(queued, [("https://example.com/video", "Video")])
        self.assertIn("will be skipped", prompt.setText.call_args.args[0])
        tab.deleteLater()


if __name__ == "__main__":
    unittest.main()
