"""Application shell and safe background-worker shutdown."""
import json
import logging
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QAction, QDesktopServices
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QSplitter, QMessageBox, QApplication, QSystemTrayIcon)
from yt_dlp.version import __version__ as ydl_version
from app.core.ffmpeg import detect, version_status
from app.core.format_builder import build_options
from app.core.models import Status
from app.core.utils import valid_url
from app.services.settings import ROOT
from app.ui.downloader import DownloaderTab
from app.ui.dialogs import SettingsDialog, SupportedSitesDialog, show_about
from app.ui.library import QueueView, HistoryTab, LogTab
from app.ui.theme import apply_theme
from app.ui.widgets import button, details, open_path

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, settings, repository, manager, log_bus):
        super().__init__()
        self.settings, self.repository, self.manager = settings, repository, manager
        self.exiting = False
        self.seen_clipboard = ""
        self.sites_dialog = None
        self.setWindowTitle("Simple Video Downloader")
        self.setWindowIcon(QIcon(str(ROOT / "assets/icons/app.svg")))
        self.setMinimumSize(1100, 700)
        self.resize(max(1100, settings["width"]), max(700, settings["height"]))
        if settings["window_x"] >= 0 and settings["window_y"] >= 0:
            from PySide6.QtCore import QPoint
            point = QPoint(settings["window_x"], settings["window_y"])
            if any(screen.availableGeometry().contains(point) for screen in QApplication.screens()):
                self.move(point)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 16, 22, 8)
        header = QHBoxLayout()
        title_stack = QVBoxLayout()
        title = QLabel("↓  Simple Video Downloader")
        title.setObjectName("heading")
        subtitle = QLabel("Your media, neatly saved.  •  Powered by yt-dlp")
        subtitle.setObjectName("muted")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        header.addLayout(title_stack, 1)
        header.addWidget(button("Supported Websites", self.supported))
        header.addWidget(button("⚙  Settings", self.configure))
        layout.addLayout(header)
        notice = QLabel("Download only content you own or have permission to save. You are responsible for respecting copyright and website terms. DRM is not supported.")
        notice.setWordWrap(True)
        notice.setObjectName("notice")
        layout.addWidget(notice)
        self.clipboard_banner = QWidget()
        clipboard_layout = QHBoxLayout(self.clipboard_banner)
        clipboard_layout.setContentsMargins(0, 0, 0, 0)
        clipboard_layout.addWidget(QLabel("URL detected in clipboard."), 1)
        clipboard_layout.addWidget(button("Use URL", self.use_clipboard))
        clipboard_layout.addWidget(button("Ignore", self.clipboard_banner.hide))
        layout.addWidget(self.clipboard_banner)
        self.clipboard_banner.hide()
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        download_page = QWidget()
        download_layout = QVBoxLayout(download_page)
        download_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.downloader = DownloaderTab(settings)
        self.queue = QueueView(manager)
        splitter.addWidget(self.downloader)
        splitter.addWidget(self.queue)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 190])
        splitter.setChildrenCollapsible(False)
        download_layout.addWidget(splitter)
        self.tabs.addTab(download_page, "Downloader")
        self.history = HistoryTab(repository)
        self.tabs.addTab(self.history, "History")
        self.logs = LogTab(log_bus)
        self.tabs.addTab(self.logs, "Log")
        self.tabs.setCurrentIndex(max(0, min(2, settings["tab"])))
        self.setCentralWidget(central)
        self.downloader.request_download.connect(manager.add)
        self.history.retry_requested.connect(self.retry_history)
        self.tabs.currentChanged.connect(lambda index: self.history.refresh() if index == 1 else None)
        self.manager.changed.connect(self.status)
        self.manager.ended.connect(self.task_ended)
        self.build_menu()
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.status()
        QApplication.instance().styleHints().colorSchemeChanged.connect(lambda scheme: apply_theme(QApplication.instance(), "System") if self.settings["theme"] == "System" else None)
        ffmpeg_info = detect(settings["ffmpeg"])
        if not ffmpeg_info["ffmpeg"]:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "FFmpeg not found", "FFmpeg was not found. Best combined video and original audio can still be downloaded; merging, conversion and embedding require FFmpeg. Configure its folder in Settings."))
        elif ffmpeg_info["ffmpeg_compatible"] is False:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "FFmpeg is too old", f"Installed FFmpeg is {ffmpeg_info['ffmpeg_version']}; this application requires FFmpeg {ffmpeg_info['minimum_version']} or newer for supported media processing."))

    def action(self, menu, label, callback, shortcut=None):
        action = QAction(label, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def build_menu(self):
        file_menu = self.menuBar().addMenu("File")
        self.action(file_menu, "Add URL", self.focus_url, "Ctrl+L")
        self.action(file_menu, "Import URLs…", self.downloader.import_urls, "Ctrl+O")
        self.action(file_menu, "Open Download Folder", lambda: open_path(self.downloader.output.text(), True))
        self.action(file_menu, "Settings", self.configure, "Ctrl+,")
        file_menu.addSeparator()
        self.action(file_menu, "Exit", self.close, "Ctrl+Q")
        tools = self.menuBar().addMenu("Tools")
        self.action(tools, "Supported Websites", self.supported)
        self.action(tools, "FFmpeg Status", lambda: details(self, "FFmpeg status", detect(self.settings["ffmpeg"])))
        self.action(tools, "Clear Completed", self.queue.clear_completed)
        self.action(tools, "Refresh", self.refresh, "F5")
        self.action(tools, "View Log", lambda: self.tabs.setCurrentIndex(2), "Ctrl+Shift+L")
        help_menu = self.menuBar().addMenu("Help")
        self.action(help_menu, "About", lambda: show_about(self, self.settings))
        self.action(help_menu, "yt-dlp GitHub", lambda: QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp")))
        self.action(help_menu, "Documentation", lambda: QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp#readme")))

    def focus_url(self):
        self.tabs.setCurrentIndex(0)
        self.downloader.url.setFocus()
        self.downloader.url.selectAll()

    def refresh(self):
        self.history.refresh()
        self.status()
        if self.tabs.currentIndex() == 0 and valid_url(self.downloader.url.text()):
            self.downloader.analyze()

    def status(self):
        ff = version_status(detect(self.settings["ffmpeg"]))
        self.statusBar().showMessage(f"{'Waiting for workers to stop…' if self.exiting else 'Ready'}   |   yt-dlp {ydl_version}   |   FFmpeg: {ff}   |   Active: {len(self.manager.workers)}")

    def configure(self):
        if SettingsDialog(self.settings, self).exec():
            apply_theme(QApplication.instance(), self.settings["theme"])
            self.manager.concurrency = self.settings["concurrency"]
            for key in ["format", "quality", "audio_quality", "container"]:
                getattr(self.downloader, key).setCurrentText(self.settings[key])
            self.downloader.output.setText(self.settings["output"])
            self.manager.pump()
            self.status()

    def supported(self):
        if self.sites_dialog is None:
            self.sites_dialog = SupportedSitesDialog(self)
        self.sites_dialog.show()
        self.sites_dialog.raise_()
        self.sites_dialog.activateWindow()

    def retry_history(self, record):
        preferences = self.settings.values.copy()
        try:
            saved = json.loads(record["preferences"] or "{}")
            if not isinstance(saved, dict):
                raise ValueError("History preferences are invalid.")
            preferences.update(saved)
            preferences["mode"] = record["media_type"]
            if not valid_url(record["source_url"]):
                raise ValueError("History does not contain a valid HTTP/HTTPS URL.")
            build_options(preferences)
            self.manager.add(record["source_url"], preferences, record["media_type"])
            self.tabs.setCurrentIndex(0)
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Cannot retry", str(error))

    def task_ended(self, task):
        self.history.refresh()
        if self.settings["notifications"] and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage("Download " + str(task.status).lower(), task.title, QSystemTrayIcon.MessageIcon.Information if task.status == Status.COMPLETED else QSystemTrayIcon.MessageIcon.Warning)
        if self.settings["auto_open"] and task.status == Status.COMPLETED:
            open_path(task.options["output"], True)

    def clipboard_changed(self):
        if not self.settings["clipboard"]:
            return
        value = QApplication.clipboard().text().strip()
        if value != self.seen_clipboard and valid_url(value):
            self.seen_clipboard = value
            self.clipboard_banner.show()

    def use_clipboard(self):
        self.downloader.url.setText(self.seen_clipboard)
        self.tabs.setCurrentIndex(0)
        self.clipboard_banner.hide()

    def busy(self):
        return bool(self.manager.workers or self.downloader.worker
                    or self.downloader.resolution_worker or self.downloader.batch_validation_worker
                    or self.sites_dialog and self.sites_dialog.worker)

    def closeEvent(self, event):
        if self.exiting:
            if self.busy():
                event.ignore()
                return
            self.save_state()
            event.accept()
            return
        if self.busy() or any(t.status in {Status.WAITING, Status.PAUSING, Status.PAUSED, Status.RETRYING} for t in self.manager.tasks.values()):
            answer = QMessageBox.question(self, "Background work is running", "Downloads or analysis are still running. Cancel downloads and exit after workers stop?\n\nCancellation waits for the next yt-dlp hook. An ongoing network request or FFmpeg operation may need to finish first.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.exiting = True
            self.manager.shutdown()
            self.centralWidget().setEnabled(False)
            self.menuBar().setEnabled(False)
            self.status()
            self.exit_timer = QTimer(self)
            self.exit_timer.timeout.connect(lambda: self.close() if not self.busy() else None)
            self.exit_timer.start(250)
            event.ignore()
            return
        if self.settings["confirm_exit"] and QMessageBox.question(self, "Exit", "Close Simple Video Downloader?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self.save_state()
        event.accept()

    def save_state(self):
        self.settings.values.update(width=self.width(), height=self.height(), tab=self.tabs.currentIndex(), window_x=self.x(), window_y=self.y())
        try:
            self.downloader.persist_preferences()
        except OSError as error:
            logger.error("Unable to save window state: %s", error)
        logger.info("Application shutdown")
