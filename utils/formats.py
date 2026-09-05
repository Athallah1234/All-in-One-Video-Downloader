from typing import Any
import re
from utils.drm import is_format_usable


RESOLUTION_PRESETS=(("Best Available",None),("144p",144),("240p",240),("360p",360),("480p",480),("720p",720),("1080p",1080),("1440p",1440),("4K / 2160p",2160),("8K / 4320p",4320))
CODEC_PRESETS=(("Auto / Any codec",None),("H.264 / AVC","h264"),("H.265 / HEVC","h265"),("VP9","vp9"),("AV1","av1"))
CODEC_PATTERNS={"h264":r"^(?:avc1|avc|h264)","h265":r"^(?:hev1|hvc1|hevc|h265|dvhe|dvh1)","vp9":r"^(?:vp9|vp09)","av1":r"^(?:av01|av1)"}
AUDIO_CODEC_PRESETS=(("Auto / Best audio",None),("AAC","aac"),("Opus","opus"),("Vorbis","vorbis"),("MP3","mp3"),("FLAC","flac"))
AUDIO_CODEC_PATTERNS={"aac":r"^(?:mp4a|aac)","opus":r"^opus","vorbis":r"^vorbis","mp3":r"^mp3","flac":r"^flac"}
FPS_PRESETS=(("Auto / Any FPS",None),("24 fps",24),("25 fps",25),("30 fps",30),("48 fps",48),("50 fps",50),("60 fps",60),("100 fps",100),("120 fps",120),("144 fps",144),("240 fps",240))
BIT_DEPTH_PRESETS=(("Auto / Any bit depth",None),("8-bit",8),("10-bit (HDR-capable)",10),("12-bit (HDR-capable)",12))
DYNAMIC_RANGE_PRESETS=(("Auto / Any dynamic range",None),("HDR / Best HDR","HDR"),("SDR","SDR"),("HDR10","HDR10"),("HDR10+","HDR10+"),("HDR12","HDR12"),("HLG","HLG"),("Dolby Vision","DV"))


