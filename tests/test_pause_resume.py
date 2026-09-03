from threading import Event, Thread
import time
from models.download import DownloadRequest
from services.ytdlp_service import DownloadCancelled, YTDLPService
from workers.tasks import DownloadWorker

def test_pause_waits_and_resumes():
    pause, cancel = Event(), Event(); states=[]; pause.set()
    thread=Thread(target=YTDLPService.wait_while_paused,args=(pause,cancel,states.append)); thread.start()
    deadline=time.monotonic()+2
    while states!=[True] and time.monotonic()<deadline: time.sleep(0.01)
    assert thread.is_alive() and states==[True]
    pause.clear(); thread.join(2)
    assert not thread.is_alive() and states==[True,False]

def test_cancel_interrupts_pause_immediately():
    pause, cancel = Event(), Event(); pause.set(); errors=[]
    def run():
        try:YTDLPService.wait_while_paused(pause,cancel,lambda _paused:None)
        except Exception as exc:errors.append(exc)
    thread=Thread(target=run); thread.start(); time.sleep(0.05); started=time.monotonic(); cancel.set(); thread.join(1)
    assert not thread.is_alive() and time.monotonic()-started<0.5
    assert isinstance(errors[0],DownloadCancelled)

def test_worker_pause_resume_cancel_flags(tmp_path):
    worker=DownloadWorker(object(),DownloadRequest("https://example.com/v","Title",str(tmp_path)))
    assert worker.pause() and worker.pause_event.is_set()
    assert worker.resume() and not worker.pause_event.is_set()
    worker.pause(); worker.cancel()
    assert worker.cancel_event.is_set() and not worker.pause_event.is_set()
    assert not worker.pause()

