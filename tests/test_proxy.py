"""SOCKS5 configuration, validation, privacy and UI regressions."""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLineEdit
from yt_dlp import YoutubeDL

from app.core.format_builder import build_options
from app.core.models import Task
from app.core.proxy import proxy_options
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS, Settings
from app.ui.dialogs import SettingsDialog
from app.workers.jobs import YDLLogger


SOCKS = {
    "proxy_type": "SOCKS5", "socks_host": "proxy.example.test", "socks_port": 1080,
    "socks_username": "user name@corp", "socks_password": "p@ss:/ word",
}


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_socks5_and_remote_dns_all_modes(self):
        expected = "socks5://user%20name%40corp:p%40ss%3A%2F%20word@proxy.example.test:1080"
        self.assertEqual(proxy_options(DEFAULTS | SOCKS), {"proxy": expected})
        remote = proxy_options(DEFAULTS | SOCKS | {"proxy_type": "SOCKS5h (remote DNS)"})
        self.assertEqual(remote["proxy"], expected.replace("socks5://", "socks5h://"))
        with patch("app.core.format_builder.detect", return_value={"ffmpeg": "ffmpeg"}):
            for mode in ("Video", "Audio", "Playlist", "Channel", "Subtitle", "Metadata", "Batch URL"):
                for analyze in (False, True):
                    opts = build_options(DEFAULTS | SOCKS | {"mode": mode}, analyze=analyze)
                    self.assertEqual(opts["proxy"], expected)
                    with YoutubeDL(opts) as ydl:
                        self.assertEqual(ydl.params["proxy"], expected)

    def test_ipv4_ipv6_idn_and_anonymous(self):
        base = DEFAULTS | SOCKS | {"socks_username": "", "socks_password": ""}
        self.assertEqual(proxy_options(base | {"socks_host": "127.0.0.1"})["proxy"], "socks5://127.0.0.1:1080")
        self.assertEqual(proxy_options(base | {"socks_host": "2001:0db8::1"})["proxy"], "socks5://[2001:db8::1]:1080")
        self.assertEqual(proxy_options(base | {"socks_host": "münchen.example"})["proxy"], "socks5://xn--mnchen-3ya.example:1080")

    def test_modes_and_legacy_url(self):
        self.assertEqual(proxy_options(DEFAULTS), {})
        self.assertEqual(proxy_options(DEFAULTS | {"proxy_type": "No Proxy"}), {"proxy": ""})
        for scheme in ("http", "https", "socks4", "socks4a", "socks5", "socks5h"):
            url = f"{scheme}://user:pass@localhost:9999"
            self.assertEqual(proxy_options(DEFAULTS | {"proxy_type": "Proxy URL", "proxy": url}), {"proxy": url})

    def test_invalid_values(self):
        changes = [
            {"socks_host": ""}, {"socks_host": "socks5://host"}, {"socks_host": "host:1080"},
            {"socks_host": "[::1]"}, {"socks_host": "bad host"}, {"socks_port": 0},
            {"socks_port": 65536}, {"socks_port": "bad"}, {"socks_password": "secret", "socks_username": ""},
            {"socks_username": "bad\nname"}, {"proxy_type": "invalid"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                proxy_options(DEFAULTS | SOCKS | change)
        for url in ("", "proxy:8080", "ftp://host:21", "http://", "http://host/path", "http://host:99999", "http://host\n:80"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                proxy_options(DEFAULTS | {"proxy_type": "Proxy URL", "proxy": url})

    def test_settings_migration_session_password_and_history_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"proxy": "http://legacy:8080"}))
            migrated = Settings(path)
            self.assertEqual(migrated["proxy_type"], "Proxy URL")
            migrated.values.update(SOCKS)
            migrated.save()
            raw = path.read_text()
            self.assertNotIn(SOCKS["socks_password"], raw)
            loaded = Settings(path)
            self.assertEqual(loaded["socks_password"], "")
            self.assertEqual(loaded["socks_host"], SOCKS["socks_host"])

            repo = HistoryRepository(Path(directory) / "history.db")
            try:
                task = Task("https://example.test/video", DEFAULTS | SOCKS, error=SOCKS["socks_password"])
                repo.save(task)
                record = repo.list()[0]
                saved = json.loads(record["preferences"])
                for key in ("proxy_type", "socks_host", "socks_port", "socks_username", "socks_password"):
                    self.assertNotIn(key, saved)
                self.assertNotIn(SOCKS["socks_password"], record["error_message"])
            finally:
                repo.close()

    def test_logger_redacts_raw_and_encoded_proxy_credentials(self):
        logger = YDLLogger(DEFAULTS | SOCKS)
        for secret in (SOCKS["socks_username"], SOCKS["socks_password"], "p%40ss%3A%2F%20word"):
            self.assertNotIn(secret, logger.clean("Proxy rejected " + secret))

    def test_ui_switching_validation_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            dialog = SettingsDialog(settings)
            self.assertFalse(dialog.fields["socks_host"].isEnabled())
            dialog.fields["proxy_type"].setCurrentText("SOCKS5h (remote DNS)")
            self.assertTrue(dialog.fields["socks_host"].isEnabled())
            self.assertFalse(dialog.fields["proxy"].isEnabled())
            self.assertEqual(dialog.fields["socks_password"].echoMode(), QLineEdit.EchoMode.Password)
            for key, value in SOCKS.items():
                field = dialog.fields[key]
                field.setCurrentText(value) if key == "proxy_type" else field.setValue(value) if key == "socks_port" else field.setText(value)
            dialog.save()
            self.assertEqual(settings["socks_password"], SOCKS["socks_password"])
            dialog.deleteLater()
