from models.download import DownloadRequest
from services.ytdlp_service import YTDLPService
from utils.sponsorblock import validate_sponsorblock

class Logger:
    def debug(self,*_):pass
    def info(self,*_):pass
    def warning(self,*_):pass
    def error(self,*_):pass

def test_sponsorblock_validation():
    assert validate_sponsorblock({"chapter"},{"sponsor"},"https://sponsor.ajay.app","[SB] %(category_names)l").valid
    assert not validate_sponsorblock(set(),{"chapter"},"https://sponsor.ajay.app","x").valid
    assert not validate_sponsorblock({"sponsor"},set(),"not-a-url","x").valid
    assert not validate_sponsorblock({"sponsor"},set(),"https://user:pass@example.com","x").valid
    assert not validate_sponsorblock({"sponsor"},set(),"https://example.com","%(title)s").valid

def test_sponsorblock_postprocessor_order_and_options(tmp_path):
    request=DownloadRequest("https://youtube.com/watch?v=abcdefghijk","Example",str(tmp_path),sponsorblock_enabled=True,sponsorblock_mark={"intro","chapter"},sponsorblock_remove={"sponsor"},sponsorblock_force_keyframes=True,video_embed_chapters=False)
    processors=YTDLPService(Logger()).build_options(request)["postprocessors"]
    sponsor=next(item for item in processors if item["key"]=="SponsorBlock")
    modify=next(item for item in processors if item["key"]=="ModifyChapters")
    metadata=next(item for item in processors if item["key"]=="FFmpegMetadata")
    assert sponsor["when"]=="after_filter"
    assert sponsor["categories"]=={"intro","chapter","sponsor"}
    assert modify["remove_sponsor_segments"]=={"sponsor"}
    assert modify["force_keyframes"] is True
    assert metadata["add_chapters"] is True
    assert processors.index(modify)<processors.index(metadata)

def test_sponsorblock_audio_pipeline_is_not_overwritten(tmp_path):
    request=DownloadRequest("https://youtube.com/watch?v=abcdefghijk","Example",str(tmp_path),download_type="Audio Only",sponsorblock_enabled=True,sponsorblock_remove={"sponsor"})
    keys=[item["key"] for item in YTDLPService(Logger()).build_options(request)["postprocessors"]]
    assert "SponsorBlock" in keys and "FFmpegExtractAudio" in keys and "ModifyChapters" in keys
    assert keys.index("FFmpegExtractAudio")<keys.index("ModifyChapters")

def test_removed_segments_make_size_approximate(monkeypatch,tmp_path):
    service=YTDLPService(Logger());request=DownloadRequest("https://youtube.com/watch?v=abcdefghijk","Example",str(tmp_path),sponsorblock_enabled=True,sponsorblock_remove={"sponsor"})
    class FakeYDL:
        def __init__(self,_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def extract_info(self,*_,**__):return {"filesize":100}
    monkeypatch.setattr("services.ytdlp_service.yt_dlp.YoutubeDL",FakeYDL)
    result=service.estimate_download_size(request)
    assert result["bytes"]==100 and result["confidence"]=="approximate"
