import sys,logging
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app.constants import APP_NAME,ORG_NAME
from repositories.history_repository import HistoryRepository
from services.ytdlp_service import YTDLPService
from services.cookie_service import cookie_file_from_settings,cookie_source_from_settings
from services.ffmpeg_service import FFmpegService
from ui.main_window import MainWindow
from utils.logger import setup_logging
from utils.paths import DATA_DIR,ensure_directories

def run() -> int:
    ensure_directories(); app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName(ORG_NAME); app.setApplicationVersion("1.0.0")
    logger,emitter=setup_logging(); settings=QSettings(); repo=HistoryRepository(DATA_DIR/"history.db"); service=YTDLPService(logger)
    FFmpegService.set_location(settings.value("ffmpeg/location","") or None);service.configure(settings);logger.setLevel(getattr(logging,str(settings.value("advanced/log_level","INFO")),logging.INFO))
    try:service.set_cookie_source(cookie_source_from_settings(settings));service.set_cookie_file(cookie_file_from_settings(settings))
    except ValueError as exc:logger.warning("Invalid cookie settings ignored: %s",exc);service.set_cookie_source(None);service.set_cookie_file(None)
    window=MainWindow(service,repo,settings,logger,emitter); window.show(); return app.exec()
