from models.download import DownloadRequest
from services.ytdlp_service import YTDLPService
import logging
from threading import Event

def test_empty_extractor_result_is_reported_as_failure(monkeypatch):
    class EmptyYDL:
        def __init__(self,_options):pass
        def __enter__(self):return self
        def __exit__(self,*_args):pass
        def extract_info(self,_url,download=False):return None
    monkeypatch.setattr("services.ytdlp_service.yt_dlp.YoutubeDL",EmptyYDL)
    try:YTDLPService(logging.getLogger("test")).extract_info("https://example.com/empty")
    except RuntimeError as exc:assert "no metadata" in str(exc)
    else:raise AssertionError("empty metadata was accepted")

def test_empty_download_result_is_reported_as_failure(monkeypatch,tmp_path):
    class EmptyYDL:
        def __init__(self,_options):pass
        def __enter__(self):return self
        def __exit__(self,*_args):pass
        def extract_info(self,_url,download=False):return None
    monkeypatch.setattr("services.ytdlp_service.yt_dlp.YoutubeDL",EmptyYDL)
    request=DownloadRequest("https://example.com/empty","Empty",str(tmp_path))
    try:YTDLPService(logging.getLogger("test")).download(request,lambda _data:None,lambda _data:None,Event(),Event(),lambda _paused:None)
    except RuntimeError as exc:assert "no download result" in str(exc)
    else:raise AssertionError("empty download result was accepted")

def test_audio_options(tmp_path):
    request=DownloadRequest("https://example.com","Example",str(tmp_path),download_type="Audio Only",audio_format="mp3",audio_quality="192")
    opts=YTDLPService(logging.getLogger("test")).build_options(request)
    assert opts["format"]=="bestaudio/best"
    assert opts["postprocessors"][0]["preferredcodec"]=="mp3"

def test_explicit_audio_codec_controls_conversion(tmp_path):
    request=DownloadRequest("https://example.com","Example",str(tmp_path),download_type="Audio Only",audio_format="m4a",audio_codec="vorbis")
    opts=YTDLPService(logging.getLogger("test")).build_options(request)
    assert opts["postprocessors"][0]["preferredcodec"]=="vorbis"

def test_extractor_listing():
    rows=YTDLPService.get_extractors()
    assert rows and any(row["name"]=="generic" for row in rows)

def test_selected_playlist_options(tmp_path):
    request=DownloadRequest("https://example.com/playlist","Playlist",str(tmp_path),playlist_items=[2,5,9])
    opts=YTDLPService(logging.getLogger("test")).build_options(request)
    assert opts["playlist_items"]=="2,5,9"
    assert opts["noplaylist"] is False

def test_explicit_video_container_configures_merge_and_final_remux(tmp_path):
    request=DownloadRequest("https://example.com/video","Example",str(tmp_path),output_container="mkv",output_container_label="MKV / Matroska")
    opts=YTDLPService(logging.getLogger("test")).build_options(request)
    assert opts["merge_output_format"]=="mkv"
    assert {"key":"FFmpegVideoRemuxer","preferedformat":"mkv"} in opts["postprocessors"]

def test_video_container_is_ignored_for_audio_only(tmp_path):
    request=DownloadRequest("https://example.com/audio","Example",str(tmp_path),download_type="Audio Only",output_container="mov")
    opts=YTDLPService(logging.getLogger("test")).build_options(request)
    assert "merge_output_format" not in opts
    assert "FFmpegVideoRemuxer" not in [processor["key"] for processor in opts["postprocessors"]]

def test_audio_sample_rate_channels_and_ffmpeg_threads(tmp_path):
    service=YTDLPService(logging.getLogger("test"));service.ffmpeg_threads=3
    request=DownloadRequest("https://example.com/audio","Example",str(tmp_path),download_type="Audio Only",audio_sample_rate=48000,audio_channels=2)
    opts=service.build_options(request);args=opts["postprocessor_args"]["FFmpegExtractAudio+ffmpeg_o"]
    assert args==["-ar","48000","-ac","2","-threads","3"]

def test_audio_metadata_cover_and_chapter_postprocessor_order(tmp_path):
    request=DownloadRequest("https://example.com/audio","Example",str(tmp_path),download_type="Audio Only",audio_format="mp3",embed_thumbnail=True,embed_metadata=True,audio_thumbnail_format="jpg",audio_keep_thumbnail=True,audio_embed_chapters=True,audio_embed_infojson=True)
    opts=YTDLPService(logging.getLogger("test")).build_options(request);processors=opts["postprocessors"]
    assert [item["key"] for item in processors]==["FFmpegThumbnailsConvertor","FFmpegExtractAudio","FFmpegMetadata","EmbedThumbnail"]
    assert processors[0]["format"]=="jpg" and processors[0]["when"]=="before_dl"
    assert processors[2]=={"key":"FFmpegMetadata","add_metadata":True,"add_chapters":True,"add_infojson":True}
    assert processors[3]["already_have_thumbnail"] is True and opts["writethumbnail"] is True

def test_audio_cover_rejects_unsupported_output(tmp_path):
    request=DownloadRequest("https://example.com/audio","Example",str(tmp_path),download_type="Audio Only",audio_format="wav",embed_thumbnail=True)
    try:YTDLPService(logging.getLogger("test")).build_options(request)
    except ValueError as exc:assert "not supported" in str(exc)
    else:raise AssertionError("WAV cover embedding was accepted")

def test_video_metadata_poster_and_chapter_postprocessor_order(tmp_path):
    request=DownloadRequest("https://example.com/video","Example",str(tmp_path),download_type="Video",output_container="mp4",embed_thumbnail=True,embed_metadata=True,video_thumbnail_format="png",video_keep_thumbnail=True,video_embed_chapters=True,video_embed_infojson=True)
    opts=YTDLPService(logging.getLogger("test")).build_options(request);processors=opts["postprocessors"]
    assert [item["key"] for item in processors]==["FFmpegThumbnailsConvertor","FFmpegVideoRemuxer","FFmpegMetadata","EmbedThumbnail"]
    assert processors[0]["format"]=="png" and processors[0]["when"]=="before_dl"
    assert processors[2]=={"key":"FFmpegMetadata","add_metadata":True,"add_chapters":True,"add_infojson":True}
    assert processors[3]["already_have_thumbnail"] is True and opts["writethumbnail"] is True

def test_video_poster_rejects_incompatible_container(tmp_path):
    request=DownloadRequest("https://example.com/video","Example",str(tmp_path),download_type="Video",output_container="webm",embed_thumbnail=True)
    try:YTDLPService(logging.getLogger("test")).build_options(request)
    except ValueError as exc:assert "not supported" in str(exc)
    else:raise AssertionError("WebM poster embedding was accepted")
