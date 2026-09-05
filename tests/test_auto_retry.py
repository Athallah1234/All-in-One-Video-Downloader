from models.download import DownloadRequest
from utils.retry_policy import classify_failure,exponential_backoff
from workers.tasks import DownloadWorker
from utils.queue_eta import estimate_queue_eta

def request(tmp_path):return DownloadRequest("https://example.com/video","Title",str(tmp_path))

def test_exponential_backoff_and_cap():
    assert [exponential_backoff(attempt,2,10) for attempt in range(1,6)]==[2,4,8,10,10]
    class Fixed:
        @staticmethod
        def uniform(low,high):return high
    assert exponential_backoff(2,10,100,25,Fixed)==25

def test_failure_classification_skips_permanent_errors():
    assert not classify_failure("This format is DRM protected").retryable
    assert not classify_failure("HTTP Error 404: Not Found").retryable
    assert not classify_failure("Permission denied").retryable
    assert classify_failure("HTTP Error 503: Service Unavailable").retryable
    assert classify_failure("Connection reset by peer").retryable

def test_transient_download_failure_retries_then_completes(tmp_path):
    class Service:
        def __init__(self):self.calls=0
        def download(self,*_):
            self.calls+=1
            if self.calls<3:raise RuntimeError("HTTP Error 503")
            return {"id":"ok"}
    service=Service();worker=DownloadWorker(service,request(tmp_path),False,0,3,0,0,0);events=[];completed=[]
    worker.signals.auto_retry.connect(lambda attempt,maximum,delay,reason:events.append((attempt,maximum,delay,reason)));worker.signals.completed.connect(completed.append);worker.run()
    assert service.calls==3 and [event[0] for event in events]==[1,2]
    assert completed[0]["_failure_retries"]==2 and completed[0]["_integrity_retries"]==0

def test_permanent_failure_is_not_retried(tmp_path):
    class Service:
        def __init__(self):self.calls=0
        def download(self,*_):self.calls+=1;raise RuntimeError("This content is DRM protected")
    service=Service();worker=DownloadWorker(service,request(tmp_path),False,0,5,0,0,0);failures=[];retries=[];worker.signals.failed.connect(failures.append);worker.signals.auto_retry.connect(lambda *_:retries.append(1));worker.run()
    assert service.calls==1 and failures and not retries

def test_failure_and_integrity_retry_budgets_are_independent(tmp_path):
    class Service:
        def __init__(self):self.calls=0;self.verifications=0
        def download(self,*_):
            self.calls+=1
            if self.calls==2:raise RuntimeError("connection reset")
            return {"id":"ok"}
        def verify_download(self,*_):
            self.verifications+=1
            return {"valid":self.verifications>1,"conclusive":True,"files":["x"],"invalid_files":["x"],"errors":[] if self.verifications>1 else ["hash mismatch"]}
        def quarantine_corrupt(self,*_):return ["x.corrupt"]
    service=Service();worker=DownloadWorker(service,request(tmp_path),True,1,1,0,0,0);completed=[];worker.signals.completed.connect(completed.append);worker.run()
    assert service.calls==3 and completed[0]["_integrity_retries"]==1 and completed[0]["_failure_retries"]==1

def test_cancel_interrupts_retry_backoff(tmp_path):
    class Service:
        def download(self,*_):raise RuntimeError("timeout")
    worker=DownloadWorker(Service(),request(tmp_path),False,0,2,60,60,0)
    worker.signals.auto_retry.connect(lambda *_:worker.cancel());cancelled=[];worker.signals.cancelled.connect(lambda:cancelled.append(True));worker.run()
    assert cancelled

def test_queue_eta_includes_retry_backoff(tmp_path):
    item={"request":request(tmp_path),"status":"Retrying failed download (1/3) in 8.0s","retry_ready_monotonic":108.0,"estimate":{"bytes":1000,"confidence":"exact"},"progress":0,"speed_bytes":100.0}
    result=estimate_queue_eta([item],1,None,10,100.0)
    assert result.seconds==18.0
