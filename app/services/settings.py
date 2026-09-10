"""Versioned local JSON settings, written atomically."""
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION_KEYS = {"username", "password", "site_login", "socks_password"}
DEFAULTS = {
    "use_netrc": False, "netrc_location": "",
    "username": "", "password": "", "site_login": False,
    "output": str(ROOT / "downloads"), "theme": "System", "language": "English",
    "confirm_exit": True, "auto_open": False, "clipboard": False, "notifications": False,
    "format": "Best Video + Audio", "quality": "Best Available", "audio_quality": "Best",
    "container": "Auto", "concurrency": 1, "retries": 3, "timeout": 30, "archive": False,
    "auto_retry": False, "auto_retry_attempts": 3,
    "auto_retry_base_delay": 2, "auto_retry_max_delay": 60,
    "use_aria2c": False, "aria2c_path": "", "aria2c_connections": 16,
    "aria2c_splits": 16, "aria2c_min_split_mib": 1, "aria2c_disable_ipv6": False,
    "live_hours": 0, "live_minutes": 30, "live_seconds": 0, "live_from_start": False,
    "template": "%(title)s [%(id)s].%(ext)s", "proxy": "", "rate_limit": "", "source_address": "",
    "proxy_type": "System / environment", "socks_host": "", "socks_port": 1080,
    "socks_username": "", "socks_password": "",
    "ip": "Auto", "cookies": "No Cookies", "cookie_file": "", "browser": "chrome",
    "ffmpeg": "", "extra": "", "width": 1200, "height": 820, "tab": 0,
    "window_x": -1, "window_y": -1, "mode_index": 0,
    "custom_format": "", "audio_format": "MP3", "languages": "en", "subtitle_format": "Best available",
    "manual_subtitles": True, "all_languages": False, "convert_srt": False,
    "subtitles": False, "auto_subtitles": False, "thumbnail": False, "embed_thumbnail": False,
    "embed_subtitle": False, "embed_metadata": False, "description": False, "info_json": False,
    "keep_files": False, "sponsorblock": False, "start": 1, "end": 0, "items": "",
    "reverse": False, "random": False, "ignore_unavailable": True,
    "channel_selection": "All Videos", "number": 10, "date_from": "", "date_to": "",
}


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or ROOT / "data/settings.json"
        self.values = DEFAULTS.copy()
        saved = {}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for key, default in DEFAULTS.items():
                if key not in SESSION_KEYS and key in saved and type(saved[key]) is type(default):
                    self.values[key] = saved[key]
        except FileNotFoundError:
            pass
        except (ValueError, OSError, TypeError):
            logging.getLogger(__name__).warning("Settings unreadable; using defaults")
        if "proxy_type" not in saved and self.values["proxy"]:
            self.values["proxy_type"] = "Proxy URL"
        self.values["concurrency"] = max(1, min(3, self.values["concurrency"]))
        self.values["auto_retry_attempts"] = max(1, min(20, self.values["auto_retry_attempts"]))
        self.values["auto_retry_base_delay"] = max(1, min(3600, self.values["auto_retry_base_delay"]))
        self.values["auto_retry_max_delay"] = max(1, min(86400, self.values["auto_retry_max_delay"]))
        self.values["aria2c_connections"] = max(1, min(16, self.values["aria2c_connections"]))
        self.values["aria2c_splits"] = max(1, min(16, self.values["aria2c_splits"]))
        self.values["aria2c_min_split_mib"] = max(1, min(1024, self.values["aria2c_min_split_mib"]))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({k: v for k, v in self.values.items() if k not in SESSION_KEYS}, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def __getitem__(self, key: str):
        return self.values[key]
