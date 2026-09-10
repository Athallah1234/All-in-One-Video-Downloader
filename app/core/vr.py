"""Strict selection and validation for equirectangular 360-degree media."""
import re


def is_equirectangular(value):
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return bool(re.search(r"(?:^|[\s,;/()])(equi|equirect|equirectangular)(?:$|[\s,;/()])", normalized))


def format_is_equirectangular(fmt):
    return any(is_equirectangular(fmt.get(key)) for key in (
        "format_note", "format", "projection", "projection_type"))


def validate_vr_info(info):
    """Require extractor-provided projection metadata, never infer from title/tags."""
    candidates = []
    candidates.extend(info.get("requested_formats") or [])
    candidates.extend(info.get("formats") or [])
    candidates.append(info)
    if any(format_is_equirectangular(item) for item in candidates if isinstance(item, dict)):
        return
    raise ValueError(
        "No equirectangular 360° format was reported by this extractor. "
        "Confirm that the source is a 360° video and update yt-dlp; use Video mode only if a flat download is acceptable.")


def vr_selector(preferences, ffmpeg=True):
    quality = preferences.get("quality", "Best Available")
    cap = f"[height<={int(quality.removesuffix('p'))}]" if quality != "Best Available" else ""
    projection = "[format_note*=equi]"
    if not ffmpeg:
        return f"best{cap}{projection}"
    return f"bestvideo{cap}{projection}+bestaudio/best{cap}{projection}"
