from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

class DownloadStatus(str, Enum):
    WAITING="Waiting"; DOWNLOADING="Downloading"; PAUSING="Pausing…"; PAUSED="Paused"; CANCELLING="Cancelling…"; COMPLETED="Completed"; CANCELLED="Cancelled"; FAILED="Failed"

@dataclass
class DownloadRequest:
    url: str
    title: str
    folder: str
    format_selector: str = "bestvideo*+bestaudio/best"
    download_type: str = "Video"
    output_template: str = "%(title)s [%(id)s].%(ext)s"
    audio_format: str = "mp3"
    audio_quality: str = "192"
    audio_sample_rate: int = 0
    audio_channels: int = 0
    audio_thumbnail_format: str = "auto"
    audio_keep_thumbnail: bool = False
    audio_embed_chapters: bool = True
    audio_embed_infojson: bool = False
    video_thumbnail_format: str = "auto"
    video_keep_thumbnail: bool = False
    video_embed_chapters: bool = True
    video_embed_infojson: bool = False
    extractor_args: dict[str,dict[str,list[str]]] = field(default_factory=dict)
    custom_video_filter: str = ""
    custom_audio_filter: str = ""
    custom_video_encoder: str = "auto"
    custom_audio_encoder: str = "auto"
    sponsorblock_enabled: bool = False
    sponsorblock_mark: set[str] = field(default_factory=set)
    sponsorblock_remove: set[str] = field(default_factory=set)
    sponsorblock_api: str = "https://sponsor.ajay.app"
    sponsorblock_chapter_title: str = "[SponsorBlock]: %(category_names)l"
    sponsorblock_force_keyframes: bool = False
    subtitles: bool = False
    subtitle_languages: list[str] = field(default_factory=lambda: ["all"])
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    write_info_json: bool = False
    playlist_items: list[int] = field(default_factory=list)
    video_quality: str = "Advanced / Best"
    video_codec: str = "Auto / Any codec"
    audio_codec: str = "auto"
    audio_codec_label: str = "Auto / Best audio"
    video_fps: str = "Auto / Any FPS"
    video_bit_depth: str = "Auto / Any bit depth"
    dynamic_range: str = "Auto / Any dynamic range"
    output_container: str = "auto"
    output_container_label: str = "Auto / Source container"
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
