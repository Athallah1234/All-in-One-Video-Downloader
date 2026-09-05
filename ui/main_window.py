from PySide6.QtCore import QSettings,Qt,QUrl
from PySide6.QtGui import QAction,QDesktopServices,QKeySequence,QShortcut
from PySide6.QtWidgets import QApplication,QMainWindow,QMessageBox,QTabWidget,QToolBar
from app.constants import APP_NAME,APP_VERSION
from services.ffmpeg_service import FFmpegService
from ui.dialogs import AboutDialog,SettingsDialog,SupportedSitesDialog
from ui.styles import DARK,LIGHT
from ui.tabs import DownloaderTab,HistoryTab,LogTab
from utils.paths import LOG_DIR
from services.cookie_service import cookie_file_from_settings,cookie_source_from_settings

class MainWindow(QMainWindow):
    def __init__(self,service,repo,settings:QSettings,logger,emitter):
        super().__init__(); self.settings=settings; self.logger=logger; self.active=0; self.setWindowTitle(f"{APP_NAME} {APP_VERSION}"); self.resize(1180,780); self.setAcceptDrops(True)
        toolbar=QToolBar("Main toolbar"); toolbar.setMovable(False); self.addToolBar(toolbar); toolbar.addWidget(self._spacer());
        for title,callback in (("Supported Websites",self.sites),("Settings",self.open_settings),("About",lambda:AboutDialog(self).exec())):
            action=QAction(title,self); action.triggered.connect(callback); toolbar.addAction(action)
        self.tabs=QTabWidget(); self.downloader=DownloaderTab(service,repo,settings,logger); self.history=HistoryTab(repo); self.log=LogTab(emitter,LOG_DIR/"app.log"); self.tabs.addTab(self.downloader,"Downloader"); self.tabs.addTab(self.history,"History"); self.tabs.addTab(self.log,"Log"); self.setCentralWidget(self.tabs);startup={"Downloader":0,"History":1,"Log":2}.get(str(settings.value("general/startup_tab","Downloader")),0);self.tabs.setCurrentIndex(startup)
        self.downloader.status.connect(self.statusBar().showMessage); self.downloader.history_changed.connect(self.history.refresh); self.downloader.active_changed.connect(self.set_active); self.statusBar().showMessage(f"yt-dlp {service.version()} · FFmpeg {'Detected' if FFmpegService.available() else 'Not Detected'} · v{APP_VERSION}")
        self.shortcuts(); self.apply_theme()
        if str(settings.value("general/remember_window",True)).lower() in {"true","1","yes"} and settings.value("general/window_geometry"):self.restoreGeometry(settings.value("general/window_geometry"))
        self.logger.info("Application started")
    def _spacer(self):
        from PySide6.QtWidgets import QWidget,QSizePolicy
        w=QWidget(); w.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred); return w
    def shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"),self,activated=self.downloader.url.setFocus); QShortcut(QKeySequence("Ctrl+Enter"),self,activated=self.downloader.analyze); QShortcut(QKeySequence("Ctrl+H"),self,activated=lambda:self.tabs.setCurrentIndex(1)); QShortcut(QKeySequence("Ctrl+Shift+L"),self,activated=lambda:self.tabs.setCurrentIndex(2));QShortcut(QKeySequence("Ctrl+Shift+P"),self,activated=self.downloader.toggle_global_pause); QShortcut(QKeySequence("Ctrl+,"),self,activated=self.open_settings); QShortcut(QKeySequence("Ctrl+Q"),self,activated=self.close)
    def sites(self): SupportedSitesDialog(self).exec()
    def open_settings(self):
        dialog=SettingsDialog(self.settings,self);dialog.settings_applied.connect(self.apply_settings);dialog.exec()
    def apply_settings(self):
        FFmpegService.set_location(self.settings.value("ffmpeg/location","") or None);self.downloader.service.configure(self.settings);self.logger.setLevel(getattr(__import__("logging"),str(self.settings.value("advanced/log_level","INFO")),20));self.apply_theme();self.downloader.apply_saved_defaults();self.downloader.populate_containers()
        try:self.downloader.service.set_cookie_source(cookie_source_from_settings(self.settings));self.downloader.service.set_cookie_file(cookie_file_from_settings(self.settings))
        except ValueError as exc:self.logger.warning("Invalid cookie settings ignored: %s",exc);self.downloader.service.set_cookie_source(None);self.downloader.service.set_cookie_file(None);QMessageBox.warning(self,"Invalid cookie settings","Cookie authentication was disabled because its configuration is invalid.")
        preferred=self.settings.value("video/container","auto");index=self.downloader.container.findData(None if preferred=="auto" else preferred)
        if index>=0 and self.downloader.container.model().item(index).isEnabled():self.downloader.container.setCurrentIndex(index)
    def apply_theme(self):
        theme=self.settings.value("appearance/theme","Dark");compact="QPushButton,QLineEdit,QComboBox,QSpinBox{padding:3px;}" if str(self.settings.value("appearance/compact",False)).lower() in {"true","1","yes"} else "";QApplication.instance().setStyleSheet((LIGHT if theme in ("Light","System") else DARK)+compact)
        try:font_size=int(self.settings.value("appearance/font_size",10))
        except (TypeError,ValueError):font_size=10
        font=QApplication.instance().font();font.setPointSize(max(8,min(20,font_size)));QApplication.instance().setFont(font);self.statusBar().setVisible(str(self.settings.value("appearance/statusbar",True)).lower() in {"true","1","yes"})
        alternating=str(self.settings.value("appearance/alternating_rows",True)).lower() in {"true","1","yes"}
        for table in self.findChildren(__import__("PySide6.QtWidgets",fromlist=["QTableWidget"]).QTableWidget):table.setAlternatingRowColors(alternating)
        self.downloader.preview_panel.setVisible(str(self.settings.value("appearance/show_preview",True)).lower() in {"true","1","yes"})
    def set_active(self,count): self.active=count
    def dragEnterEvent(self,event):
        if event.mimeData().hasText() and event.mimeData().text().strip().startswith(("http://","https://")):event.acceptProposedAction()
    def dropEvent(self,event): self.downloader.url.setText(event.mimeData().text().strip()); self.tabs.setCurrentIndex(0); event.acceptProposedAction()
    def closeEvent(self,event):
        confirm=str(self.settings.value("general/confirm_exit",True)).lower() in {"true","1","yes"}
        if self.active and confirm and QMessageBox.question(self,"Downloads active",f"Cancel {self.active} active download(s) and exit?")==QMessageBox.No:event.ignore();return
        if self.active:self.downloader.cancel_all()
        if str(self.settings.value("general/remember_window",True)).lower() in {"true","1","yes"}:self.settings.setValue("general/window_geometry",self.saveGeometry())
        event.accept()
