from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

class WorkerSignals(QObject):
    metadata=Signal(object); estimate=Signal(object); progress=Signal(object); phase=Signal(str); pause_state=Signal(bool); integrity=Signal(object); retry=Signal(int,str); auto_retry=Signal(int,int,float,str); completed=Signal(object); failed=Signal(str); cancelled=Signal()

def safe_emit(signal,*args):
    """Ignore emissions after Qt has destroyed a closing worker's signals."""
    try:signal.emit(*args)
    except RuntimeError:pass

class MetadataWorker(QRunnable):
    def __init__(self,service,url,extractor_args=None): super().__init__(); self.service=service; self.url=url;self.extractor_args=extractor_args or {}; self.signals=WorkerSignals()
    @Slot()
    def run(self):
        try:
            result=self.service.extract_info(self.url,self.extractor_args) if self.extractor_args else self.service.extract_info(self.url)
            if not isinstance(result,dict):raise RuntimeError("No metadata was returned for this URL")
            safe_emit(self.signals.metadata,result)
        except Exception as exc:safe_emit(self.signals.failed,str(exc))

class SizeEstimateWorker(QRunnable):
    def __init__(self,service,request):super().__init__();self.service=service;self.request=request;self.signals=WorkerSignals()
    @Slot()
    def run(self):
        try:safe_emit(self.signals.estimate,self.service.estimate_download_size(self.request))
        except Exception as exc:safe_emit(self.signals.failed,str(exc))

class DownloadWorker(QRunnable):
    def __init__(self,service,request,verify_integrity=True,integrity_retries=2,failure_retries=0,backoff_base=2,backoff_max=60,jitter_percent=10): super().__init__(); self.service=service; self.request=request; self.verify_integrity=verify_integrity; self.integrity_retries=max(0,int(integrity_retries));self.failure_retries=max(0,int(failure_retries));self.backoff_base=max(0,float(backoff_base));self.backoff_max=max(0,float(backoff_max));self.jitter_percent=max(0,min(100,int(jitter_percent))); self.cancel_event=Event(); self.pause_event=Event(); self.signals=WorkerSignals();self.failure_attempts=0
    def pause(self):
        if self.cancel_event.is_set(): return False
        self.pause_event.set(); return True
    def resume(self):
        was_paused=self.pause_event.is_set(); self.pause_event.clear(); return was_paused
    def cancel(self): self.cancel_event.set(); self.pause_event.clear()
    def download_with_retry(self):
        from utils.retry_policy import classify_failure,exponential_backoff
        while True:
            if self.pause_event.is_set():
                safe_emit(self.signals.pause_state,True)
                while self.pause_event.is_set():
                    if self.cancel_event.wait(0.1):raise RuntimeError("Download cancelled while paused")
                safe_emit(self.signals.pause_state,False)
            try:return self.service.download(self.request,lambda data:safe_emit(self.signals.progress,data),lambda d:safe_emit(self.signals.phase,str(d.get("postprocessor") or d.get("status") or "Post-processing")),self.cancel_event,self.pause_event,lambda paused:safe_emit(self.signals.pause_state,paused))
            except Exception as exc:
                if self.cancel_event.is_set():raise
                decision=classify_failure(exc)
                if not decision.retryable or self.failure_attempts>=self.failure_retries:raise
                self.failure_attempts+=1;delay=exponential_backoff(self.failure_attempts,self.backoff_base,self.backoff_max,self.jitter_percent);safe_emit(self.signals.auto_retry,self.failure_attempts,self.failure_retries,delay,str(exc))
                if self.cancel_event.wait(delay):raise RuntimeError("Download cancelled during retry backoff") from exc
    @Slot()
    def run(self):
        try:
            attempt=0
            while True:
                result=self.download_with_retry()
                if not self.verify_integrity:
                    report={"valid":True,"conclusive":False,"confidence":"disabled","files":[],"errors":[],"hashes":{},"invalid_files":[]};break
                safe_emit(self.signals.phase,"Verifying integrity")
                report=self.service.verify_download(result,self.request,self.cancel_event);safe_emit(self.signals.integrity,report)
                if report.get("valid") or not report.get("conclusive"):break
                if attempt>=self.integrity_retries:raise RuntimeError("Integrity verification failed after automatic retries: "+"; ".join(report.get("errors") or ["unknown corruption"]))
                attempt+=1;self.service.quarantine_corrupt(report.get("invalid_files") or report.get("files") or [],self.request.folder); reason="; ".join(report.get("errors") or ["integrity validation failed"]);safe_emit(self.signals.retry,attempt,reason);self.pause_event.clear()
            result["_integrity"]=report;result["_integrity_retries"]=attempt;result["_failure_retries"]=self.failure_attempts
            if self.cancel_event.is_set():safe_emit(self.signals.cancelled)
            else:safe_emit(self.signals.completed,result)
        except Exception as exc:
            if self.cancel_event.is_set():safe_emit(self.signals.cancelled)
            else:safe_emit(self.signals.failed,str(exc))
