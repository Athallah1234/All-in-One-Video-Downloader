"""Regression coverage for extraction failure diagnostics."""
import unittest
from unittest.mock import patch

from app.services.settings import DEFAULTS
from app.workers.jobs import analyze
from app.core.utils import friendly_error


class AnalyzeErrorTests(unittest.TestCase):
    def test_preserves_extractor_error_when_no_metadata(self):
        with patch("app.workers.jobs.YoutubeDL") as factory:
            def extract(*args, **kwargs):
                factory.call_args.args[0]["logger"].error(
                    "ERROR: [youtube] example: The page needs to be reloaded.")
                return None

            factory.return_value.__enter__.return_value.extract_info.side_effect = extract
            with self.assertRaisesRegex(ValueError, "page needs to be reloaded"):
                analyze("https://www.youtube.com/watch?v=example", DEFAULTS)

    def test_empty_metadata_without_logged_error(self):
        with patch("app.workers.jobs.YoutubeDL") as factory:
            factory.return_value.__enter__.return_value.extract_info.return_value = None
            with self.assertRaisesRegex(ValueError, "No metadata returned"):
                analyze("https://example.com/video", DEFAULTS)

    def test_youtube_error_has_repair_hint_and_original_error(self):
        message = friendly_error("ERROR: [youtube] example: The page needs to be reloaded.")
        self.assertIn("requirements.txt", message)
        self.assertIn("deno --version", message)
        self.assertIn("The page needs to be reloaded.", message)
