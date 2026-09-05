from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class DRMStatus:
    level: str
    label: str
    blocked: bool
    evidence: tuple[str,...]=()

def detect_format_drm(format_info:dict[str,Any]) -> DRMStatus:
    value=format_info.get("has_drm")
    if value is True or (isinstance(value,int) and not isinstance(value,bool) and value==1) or (isinstance(value,str) and value.casefold()=="true"):return DRMStatus("confirmed","DRM",True,("has_drm=true",))
    if isinstance(value,str) and value.casefold()=="maybe":return DRMStatus("suspected","Possible DRM",True,("has_drm=maybe",))
    explicit=[]
    for key in ("drm_family","drm_scheme","encryption_scheme","license_url","license_server"):
        field=format_info.get(key)
        if field not in (None,"",False,"none","clear"):explicit.append(f"{key}={field}")
    drm_value=format_info.get("drm")
    if drm_value is True:explicit.append("drm=true")
    elif isinstance(drm_value,str) and drm_value.casefold() not in {"","none","false","clear","unencrypted"}:explicit.append(f"drm={drm_value}")
    if explicit:return DRMStatus("confirmed","DRM",True,tuple(explicit))
    if value is False:return DRMStatus("clear","Clear",False,("has_drm=false",))
    return DRMStatus("unknown","Unknown",False)

def is_format_usable(format_info:dict[str,Any]) -> bool:return not detect_format_drm(format_info).blocked

def all_stream_formats_blocked(formats:list[dict[str,Any]],stream:str) -> bool:
    key="vcodec" if stream=="video" else "acodec";candidates=[item for item in formats if str(item.get(key) or "none").lower()!="none"]
    return bool(candidates) and all(detect_format_drm(item).blocked for item in candidates)

def drm_report(formats:list[dict[str,Any]]) -> dict[str,Any]:
    statuses=[detect_format_drm(item) for item in formats];counts={key:sum(status.level==key for status in statuses) for key in ("confirmed","suspected","clear","unknown")}
    blocked_ids=[str(item.get("format_id") or "?") for item,status in zip(formats,statuses,strict=False) if status.blocked]
    media=[item for item in formats if str(item.get("vcodec") or "none").lower()!="none" or str(item.get("acodec") or "none").lower()!="none"]
    return {**counts,"total":len(formats),"blocked_ids":blocked_ids,"all_media_blocked":bool(media) and all(detect_format_drm(item).blocked for item in media)}

def selector_uses_blocked_format(selector:str,formats:list[dict[str,Any]]) -> DRMStatus|None:
    selected={part.strip() for alternative in selector.split("/") for part in alternative.split("+") if part.strip() and "[" not in part}
    for item in formats:
        if str(item.get("format_id") or "") in selected:
            status=detect_format_drm(item)
            if status.blocked:return status
    return None
