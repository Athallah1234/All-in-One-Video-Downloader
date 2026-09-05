from threading import Event
from services.system_state_service import SystemState,automatic_pause_reasons

def test_idle_policy_threshold():
    assert not automatic_pause_reasons(SystemState(idle_seconds=599),True,10,False,20,5)
    assert automatic_pause_reasons(SystemState(idle_seconds=600),True,10,False,20,5)=={"Computer idle ≥ 10 min"}

def test_low_battery_requires_battery_power_and_has_hysteresis():
    low=SystemState(battery_percent=20,on_battery=True,charging=False)
    assert automatic_pause_reasons(low,False,30,True,20,5)
    assert automatic_pause_reasons(SystemState(battery_percent=24,on_battery=True),False,30,True,20,5,True)
    assert not automatic_pause_reasons(SystemState(battery_percent=26,on_battery=True),False,30,True,20,5,True)
    assert not automatic_pause_reasons(SystemState(battery_percent=10,on_battery=False,charging=True),False,30,True,20,5,True)
    assert not automatic_pause_reasons(SystemState(),True,30,True,20,5)

class FakeWorker:
    def __init__(self,paused=False):self.pause_event=Event();self.cancel_event=Event();self.pause_calls=0;self.resume_calls=0
    def pause(self):self.pause_calls+=1;self.pause_event.set();return True
    def resume(self):self.resume_calls+=1;was=self.pause_event.is_set();self.pause_event.clear();return was

def test_global_pause_tracks_only_workers_it_paused(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from models.download import DownloadRequest
    from services.ytdlp_service import YTDLPService
    from ui.tabs import DownloaderTab
    import logging
    class Repo:pass
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat);tab=DownloaderTab(YTDLPService(logging.getLogger("test")),Repo(),settings,logging.getLogger("test"))
    first=DownloadRequest("https://example.com/1","One",str(tmp_path));second=DownloadRequest("https://example.com/2","Two",str(tmp_path));manual=FakeWorker();manual.pause();global_worker=FakeWorker()
    tab.workers={first.id:manual,second.id:global_worker};tab.queue=[{"request":first,"status":"Paused","progress":0,"output":"","estimated_size":"Unknown","integrity_label":"Pending"},{"request":second,"status":"Downloading","progress":0,"output":"","estimated_size":"Unknown","integrity_label":"Pending"}]
    assert tab.global_pause_button.text()=="Pause All" and not hasattr(tab,"global_resume_button")
    tab.toggle_global_pause();assert tab.global_pause_button.text()=="Resume All";assert tab.globally_paused_ids=={second.id};assert global_worker.pause_event.is_set()
    tab.toggle_global_pause();assert tab.global_pause_button.text()=="Pause All";assert not global_worker.pause_event.is_set();assert manual.pause_event.is_set();tab.close()

def test_resume_button_overrides_active_automatic_policy_until_clear(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from services.ytdlp_service import YTDLPService
    from ui.tabs import DownloaderTab
    import logging
    app=QApplication.instance() or QApplication([]);settings=QSettings(str(tmp_path/"policy.ini"),QSettings.IniFormat);tab=DownloaderTab(YTDLPService(logging.getLogger("test")),object(),settings,logging.getLogger("test"));tab.global_policy_reasons={"Battery low (10% ≤ 20%)"};tab.update_global_pause_status();assert tab.global_pause_button.text()=="Resume All"
    tab.toggle_global_pause();assert tab.global_policy_override and tab.global_pause_button.text()=="Pause All";tab.global_policy_reasons.clear();tab.update_global_pause_status();tab.close()

def test_global_pause_blocks_new_scheduler_starts():
    from types import SimpleNamespace
    from ui.tabs import DownloaderTab
    class Harness:
        start_available=DownloaderTab.start_available;global_pause_active=DownloaderTab.global_pause_active
        def __init__(self):self.queue=[{"request":SimpleNamespace(id="x"),"status":"Waiting"}];self.workers={};self.queue_run_enabled=True;self.global_manual_pause=True;self.global_policy_reasons=set();self.global_policy_override=False;self.settings=SimpleNamespace(value=lambda *_:2);self.started=[]
        def start_item(self,item):self.started.append(item);return True
    harness=Harness();harness.start_available();assert not harness.started
