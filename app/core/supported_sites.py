"""Discover extractors from the installed yt-dlp package."""
import logging
import re
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit


@lru_cache(maxsize=1)
def extractor_classes():
    """Installed extractor classes in yt-dlp's own dispatch order."""
    from yt_dlp import extractor
    try:
        return tuple(extractor.gen_extractor_classes())
    except AttributeError:
        logging.getLogger(__name__).warning("Using compatible extractor instance API")
        return tuple(type(item) for item in extractor.gen_extractors())


def supported_sites() -> list[dict]:
    classes = extractor_classes()
    rows = []
    for item in classes:
        name = getattr(item, "IE_NAME", type(item).__name__)
        description = getattr(item, "IE_DESC", None)
        if description is False:
            continue
        rows.append({"name": name, "description": description or name,
                     "working": "Working" if item.working() else "Currently broken"})
    return sorted(rows, key=lambda row: row["name"].casefold())


def _words(value):
    """Normalize extractor identifiers and CamelCase class names into tokens."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {word.casefold() for word in re.split(r"[^A-Za-z0-9]+", value) if word}


def _classify(item, url):
    name = getattr(item, "IE_NAME", item.__name__)
    lowered = name.casefold()
    parsed = urlsplit(url)
    path = parsed.path.casefold()
    query = parse_qs(parsed.query)
    contextual_playlist = False

    if lowered == "youtube":
        contextual_playlist = "list" in query
        kind = "YouTube video in playlist" if contextual_playlist else "YouTube video"
        return kind, "Video", "Playlist" if contextual_playlist else None
    if lowered == "youtube:tab":
        if path == "/watch" and "list" in query:
            return "YouTube video in playlist", "Playlist", "Video"
        if path.startswith("/playlist") or "list" in query:
            return "YouTube playlist", "Playlist", None
        return "YouTube channel / tab", "Channel", None
    if lowered == "vimeo":
        return "Vimeo video", "Video", None
    if lowered == "soundcloud":
        return "SoundCloud track", "Video", None

    name_tokens = {word.casefold() for word in re.split(r"[^A-Za-z0-9]+", name) if word}
    class_tokens = _words(item.__name__.removesuffix("IE"))
    single_markers = {"episode", "track", "video", "clip", "movie", "vod", "live", "player"}
    playlist_markers = {
        "playlist", "playlists", "set", "sets", "album", "albums", "collection", "collections",
        "mix", "series", "season", "course", "courses", "show", "shows", "feed", "podcast",
        "podcasts", "category", "categories", "chart", "charts", "search", "tag", "tags",
        "discography", "release", "releases", "program",
    }
    channel_markers = {
        "channel", "channels", "user", "users", "profile", "profiles", "creator", "creators",
        "artist", "artists", "author", "authors", "uploader", "uploaders", "uploads", "tab",
    }
    branded_single_extractors = {
        "amhistorychannel", "buzzfeed", "cookingchannel", "islamchannel", "mediaset",
        "sciencechannel", "theweatherchannel", "travelchannel",
    }
    channel_tokens = name_tokens & channel_markers
    class_channel_tokens = class_tokens & channel_markers
    if channel_tokens or class_channel_tokens and lowered not in branded_single_extractors:
        label_order = ["channel", "user", "profile", "artist", "creator", "author", "uploader", "uploads", "tab"]
        subtype = next((word for word in label_order if word in channel_tokens or word in class_channel_tokens), "channel")
        provider = name.split(":", 1)[0]
        if ":" not in name:
            provider = re.sub(rf"(?i){subtype}s?$", "", provider) or provider
        provider = {"dailymotion": "Dailymotion", "soundcloud": "SoundCloud", "tiktok": "TikTok",
                    "vimeo": "Vimeo"}.get(provider.casefold(), provider)
        return f"{provider} {subtype}", "Channel", None
    collection_tokens = name_tokens & playlist_markers
    # Class names cover extractors whose public IE_NAME omits their return shape.
    # An explicit single-item suffix wins for PodcastEpisodeIE and similar classes.
    if lowered not in branded_single_extractors and not class_tokens & single_markers:
        collection_tokens |= class_tokens & playlist_markers
    if collection_tokens:
        label_order = ["playlist", "set", "album", "collection", "series", "season", "course",
                       "show", "feed", "podcast", "category", "chart", "search", "tag", "release", "mix"]
        label = next((word for word in label_order if word in collection_tokens), "collection")
        provider = name.split(":", 1)[0]
        return f"{provider} {label}", "Playlist", None
    return "Single media", "Video", None


@lru_cache(maxsize=512)
def detect_url_type(url):
    """Match a URL to the first specific installed extractor, without network access."""
    candidates = []
    for item in extractor_classes():
        name = getattr(item, "IE_NAME", item.__name__)
        if name.casefold() == "generic" or getattr(item, "IE_DESC", None) is False:
            continue
        try:
            if item.suitable(url):
                candidates.append(item)
        except (AttributeError, TypeError, ValueError, re.error):
            logging.getLogger(__name__).debug("Extractor suitability check failed for %s", name, exc_info=True)
            continue
    item = candidates[0] if candidates else None
    if item is None:
        return {"extractor": "generic", "description": "Generic / unknown website",
                "working": None, "kind": "Unknown URL type", "suggested_mode": None,
                "alternate_mode": None, "source_type": "unknown", "is_playlist": None,
                "is_channel": None, "is_video": None,
                "supports_authentication": False,
                "specific": False}
    name = getattr(item, "IE_NAME", item.__name__)
    description = getattr(item, "IE_DESC", None) or name
    kind, suggested, alternate = _classify(item, url)
    try:
        working = bool(item.working())
    except (AttributeError, TypeError):
        working = None
    source_type = "playlist" if suggested == "Playlist" else "channel" if suggested == "Channel" else "video"
    return {"extractor": name, "description": description, "working": working,
            "kind": kind, "suggested_mode": suggested, "alternate_mode": alternate,
            "source_type": source_type, "is_playlist": source_type in {"playlist", "channel"},
            "is_channel": source_type == "channel", "is_video": source_type == "video",
            "supports_authentication": bool(getattr(item, "_NETRC_MACHINE", None)),
            "specific": True}


def filter_sites(rows: list[dict], query: str) -> list[dict]:
    return [row for row in rows if query.casefold() in (row["name"] + " " + row["description"]).casefold()]
