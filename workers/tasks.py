from threading import Event
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

class WorkerSignals(QObject):
    metadata=Signal(object); estimate=Signal(object); progress=Signal(object); phase=Signal(str); pause_state=Signal(bool); integrity=Signal(object); retry=Signal(int,str); completed=Signal(object); failed=Signal(str); cancelled=Signal()

class MetadataWorker(QRunnable):
    def __init__(self,service,url): super().__init__(); self.service=service; self.url=url; self.signals=WorkerSignals()
    @Slot()
    def run(self):
        try: self.signals.metadata.emit(self.service.extract_info(self.url))
        except Exception as exc: self.signals.failed.emit(str(exc))

class SizeEstimateWorker(QRunnable):
    def __init__(self,service,request):super().__init__();self.service=service;self.request=request;self.signals=WorkerSignals()
    @Slot()
    def run(self):
        try:self.signals.estimate.emit(self.service.estimate_download_size(self.request))
        except Exception as exc:self.signals.failed.emit(str(exc))

class DownloadWorker(QRunnable):
    def __init__(self,service,request,verify_integrity=True,integrity_retries=2): super().__init__(); self.service=service; self.request=request; self.verify_integrity=verify_integrity; self.integrity_retries=max(0,int(integrity_retries)); self.cancel_event=Event(); self.pause_event=Event(); self.signals=WorkerSignals()
    def pause(self):
        if self.cancel_event.is_set(): return False
        self.pause_event.set(); return True
    def resume(self):
        was_paused=self.pause_event.is_set(); self.pause_event.clear(); return was_paused
    def cancel(self): self.cancel_event.set(); self.pause_event.clear()
    @Slot()
    def run(self):
        try:
            attempt=0
            while True:
                result=self.service.download(self.request,self.signals.progress.emit,lambda d:self.signals.phase.emit(str(d.get("postprocessor") or d.get("status") or "Post-processing")),self.cancel_event,self.pause_event,self.signals.pause_state.emit)
                if not self.verify_integrity:
                    report={"valid":True,"conclusive":False,"confidence":"disabled","files":[],"errors":[],"hashes":{},"invalid_files":[]};break
                self.signals.phase.emit("Verifying integrity")
                report=self.service.verify_download(result,self.request,self.cancel_event);self.signals.integrity.emit(report)
                if report.get("valid") or not report.get("conclusive"):break
                if attempt>=self.integrity_retries:raise RuntimeError("Integrity verification failed after automatic retries: "+"; ".join(report.get("errors") or ["unknown corruption"]))
                attempt+=1; moved=self.service.quarantine_corrupt(report.get("invalid_files") or report.get("files") or [],self.request.folder); reason="; ".join(report.get("errors") or ["integrity validation failed"]);self.signals.retry.emit(attempt,reason);self.pause_event.clear()
            result["_integrity"]=report;result["_integrity_retries"]=attempt
            if self.cancel_event.is_set(): self.signals.cancelled.emit()
            else: self.signals.completed.emit(result)
        except Exception as exc:
            if self.cancel_event.is_set(): self.signals.cancelled.emit()
            else: self.signals.failed.emit(str(exc))
