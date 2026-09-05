from types import SimpleNamespace

from ui.tabs import DownloaderTab


def queue_item(identifier,status):
    return {"request":SimpleNamespace(id=identifier),"status":status}


class SchedulerHarness:
    start_available=DownloaderTab.start_available
    start_all=DownloaderTab.start_all
    cancel_all=DownloaderTab.cancel_all

    def __init__(self,items):
        self.queue=items;self.queue_run_enabled=True;self.workers={};self.estimators={};self.started=[];self.rendered=0
        self.settings=SimpleNamespace(value=lambda _key,default=None:2)

    def start_item(self,item):
        self.started.append(item["request"].id);item["status"]="Downloading";return True

    def cancel_item(self,item):
        self.workers[item["request"].id].cancel();item["status"]="Cancelling…"

    def render_queue(self):self.rendered+=1


class FakeWorker:
    def __init__(self):self.cancelled=False
    def cancel(self):self.cancelled=True


def test_scheduler_does_not_automatically_restart_failed_or_cancelled_items():
    harness=SchedulerHarness([queue_item("waiting","Waiting"),queue_item("failed","Failed"),queue_item("cancelled","Cancelled")])
    harness.start_available()
    assert harness.started==["waiting"]


def test_start_all_explicitly_retries_failed_and_cancelled_items():
    harness=SchedulerHarness([queue_item("failed","Failed"),queue_item("cancelled","Cancelled")])
    harness.start_all()
    assert harness.started==["failed","cancelled"]


def test_start_all_resumes_an_estimate_that_was_cancelled_logically():
    item=queue_item("estimate","Cancelled");harness=SchedulerHarness([item]);harness.estimators={"estimate":object()}
    harness.start_all()
    assert item["status"]=="Estimating size…" and harness.started==[]


def test_cancel_all_stops_scheduler_and_cancels_waiting_items():
    active=queue_item("active","Downloading");waiting=queue_item("waiting","Waiting");estimating=queue_item("estimate","Estimating size…")
    harness=SchedulerHarness([active,waiting,estimating]);worker=FakeWorker();harness.workers={"active":worker}
    harness.cancel_all()
    assert not harness.queue_run_enabled and worker.cancelled
    assert active["status"]=="Cancelling…"
    assert waiting["status"]==estimating["status"]=="Cancelled"
