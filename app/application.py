"""Startup sequence and resource ownership."""
import logging
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from app.core.ffmpeg import detect
from app.core.queue_manager import QueueManager
from app.database.history import HistoryRepository
from app.services.settings import Settings
from app.services.logging_service import initialize
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Simple Video Downloader")
    app.setOrganizationName("SimpleVideoDownloader")
    app.setStyle("Fusion")
    try:
        bus = initialize()
        settings = Settings()
        repository = HistoryRepository()
        apply_theme(app, settings["theme"])
        manager = QueueManager(repository, settings["concurrency"])
        window = MainWindow(settings, repository, manager, bus)
    except Exception as error:
        logging.getLogger(__name__).error("Startup failed: %s", error)
        QMessageBox.critical(None, "Startup failed", f"The application could not start:\n{error}\n\nCheck write permissions for the project folder and installed dependencies.")
        return 1
    window.show()
    logging.getLogger(__name__).info("Application startup; Python %s", sys.version.split()[0])
    logging.getLogger(__name__).info("FFmpeg detection: %s", detect(settings["ffmpeg"]))
    result = app.exec()
    repository.close()
    logging.shutdown()
    return result
