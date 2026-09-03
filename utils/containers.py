from dataclasses import dataclass


CONTAINER_PRESETS=(("Auto / Source container",None),("MP4","mp4"),("MKV / Matroska","mkv"),("WebM","webm"),("AVI","avi"),("MOV / QuickTime","mov"))


@dataclass(frozen=True)
class ContainerCompatibility:
    compatible: bool
    reason: str = ""


def check_container_compatibility(container: str | None,video_codec: str | None,audio_codec: str | None,dynamic_range: str | None,video_only: bool=False) -> ContainerCompatibility:
    if container is None or container=="mkv":return ContainerCompatibility(True)
    hdr=dynamic_range not in {None,"SDR"}
    if container=="webm":
        if video_codec in {"h264","h265"}:return ContainerCompatibility(False,"WebM does not support the selected H.264/HEVC video stream")
        if not video_only and audio_codec in {"aac","mp3","flac"}:return ContainerCompatibility(False,"WebM requires Opus or Vorbis for the selected audio stream")
        if dynamic_range=="DV":return ContainerCompatibility(False,"Dolby Vision is not supported in WebM")
    elif container=="avi":
        if video_codec in {"h265","vp9","av1"}:return ContainerCompatibility(False,"AVI is not a safe container for the selected modern video codec")
        if not video_only and audio_codec in {"aac","opus","vorbis","flac"}:return ContainerCompatibility(False,"AVI is not compatible with the selected audio codec")
        if hdr:return ContainerCompatibility(False,"AVI cannot reliably preserve HDR or Dolby Vision metadata")
    elif container=="mov":
        if video_codec in {"vp9","av1"}:return ContainerCompatibility(False,"MOV is not a portable container for VP9 or AV1")
        if not video_only and audio_codec in {"opus","vorbis"}:return ContainerCompatibility(False,"MOV is not compatible with the selected Opus/Vorbis stream")
    elif container=="mp4":
        if not video_only and audio_codec in {"opus","vorbis","flac"}:return ContainerCompatibility(False,"MP4 portability requires AAC or MP3 for this selection")
    return ContainerCompatibility(True)
