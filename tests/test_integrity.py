from hashlib import sha256
from pathlib import Path
from threading import Event
import logging
from models.download import DownloadRequest
from services.integrity_service import IntegrityService
from workers.tasks import DownloadWorker

def request(tmp_path,download_type="Video Only"):
    return DownloadRequest("https://example.com/v","Title",str(tmp_path),download_type=download_type)

def test_hash_verification_success_and_mismatch(tmp_path):
    path=tmp_path/"video.bin";path.write_bytes(b"valid media bytes");expected=sha256(path.read_bytes()).hexdigest();service=IntegrityService(logging.getLogger("test"));req=request(tmp_path)
    valid=service.verify({"_filename":str(path),"sha256":expected},req,Event())
    assert valid.valid and valid.confidence=="hash" and valid.hashes["sha256"]==expected
    invalid=service.verify({"_filename":str(path),"sha256":"0"*64},req,Event())
    assert not invalid.valid and str(path.resolve()) in invalid.invalid_files

def test_empty_file_is_corrupt(tmp_path):
    path=tmp_path/"empty.bin";path.touch();result=IntegrityService(logging.getLogger("test")).verify({"filepath":str(path)},request(tmp_path),Event())
    assert result.conclusive and not result.valid and result.invalid_files

def test_exact_size_mismatch_is_corrupt(tmp_path):
    path=tmp_path/"video.bin";path.write_bytes(b"short");result=IntegrityService(logging.getLogger("test")).verify({"filepath":str(path),"filesize":100},request(tmp_path),Event())
    assert not result.valid and "File size mismatch" in result.errors[0]

def test_observed_output_paths_are_discovered(tmp_path):
    path=tmp_path/"observed.bin";path.write_bytes(b"content");result=IntegrityService(logging.getLogger("test")).verify({"_observed_output_paths":[str(path)]},request(tmp_path,"Metadata Only"),Event())
    assert result.valid and result.conclusive and result.files==[str(path.resolve())]

def test_missing_exposed_path_is_inconclusive(tmp_path):
    result=IntegrityService(logging.getLogger("test")).verify({},request(tmp_path),Event())
    assert result.valid and not result.conclusive and result.confidence=="unavailable"

def test_quarantine_stays_in_download_folder(tmp_path):
    path=tmp_path/"bad.bin";path.write_bytes(b"bad");moved=IntegrityService.quarantine([str(path)],str(tmp_path))
    assert not path.exists() and len(moved)==1 and ".corrupt-" in moved[0] and Path(moved[0]).exists()

def test_worker_redownloads_after_integrity_failure(tmp_path):
    class FakeService:
        def __init__(self):self.downloads=0;self.quarantines=0
        def download(self,*_args):self.downloads+=1;return {"id":"v"}
        def verify_download(self,*_args):
            if self.downloads==1:return {"valid":False,"conclusive":True,"confidence":"structural","files":["bad"],"invalid_files":["bad"],"errors":["corrupt"],"hashes":{}}
            return {"valid":True,"conclusive":True,"confidence":"ffprobe","files":["good"],"invalid_files":[],"errors":[],"hashes":{}}
        def quarantine_corrupt(self,*_args):self.quarantines+=1;return ["bad.corrupt"]
    service=FakeService();worker=DownloadWorker(service,request(tmp_path),True,2);completed=[];retries=[];worker.signals.completed.connect(completed.append);worker.signals.retry.connect(lambda attempt,reason:retries.append((attempt,reason)));worker.run()
    assert service.downloads==2 and service.quarantines==1 and retries==[(1,"corrupt")]
    assert completed[0]["_integrity"]["valid"] and completed[0]["_integrity_retries"]==1

def test_worker_stops_after_retry_limit(tmp_path):
    class AlwaysBad:
        def download(self,*_args):return {}
        def verify_download(self,*_args):return {"valid":False,"conclusive":True,"files":["bad"],"invalid_files":["bad"],"errors":["hash mismatch"]}
        def quarantine_corrupt(self,*_args):return []
    worker=DownloadWorker(AlwaysBad(),request(tmp_path),True,1);failures=[];worker.signals.failed.connect(failures.append);worker.run()
    assert failures and "after automatic retries" in failures[0]
