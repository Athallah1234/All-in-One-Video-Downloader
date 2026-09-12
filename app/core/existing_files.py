"""Predict yt-dlp output names and find files that would be skipped."""
from pathlib import Path
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL

from app.core.format_builder import build_options


def _final_extension(info, preferences):
    mode = preferences.get("mode", "Video")
    audio_only = mode == "Audio" or preferences.get("format") in {"Audio Only", "Best Audio"}
    if mode not in {"Subtitle", "Metadata"} and (mode == "Audio" or preferences.get("format") == "Audio Only"):
        audio = preferences.get("audio_format", "MP3").casefold()
        if audio != "best audio":
            return "ogg" if audio == "vorbis" else audio
    container = preferences.get("container", "Auto").casefold()
    if container != "auto" and not audio_only and mode not in {"Subtitle", "Metadata"}:
        return container
    if preferences.get("format") in {"MP4", "WebM"}:
        return preferences["format"].casefold()
    return info.get("ext") or "mp4"


def _entries(info):
    values = info.get("entries")
    return list(values) if values is not None else [info]


def _selected(entries, preferences):
    expression = str(preferences.get("items", "")).strip()
    if expression:
        try:
            indices = set()
            total = len(entries)
            for section in expression.split(","):
                parts = section.strip().split(":")
                if len(parts) == 1:
                    value = int(parts[0])
                    indices.add(total + value + 1 if value < 0 else value)
                    continue
                if len(parts) not in {2, 3}:
                    raise ValueError()
                step = int(parts[2]) if len(parts) == 3 and parts[2] else 1
                if step == 0:
                    raise ValueError()
                start = int(parts[0]) if parts[0] else (1 if step > 0 else total)
                end = int(parts[1]) if parts[1] else (total if step > 0 else 1)
                start = total + start + 1 if start < 0 else start
                end = total + end + 1 if end < 0 else end
                indices.update(range(start, end + (1 if step > 0 else -1), step))
            return [entry for index, entry in enumerate(entries, 1) if index in indices]
        except (TypeError, ValueError):
            # build_options/yt-dlp performs final syntax validation; checking all
            # entries here is safer than silently missing an existing file.
            return entries
    start, end = int(preferences.get("start", 1)), int(preferences.get("end", 0))
    if preferences.get("mode") == "Channel" and preferences.get("channel_selection") in {"Latest N Videos", "Oldest N Videos"}:
        count = int(preferences.get("number", 10))
        return entries[-count:] if preferences.get("channel_selection") == "Oldest N Videos" else entries[:count]
    selected = entries[max(0, start - 1):end or None]
    if preferences.get("mode") == "Channel" and preferences.get("channel_selection") == "Date Range":
        beginning = str(preferences.get("date_from", ""))
        ending = str(preferences.get("date_to", ""))
        selected = [entry for entry in selected if entry and (not beginning or str(entry.get("upload_date", "")) >= beginning)
                    and (not ending or str(entry.get("upload_date", "")) <= ending)]
    return selected


def predicted_output_paths(info, preferences, *, already_selected=False):
    """Return conservative final-media and sidecar paths for analyzed metadata."""
    options = build_options(preferences)
    output = Path(preferences["output"])
    paths = []
    with YoutubeDL(options | {"quiet": True}) as ydl:
        entries = _entries(info)
        if not already_selected and preferences.get("mode") in {"Playlist", "Channel"}:
            entries = _selected(entries, preferences)
        for original in entries:
            if not original:
                continue
            entry = dict(original)
            entry.setdefault("playlist_index", original.get("playlist_index"))
            entry["ext"] = _final_extension(entry, preferences)
            media = Path(ydl.prepare_filename(entry))
            mode = preferences.get("mode")
            if mode not in {"Subtitle", "Metadata"}:
                paths.append(media)
            stem = media.with_suffix("")
            if preferences.get("description"):
                paths.append(Path(str(stem) + ".description"))
            if preferences.get("info_json") or mode == "Metadata":
                paths.append(Path(ydl.prepare_filename(entry, "infojson")))
            if preferences.get("thumbnail"):
                thumbnail = entry.get("thumbnail", "")
                extension = Path(urlsplit(thumbnail).path).suffix or ".jpg"
                paths.append(Path(str(stem) + extension))
            if preferences.get("subtitles") or preferences.get("auto_subtitles") or mode == "Subtitle":
                available = set((entry.get("subtitles") or {})) | set((entry.get("automatic_captions") or {}))
                languages = available if preferences.get("all_languages") else {
                    value.strip() for value in preferences.get("languages", "en").split(",") if value.strip()}
                extension = "srt" if preferences.get("convert_srt") else preferences.get("subtitle_format", "Best available").casefold()
                extension = "vtt" if extension == "best available" else extension
                for language in sorted(languages & available):
                    paths.append(Path(f"{stem}.{language}.{extension}"))
    return list(dict.fromkeys(output / path.name for path in paths))


def existing_output_files(info, preferences, *, already_selected=False):
    """Find predicted files using Windows-compatible case-insensitive comparison."""
    output = Path(preferences["output"])
    try:
        existing = {item.name.casefold(): item for item in output.iterdir() if item.is_file()}
    except FileNotFoundError:
        return []
    except OSError as error:
        raise ValueError(f"Unable to inspect the output folder: {error}") from None
    return [existing[path.name.casefold()] for path in predicted_output_paths(info, preferences, already_selected=already_selected)
            if path.name.casefold() in existing]
