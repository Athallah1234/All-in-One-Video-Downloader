import os
import time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.dialogs import BatchUrlDialog

class FakeService:
    def extract_info(self,url):
        if "bad" in url: raise RuntimeError("simulated extractor error")
        return {"id":url.rsplit("/",1)[-1],"title":f"Title {url[-1]}","webpage_url":url}

def test_batch_analysis_success_and_failure():
    app=QApplication.instance() or QApplication([])
    dialog=BatchUrlDialog(FakeService())
    dialog.input.setPlainText("https://example.com/1\nhttps://example.com/bad\nhttps://example.com/2")
    dialog.start_analysis()
    deadline=time.monotonic()+5
    while dialog.active or dialog.pending:
        app.processEvents()
        if time.monotonic()>deadline: raise AssertionError("batch workers timed out")
    assert [record["status"] for record in dialog.records].count("Ready")==2
    assert [record["status"] for record in dialog.records].count("Failed")==1
    assert len(dialog.chosen_rows())==2
    dialog.accept_results()
    assert len(dialog.results())==2
    dialog.close()
