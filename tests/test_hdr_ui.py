import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import logging
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from ui.tabs import DownloaderTab

def test_hdr_and_dolby_vision_ui():
    app=QApplication.instance() or QApplication([])
    tab=DownloaderTab(None,None,QSettings("HdrSmoke","HdrSmoke"),logging.getLogger("test"))
    formats=[
        {"format_id":"dv","height":2160,"vcodec":"dvhe.05.06","acodec":"none","fps":60,"dynamic_range":"DV","tbr":10000},
        {"format_id":"h10","height":2160,"vcodec":"hev1.2.4","acodec":"none","fps":60,"dynamic_range":"HDR10","tbr":9000},
        {"format_id":"sdr","height":2160,"vcodec":"hev1.1.4","acodec":"none","fps":60,"dynamic_range":"SDR","tbr":8000},
        {"format_id":"audio","vcodec":"none","acodec":"mp4a"},
    ]
    tab.show_info({"title":"HDR","formats":formats});tab.resolution.setCurrentIndex(tab.resolution.findData(2160));tab.codec.setCurrentIndex(tab.codec.findData("h265"));tab.fps.setCurrentIndex(tab.fps.findData(60))
    dv=tab.dynamic_range.findData("DV");hdr10=tab.dynamic_range.findData("HDR10");hdr12=tab.dynamic_range.findData("HDR12")
    assert tab.dynamic_range.model().item(dv).isEnabled() and tab.dynamic_range.model().item(hdr10).isEnabled() and not tab.dynamic_range.model().item(hdr12).isEnabled()
    tab.dynamic_range.setCurrentIndex(dv);assert tab.selected_format_selector(tab.info,[])=="dv+bestaudio"
    tab.show_info({"_type":"playlist","title":"HDR List","entries":[{"id":"1"}]});tab.resolution.setCurrentIndex(tab.resolution.findData(2160));tab.codec.setCurrentIndex(tab.codec.findData("h265"));tab.dynamic_range.setCurrentIndex(tab.dynamic_range.findData("DV"));selector=tab.selected_format_selector(tab.info,[1])
    assert "dynamic_range='DV'" in selector and not selector.startswith("dv+")
    assert tab.dynamic_range.isEnabled() and not tab.bit_depth.isEnabled()
    tab.close()
