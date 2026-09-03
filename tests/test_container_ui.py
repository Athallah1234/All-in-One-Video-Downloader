import logging,os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from services.ffmpeg_service import FFmpegService
from ui.tabs import DownloaderTab


def test_container_choices_follow_codec_hdr_and_download_type(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(FFmpegService,"available",classmethod(lambda cls:True))
    settings=QSettings("ContainerSmoke","ContainerSmoke");settings.clear()
    tab=DownloaderTab(None,None,settings,logging.getLogger("test"))
    formats=[
        {"format_id":"h264","height":1080,"vcodec":"avc1.640028","acodec":"none","fps":30,"dynamic_range":"SDR"},
        {"format_id":"vp9","height":1080,"vcodec":"vp09.00.51.08","acodec":"none","fps":30,"dynamic_range":"HDR10"},
        {"format_id":"aac","vcodec":"none","acodec":"mp4a.40.2"},
        {"format_id":"opus","vcodec":"none","acodec":"opus"},
    ]
    tab.show_info({"title":"Containers","formats":formats})
    tab.codec.setCurrentIndex(tab.codec.findData("h264"));tab.audio_codec.setCurrentIndex(tab.audio_codec.findData("aac"))
    webm=tab.container.findData("webm");mkv=tab.container.findData("mkv")
    assert not tab.container.model().item(webm).isEnabled()
    assert tab.container.model().item(mkv).isEnabled()
    tab.kind.setCurrentText("Audio Only")
    assert not tab.container.isEnabled() and tab.container.currentData() is None
    tab.close();settings.clear()
