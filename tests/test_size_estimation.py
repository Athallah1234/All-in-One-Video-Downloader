from models.download import DownloadRequest
from services.ytdlp_service import YTDLPService
from workers.tasks import SizeEstimateWorker

def test_exact_merged_format_size():
    result=YTDLPService.estimate_info_size({"requested_formats":[{"filesize":10_000_000},{"filesize":2_000_000}]})
    assert result=={"bytes":12_000_000,"confidence":"exact","known_items":2,"total_items":2}

def test_bitrate_based_approximation():
    result=YTDLPService.estimate_info_size({"duration":100,"tbr":800})
    assert result["bytes"]==10_000_000
    assert result["confidence"]=="approximate"

def test_playlist_partial_estimate():
    result=YTDLPService.estimate_info_size({"entries":[{"filesize":1000},{"title":"Unknown"},{"filesize_approx":500}]})
    assert result["bytes"]==1500
    assert result["confidence"]=="partial"
    assert (result["known_items"],result["total_items"])==(2,3)

def test_auxiliary_output_is_unknown_without_fetch(tmp_path):
    service=YTDLPService.__new__(YTDLPService)
    request=DownloadRequest("https://example.com/v","Title",str(tmp_path),download_type="Subtitle Only")
    result=service.estimate_download_size(request)
    assert result["bytes"] is None and result["confidence"]=="unknown"

def test_size_worker_emits_result(tmp_path):
    class FakeService:
        def estimate_download_size(self,_request):return {"bytes":42,"confidence":"exact","known_items":1,"total_items":1}
    worker=SizeEstimateWorker(FakeService(),DownloadRequest("https://example.com/v","Title",str(tmp_path))); received=[]; worker.signals.estimate.connect(received.append); worker.run()
    assert received and received[0]["bytes"]==42

