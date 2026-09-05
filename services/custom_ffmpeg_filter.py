import os
from pathlib import Path
from uuid import uuid4
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import PostProcessingError
from utils.ffmpeg_filters import resolve_audio_encoder,resolve_video_encoder

class CustomFFmpegFilterPP(FFmpegPostProcessor):
    """Apply user filtergraphs without a shell and replace the input only on success."""
    def __init__(self,downloader,video_filter="",audio_filter="",video_encoder="auto",audio_encoder="auto",threads=0):
        super().__init__(downloader);self.video_filter=video_filter.strip();self.audio_filter=audio_filter.strip();self.video_encoder=video_encoder;self.audio_encoder=audio_encoder;self.threads=threads

    def run(self,information):
        filepath=information.get("filepath") or information.get("_filename")
        if not filepath or not (self.video_filter or self.audio_filter):return [],information
        source=Path(filepath);temporary=source.with_name(f"{source.stem}.custom-filter-{uuid4().hex}{source.suffix}")
        options=["-map","0","-map_metadata","0","-map_chapters","0","-c","copy"]
        if self.video_filter:
            options += ["-filter:v:0",self.video_filter,"-c:v:0",resolve_video_encoder(self.video_encoder,source.suffix.lstrip("."))]
        if self.audio_filter:
            options += ["-filter:a:0",self.audio_filter,"-c:a:0",resolve_audio_encoder(self.audio_encoder,source.suffix.lstrip("."))]
        if self.threads:options += ["-threads",str(self.threads)]
        try:
            self.to_screen("Applying custom FFmpeg filter(s)")
            self.real_run_ffmpeg([(str(source),[])],[(str(temporary),options)])
            os.replace(temporary,source)
        except Exception as exc:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
            if isinstance(exc,PostProcessingError):raise
            raise PostProcessingError(f"Custom FFmpeg filter failed: {exc}") from exc
        information["filepath"]=str(source)
        return [],information
