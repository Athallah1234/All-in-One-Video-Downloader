import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.logger import LogEmitter


class FakeService:
    def version(self):return "test"
    def configure(self,_settings):pass
    def set_cookie_source(self,_source):pass
    def set_cookie_file(self,_path):pass


class FakeRepository:
    def get_all(self,*_args):return []


def test_main_window_survives_corrupt_font_size_setting(tmp_path):
    app=QApplication.instance() or QApplication([])
    settings=QSettings(str(tmp_path/"settings.ini"),QSettings.IniFormat);settings.setValue("appearance/font_size","not-a-number")
    window=MainWindow(FakeService(),FakeRepository(),settings,logging.getLogger("test-main-window"),LogEmitter())
    assert app.font().pointSize()==10
    assert window.tabs.count()==3
    window.close()
