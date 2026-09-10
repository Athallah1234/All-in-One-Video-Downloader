"""Offline URL extractor detection and downloader UI tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.supported_sites import _classify, detect_url_type
from app.core.url_resolver import URLResolution
from app.services.settings import Settings
from app.ui.downloader import DownloaderTab


class URLDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_specific_installed_extractors_and_modes(self):
        cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube", "Video", "video", False),
            ("https://www.youtube.com/playlist?list=PL1234567890ABCDEF", "youtube:tab", "Playlist", "playlist", True),
            ("https://www.youtube.com/@OpenAI", "youtube:tab", "Channel", "channel", True),
            ("https://vimeo.com/123456789", "vimeo", "Video", "video", False),
            ("https://vimeo.com/album/1234567", "vimeo:album", "Playlist", "playlist", True),
            ("https://vimeo.com/showcase/1234567", "vimeo:album", "Playlist", "playlist", True),
            ("https://artist.bandcamp.com/track/example-track", "Bandcamp", "Video", "video", False),
            ("https://artist.bandcamp.com/album/example-album", "Bandcamp:album", "Playlist", "playlist", True),
            ("https://soundcloud.com/example/track", "soundcloud", "Video", "video", False),
            ("https://soundcloud.com/example/sets/collection", "soundcloud:set", "Playlist", "playlist", True),
        ]
        for url, extractor, mode, source_type, is_playlist in cases:
            with self.subTest(url=url):
                result = detect_url_type(url)
                self.assertTrue(result["specific"])
                self.assertEqual(result["extractor"], extractor)
                self.assertEqual(result["suggested_mode"], mode)
                self.assertEqual(result["source_type"], source_type)
                self.assertIs(result["is_playlist"], is_playlist)
        self.assertEqual(detect_url_type("https://vimeo.com/123456789")["kind"], "Vimeo video")
        self.assertEqual(detect_url_type("https://soundcloud.com/example/track")["kind"], "SoundCloud track")

    def test_youtube_video_inside_playlist_preserves_both_contexts(self):
        result = detect_url_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890ABCDEF")
        self.assertEqual(result["extractor"], "youtube:tab")
        self.assertEqual(result["suggested_mode"], "Playlist")
        self.assertEqual(result["alternate_mode"], "Video")
        self.assertEqual(result["source_type"], "playlist")
        self.assertTrue(result["is_playlist"])
        self.assertIn("in playlist", result["kind"])

    def test_cross_platform_collection_taxonomy_and_brand_names(self):
        examples = [
            ("ExampleSeries", "ExampleSeriesIE", "Playlist"),
            ("ExampleSeason", "ExampleSeasonIE", "Playlist"),
            ("example:course", "ExampleCourseIE", "Playlist"),
            ("example:podcast", "ExamplePodcastIE", "Playlist"),
            ("example:category", "ExampleCategoryIE", "Playlist"),
            ("example:search", "ExampleSearchIE", "Playlist"),
            ("example:user", "ExampleUserIE", "Channel"),
            ("BuzzFeed", "BuzzFeedIE", "Video"),
            ("CookingChannel", "CookingChannelIE", "Video"),
            ("MediaSet", "MediaSetIE", "Video"),
        ]
        for name, class_name, expected in examples:
            extractor = type(class_name, (), {"IE_NAME": name})
            with self.subTest(extractor=name):
                self.assertEqual(_classify(extractor, "https://example.com/item")[1], expected)

    def test_channel_and_video_pairs_beyond_youtube(self):
        cases = [
            ("https://vimeo.com/channels/staffpicks", "vimeo:channel", "Vimeo channel", "channel"),
            ("https://vimeo.com/user12345678", "vimeo:user", "Vimeo user", "channel"),
            ("https://vimeo.com/123456789", "vimeo", "Vimeo video", "video"),
            ("https://www.dailymotion.com/user/example", "dailymotion:user", "Dailymotion user", "channel"),
            ("https://www.dailymotion.com/video/x8abcde", "dailymotion", "Single media", "video"),
            ("https://www.tiktok.com/@example", "tiktok:user", "TikTok user", "channel"),
            ("https://www.tiktok.com/@example/video/1234567890123456789", "TikTok", "Single media", "video"),
            ("https://www.bitchute.com/channel/abcdef/", "BitChuteChannel", "BitChute channel", "channel"),
            ("https://www.bitchute.com/video/abcdef/", "BitChute", "Single media", "video"),
        ]
        for url, extractor, kind, source_type in cases:
            with self.subTest(url=url):
                result = detect_url_type(url)
                self.assertEqual(result["extractor"], extractor)
                self.assertEqual(result["kind"], kind)
                self.assertEqual(result["source_type"], source_type)
                self.assertIs(result["is_channel"], source_type == "channel")
                self.assertIs(result["is_video"], source_type == "video")

    def test_unknown_url_uses_generic_fallback(self):
        result = detect_url_type("https://example.invalid/media.mp4")
        self.assertFalse(result["specific"])
        self.assertEqual(result["extractor"], "generic")
        self.assertIsNone(result["suggested_mode"])
        self.assertEqual(result["source_type"], "unknown")
        self.assertIsNone(result["is_playlist"])
        self.assertIsNone(result["is_channel"])
        self.assertIsNone(result["is_video"])

    def test_ui_shows_detection_without_network_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            tab = DownloaderTab(settings)
            tab.url.setText("https://vimeo.com/123456789")
            result = tab.detect_source()
            self.assertEqual(result["extractor"], "vimeo")
            self.assertIn("Extractor: vimeo", tab.url_detection.text())
            self.assertIn("Vimeo video", tab.url_detection.text())
            self.assertIn("Authentication likelihood: Possible", tab.auth_detection.text())
            tab.deleteLater()

    def test_ui_replaces_short_url_before_extractor_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            tab = DownloaderTab(Settings(Path(directory) / "settings.json"))
            original = "https://youtu.be/dQw4w9WgXcQ"
            final = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            tab.url.setText(original)
            tab.short_url_resolved(URLResolution(original, final, (final,)), original)
            self.assertEqual(tab.url.text(), final)
            self.assertEqual(tab.resolution_cache[original], final)
            tab.detect_source()
            self.assertIn("Expanded from youtu.be", tab.url_detection.text())
            self.assertIn("Extractor: youtube", tab.url_detection.text())
            tab.deleteLater()

    def test_batch_expansion_keeps_failures_and_continues(self):
        good = URLResolution("https://bit.ly/good", "https://vimeo.com/123456789", ("https://vimeo.com/123456789",))
        with patch("app.ui.downloader.expand_short_url", side_effect=[good, ValueError("redirect loop")]):
            urls, errors = DownloaderTab.expand_batch_urls(["https://bit.ly/good", "https://t.co/bad", "invalid"])
        self.assertEqual(urls, ["https://vimeo.com/123456789", "https://t.co/bad", "invalid"])
        self.assertEqual(len(errors), 1)
        self.assertIn("#2", errors[0])
        self.assertIn("redirect loop", errors[0])

    def test_batch_validation_reports_detected_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            tab = DownloaderTab(Settings(Path(directory) / "settings.json"))
            tab.batch.setPlainText("https://vimeo.com/123456789\nhttps://soundcloud.com/example/sets/collection")
            with patch("app.ui.downloader.QMessageBox.information") as information:
                tab.validate_batch()
            message = information.call_args.args[2]
            self.assertIn("vimeo", message)
            self.assertIn("soundcloud:set", message)
            self.assertIn("soundcloud set", message)
            tab.deleteLater()


if __name__ == "__main__":
    unittest.main()
