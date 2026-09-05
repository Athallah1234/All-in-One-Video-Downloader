from dataclasses import dataclass

VIDEO_FILTER_PRESETS=(
    ("Custom / none", ""), ("Scale to 1080p", "scale=-2:1080"),
    ("Denoise (light)", "hqdn3d=1.5:1.5:6:6"),
    ("Sharpen (light)", "unsharp=5:5:0.7:5:5:0"),
    ("Grayscale", "format=gray"), ("Deinterlace", "bwdif"),
)
AUDIO_FILTER_PRESETS=(
    ("Custom / none", ""), ("Normalize loudness (EBU R128)", "loudnorm=I=-16:LRA=11:TP=-1.5"),
    ("Boost volume +3 dB", "volume=3dB"), ("High-pass 80 Hz", "highpass=f=80"),
    ("Low-pass 16 kHz", "lowpass=f=16000"),
)
VIDEO_ENCODERS=(
    ("Automatic for container", "auto"), ("H.264 (libx264)", "libx264"),
    ("H.265 / HEVC (libx265)", "libx265"), ("VP9 (libvpx-vp9)", "libvpx-vp9"),
    ("AV1 (libaom-av1)", "libaom-av1"),
)
AUDIO_ENCODERS=(
    ("Automatic for container", "auto"), ("AAC", "aac"), ("Opus", "libopus"),
    ("MP3", "libmp3lame"), ("FLAC", "flac"),
)

@dataclass(frozen=True)
class FilterValidation:
    valid: bool
    error: str = ""

def validate_filtergraph(value: str) -> FilterValidation:
    """Structural validation; FFmpeg remains the authority for filter names/options."""
    if not value.strip(): return FilterValidation(True)
    if len(value)>4096:return FilterValidation(False,"Filter is longer than 4096 characters")
    if any(char in value for char in ("\0","\r","\n")):return FilterValidation(False,"Filter must be a single line and contain no NUL characters")
    pairs={")":"(","]":"[","}":"{"};stack=[];quote=None;escaped=False
    for char in value:
        if escaped:escaped=False;continue
        if char=="\\":escaped=True;continue
        if quote:
            if char==quote:quote=None
            continue
        if char in "'\"":quote=char
        elif char in "([{":stack.append(char)
        elif char in pairs:
            if not stack or stack.pop()!=pairs[char]:return FilterValidation(False,f"Unbalanced '{char}'")
    if quote:return FilterValidation(False,"Unterminated quote")
    if stack:return FilterValidation(False,f"Unclosed '{stack[-1]}'")
    return FilterValidation(True)

def resolve_video_encoder(value: str, extension: str) -> str:
    if value!="auto":return value
    return "libvpx-vp9" if extension.lower()=="webm" else "libx264"

def resolve_audio_encoder(value: str, extension: str) -> str:
    if value!="auto":return value
    return {"webm":"libopus","opus":"libopus","ogg":"libvorbis","oga":"libvorbis","vorbis":"libvorbis","mp3":"libmp3lame","flac":"flac","wav":"pcm_s16le","avi":"libmp3lame"}.get(extension.lower(),"aac")

def validate_encoder_container(video_encoder: str,audio_encoder: str,extension: str,has_video: bool,has_audio: bool) -> FilterValidation:
    ext=extension.lower()
    allowed_video={"webm":{"auto","libvpx-vp9","libaom-av1"},"mp4":{"auto","libx264","libx265","libaom-av1"},"mov":{"auto","libx264","libx265"},"avi":{"auto","libx264"}}
    allowed_audio={"webm":{"auto","libopus"},"mp4":{"auto","aac"},"m4a":{"auto","aac"},"mov":{"auto","aac"},"mp3":{"auto","libmp3lame"},"flac":{"auto","flac"},"avi":{"auto","libmp3lame"}}
    if has_video and ext in allowed_video and video_encoder not in allowed_video[ext]:return FilterValidation(False,f"Video encoder is not compatible with {ext.upper()}")
    if has_audio and ext in allowed_audio and audio_encoder not in allowed_audio[ext]:return FilterValidation(False,f"Audio encoder is not compatible with {ext.upper()}")
    return FilterValidation(True)
