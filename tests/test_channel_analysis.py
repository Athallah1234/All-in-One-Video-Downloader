from services.ytdlp_service import YTDLPService
from utils.channels import channel_entry_type,format_upload_date,is_channel_info,looks_like_channel_url

class Logger:
    def debug(self,*_):pass
    def info(self,*_):pass
    def warning(self,*_):pass
    def error(self,*_):pass

def test_channel_url_detection_avoids_normal_playlists():
    assert looks_like_channel_url("https://www.youtube.com/@creator/videos")
    assert looks_like_channel_url("https://www.youtube.com/channel/UC123/shorts")
    assert not looks_like_channel_url("https://www.youtube.com/playlist?list=PL123")
    assert not looks_like_channel_url("https://www.youtube.com/watch?v=abc")

def test_channel_entry_classification():
    assert channel_entry_type({"url":"https://youtube.com/shorts/abc"})=="Short"
    assert channel_entry_type({"live_status":"is_live"})=="Live"
    assert channel_entry_type({"live_status":"was_live"})=="Past live"
    assert channel_entry_type({"url":"https://youtube.com/watch?v=abc"})=="Video"
    assert format_upload_date("20260905")=="2026-09-05"

def test_channel_analysis_is_bounded_and_annotated(monkeypatch):
    captured={}
    class FakeYDL:
        def __init__(self,options):captured.update(options)
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def extract_info(self,*_,**__):return {"_type":"playlist","title":"Creator - Videos","channel":"Creator","channel_id":"UC123","entries":[{"id":str(index),"title":f"Video {index}"} for index in range(3)]}
    monkeypatch.setattr("services.ytdlp_service.yt_dlp.YoutubeDL",FakeYDL)
    service=YTDLPService(Logger());service.channel_analysis_limit=3
    result=service.extract_info("https://youtube.com/@creator/videos")
    assert captured["playlistend"]==3
    assert result["_app_is_channel"] is True and result["_app_channel_loaded"]==3
    assert result["_app_channel_truncated"] is True

def test_regular_playlist_does_not_get_channel_limit(monkeypatch):
    captured={}
    class FakeYDL:
        def __init__(self,options):captured.update(options)
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def extract_info(self,*_,**__):return {"_type":"playlist","playlist_id":"PL123","entries":[]}
    monkeypatch.setattr("services.ytdlp_service.yt_dlp.YoutubeDL",FakeYDL)
    YTDLPService(Logger()).extract_info("https://youtube.com/playlist?list=PL123")
    assert "playlistend" not in captured
