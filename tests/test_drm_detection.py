from services.ytdlp_service import YTDLPService
from utils.drm import all_stream_formats_blocked,detect_format_drm,drm_report,selector_uses_blocked_format
from utils.formats import available_resolution_counts,build_explicit_video_selector

class Logger:
    def debug(self,*_):pass
    def info(self,*_):pass
    def warning(self,*_):pass
    def error(self,*_):pass

def test_official_has_drm_states_are_distinct():
    assert detect_format_drm({"has_drm":True}).level=="confirmed"
    assert detect_format_drm({"has_drm":"maybe"}).level=="suspected"
    assert detect_format_drm({"has_drm":False}).level=="clear"
    assert detect_format_drm({}).level=="unknown"
    assert detect_format_drm({"has_drm":"maybe"}).blocked
    assert not detect_format_drm({}).blocked

def test_explicit_drm_evidence_is_reported_without_codec_guessing():
    status=detect_format_drm({"drm_family":"widevine","vcodec":"avc1"})
    assert status.level=="confirmed" and "drm_family=widevine" in status.evidence
    assert detect_format_drm({"vcodec":"avc1","format_note":"encrypted-looking-name"}).level=="unknown"

def test_reports_and_selectors_exclude_blocked_formats():
    formats=[{"format_id":"drm","height":1080,"vcodec":"avc1","acodec":"none","has_drm":True},{"format_id":"clear","height":720,"vcodec":"avc1","acodec":"none","has_drm":False},{"format_id":"audio","vcodec":"none","acodec":"opus","has_drm":False}]
    report=drm_report(formats)
    assert report["confirmed"]==1 and report["clear"]==2 and report["blocked_ids"]==["drm"]
    assert available_resolution_counts(formats)[1080]==0
    assert build_explicit_video_selector(formats,height=1080,video_only=True) is None
    assert build_explicit_video_selector(formats,height=720,video_only=True)=="clear"
    assert selector_uses_blocked_format("drm+audio",formats).blocked

def test_stream_specific_blocking():
    formats=[{"vcodec":"avc1","acodec":"none","has_drm":False},{"vcodec":"none","acodec":"aac","has_drm":"maybe"}]
    assert not all_stream_formats_blocked(formats,"video")
    assert all_stream_formats_blocked(formats,"audio")

def test_analysis_includes_drm_for_inspection_but_download_disallows_it(tmp_path):
    service=YTDLPService(Logger())
    from models.download import DownloadRequest
    assert service.build_options(DownloadRequest("https://example.com","x",str(tmp_path)))["allow_unplayable_formats"] is False
