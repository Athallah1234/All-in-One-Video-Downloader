from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref_src"}


def canonicalize_url(url: str) -> str:
    """Normalize safe URL components without changing media-specific values."""
    value=url.strip()
    try:
        parsed=urlsplit(value)
        scheme=parsed.scheme.lower(); host=(parsed.hostname or "").lower().encode("idna").decode("ascii")
        port=parsed.port
        if port and not ((scheme=="http" and port==80) or (scheme=="https" and port==443)):host=f"{host}:{port}"
        if ":" in host and not host.startswith("[") and host.count(":")>1:host=f"[{host}]"
        path=parsed.path or "/"
        if path!="/":path=path.rstrip("/")
        query=[]
        for key,item_value in parse_qsl(parsed.query,keep_blank_values=True):
            if key.lower().startswith("utm_") or key.lower() in TRACKING_KEYS:continue
            query.append((key,item_value))
        query.sort(key=lambda pair:(pair[0],pair[1]))
        return urlunsplit((scheme,host,path,urlencode(query,doseq=True),""))
    except (UnicodeError,ValueError):
        return value


def media_identity(info: dict[str,Any] | None) -> tuple[str,str] | None:
    info=info or {}; extractor=info.get("extractor_key") or info.get("extractor"); media_id=info.get("id")
    if not extractor or not media_id:return None
    return str(extractor).casefold(),str(media_id)


@dataclass(frozen=True)
class DuplicateReport:
    matching_rows: tuple[int,...]
    overlapping_items: tuple[int,...]
    new_items: tuple[int,...]
    exact: bool


def find_duplicates(queue: list[dict[str,Any]],url: str,info: dict[str,Any] | None,playlist_items: list[int]) -> DuplicateReport:
    canonical=canonicalize_url(url); identity=media_identity(info); matching=[]; overlap=set(); requested=set(playlist_items)
    for row,item in enumerate(queue):
        same_url=item.get("canonical_url") == canonical or canonicalize_url(item["request"].url)==canonical
        same_media=bool(identity and item.get("media_identity")==identity)
        if not (same_url or same_media):continue
        matching.append(row); existing=set(item["request"].playlist_items)
        if requested and existing:overlap.update(requested & existing)
    if not matching:return DuplicateReport((),(),tuple(sorted(requested)),False)
    if requested:
        new=requested-overlap; exact=not new
        return DuplicateReport(tuple(matching),tuple(sorted(overlap)),tuple(sorted(new)),exact)
    return DuplicateReport(tuple(matching),(),(),True)
