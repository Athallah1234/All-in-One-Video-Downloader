"""Live-stream recording validation and yt-dlp range configuration."""
from yt_dlp.utils import download_range_func

MAX_LIVE_SECONDS = 7 * 24 * 60 * 60


def live_duration(preferences):
    try:
        hours = int(preferences.get("live_hours", 0))
        minutes = int(preferences.get("live_minutes", 30))
        seconds = int(preferences.get("live_seconds", 0))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Live recording duration must use valid hour, minute, and second values.") from None
    if not 0 <= hours <= 168 or not 0 <= minutes <= 59 or not 0 <= seconds <= 59:
        raise ValueError("Live duration allows 0–168 hours and 0–59 minutes/seconds.")
    total = hours * 3600 + minutes * 60 + seconds
    if not 1 <= total <= MAX_LIVE_SECONDS:
        raise ValueError("Live recording duration must be between 1 second and 7 days.")
    return total


def live_options(preferences, ffmpeg, proxy=None, analyze=False):
    if preferences.get("mode") != "Live Stream":
        return {}
    total = live_duration(preferences)
    if not analyze:
        if not ffmpeg:
            raise ValueError("FFmpeg is required to record a live stream. Configure it in Settings > FFmpeg.")
        if isinstance(proxy, str) and proxy.lower().startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
            raise ValueError("FFmpeg live recording does not support SOCKS proxies. Use an HTTP/HTTPS proxy or record without a proxy.")
    return {
        "live_from_start": bool(preferences.get("live_from_start", False)),
        "download_ranges": download_range_func([], [[0, total]]),
        "force_keyframes_at_cuts": False,
    }


def validate_live_info(info):
    if info.get("is_live"):
        return
    status = info.get("live_status")
    if status == "is_upcoming":
        raise ValueError("This stream has not started yet. Wait until it is live, then analyze or record it again.")
    if status in {"was_live", "post_live"}:
        raise ValueError("This live stream has ended. Download its replay in Video mode if one is available.")
    raise ValueError("The URL is not currently a live stream. Use Video mode for recorded media.")
