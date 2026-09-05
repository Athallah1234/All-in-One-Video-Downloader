from urllib.parse import parse_qs,urlparse

CHANNEL_PATH_MARKERS=("/channel/","/user/","/c/","/@","/videos","/shorts","/streams","/releases","/podcasts")

def looks_like_channel_url(url:str) -> bool:
    try:
        parsed=urlparse(url);path=parsed.path.lower();query=parse_qs(parsed.query)
    except ValueError:return False
    if "list" in query:return False
    return any(marker in path for marker in CHANNEL_PATH_MARKERS)

def is_channel_info(info:dict,url:str="") -> bool:
    if looks_like_channel_url(url or str(info.get("webpage_url") or info.get("original_url") or "")):return True
    extractor=" ".join(str(info.get(key) or "") for key in ("extractor","extractor_key","ie_key")).lower()
    kind=str(info.get("_type") or "").lower()
    return kind in {"playlist","multi_video"} and any(word in extractor for word in ("channel","user","tab")) and not info.get("playlist_id")

def channel_entry_type(entry:dict) -> str:
    url=str(entry.get("webpage_url") or entry.get("url") or "").lower();live=str(entry.get("live_status") or "").lower()
    if "/shorts/" in url:return "Short"
    if live in {"is_live","is_upcoming"} or entry.get("is_live"):return "Live"
    if live=="was_live" or entry.get("was_live"):return "Past live"
    return "Video"

def format_upload_date(value) -> str:
    text=str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text)==8 and text.isdigit() else "—"
