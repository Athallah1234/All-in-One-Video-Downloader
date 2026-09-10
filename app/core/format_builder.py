"""Translate UI preferences into a restricted YoutubeDL configuration."""
from pathlib import Path
import shlex
from yt_dlp import YoutubeDL
from yt_dlp.utils import DateRange, parse_bytes
from app.core.ffmpeg import detect
from app.core.netrc_auth import read_netrc
from app.core.proxy import proxy_options
from app.core.aria2 import aria2_options
from app.core.live import live_options
from app.core.vr import vr_selector
from app.services.settings import ROOT

FORMATS = ["Best Video + Audio", "Best Video", "Best Audio", "MP4", "WebM", "Audio Only", "Custom"]
QUALITIES = ["Best Available", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
AUDIO_QUALITIES = ["Best", "320 kbps", "256 kbps", "192 kbps", "128 kbps", "96 kbps"]
AUDIO_FORMATS = ["MP3", "M4A", "AAC", "FLAC", "WAV", "Opus", "Vorbis", "Best Audio"]


def selector(p: dict, ffmpeg: bool = True) -> str:
    choice = p.get("format", FORMATS[0])
    if p.get("mode") == "Audio" or choice in {"Best Audio", "Audio Only"}:
        return "bestaudio/best"
    if choice == "Custom":
        value = p.get("custom_format", "").strip()
        if not value:
            raise ValueError("Enter a custom format selector or choose a preset.")
        return value
    quality = p.get("quality", "Best Available")
    cap = f"[height<={int(quality.removesuffix('p'))}]" if quality != "Best Available" else ""
    if choice == "Best Video":
        return f"bestvideo{cap}/best{cap}"
    ext = "[ext=mp4]" if choice == "MP4" else "[ext=webm]" if choice == "WebM" else ""
    if not ffmpeg:
        return f"best{cap}{ext}"
    audio = "[ext=m4a]" if choice == "MP4" else "[ext=webm]" if choice == "WebM" else ""
    return f"bestvideo*{cap}{ext}+bestaudio{audio}/best{cap}{ext}"


def extra_options(text: str) -> dict:
    """Explicit allowlist excludes exec, plugins, paths and access-control overrides."""
    value_options = {"--retries": ("retries", int), "--fragment-retries": ("fragment_retries", int),
                     "--socket-timeout": ("socket_timeout", float), "--sleep-interval": ("sleep_interval", float),
                     "--max-sleep-interval": ("max_sleep_interval", float), "--limit-rate": ("ratelimit", parse_bytes)}
    flags = {"--prefer-free-formats": ("prefer_free_formats", True), "--no-mtime": ("updatetime", False)}
    tokens = iter(shlex.split(text))
    result = {}
    for token in tokens:
        if token in flags:
            key, value = flags[token]
        elif token in value_options:
            key, parser = value_options[token]
            try:
                value = parser(next(tokens))
                if value is None or value < 0:
                    raise ValueError()
            except (StopIteration, ValueError):
                raise ValueError(f"Invalid value for {token}") from None
        else:
            raise ValueError("Additional argument is not allowed. Use Settings > Authentication for --username / --password / --netrc / --netrc-location; see README for the safe allowlist.")
        result[key] = value
    return result


def authentication_options(p: dict) -> dict:
    """Equivalent to --username/--password, without interactive console prompts."""
    if p.get("use_netrc"):
        if p.get("site_login"):
            raise ValueError("Choose either site username/password or netrc authentication, not both.")
        path, _ = read_netrc(p)
        return {"usenetrc": True, "netrc_location": path}
    if not p.get("site_login"):
        return {}
    username, password = p.get("username", ""), p.get("password", "")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Enter a site username in Settings > Authentication.")
    if not isinstance(password, str) or not password:
        raise ValueError("Enter a site password in Settings > Authentication.")
    if any(c in username + password for c in ("\x00", "\r", "\n")):
        raise ValueError("Site credentials cannot contain NUL or line breaks.")
    return {"username": username, "password": password}


def filename_preview(template: str) -> str:
    validate_template(template)
    with YoutubeDL({"quiet": True, "outtmpl": template, "windowsfilenames": True}) as ydl:
        return ydl.prepare_filename({"title": "Example video", "id": "abc123", "ext": "mp4", "uploader": "Creator", "upload_date": "20260908", "playlist_index": 1})


def validate_template(template: str) -> None:
    if not template.strip() or any(c in template for c in ("/", "\\", "\x00")) or template in {".", ".."}:
        raise ValueError("Filename template must be a filename, without directories.")
    error = YoutubeDL.validate_outtmpl(template)
    if error:
        raise ValueError(f"Invalid filename template: {error}")


def build_options(p: dict, analyze: bool = False) -> dict:
    authentication = authentication_options(p)
    ff = detect(p.get("ffmpeg", ""))
    mode = p.get("mode", "Video")
    template = p.get("template", "%(title)s [%(id)s].%(ext)s")
    validate_template(template)
    opts = dict(quiet=True, no_warnings=False, noprogress=True, windowsfilenames=True,
                trim_file_name=180, overwrites=False, continuedl=True, allowed_extractors=["default"],
                retries=p.get("retries", 3), socket_timeout=p.get("timeout", 30),
                noplaylist=mode not in {"Playlist", "Channel"},
                paths={"home": p["output"]}, outtmpl=template, allow_unplayable_formats=False,
                ignoreerrors=p.get("ignore_unavailable", False), cachedir=False)
    if p.get("ffmpeg"):
        opts["ffmpeg_location"] = p["ffmpeg"]
    opts.update(proxy_options(p))
    if mode != "Live Stream":
        opts.update(aria2_options(p, opts.get("proxy")))
    opts.update(live_options(p, ff["ffmpeg"], opts.get("proxy"), analyze))
    if p.get("source_address"):
        opts["source_address"] = p["source_address"]
    if p.get("ip") in {"IPv4", "IPv6"}:
        opts["source_address"] = "0.0.0.0" if p["ip"] == "IPv4" else "::"
    if p.get("rate_limit"):
        rate = parse_bytes(p["rate_limit"])
        if not rate:
            raise ValueError("Rate limit must be a size such as 2M or 500K.")
        opts["ratelimit"] = rate
    if p.get("cookies") == "Cookie File":
        if not Path(p.get("cookie_file", "")).is_file():
            raise ValueError("Select an existing Netscape cookie file in Settings.")
        opts["cookiefile"] = p["cookie_file"]
    elif p.get("cookies") == "Cookies from Browser":
        opts["cookiesfrombrowser"] = (p.get("browser", "chrome"),)
    opts.update(authentication)
    opts.update(extra_options(p.get("extra", "")))
    if analyze:
        opts.update(skip_download=True, extract_flat="in_playlist", ignoreerrors=True)
        return opts
    opts["format"] = "bestvideo/bestaudio/best" if mode in {"Subtitle", "Metadata"} else vr_selector(p, bool(ff["ffmpeg"])) if mode == "360° / VR" else selector(p, bool(ff["ffmpeg"]))
    post = []
    audio = mode == "Audio" or p.get("format") == "Audio Only"
    audio_format = p.get("audio_format", "MP3")
    if audio and audio_format != "Best Audio":
        post.append({"key": "FFmpegExtractAudio", "preferredcodec": audio_format.lower(), "preferredquality": "0" if p.get("audio_quality", "Best") == "Best" else p["audio_quality"].split()[0]})
        opts["final_ext"] = {"vorbis": "ogg"}.get(audio_format.lower(), audio_format.lower())
    container = p.get("container", "Auto")
    if container != "Auto" and mode not in {"Audio", "Subtitle", "Metadata"}:
        opts["merge_output_format"] = container.lower()
        post.append({"key": "FFmpegVideoRemuxer", "preferedformat": container.lower()})
    opts.update(writesubtitles=p.get("subtitles", False) or mode == "Subtitle" and p.get("manual_subtitles", True),
                writeautomaticsub=p.get("auto_subtitles", False),
                subtitleslangs=["all", "-live_chat"] if p.get("all_languages") else [x.strip() for x in p.get("languages", "en").split(",") if x.strip()],
                subtitlesformat="best" if p.get("subtitle_format", "Best available") == "Best available" else p["subtitle_format"].lower() + "/best",
                writethumbnail=p.get("thumbnail", False) or p.get("embed_thumbnail", False),
                writedescription=p.get("description", False), writeinfojson=p.get("info_json", False) or mode == "Metadata",
                keepvideo=p.get("keep_files", False), skip_download=mode in {"Subtitle", "Metadata"})
    subtitle_target = "srt" if p.get("convert_srt") else p.get("subtitle_format", "Best available").lower()
    if subtitle_target in {"srt", "ass", "vtt"} and (opts["writesubtitles"] or opts["writeautomaticsub"]):
        post.append({"key": "FFmpegSubtitlesConvertor", "format": subtitle_target, "when": "before_dl"})
    if p.get("embed_subtitle"):
        if mode == "Subtitle":
            raise ValueError("Embedding subtitles needs a video. Use Video mode and enable Download Subtitle + Embed Subtitle.")
        opts["writesubtitles"] = True
        post.append({"key": "FFmpegEmbedSubtitle"})
    if p.get("sponsorblock"):
        post.append({"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]})
    if p.get("embed_metadata"):
        post.append({"key": "FFmpegMetadata", "add_metadata": True})
    if p.get("embed_thumbnail"):
        post.append({"key": "EmbedThumbnail", "already_have_thumbnail": p.get("thumbnail", False)})
    if mode in {"Subtitle", "Metadata"}:
        post = [item for item in post if item["key"] == "FFmpegSubtitlesConvertor"]
    if post and not ff["ffmpeg"]:
        raise ValueError("FFmpeg is required for conversion/embedding. Configure FFmpeg in Settings, or choose Best Audio / Auto without embedding.")
    opts["postprocessors"] = post
    if mode in {"Playlist", "Channel"}:
        opts.update(playlistreverse=p.get("reverse", False), playlistrandom=p.get("random", False))
        expression = p.get("items", "").strip()
        if expression:
            opts["playlist_items"] = expression
        else:
            opts["playliststart"] = p.get("start", 1)
            if p.get("end", 0):
                opts["playlistend"] = p["end"]
        if mode == "Channel":
            choice = p.get("channel_selection", "All Videos")
            count = p.get("number", 10)
            if choice == "Latest N Videos":
                opts["playlist_items"] = f"1:{count}"
            elif choice == "Oldest N Videos":
                opts["playlist_items"] = f"-{count}:"
                opts["playlistreverse"] = True
            elif choice == "Date Range":
                opts["daterange"] = DateRange(p.get("date_from") or None, p.get("date_to") or None)
            elif choice == "Custom Playlist Items" and not expression:
                raise ValueError("Enter a playlist item selection expression.")
    if p.get("archive"):
        opts["download_archive"] = str(ROOT / "data/download_archive.txt")
    return opts
