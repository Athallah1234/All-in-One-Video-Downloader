"""Offline tests for settings, selectors, privacy and persistence."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from yt_dlp import YoutubeDL
from app.core.models import Task, Status
from app.core.format_builder import selector, build_options, extra_options, filename_preview
from app.core.supported_sites import supported_sites, filter_sites
from app.core.utils import valid_url, private_url, redact
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS, Settings


class CoreTests(unittest.TestCase):
    def test_url_validation(self):
        for url in ["https://example.com/watch?v=a", "http://localhost:8888/test.mp4", "https://例え.jp/a"]:
            self.assertTrue(valid_url(url))
        for url in ["", "file:///tmp/a", "javascript:alert(1)", "https://", "https://a.com/a b", "https://[invalid"]:
            self.assertFalse(valid_url(url))

    def test_format_cap_and_no_ffmpeg(self):
        p = DEFAULTS | {"quality": "720p"}
        self.assertEqual(selector(p), "bestvideo*[height<=720]+bestaudio/best[height<=720]")
        self.assertEqual(selector(p, False), "best[height<=720]")
        for quality in ["Best Available", "2160p", "1080p", "144p"]:
            for fmt in ["Best Video + Audio", "Best Video", "Best Audio", "MP4", "WebM"]:
                expression = selector(p | {"quality": quality, "format": fmt})
                with YoutubeDL({"quiet": True}) as ydl:
                    self.assertIsNotNone(ydl.build_format_selector(expression))

    def test_audio_and_missing_ffmpeg(self):
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": None, "ffprobe": None}):
            with self.assertRaisesRegex(ValueError, "FFmpeg"):
                build_options(DEFAULTS | {"mode": "Audio", "audio_format": "MP3"})
            opts = build_options(DEFAULTS | {"mode": "Audio", "audio_format": "Best Audio"})
            self.assertEqual(opts["format"], "bestaudio/best")
            self.assertEqual(opts["postprocessors"], [])

    def test_safe_arguments(self):
        self.assertEqual(extra_options("--retries 5 --limit-rate 2M --no-mtime"), {"retries": 5, "ratelimit": 2097152, "updatetime": False})
        for text in ["--exec calc", "--allow-unplayable-formats", "--plugin-dirs x", "--retries", "--retries -1", "--output ../outside"]:
            with self.assertRaises(ValueError):
                extra_options(text)

    def test_filename(self):
        name = filename_preview("%(title)s [%(id)s].%(ext)s")
        self.assertEqual(name, "Example video [abc123].mp4")
        for template in ["../%(title)s", "C:\\%(id)s", ""]:
            with self.assertRaises(ValueError):
                filename_preview(template)

    def test_settings_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(path)
            settings.values.update(theme="Dark", concurrency=3)
            settings.save()
            loaded = Settings(path)
            self.assertEqual(loaded["theme"], "Dark")
            self.assertEqual(loaded["concurrency"], 3)
            path.write_text("invalid", encoding="utf-8")
            self.assertEqual(Settings(path)["theme"], "System")

    def test_history_and_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = HistoryRepository(Path(directory) / "history.db")
            task = Task("https://user:password@example.com/watch?v=abc&token=secret", DEFAULTS | {"proxy": "https://user:secret@proxy/", "extra": "--retries 3"})
            task.title = "Test'; DROP TABLE history;--"
            task.history_id = repo.save(task)
            task.status = Status.COMPLETED
            repo.save(task)
            rows = repo.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "Completed")
            self.assertNotIn("secret", str(rows))
            self.assertNotIn("password", str(rows))
            self.assertEqual(len(repo.list("DROP")), 1)
            repo.delete([task.history_id])
            self.assertEqual(repo.list(), [])
            repo.close()

    def test_redaction(self):
        self.assertEqual(private_url("https://user:secret@example.com/video?v=abc&token=secret"), "https://example.com/video?v=abc")
        self.assertNotIn("secret", redact("request https://user:secret@example.com/?token=secret"))
        self.assertNotIn("secret", redact("Cookie: session=secret"))

    def test_supported_sites_dynamic(self):
        rows = supported_sites()
        self.assertGreater(len(rows), 100)
        matches = filter_sites(rows, "yOuTuBe")
        self.assertTrue(matches)
        self.assertTrue(all("youtube" in (r["name"] + r["description"]).lower() for r in matches))

    def test_collection_and_metadata_options(self):
        opts = build_options(DEFAULTS | {"mode": "Channel", "channel_selection": "Latest N Videos", "number": 10})
        self.assertFalse(opts["noplaylist"])
        self.assertEqual(opts["playlist_items"], "1:10")
        opts = build_options(DEFAULTS | {"mode": "Metadata"})
        self.assertTrue(opts["skip_download"])
        self.assertTrue(opts["writeinfojson"])
        self.assertFalse(opts["allow_unplayable_formats"])


if __name__ == "__main__":
    unittest.main()