def available_resolution_counts(formats: list[dict[str,Any]]) -> dict[int,int]:
    counts={height:0 for _label,height in RESOLUTION_PRESETS if height is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        height=format_info.get("height");vcodec=str(format_info.get("vcodec") or "none").lower()
        if isinstance(height,(int,float)) and vcodec!="none":
            normalized=int(height)
            if normalized in counts:counts[normalized]+=1
    return counts


def normalize_video_codec(value: object) -> str | None:
    codec=str(value or "").casefold()
    if codec in {"","none"}:return None
    for name,pattern in (("h264",("avc1","avc","h264")),("h265",("hev1","hvc1","hevc","h265","dvhe","dvh1")),("vp9",("vp9","vp09")),("av1",("av01","av1"))):
        if codec.startswith(pattern):return name
    return None


def available_codec_counts(formats: list[dict[str,Any]],height: int | None=None) -> dict[str,int]:
    counts={codec:0 for _label,codec in CODEC_PRESETS if codec is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        format_height=format_info.get("height")
        if height is not None and (not isinstance(format_height,(int,float)) or int(format_height)!=int(height)):continue
        codec=normalize_video_codec(format_info.get("vcodec"))
        if codec in counts:counts[codec]+=1
    return counts


def normalize_audio_codec(value: object) -> str | None:
    codec=str(value or "").casefold()
    if codec in {"","none"}:return None
    for name,prefixes in (("aac",("mp4a","aac")),("opus",("opus",)),("vorbis",("vorbis",)),("mp3",("mp3",)),("flac",("flac",))):
        if codec.startswith(prefixes):return name
    return None


def available_audio_codec_counts(formats: list[dict[str,Any]]) -> dict[str,int]:
    counts={codec:0 for _label,codec in AUDIO_CODEC_PRESETS if codec is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        codec=normalize_audio_codec(format_info.get("acodec"))
        if codec in counts:counts[codec]+=1
    return counts


def normalize_frame_rate(value: object) -> int | None:
    if not isinstance(value,(int,float)) or value<=0:return None
    for _label,target in FPS_PRESETS:
        if target is not None and abs(float(value)-target)<0.51:return target
    return None


def available_fps_counts(formats: list[dict[str,Any]],height: int | None=None,video_codec: str | None=None) -> dict[int,int]:
    counts={fps:0 for _label,fps in FPS_PRESETS if fps is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        format_height=format_info.get("height")
        if height is not None and (not isinstance(format_height,(int,float)) or int(format_height)!=int(height)):continue
        if video_codec is not None and normalize_video_codec(format_info.get("vcodec"))!=video_codec:continue
        fps=normalize_frame_rate(format_info.get("fps"))
        if fps in counts:counts[fps]+=1
    return counts


def fps_filter(target: int | None) -> str:
    if target is None:return ""
    return f"[fps>={target-0.5:g}][fps<{target+0.5:g}]"


def detect_bit_depth(format_info: dict[str,Any]) -> tuple[int | None,str]:
    for key in ("bit_depth","video_bit_depth","bits_per_raw_sample"):
        value=format_info.get(key)
        try:value=int(value)
        except (TypeError,ValueError):continue
        if value in {8,10,12}:return value,"explicit"
    note=" ".join(str(format_info.get(key) or "") for key in ("format_note","format","profile"))
    note_match=re.search(r"(?<!\d)(8|10|12)[ -]?bit(?!\d)",note,re.I)
    if note_match:return int(note_match.group(1)),"declared"
    codec=str(format_info.get("vcodec") or "").casefold()
    codec_match=re.match(r"^(?:av01|vp09)\.[^.]+\.[^.]+\.(08|10|12)(?:\.|$)",codec)
    if codec_match:return int(codec_match.group(1)),"codec"
    hevc_match=re.match(r"^(?:hev1|hvc1)\.(\d+)(?:\.|$)",codec)
    if hevc_match and hevc_match.group(1) in {"1","2"}:return (8 if hevc_match.group(1)=="1" else 10),"profile"
    dynamic=str(format_info.get("dynamic_range") or "").upper()
    if dynamic in {"HDR10","HDR10+"}:return 10,"dynamic-range"
    if dynamic=="HDR12":return 12,"dynamic-range"
    if codec.startswith(("avc1","avc","h264","vp9.0","vp9")) and not codec.startswith(("vp9.2","vp9.3")):return 8,"profile"
    return None,"unknown"


def available_bit_depth_counts(formats: list[dict[str,Any]],height: int | None=None,video_codec: str | None=None,fps: int | None=None) -> dict[int,int]:
    counts={depth:0 for _label,depth in BIT_DEPTH_PRESETS if depth is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        if height is not None and int(format_info.get("height") or 0)!=int(height):continue
        if video_codec is not None and normalize_video_codec(format_info.get("vcodec"))!=video_codec:continue
        if fps is not None and normalize_frame_rate(format_info.get("fps"))!=fps:continue
        depth,_confidence=detect_bit_depth(format_info)
        if depth in counts:counts[depth]+=1
    return counts


def normalize_dynamic_range(value: object) -> str:
    dynamic=str(value or "SDR").upper().replace(" ","")
    aliases={"HDR":"HDR","HDR10":"HDR10","HDR10+":"HDR10+","HDR12":"HDR12","HLG":"HLG","DV":"DV","DOLBYVISION":"DV","SDR":"SDR"}
    return aliases.get(dynamic,dynamic)


def dynamic_range_matches(actual: object,target: str | None) -> bool:
    if target is None:return True
    normalized=normalize_dynamic_range(actual)
    return normalized!="SDR" if target=="HDR" else normalized==target


def available_dynamic_range_counts(formats: list[dict[str,Any]],height: int | None=None,video_codec: str | None=None,fps: int | None=None,bit_depth: int | None=None) -> dict[str,int]:
    counts={dynamic:0 for _label,dynamic in DYNAMIC_RANGE_PRESETS if dynamic is not None}
    for format_info in formats:
        if not is_format_usable(format_info):continue
        if height is not None and int(format_info.get("height") or 0)!=int(height):continue
        if video_codec is not None and normalize_video_codec(format_info.get("vcodec"))!=video_codec:continue
        if fps is not None and normalize_frame_rate(format_info.get("fps"))!=fps:continue
        if bit_depth is not None and detect_bit_depth(format_info)[0]!=bit_depth:continue
        dynamic=normalize_dynamic_range(format_info.get("dynamic_range"));counts["HDR"]+=int(dynamic!="SDR")
        if dynamic in counts and dynamic!="HDR":counts[dynamic]+=1
    return counts


def dynamic_range_filter(target: str | None) -> str:
    if target is None:return ""
    return "[dynamic_range!='SDR']" if target=="HDR" else f"[dynamic_range='{target}']"


def build_explicit_video_selector(formats: list[dict[str,Any]],height: int | None=None,video_codec: str | None=None,fps: int | None=None,bit_depth: int | None=None,dynamic_range: str | None=None,audio_codec: str | None=None,video_only: bool=False) -> str | None:
    candidates=[]
    for format_info in formats:
        if not is_format_usable(format_info):continue
        if str(format_info.get("vcodec") or "none").lower()=="none":continue
        if bit_depth is not None and detect_bit_depth(format_info)[0]!=bit_depth:continue
        if not dynamic_range_matches(format_info.get("dynamic_range"),dynamic_range):continue
        if height is not None and int(format_info.get("height") or 0)!=int(height):continue
        if video_codec is not None and normalize_video_codec(format_info.get("vcodec"))!=video_codec:continue
        if fps is not None and normalize_frame_rate(format_info.get("fps"))!=fps:continue
        if not video_only and audio_codec is not None and str(format_info.get("acodec") or "none").lower()!="none" and normalize_audio_codec(format_info.get("acodec"))!=audio_codec:continue
        candidates.append(format_info)
    if not candidates:return None
    chosen=max(candidates,key=lambda item:(float(item.get("quality") or -1),float(item.get("preference") or -1),float(item.get("tbr") or 0),float(item.get("filesize") or item.get("filesize_approx") or 0)))
    format_id=str(chosen.get("format_id") or "")
    if not format_id:return None
    if video_only or str(chosen.get("acodec") or "none").lower()!="none":return format_id
    audio_filter="" if audio_codec is None else f"[acodec~='{AUDIO_CODEC_PATTERNS[audio_codec]}']"
    return f"{format_id}+bestaudio{audio_filter}"


def build_explicit_bit_depth_selector(formats: list[dict[str,Any]],bit_depth: int,height: int | None=None,video_codec: str | None=None,fps: int | None=None,audio_codec: str | None=None,video_only: bool=False) -> str | None:
    return build_explicit_video_selector(formats,height,video_codec,fps,bit_depth,None,audio_codec,video_only)


def build_video_selector(height: int | None,codec: str | None=None,audio_codec: str | None=None,video_only: bool=False,maximum: bool=False,fps: int | None=None,dynamic_range: str | None=None) -> str:
    if height is None and codec is None and audio_codec is None and fps is None and dynamic_range is None:return "bestvideo/best" if video_only else "bestvideo*+bestaudio/best"
    height_filter="" if height is None else f"[height{'<=' if maximum else '='}{int(height)}]"
    codec_filter="" if codec is None else f"[vcodec~='{CODEC_PATTERNS[codec]}']"
    frame_filter=fps_filter(fps);range_filter=dynamic_range_filter(dynamic_range);video=f"bestvideo{height_filter}{codec_filter}{frame_filter}{range_filter}"
    if video_only:return video
    audio_filter="" if audio_codec is None else f"[acodec~='{AUDIO_CODEC_PATTERNS[audio_codec]}']"
    muxed=f"best{height_filter}{codec_filter}{frame_filter}{range_filter}{audio_filter}"
    return f"{video}+bestaudio{audio_filter}/{muxed}"


def build_resolution_selector(height: int | None,video_only: bool=False,maximum: bool=False) -> str:
    return build_video_selector(height,None,None,video_only,maximum)
