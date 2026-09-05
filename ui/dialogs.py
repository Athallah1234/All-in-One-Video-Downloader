import csv, json, platform, sys
from pathlib import Path
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QSettings, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import *
from app.constants import APP_NAME, APP_VERSION
from services.ffmpeg_service import FFmpegService
from services.aria2_service import Aria2Service
from services.ytdlp_service import YTDLPService
from workers.tasks import MetadataWorker
from utils.formatters import format_duration
from utils.validators import parse_batch_urls,validate_output_template
from utils.containers import CONTAINER_PRESETS
from services.cookie_service import SUPPORTED_COOKIE_BROWSERS,detected_browsers,validate_netscape_cookie_file
from utils.extractor_args import parse_batch_url_specs
from utils.channels import channel_entry_type,format_upload_date,is_channel_info

class PlaylistDialog(QDialog):
    """Checklist dialog for selecting exact one-based playlist entries."""
    BATCH_SIZE = 250

    def __init__(self, playlist: dict, selected: list[int] | None = None, parent=None):
        super().__init__(parent)
        self.is_channel=bool(playlist.get("_app_is_channel") or is_channel_info(playlist))
        self.setWindowTitle("Choose Channel Videos" if self.is_channel else "Choose Playlist Items")
        self.resize(1120 if self.is_channel else 940, 680)
        self.entries = list(playlist.get("entries") or [])
        self.initial_selected = set(selected or [])
        self.entry_by_index = {}
        self._next_entry = 0
        self._selection = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel(f"<h2>{playlist.get('channel') or playlist.get('title') or ('Channel' if self.is_channel else 'Playlist')}</h2>"))
        detail=f"{playlist.get('uploader') or playlist.get('channel') or 'Unknown uploader'} · {len(self.entries)} loaded item(s)"
        if self.is_channel:
            detail+=f" · ID {playlist.get('channel_id') or playlist.get('uploader_id') or '—'}"
            if playlist.get("channel_follower_count") is not None:detail+=f" · {int(playlist['channel_follower_count']):,} followers"
            if playlist.get("_app_channel_truncated"):detail+=f" · analysis limited to first {playlist.get('_app_channel_limit')} items"
        header=QLabel(detail);header.setWordWrap(True);root.addWidget(header)
        if self.is_channel:
            notice=QLabel("Channel items are not selected automatically. Search or filter the loaded results, then explicitly select the videos to queue. Increase the channel analysis limit in Settings if older items are needed.");notice.setWordWrap(True);root.addWidget(notice)
        tools = QHBoxLayout()
        self.search = QLineEdit(); self.search.setClearButtonEnabled(True); self.search.setPlaceholderText("Search title, uploader, or media ID…")
        self.availability = QComboBox(); self.availability.addItems(["All items", "Available only", "Unavailable only"])
        self.content_type=QComboBox();self.content_type.addItems(["All content","Videos","Shorts","Live / past live"]);self.content_type.setVisible(self.is_channel)
        select = QPushButton("Select Visible"); none = QPushButton("Select None"); invert = QPushButton("Invert Visible")
        tools.addWidget(self.search, 1);tools.addWidget(self.content_type); tools.addWidget(self.availability); tools.addWidget(select); tools.addWidget(none); tools.addWidget(invert); root.addLayout(tools)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Download", "#", "Title", "Type", "Duration", "Upload date", "Views", "Uploader", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.update_summary)
        self.table.itemDoubleClicked.connect(self.toggle_row)
        root.addWidget(self.table, 1)
        status = QHBoxLayout(); self.loading = QProgressBar(); self.loading.setRange(0, max(1, len(self.entries))); self.summary = QLabel("Preparing playlist…"); status.addWidget(self.loading, 1); status.addWidget(self.summary); root.addLayout(status)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel); self.use_button = buttons.addButton("Use Selected Items", QDialogButtonBox.AcceptRole); self.use_button.setObjectName("primary"); self.use_button.setEnabled(False); root.addWidget(buttons)
        self.search.textChanged.connect(self.apply_filter); self.availability.currentIndexChanged.connect(self.apply_filter);self.content_type.currentIndexChanged.connect(self.apply_filter)
        select.clicked.connect(lambda: self.set_visible_checks(Qt.Checked)); none.clicked.connect(self.select_none); invert.clicked.connect(self.invert_visible)
        buttons.accepted.connect(self.accept_selection); buttons.rejected.connect(self.reject)
        QTimer.singleShot(0, self.populate_batch)

    @staticmethod
    def entry_index(entry: dict, fallback: int) -> int:
        value = entry.get("playlist_index") or entry.get("playlist_autonumber") or fallback
        try: return max(1, int(value))
        except (TypeError, ValueError): return fallback

    @staticmethod
    def is_available(entry: dict) -> bool:
        restricted = {"private", "premium_only", "subscriber_only", "needs_auth"}
        return bool(entry.get("id") or entry.get("url")) and entry.get("availability") not in restricted

    def populate_batch(self):
        end = min(self._next_entry + self.BATCH_SIZE, len(self.entries))
        self.table.blockSignals(True)
        for offset in range(self._next_entry, end):
            entry = self.entries[offset] or {}; index = self.entry_index(entry, offset + 1); self.entry_by_index[index] = entry
            row = self.table.rowCount(); self.table.insertRow(row)
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable); check.setData(Qt.UserRole, index)
            checked = index in self.initial_selected if self.initial_selected else (self.is_available(entry) and not self.is_channel); check.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            if not self.is_available(entry): check.setToolTip("Item appears unavailable and is not selected by default.")
            self.table.setItem(row, 0, check)
            views=f"{int(entry['view_count']):,}" if isinstance(entry.get("view_count"),(int,float)) else "—";values = (index, entry.get("title") or "Unavailable / untitled item",channel_entry_type(entry), format_duration(entry.get("duration")),format_upload_date(entry.get("upload_date") or entry.get("release_date")),views, entry.get("uploader") or entry.get("channel") or "—", entry.get("id") or "—")
            for column, value in enumerate(values, 1): self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.blockSignals(False); self._next_entry = end; self.loading.setValue(end); self.apply_filter()
        if end < len(self.entries): QTimer.singleShot(0, self.populate_batch)
        else: self.loading.hide(); self.table.setSortingEnabled(True); self.update_summary()

    def apply_filter(self):
        term = self.search.text().strip().casefold(); mode = self.availability.currentIndex();content=self.content_type.currentIndex()
        for row in range(self.table.rowCount()):
            index = int(self.table.item(row, 0).data(Qt.UserRole)); entry = self.entry_by_index.get(index, {}); available = self.is_available(entry)
            haystack = " ".join(self.table.item(row, col).text() for col in range(1,9)).casefold();kind=channel_entry_type(entry);kind_ok=content==0 or (content==1 and kind=="Video") or (content==2 and kind=="Short") or (content==3 and kind in {"Live","Past live"})
            visible = term in haystack and kind_ok and (mode == 0 or (mode == 1 and available) or (mode == 2 and not available))
            self.table.setRowHidden(row, not visible)
        self.update_summary()

    def set_visible_checks(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row): self.table.item(row, 0).setCheckState(state)
        self.table.blockSignals(False); self.update_summary()

    def select_none(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()): self.table.item(row, 0).setCheckState(Qt.Unchecked)
        self.table.blockSignals(False); self.update_summary()

    def invert_visible(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                item = self.table.item(row, 0); item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.table.blockSignals(False); self.update_summary()

    def toggle_row(self, item):
        check = self.table.item(item.row(), 0); check.setCheckState(Qt.Unchecked if check.checkState() == Qt.Checked else Qt.Checked)

    def selected_indices(self) -> list[int]:
        return sorted({int(self.table.item(row, 0).data(Qt.UserRole)) for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.Checked})

    def update_summary(self, *_):
        chosen = self.selected_indices(); visible = sum(not self.table.isRowHidden(row) for row in range(self.table.rowCount()))
        self.summary.setText(f"{len(chosen)} selected · {visible} visible · {len(self.entries)} total")
        self.use_button.setEnabled(bool(chosen) and self._next_entry >= len(self.entries))

    def accept_selection(self):
        self._selection = self.selected_indices()
        if not self._selection: QMessageBox.information(self, "No selection", "Select at least one playlist item."); return
        self.accept()

    def selection(self) -> list[int]: return list(self._selection)

class BatchUrlDialog(QDialog):
    """Analyze many URLs safely with bounded parallelism and per-URL results."""
    MAX_TEXT_FILE_BYTES = 20 * 1024 * 1024

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.pool = QThreadPool.globalInstance()
        self.records = []
        self.pending = []
        self.workers = {}
        self.active = 0
        self.stopped = False
        self._discarded = False
        self._results = []
        self.setWindowTitle("Batch URL Input & Analysis")
        self.resize(1080, 760)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("<h2>Batch URL Input</h2>"))
        hint = QLabel("Paste one URL per line. For per-URL extractor arguments, append a TAB then EXTRACTOR:ARG=VALUE. Blank/comment lines are ignored and duplicate URLs are analyzed once.")
        hint.setWordWrap(True); root.addWidget(hint)
        self.input = QPlainTextEdit(); self.input.setPlaceholderText("https://example.com/video-1\nhttps://youtube.com/watch?v=…\tyoutube:player_client=web;player_skip=webpage\n# comments are ignored"); self.input.setMaximumBlockCount(100000); root.addWidget(self.input, 1)
        input_tools = QHBoxLayout(); paste = QPushButton("Paste"); load = QPushButton("Load .txt…"); clear = QPushButton("Clear"); self.concurrent = QSpinBox(); self.concurrent.setRange(1, 5); self.concurrent.setValue(3); self.analyze = QPushButton("Analyze URLs"); self.analyze.setObjectName("primary"); self.stop = QPushButton("Stop Scheduling"); self.stop.setEnabled(False)
        input_tools.addWidget(paste); input_tools.addWidget(load); input_tools.addWidget(clear); input_tools.addStretch(); input_tools.addWidget(QLabel("Concurrent analyses")); input_tools.addWidget(self.concurrent); input_tools.addWidget(self.analyze); input_tools.addWidget(self.stop); root.addLayout(input_tools)
        self.validation = QLabel("Ready"); self.validation.setWordWrap(True); root.addWidget(self.validation)
        result_tools = QHBoxLayout(); successful = QPushButton("Select Successful"); none = QPushButton("Select None"); invert = QPushButton("Invert Selection"); playlist = QPushButton("Configure Playlist Items…"); retry = QPushButton("Retry Failed"); result_tools.addWidget(successful); result_tools.addWidget(none); result_tools.addWidget(invert); result_tools.addWidget(playlist); result_tools.addWidget(retry); result_tools.addStretch(); root.addLayout(result_tools)
        self.table = QTableWidget(0, 8); self.table.setHorizontalHeaderLabels(["Use", "#", "URL", "Title", "Type", "Items", "Status", "Error"]); self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch); self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setContextMenuPolicy(Qt.CustomContextMenu); root.addWidget(self.table, 2)
        footer = QHBoxLayout(); self.progress = QProgressBar(); self.progress.setRange(0, 1); self.summary = QLabel("0 URLs"); footer.addWidget(self.progress, 1); footer.addWidget(self.summary); root.addLayout(footer)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel); self.add_button = buttons.addButton("Add Selected to Queue", QDialogButtonBox.AcceptRole); self.add_button.setObjectName("primary"); self.add_button.setEnabled(False); root.addWidget(buttons)
        paste.clicked.connect(lambda: self.input.setPlainText(QApplication.clipboard().text())); load.clicked.connect(self.load_file); clear.clicked.connect(self.reset); self.analyze.clicked.connect(self.start_analysis); self.stop.clicked.connect(self.stop_scheduling)
        successful.clicked.connect(self.select_successful); none.clicked.connect(lambda: self.set_all_checks(Qt.Unchecked)); invert.clicked.connect(self.invert_selection); playlist.clicked.connect(self.configure_current_playlist); retry.clicked.connect(self.retry_failed)
        self.table.itemDoubleClicked.connect(lambda _item: self.configure_current_playlist()); self.table.customContextMenuRequested.connect(self.context_menu); self.table.itemChanged.connect(self.update_summary)
        buttons.accepted.connect(self.accept_results); buttons.rejected.connect(self.reject)

    def load_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Load URL list", "", "Text files (*.txt);;All files (*)")
        if not filename: return
        path = Path(filename)
        try:
            if path.stat().st_size > self.MAX_TEXT_FILE_BYTES: raise ValueError("The file is larger than the 20 MB safety limit.")
            data = path.read_bytes()
            text = None
            for encoding in ("utf-8-sig", "utf-16"):
                try: text = data.decode(encoding); break
                except UnicodeError: pass
            if text is None: raise ValueError("The file is not valid UTF-8 or UTF-16 text.")
            self.input.setPlainText(text)
        except (OSError, ValueError) as exc: QMessageBox.warning(self, "Cannot load file", str(exc))

    def reset(self):
        if self.active: QMessageBox.information(self, "Analysis active", "Stop scheduling and wait for active analyses before clearing."); return
        self.input.clear(); self.records.clear(); self.pending.clear(); self.workers.clear(); self.table.setRowCount(0); self.progress.setRange(0, 1); self.progress.setValue(0); self.validation.setText("Ready"); self.update_summary()

    def start_analysis(self):
        if self.active: return
        specs, invalid, duplicates = parse_batch_url_specs(self.input.toPlainText())
        if not specs:
            QMessageBox.warning(self, "No valid URLs", "Enter at least one valid HTTP or HTTPS URL."); return
        self.records = [{"url": url,"extractor_args_text":args_text,"extractor_args":args, "status": "Pending", "info": None, "error": "", "playlist_items": []} for url,args_text,args in specs]
        self.pending = list(range(len(self.records))); self.workers.clear(); self.active = 0; self.stopped = False
        self.table.blockSignals(True); self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable); check.setCheckState(Qt.Unchecked); self.table.setItem(row, 0, check)
            for column, value in enumerate((row + 1, record["url"], "—", "—", "—", "Pending", ""), 1): self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.blockSignals(False)
        invalid_preview = "; ".join(invalid[:3]); details = f"{len(specs)} unique valid URL(s) · {duplicates} duplicate(s) skipped · {len(invalid)} invalid line(s)"
        if invalid_preview: details += f" ({invalid_preview}{'…' if len(invalid)>3 else ''})"
        self.validation.setText(details); self.progress.setRange(0, len(self.records)); self.progress.setValue(0); self.analyze.setEnabled(False); self.stop.setEnabled(True); self.concurrent.setEnabled(False); self.add_button.setEnabled(False); self.schedule_more()

    def schedule_more(self):
        limit = self.concurrent.value()
        while not self.stopped and self.pending and self.active < limit:
            row = self.pending.pop(0); record = self.records[row]; record["status"] = "Analyzing"; self.table.item(row, 6).setText("Analyzing")
            worker = MetadataWorker(self.service, record["url"],record["extractor_args"]); self.workers[row] = worker; self.active += 1
            if record["extractor_args"]:self.table.item(row,2).setToolTip(f"Custom extractor arguments: {len(record['extractor_args'])} extractor(s); values hidden")
            worker.signals.metadata.connect(lambda info, r=row: self.analysis_succeeded(r, info)); worker.signals.failed.connect(lambda error, r=row: self.analysis_failed(r, error)); self.pool.start(worker)
        self.finish_if_idle()

    def analysis_succeeded(self, row, info):
        if self._discarded:
            self.workers.pop(row, None); self.active = max(0, self.active - 1); return
        if row >= len(self.records): return
        record = self.records[row]; record["info"] = info; record["status"] = "Ready"; entries = info.get("entries"); count = len(entries) if isinstance(entries, list) else 0; media_type = "Channel" if info.get("_app_is_channel") else ("Playlist" if count else (info.get("media_type") or "Media"))
        self.table.blockSignals(True); self.table.item(row, 0).setCheckState(Qt.Checked); self.table.item(row, 3).setText(info.get("title") or "Untitled"); self.table.item(row, 4).setText(media_type); self.table.item(row, 5).setText(str(count) if count else "—"); self.table.item(row, 6).setText("Ready" if not count else "Ready · choose playlist items"); self.table.blockSignals(False)
        self.worker_finished(row)

    def analysis_failed(self, row, error):
        if self._discarded:
            self.workers.pop(row, None); self.active = max(0, self.active - 1); return
        if row >= len(self.records): return
        record = self.records[row]; record["status"] = "Failed"; record["error"] = str(error); self.table.item(row, 6).setText("Failed"); self.table.item(row, 7).setText(str(error)[:500]); self.worker_finished(row)

    def worker_finished(self, row):
        self.workers.pop(row, None); self.active = max(0, self.active - 1); completed = sum(record["status"] in {"Ready", "Failed", "Stopped"} for record in self.records); self.progress.setValue(completed); self.schedule_more(); self.update_summary()

    def finish_if_idle(self):
        if self.active or (self.pending and not self.stopped): return
        if self.stopped:
            for row in self.pending: self.records[row]["status"] = "Stopped"; self.table.item(row, 6).setText("Stopped")
            self.pending.clear(); self.progress.setValue(sum(record["status"] in {"Ready", "Failed", "Stopped"} for record in self.records))
        self.analyze.setEnabled(True); self.stop.setEnabled(False); self.concurrent.setEnabled(True); self.update_summary()

    def stop_scheduling(self): self.stopped = True; self.stop.setEnabled(False); self.finish_if_idle()

    def retry_failed(self):
        if self.active: return
        rows = [row for row, record in enumerate(self.records) if record["status"] in {"Failed", "Stopped"}]
        if not rows: return
        self.stopped = False; self.pending = rows
        for row in rows: self.records[row].update(status="Pending", error=""); self.table.item(row, 6).setText("Pending"); self.table.item(row, 7).setText("")
        self.analyze.setEnabled(False); self.stop.setEnabled(True); self.concurrent.setEnabled(False); self.schedule_more()

    def configure_current_playlist(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.records): return
        record = self.records[row]; entries = (record.get("info") or {}).get("entries")
        if not isinstance(entries, list) or not entries: QMessageBox.information(self, "Not a playlist", "The selected row is not a playlist result."); return
        dialog = PlaylistDialog(record["info"], record["playlist_items"], self)
        if dialog.exec() == QDialog.Accepted:
            record["playlist_items"] = dialog.selection(); self.table.item(row, 6).setText(f"Ready · {len(record['playlist_items'])} playlist item(s)"); self.table.item(row, 0).setCheckState(Qt.Checked); self.update_summary()

    def select_successful(self):
        self.table.blockSignals(True)
        for row, record in enumerate(self.records): self.table.item(row, 0).setCheckState(Qt.Checked if record["status"] == "Ready" else Qt.Unchecked)
        self.table.blockSignals(False); self.update_summary()

    def set_all_checks(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()): self.table.item(row, 0).setCheckState(state)
        self.table.blockSignals(False); self.update_summary()

    def invert_selection(self):
        self.table.blockSignals(True)
        for row, record in enumerate(self.records):
            if record["status"] == "Ready":
                item = self.table.item(row, 0); item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.table.blockSignals(False); self.update_summary()

    def chosen_rows(self):
        return [row for row, record in enumerate(self.records) if record["status"] == "Ready" and self.table.item(row, 0).checkState() == Qt.Checked]

    def update_summary(self, *_):
        ready = sum(record["status"] == "Ready" for record in self.records); failed = sum(record["status"] == "Failed" for record in self.records); selected = len(self.chosen_rows())
        self.summary.setText(f"{selected} selected · {ready} ready · {failed} failed · {self.active} active")
        self.add_button.setEnabled(bool(selected) and not self.active and not self.pending)

    def accept_results(self):
        chosen = self.chosen_rows()
        if not chosen: QMessageBox.information(self, "Nothing selected", "Select at least one successfully analyzed URL."); return
        for row in chosen:
            record = self.records[row]; entries = (record["info"] or {}).get("entries")
            if isinstance(entries, list) and entries and not record["playlist_items"]:
                self.table.selectRow(row); self.configure_current_playlist()
                if not record["playlist_items"]: return
        self._results = [{"url": self.records[row]["url"], "info": self.records[row]["info"], "playlist_items": list(self.records[row]["playlist_items"]),"extractor_args":self.records[row]["extractor_args"]} for row in chosen]
        self.accept()

    def results(self): return list(self._results)

    def reject(self):
        # Metadata extraction cannot always be interrupted safely inside an
        # extractor. Detach the dialog and let already-running jobs finish
        # silently; no widgets are touched after the dialog is discarded.
        self.stopped = True; self.pending.clear(); self._discarded = True
        super().reject()

    def context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0: return
        menu = QMenu(self); copy = menu.addAction("Copy URL"); open_url = menu.addAction("Open URL"); copy_error = menu.addAction("Copy Error"); action = menu.exec(self.table.viewport().mapToGlobal(pos)); record = self.records[row]
        if action == copy: QApplication.clipboard().setText(record["url"])
        elif action == open_url: QDesktopServices.openUrl(QUrl(record["url"]))
        elif action == copy_error: QApplication.clipboard().setText(record["error"])

class SupportedSitesDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("Supported Websites"); self.resize(760,560); self.all=[]
        layout=QVBoxLayout(self); top=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("Search extractors…"); refresh=QPushButton("Refresh"); export=QPushButton("Export List")
        top.addWidget(self.search,1); top.addWidget(refresh); top.addWidget(export); layout.addLayout(top)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(["#","Extractor","Description","Type"]); self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch); self.table.setSortingEnabled(True); layout.addWidget(self.table)
        self.count=QLabel(); layout.addWidget(self.count); notice=QLabel("Supported Websites lists extractors included with the currently installed yt-dlp version. Actual availability can change because websites frequently modify their services. Some websites may also work through embedded media or the Generic Extractor."); notice.setWordWrap(True); layout.addWidget(notice)
        links=QDialogButtonBox(QDialogButtonBox.Close); docs=links.addButton("Open yt-dlp Supported Sites Page",QDialogButtonBox.ActionRole); links.rejected.connect(self.reject); docs.clicked.connect(lambda:QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"))); layout.addWidget(links)
        refresh.clicked.connect(self.load); self.search.textChanged.connect(self.populate); export.clicked.connect(self.export); self.load()
    def load(self): self.all=YTDLPService.get_extractors(); self.populate()
    def populate(self):
        term=self.search.text().lower(); rows=[x for x in self.all if term in (x["name"]+x["description"]).lower()]; self.table.setSortingEnabled(False); self.table.setRowCount(len(rows))
        for r,item in enumerate(rows):
            for c,val in enumerate((r+1,item["name"],item["description"],item["type"])): self.table.setItem(r,c,QTableWidgetItem(str(val)))
        self.table.setSortingEnabled(True); self.count.setText(f"Total: {len(rows)} / {len(self.all)} extractors")
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,"Export extractors","extractors.json","JSON (*.json)")
        if path: Path(path).write_text(json.dumps(self.all,indent=2,ensure_ascii=False),encoding="utf-8")

class SettingsDialog(QDialog):
    settings_applied=Signal()
    SECTIONS=["General","Downloads","Video","Audio","Subtitle","Network","Cookies & Authentication","FFmpeg","yt-dlp","Appearance","Notification","Advanced"]
    SECTION_PREFIXES={"General":"general/","Downloads":"downloads/","Video":"video/","Audio":"audio/","Subtitle":"subtitles/","Network":"network/","Cookies & Authentication":"cookies/","FFmpeg":"ffmpeg/","yt-dlp":"ytdlp/","Appearance":"appearance/","Notification":"notifications/","Advanced":"advanced/"}
    SENSITIVE_KEYS={"cookies/file","cookies/profile","cookies/firefox_container","network/proxy"}
    NUMERIC_RANGES={"downloads/concurrent":(1,5),"downloads/integrity_retries":(0,3),"downloads/failure_retries":(0,20),"downloads/retry_backoff_base":(0,3600),"downloads/retry_backoff_max":(0,86400),"downloads/retry_jitter_percent":(0,100),"downloads/idle_pause_minutes":(1,1440),"downloads/low_battery_percent":(1,99),"downloads/battery_resume_hysteresis":(0,50),"downloads/system_monitor_seconds":(2,300),"downloads/max_filename":(40,240),"downloads/minimum_free_mib":(0,1048576),"network/timeout":(1,300),"network/retries":(0,20),"network/fragment_retries":(0,20),"network/fragments":(1,16),"network/rate_limit_kib":(0,1048576),"network/http_chunk_kib":(0,102400),"network/sleep_interval":(0,300),"ffmpeg/threads":(0,64),"ytdlp/extractor_retries":(0,20),"appearance/font_size":(8,20),"notifications/duration_ms":(1000,15000)}
    def __init__(self,settings:QSettings,parent=None):
        super().__init__(parent); self.settings=settings;self.initial_values={key:self.settings.value(key) for key in self.settings.allKeys()}; self.setWindowTitle("Settings"); self.resize(860,620)
        root=QVBoxLayout(self);body=QHBoxLayout();root.addLayout(body,1);left=QVBoxLayout();self.settings_search=QLineEdit();self.settings_search.setPlaceholderText("Search settings…");self.settings_search.setClearButtonEnabled(True);left.addWidget(self.settings_search);self.categories=QListWidget(); self.categories.setFixedWidth(210);left.addWidget(self.categories,1);body.addLayout(left); self.pages=QStackedWidget();body.addWidget(self.pages,1)
        for name in self.SECTIONS:self.categories.addItem(name);self.pages.addWidget(self.page(name))
        tools=QHBoxLayout();self.change_summary=QLabel("No unsaved changes");diagnostics=QPushButton("Copy Diagnostics");export_button=QPushButton("Export…");import_button=QPushButton("Import…");reset_section=QPushButton("Reset Section");tools.addWidget(self.change_summary,1);tools.addWidget(diagnostics);tools.addWidget(import_button);tools.addWidget(export_button);tools.addWidget(reset_section);root.addLayout(tools)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel|QDialogButtonBox.RestoreDefaults|QDialogButtonBox.Apply);buttons.accepted.connect(lambda:self.save(True));buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda:self.save(False)); buttons.rejected.connect(self.reject); buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.restore_defaults);root.addWidget(buttons)
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex);self.settings_search.textChanged.connect(self.filter_settings);export_button.clicked.connect(self.export_settings);import_button.clicked.connect(self.import_settings);reset_section.clicked.connect(self.reset_current_section);diagnostics.clicked.connect(self.copy_diagnostics);self.categories.setCurrentRow(0)
        for widget in self.findChildren(QCheckBox):widget.toggled.connect(self.mark_changed)
        for widget in self.findChildren(QComboBox):widget.currentIndexChanged.connect(self.mark_changed)
        for widget in self.findChildren(QSpinBox):widget.valueChanged.connect(self.mark_changed)
        for widget in self.findChildren(QLineEdit):
            if widget is not self.settings_search:widget.textChanged.connect(self.mark_changed)
    def page(self,name):
        w=QWidget(); f=QFormLayout(w); f.addRow(QLabel(f"<h2>{name}</h2>"))
        if name=="General":
            self.startup_clipboard=QCheckBox("Offer clipboard URL when the application starts");self.startup_clipboard.setChecked(self.flag("general/clipboard_url",True));f.addRow(self.startup_clipboard)
            self.confirm_exit=QCheckBox("Confirm before closing while downloads are active");self.confirm_exit.setChecked(self.flag("general/confirm_exit",True));f.addRow(self.confirm_exit)
            self.remember_window=QCheckBox("Remember window size and position");self.remember_window.setChecked(self.flag("general/remember_window",True));f.addRow(self.remember_window)
            self.default_download_type=self.combo(["Video","Audio Only","Video Only","Thumbnail Only","Subtitle Only","Metadata Only"],"general/default_download_type","Video");f.addRow("Default download type",self.default_download_type)
            self.auto_analyze_clipboard=QCheckBox("Automatically analyze a valid startup clipboard URL");self.auto_analyze_clipboard.setChecked(self.flag("general/auto_analyze_clipboard",False));f.addRow(self.auto_analyze_clipboard)
            self.startup_tab=self.combo(["Downloader","History","Log"],"general/startup_tab","Downloader");f.addRow("Startup tab",self.startup_tab)
        elif name=="Downloads":
            self.folder=QLineEdit(self.settings.value("downloads/folder",str(Path.home()/"Downloads"/"Video Downloader"))); browse=QPushButton("Browse"); browse.clicked.connect(self.browse); row=QHBoxLayout(); row.addWidget(self.folder); row.addWidget(browse); f.addRow("Default folder",row)
            self.concurrent=QSpinBox(); self.concurrent.setRange(1,5); self.concurrent.setValue(int(self.settings.value("downloads/concurrent",2))); f.addRow("Concurrent downloads",self.concurrent)
            self.template=QLineEdit(self.settings.value("downloads/template","%(title)s [%(id)s].%(ext)s")); f.addRow("Filename template",self.template)
            self.verify_integrity=QCheckBox("Verify completed media and automatically re-download corrupted files"); self.verify_integrity.setChecked(str(self.settings.value("downloads/verify_integrity",True)).lower() not in {"false","0","no"}); f.addRow(self.verify_integrity)
            self.integrity_retries=QSpinBox(); self.integrity_retries.setRange(0,3); self.integrity_retries.setValue(int(self.settings.value("downloads/integrity_retries",2))); self.integrity_retries.setToolTip("Maximum automatic re-downloads after a conclusive integrity failure"); f.addRow("Integrity re-downloads",self.integrity_retries)
            self.failure_retry_enabled=QCheckBox("Automatically retry failed download jobs");self.failure_retry_enabled.setChecked(self.flag("downloads/failure_retry_enabled",True));self.failure_retry_enabled.setToolTip("Separate from yt-dlp network retries and integrity re-downloads.");f.addRow(self.failure_retry_enabled)
            self.failure_retries=self.spin("downloads/failure_retries",3,0,20);f.addRow("Failure retry attempts",self.failure_retries)
            self.retry_backoff_base=self.spin("downloads/retry_backoff_base",2,0,3600," seconds");f.addRow("Initial retry delay",self.retry_backoff_base)
            self.retry_backoff_max=self.spin("downloads/retry_backoff_max",60,0,86400," seconds");f.addRow("Maximum retry delay",self.retry_backoff_max)
            self.retry_jitter=self.spin("downloads/retry_jitter_percent",10,0,100,"%");self.retry_jitter.setToolTip("Randomizes each delay to avoid many queued downloads retrying simultaneously.");f.addRow("Backoff jitter",self.retry_jitter)
            retry_widgets=(self.failure_retries,self.retry_backoff_base,self.retry_backoff_max,self.retry_jitter);self.failure_retry_enabled.toggled.connect(lambda enabled:[widget.setEnabled(enabled) for widget in retry_widgets]);[widget.setEnabled(self.failure_retry_enabled.isChecked()) for widget in retry_widgets]
            retry_note=QLabel("Delay formula: min(maximum, initial × 2^(attempt−1)), then optional jitter. DRM, unsupported URLs, authentication, invalid formats/settings, permission errors, insufficient disk space, cancellation, and exhausted integrity checks are not retried.");retry_note.setWordWrap(True);f.addRow(retry_note)
            self.pause_when_idle=QCheckBox("Globally pause downloads when the computer is idle");self.pause_when_idle.setChecked(self.flag("downloads/pause_when_idle",False));f.addRow(self.pause_when_idle);self.idle_pause_minutes=self.spin("downloads/idle_pause_minutes",30,1,1440," minutes");f.addRow("Idle threshold",self.idle_pause_minutes)
            self.pause_low_battery=QCheckBox("Globally pause downloads while battery is low");self.pause_low_battery.setChecked(self.flag("downloads/pause_low_battery",False));f.addRow(self.pause_low_battery);self.low_battery_percent=self.spin("downloads/low_battery_percent",20,1,99,"%");f.addRow("Low battery threshold",self.low_battery_percent);self.battery_resume_hysteresis=self.spin("downloads/battery_resume_hysteresis",5,0,50,"%");self.battery_resume_hysteresis.setToolTip("Resume waits until battery rises above threshold plus this margin, or AC power is connected.");f.addRow("Battery resume margin",self.battery_resume_hysteresis)
            self.auto_resume_global=QCheckBox("Automatically resume policy-paused downloads when conditions recover");self.auto_resume_global.setChecked(self.flag("downloads/auto_resume_global",True));f.addRow(self.auto_resume_global);self.system_monitor_seconds=self.spin("downloads/system_monitor_seconds",10,2,300," seconds");f.addRow("Idle/battery polling interval",self.system_monitor_seconds)
            power_note=QLabel("Only downloads paused by this global policy are resumed automatically. Individually paused downloads remain paused. Battery rules apply only while running on battery.");power_note.setWordWrap(True);f.addRow(power_note)
            self.overwrite=QCheckBox("Overwrite existing output files");self.overwrite.setChecked(self.flag("downloads/overwrite",False));f.addRow(self.overwrite)
            self.keep_fragments=QCheckBox("Keep downloaded fragments after completion");self.keep_fragments.setChecked(self.flag("downloads/keep_fragments",False));f.addRow(self.keep_fragments)
            self.auto_start=QCheckBox("Start downloads automatically after size estimation");self.auto_start.setChecked(self.flag("downloads/auto_start",True));f.addRow(self.auto_start)
            self.max_filename=self.spin("downloads/max_filename",180,40,240," chars");f.addRow("Maximum filename length",self.max_filename)
            self.temp_folder=QLineEdit(str(self.settings.value("downloads/temp_folder","") or ""));self.temp_folder.setPlaceholderText("Optional; empty uses the download folder");temp_pick=QPushButton("Browse…");temp_pick.clicked.connect(self.browse_temp);temp_row=QHBoxLayout();temp_row.addWidget(self.temp_folder,1);temp_row.addWidget(temp_pick);f.addRow("Temporary fragments folder",temp_row)
            self.minimum_free_space=self.spin("downloads/minimum_free_mib",256,0,1048576," MiB");self.minimum_free_space.setSpecialValueText("Disabled");f.addRow("Required free space reserve",self.minimum_free_space)
            self.download_archive=QLineEdit(str(self.settings.value("downloads/archive","") or ""));self.download_archive.setPlaceholderText("Optional yt-dlp archive .txt file");archive_pick=QPushButton("Browse…");archive_pick.clicked.connect(self.browse_archive);archive_row=QHBoxLayout();archive_row.addWidget(self.download_archive,1);archive_row.addWidget(archive_pick);f.addRow("Download archive",archive_row)
            self.download_backend=self.combo(["Native","aria2c"],"downloads/backend","Native");self.download_backend.setToolTip("aria2c accelerates supported HTTP/FTP transfers. Native remains available for unsupported protocols.");f.addRow("Download engine",self.download_backend)
            detected=Aria2Service.version(str(self.settings.value("downloads/aria2_location","") or "")) or "Not detected";self.aria2_status=QLabel(detected);self.aria2_status.setWordWrap(True);f.addRow("aria2c status",self.aria2_status)
            self.aria2_location=QLineEdit(str(self.settings.value("downloads/aria2_location","") or ""));self.aria2_location.setPlaceholderText("Optional aria2c executable; empty searches PATH");aria_pick=QPushButton("Browse…");aria_pick.clicked.connect(self.browse_aria2);aria_row=QHBoxLayout();aria_row.addWidget(self.aria2_location,1);aria_row.addWidget(aria_pick);f.addRow("aria2c executable",aria_row)
            self.aria2_connections=self.spin("downloads/aria2_connections",16,1,16);f.addRow("Connections per server",self.aria2_connections);self.aria2_split=self.spin("downloads/aria2_split",16,1,16);f.addRow("Download splits",self.aria2_split);self.aria2_min_split=self.spin("downloads/aria2_min_split_mib",1,1,1024," MiB");f.addRow("Minimum split size",self.aria2_min_split)
            self.aria2_max_tries=self.spin("downloads/aria2_max_tries",5,0,100);self.aria2_max_tries.setSpecialValueText("Unlimited");f.addRow("aria2 retry attempts",self.aria2_max_tries);self.aria2_retry_wait=self.spin("downloads/aria2_retry_wait",1,0,120," seconds");f.addRow("aria2 retry delay",self.aria2_retry_wait);self.aria2_timeout=self.spin("downloads/aria2_timeout",20,1,600," seconds");f.addRow("aria2 connection/read timeout",self.aria2_timeout)
            self.aria2_allocation=self.combo(["none","prealloc","trunc"],"downloads/aria2_file_allocation","none");self.aria2_allocation.setToolTip("none is the safest cross-filesystem default; prealloc may reduce fragmentation but delays startup.");f.addRow("File allocation",self.aria2_allocation)
            self.aria2_fragments=QCheckBox("Use aria2c for DASH/HLS fragments (advanced)");self.aria2_fragments.setChecked(self.flag("downloads/aria2_fragments",False));self.aria2_fragments.setToolTip("Disabled by default: yt-dlp native fragment downloads provide better progress and cooperative pause/cancel behavior.");f.addRow(self.aria2_fragments)
            aria_note=QLabel("With aria2c, yt-dlp reports progress only when the external transfer finishes. Pause/cancel is therefore handled at the next transfer boundary. Requires yt-dlp 2026.06.09 or newer.");aria_note.setWordWrap(True);f.addRow(aria_note)
        elif name=="Video":
            self.preferred_container=QComboBox()
            for label,value in CONTAINER_PRESETS:self.preferred_container.addItem(label,value or "auto")
            selected=self.preferred_container.findData(self.settings.value("video/container","auto"));self.preferred_container.setCurrentIndex(selected if selected>=0 else 0)
            self.preferred_container.setToolTip("Default final container for new downloads. Specific containers require FFmpeg.");f.addRow("Default output container",self.preferred_container)
            self.default_resolution=self.combo(["Auto","144p","240p","360p","480p","720p","1080p","1440p","2160p / 4K","4320p / 8K"],"video/resolution","Auto");f.addRow("Default resolution",self.default_resolution)
            self.default_video_codec=self.combo(["Auto","H.264","H.265 / HEVC","VP9","AV1"],"video/codec","Auto");f.addRow("Default codec",self.default_video_codec)
            self.default_fps=self.combo(["Auto","24","25","30","48","50","60","100","120","144","240"],"video/fps","Auto");f.addRow("Default frame rate",self.default_fps)
            self.default_dynamic_range=self.combo(["Auto","SDR","HDR","HDR10","HDR10+","HDR12","HLG","Dolby Vision"],"video/dynamic_range","Auto");f.addRow("Default dynamic range",self.default_dynamic_range)
            self.default_bit_depth=self.combo(["Auto","8-bit","10-bit","12-bit"],"video/bit_depth","Auto");f.addRow("Default bit depth",self.default_bit_depth)
            self.multiple_video_streams=QCheckBox("Allow multiple video streams in one output");self.multiple_video_streams.setChecked(self.flag("video/multiple_streams",False));f.addRow(self.multiple_video_streams)
            self.video_thumbnail=QCheckBox("Embed/write thumbnail by default for video");self.video_thumbnail.setChecked(self.flag("video/embed_thumbnail",False));f.addRow(self.video_thumbnail)
            self.video_metadata=QCheckBox("Embed video tags and source metadata by default");self.video_metadata.setChecked(self.flag("video/embed_metadata",True));f.addRow(self.video_metadata)
            self.video_poster_format=self.combo(["auto","jpg","png","webp"],"video/thumbnail_format","auto");f.addRow("Poster conversion",self.video_poster_format)
            self.video_keep_poster=QCheckBox("Keep poster image as a sidecar file");self.video_keep_poster.setChecked(self.flag("video/keep_thumbnail",False));f.addRow(self.video_keep_poster)
            self.video_chapters=QCheckBox("Embed chapters when available");self.video_chapters.setChecked(self.flag("video/embed_chapters",True));f.addRow(self.video_chapters)
            self.video_infojson=QCheckBox("Embed full info JSON in the video container");self.video_infojson.setChecked(self.flag("video/embed_infojson",False));f.addRow(self.video_infojson)
        elif name=="Audio":
            self.default_audio_format=self.combo(["mp3","m4a","aac","flac","wav","opus","vorbis"],"audio/format","mp3");f.addRow("Default audio format",self.default_audio_format)
            self.default_audio_quality=self.combo(["320","256","192","160","128","96","64"],"audio/quality","192");f.addRow("Default bitrate (kbps)",self.default_audio_quality)
            self.default_audio_codec=self.combo(["Auto","AAC","Opus","Vorbis","MP3","FLAC"],"audio/codec","Auto");f.addRow("Preferred codec",self.default_audio_codec)
            self.audio_thumbnail=QCheckBox("Embed thumbnail by default for audio downloads");self.audio_thumbnail.setChecked(self.flag("audio/embed_thumbnail",False));f.addRow(self.audio_thumbnail)
            self.multiple_audio_streams=QCheckBox("Allow multiple audio streams in video output");self.multiple_audio_streams.setChecked(self.flag("audio/multiple_streams",False));f.addRow(self.multiple_audio_streams)
            self.audio_sample_rate=self.combo(["Source","44100","48000","88200","96000","192000"],"audio/sample_rate","Source");f.addRow("Output sample rate (Hz)",self.audio_sample_rate)
            self.audio_channels=self.combo(["Source","1","2","6","8"],"audio/channels","Source");f.addRow("Output channels",self.audio_channels)
            self.audio_metadata=QCheckBox("Embed audio tags and source metadata by default");self.audio_metadata.setChecked(self.flag("audio/embed_metadata",True));f.addRow(self.audio_metadata)
            self.audio_cover_format=self.combo(["auto","jpg","png","webp"],"audio/thumbnail_format","auto");f.addRow("Cover-art conversion",self.audio_cover_format)
            self.audio_keep_cover=QCheckBox("Keep cover image as a sidecar file");self.audio_keep_cover.setChecked(self.flag("audio/keep_thumbnail",False));f.addRow(self.audio_keep_cover)
            self.audio_chapters=QCheckBox("Embed chapters when available");self.audio_chapters.setChecked(self.flag("audio/embed_chapters",True));f.addRow(self.audio_chapters)
            self.audio_infojson=QCheckBox("Embed full info JSON in the audio container");self.audio_infojson.setChecked(self.flag("audio/embed_infojson",False));f.addRow(self.audio_infojson)
        elif name=="Subtitle":
            self.subtitle_languages=QLineEdit(str(self.settings.value("subtitles/languages","all")));self.subtitle_languages.setPlaceholderText("all or comma-separated codes: id,en");f.addRow("Languages",self.subtitle_languages)
            self.subtitle_auto=QCheckBox("Include automatic captions");self.subtitle_auto.setChecked(self.flag("subtitles/automatic",True));f.addRow(self.subtitle_auto)
            self.subtitle_embed=QCheckBox("Embed subtitles when the container supports it");self.subtitle_embed.setChecked(self.flag("subtitles/embed",False));f.addRow(self.subtitle_embed)
            self.subtitle_format=self.combo(["best","srt","vtt","ass"],"subtitles/format","best");f.addRow("Preferred format",self.subtitle_format)
            self.subtitle_default=QCheckBox("Enable subtitle download by default");self.subtitle_default.setChecked(self.flag("subtitles/default_enabled",False));f.addRow(self.subtitle_default)
            self.subtitle_manual=QCheckBox("Download publisher-provided subtitles");self.subtitle_manual.setChecked(self.flag("subtitles/manual",True));f.addRow(self.subtitle_manual)
            self.subtitle_convert=self.combo(["none","srt","vtt","ass","lrc"],"subtitles/convert","none");f.addRow("Convert downloaded subtitles",self.subtitle_convert)
        elif name=="Network":
            self.proxy=QLineEdit(str(self.settings.value("network/proxy","") or ""));self.proxy.setPlaceholderText("Optional: http://host:port or socks5://host:port");f.addRow("Proxy",self.proxy)
            self.network_timeout=self.spin("network/timeout",20,1,300," seconds");f.addRow("Socket timeout",self.network_timeout)
            self.network_retries=self.spin("network/retries",3,0,20);f.addRow("Download retries",self.network_retries)
            self.fragment_retries=self.spin("network/fragment_retries",3,0,20);f.addRow("Fragment retries",self.fragment_retries)
            self.fragments=self.spin("network/fragments",1,1,16);f.addRow("Concurrent fragments",self.fragments)
            self.rate_limit=self.spin("network/rate_limit_kib",0,0,1048576," KiB/s");self.rate_limit.setSpecialValueText("Unlimited");f.addRow("Rate limit",self.rate_limit)
            self.ip_family=self.combo(["Auto","IPv4","IPv6"],"network/ip_family","Auto");f.addRow("IP family",self.ip_family)
            self.http_chunk=self.spin("network/http_chunk_kib",0,0,102400," KiB");self.http_chunk.setSpecialValueText("Automatic");f.addRow("HTTP chunk size",self.http_chunk)
            self.sleep_interval=self.spin("network/sleep_interval",0,0,300," seconds");f.addRow("Delay between downloads",self.sleep_interval)
            self.user_agent=QLineEdit(str(self.settings.value("network/user_agent","") or ""));self.user_agent.setPlaceholderText("Optional custom HTTP User-Agent");f.addRow("User-Agent",self.user_agent)
            self.geo_bypass=QCheckBox("Enable yt-dlp geographic restriction bypass hints");self.geo_bypass.setChecked(self.flag("network/geo_bypass",True));f.addRow(self.geo_bypass)
        elif name=="FFmpeg":
            f.addRow("Status",QLabel(FFmpegService.version() or "Not detected — merging and conversion unavailable"));self.ffmpeg_location=QLineEdit(str(self.settings.value("ffmpeg/location","") or ""));self.ffmpeg_location.setPlaceholderText("Optional FFmpeg executable or bin directory");pick=QPushButton("Browse…");pick.clicked.connect(self.browse_ffmpeg);row=QHBoxLayout();row.addWidget(self.ffmpeg_location,1);row.addWidget(pick);f.addRow("Custom location",row)
            self.preserve_timestamps=QCheckBox("Preserve source modification timestamps");self.preserve_timestamps.setChecked(self.flag("ffmpeg/preserve_timestamps",True));f.addRow(self.preserve_timestamps)
            self.ffmpeg_threads=self.spin("ffmpeg/threads",0,0,64);self.ffmpeg_threads.setSpecialValueText("Automatic");f.addRow("Processing threads",self.ffmpeg_threads)
        elif name=="yt-dlp":
            f.addRow("Installed version",QLabel(YTDLPService.version()));f.addRow("Extractors",QLabel(str(len(YTDLPService.get_extractors()))));self.flat_playlist=QCheckBox("Use fast flat extraction when analyzing playlists");self.flat_playlist.setChecked(self.flag("ytdlp/flat_playlist",True));f.addRow(self.flat_playlist);self.prefer_free_formats=QCheckBox("Prefer free/open media formats when quality is equal");self.prefer_free_formats.setChecked(self.flag("ytdlp/prefer_free_formats",False));f.addRow(self.prefer_free_formats)
            self.channel_analysis_limit=self.spin("ytdlp/channel_analysis_limit",500,25,10000," items");self.channel_analysis_limit.setToolTip("Maximum entries loaded while analyzing a detected channel. This prevents very large channels from freezing the interface.");f.addRow("Channel analysis limit",self.channel_analysis_limit)
            self.check_formats=QCheckBox("Verify selected format URLs before downloading");self.check_formats.setChecked(self.flag("ytdlp/check_formats",False));f.addRow(self.check_formats);self.extractor_retries=self.spin("ytdlp/extractor_retries",3,0,20);f.addRow("Extractor retries",self.extractor_retries);self.ignore_playlist_errors=QCheckBox("Continue playlist after unavailable items");self.ignore_playlist_errors.setChecked(self.flag("ytdlp/ignore_playlist_errors",True));f.addRow(self.ignore_playlist_errors)
            self.show_ytdlp_warnings=QCheckBox("Show yt-dlp warnings in the application log");self.show_ytdlp_warnings.setChecked(self.flag("ytdlp/show_warnings",True));f.addRow(self.show_ytdlp_warnings)
        elif name=="Appearance":
            self.theme=QComboBox(); self.theme.addItems(["System","Light","Dark"]); self.theme.setCurrentText(self.settings.value("appearance/theme","Dark")); f.addRow("Theme",self.theme);self.font_size=self.spin("appearance/font_size",10,8,20," pt");f.addRow("Interface font size",self.font_size);self.compact_ui=QCheckBox("Compact spacing and controls");self.compact_ui.setChecked(self.flag("appearance/compact",False));f.addRow(self.compact_ui)
            self.show_statusbar=QCheckBox("Show status bar");self.show_statusbar.setChecked(self.flag("appearance/statusbar",True));f.addRow(self.show_statusbar);self.alternating_rows=QCheckBox("Use alternating table row colors");self.alternating_rows.setChecked(self.flag("appearance/alternating_rows",True));f.addRow(self.alternating_rows)
            self.show_preview=QCheckBox("Show thumbnail preview panel");self.show_preview.setChecked(self.flag("appearance/show_preview",True));f.addRow(self.show_preview)
        elif name=="Notification":
            self.notify_complete=QCheckBox("Notify when a download completes");self.notify_complete.setChecked(self.flag("notifications/completed",True));f.addRow(self.notify_complete);self.notify_failed=QCheckBox("Notify when a download fails");self.notify_failed.setChecked(self.flag("notifications/failed",True));f.addRow(self.notify_failed);self.notification_sound=QCheckBox("Play system alert sound");self.notification_sound.setChecked(self.flag("notifications/sound",False));f.addRow(self.notification_sound)
            self.notify_cancelled=QCheckBox("Notify when a download is cancelled");self.notify_cancelled.setChecked(self.flag("notifications/cancelled",False));f.addRow(self.notify_cancelled);self.alert_duration=self.spin("notifications/duration_ms",3000,1000,15000," ms");f.addRow("Taskbar alert duration",self.alert_duration)
            self.notify_background_only=QCheckBox("Only alert when the application is not active");self.notify_background_only.setChecked(self.flag("notifications/background_only",False));f.addRow(self.notify_background_only)
        elif name=="Advanced":
            self.restrict_filenames=QCheckBox("Restrict filenames to portable ASCII characters");self.restrict_filenames.setChecked(self.flag("advanced/restrict_filenames",False));f.addRow(self.restrict_filenames);self.use_cache=QCheckBox("Use yt-dlp extractor cache");self.use_cache.setChecked(self.flag("advanced/use_cache",True));f.addRow(self.use_cache);self.write_info_default=QCheckBox("Write info JSON by default");self.write_info_default.setChecked(self.flag("advanced/write_info_json",False));f.addRow(self.write_info_default);self.embed_metadata_default=QCheckBox("Embed metadata by default");self.embed_metadata_default.setChecked(self.flag("advanced/embed_metadata",True));f.addRow(self.embed_metadata_default);self.log_level=self.combo(["DEBUG","INFO","WARNING","ERROR"],"advanced/log_level","INFO");f.addRow("Log level",self.log_level)
            self.use_part_files=QCheckBox("Use resumable .part files");self.use_part_files.setChecked(self.flag("advanced/use_part_files",True));f.addRow(self.use_part_files);self.write_description=QCheckBox("Write media description sidecar by default");self.write_description.setChecked(self.flag("advanced/write_description",False));f.addRow(self.write_description);self.write_xattrs=QCheckBox("Write extended filesystem attributes when supported");self.write_xattrs.setChecked(self.flag("advanced/write_xattrs",False));f.addRow(self.write_xattrs)
        elif name=="Cookies & Authentication":
            warning=QLabel("Uses your browser's existing signed-in session through yt-dlp. Close the browser if its cookie database is locked. Cookie values are never stored in application settings or displayed by this application.");warning.setWordWrap(True);f.addRow(warning)
            self.cookies_enabled=QCheckBox("Use authenticated cookies");self.cookies_enabled.setChecked(str(self.settings.value("cookies/enabled",False)).lower() in {"true","1","yes"});f.addRow(self.cookies_enabled)
            self.cookie_mode=QComboBox();self.cookie_mode.addItem("Read automatically from browser","browser");self.cookie_mode.addItem("Import Netscape cookies.txt file","file");mode=self.cookie_mode.findData(self.settings.value("cookies/mode","browser"));self.cookie_mode.setCurrentIndex(mode if mode>=0 else 0);f.addRow("Cookie source",self.cookie_mode)
            self.cookie_browser=QComboBox();detected=detected_browsers()
            for label,value in SUPPORTED_COOKIE_BROWSERS:
                text=label+(" — detected" if value in detected else "")
                self.cookie_browser.addItem(text,value)
            selected=self.cookie_browser.findData(self.settings.value("cookies/browser",None));self.cookie_browser.setCurrentIndex(selected if selected>=0 else 0);f.addRow("Browser",self.cookie_browser)
            self.cookie_profile=QLineEdit(str(self.settings.value("cookies/profile","") or ""));self.cookie_profile.setPlaceholderText("Optional profile name or absolute profile path");self.cookie_profile.setToolTip("Leave empty for the browser's default profile. Chrome/Edge examples: Default or Profile 1. Firefox accepts a profile name or path.");self.cookie_profile_browse=QPushButton("Browse…");self.cookie_profile_browse.clicked.connect(self.browse_cookie_profile);profile_row=QHBoxLayout();profile_row.addWidget(self.cookie_profile,1);profile_row.addWidget(self.cookie_profile_browse);f.addRow("Browser profile",profile_row)
            self.firefox_container=QLineEdit(str(self.settings.value("cookies/firefox_container","") or ""));self.firefox_container.setPlaceholderText("Optional Firefox container name");f.addRow("Firefox container",self.firefox_container)
            self.cookie_keyring=self.combo(["Auto","basictext","gnomekeyring","kwallet","kwallet5","kwallet6"],"cookies/keyring","Auto");self.cookie_keyring.setToolTip("Optional Chromium keyring override, primarily for Linux.");f.addRow("Chromium keyring",self.cookie_keyring)
            self.cookie_file=QLineEdit(str(self.settings.value("cookies/file","") or ""));self.cookie_file.setReadOnly(True);self.cookie_file.setPlaceholderText("Select a Netscape-format .txt cookie file");self.cookie_file_browse=QPushButton("Import…");self.cookie_file_browse.clicked.connect(self.browse_cookie_file);file_row=QHBoxLayout();file_row.addWidget(self.cookie_file,1);file_row.addWidget(self.cookie_file_browse);f.addRow("Netscape cookies file",file_row)
            self.cookie_status=QLabel();self.cookie_status.setWordWrap(True);f.addRow("Availability",self.cookie_status)
            self.cookies_enabled.toggled.connect(self.update_cookie_controls);self.cookie_mode.currentIndexChanged.connect(self.update_cookie_controls);self.cookie_browser.currentIndexChanged.connect(self.update_cookie_controls);self.update_cookie_controls()
        else:
            f.addRow(QLabel("Preferences in this category use safe application defaults. More controls can be added without changing the service architecture."))
        return w
    def flag(self,key,default=False):return str(self.settings.value(key,default)).lower() in {"true","1","yes"}
    def mark_changed(self,*_args):self.change_summary.setText("Unsaved changes")
    def filter_settings(self,text):
        term=text.strip().lower();first=None
        for index,name in enumerate(self.SECTIONS):
            page=self.pages.widget(index);texts=[name]
            for kind in (QLabel,QCheckBox,QPushButton):texts.extend(str(widget.text()) for widget in page.findChildren(kind))
            texts.extend(str(widget.placeholderText()) for widget in page.findChildren(QLineEdit));content=" ".join(texts)
            visible=not term or term in content.lower();self.categories.item(index).setHidden(not visible)
            if visible and first is None:first=index
        current=self.categories.currentRow()
        if first is not None and (current<0 or self.categories.item(current).isHidden()):self.categories.setCurrentRow(first)
    @classmethod
    def safe_export_value(cls,key,value):
        if key.startswith("cookies/") or key in cls.SENSITIVE_KEYS:return None
        if isinstance(value,(str,int,float,bool)) or value is None:return value
        return None
    def export_settings(self):
        path,_=QFileDialog.getSaveFileName(self,"Export saved settings","video-downloader-settings.json","JSON (*.json)")
        if not path:return
        exported={key:value for key in self.settings.allKeys() if (value:=self.safe_export_value(key,self.settings.value(key))) is not None}
        try:Path(path).write_text(json.dumps({"format":"video-downloader-settings","version":1,"settings":exported},indent=2,ensure_ascii=False),encoding="utf-8");QMessageBox.information(self,"Settings exported",f"Exported {len(exported)} non-sensitive saved setting(s). Authentication and proxy values were excluded.")
        except OSError as exc:QMessageBox.warning(self,"Export failed",str(exc))
    def copy_diagnostics(self):
        safe_keys=[key for key in self.settings.allKeys() if self.safe_export_value(key,self.settings.value(key)) is not None]
        lines=[f"{APP_NAME} {APP_VERSION}",f"Python: {platform.python_version()}",f"PySide6: {pyside_version}",f"yt-dlp: {YTDLPService.version()}",f"FFmpeg: {FFmpegService.version() or 'Not detected'}",f"Platform: {platform.system()} {platform.release()}",f"Safe persisted settings: {len(safe_keys)}",f"Cookie authentication enabled: {self.flag('cookies/enabled',False)}"]
        for section in self.SECTIONS:
            prefix=self.SECTION_PREFIXES[section];lines.append(f"{section}: {sum(key.startswith(prefix) for key in safe_keys)} exported setting(s)")
        QApplication.clipboard().setText("\n".join(lines));self.change_summary.setText("Sanitized diagnostics copied")
    def import_settings(self):
        path,_=QFileDialog.getOpenFileName(self,"Import settings","","JSON (*.json)")
        if not path:return
        try:data=json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:QMessageBox.warning(self,"Import failed",f"Invalid or unreadable JSON: {exc}");return
        values=data.get("settings") if isinstance(data,dict) and data.get("format")=="video-downloader-settings" else None
        if not isinstance(values,dict):QMessageBox.warning(self,"Import failed","This is not a Video Downloader settings export.");return
        allowed=tuple(self.SECTION_PREFIXES.values());accepted={}
        for key,value in values.items():
            if not isinstance(key,str) or not key.startswith(allowed) or key.startswith("cookies/") or key in self.SENSITIVE_KEYS:continue
            if not isinstance(value,(str,int,float,bool)) or isinstance(value,str) and len(value)>8192:continue
            if key in self.NUMERIC_RANGES:
                if isinstance(value,bool) or not isinstance(value,(int,float)):continue
                minimum,maximum=self.NUMERIC_RANGES[key]
                if not minimum<=value<=maximum:continue
            accepted[key]=value
        if not accepted:QMessageBox.warning(self,"Import failed","No safe supported settings were found.");return
        if QMessageBox.question(self,"Import settings",f"Import {len(accepted)} setting(s)? Authentication and proxy configuration will remain unchanged.")!=QMessageBox.Yes:return
        for key,value in accepted.items():self.settings.setValue(key,value)
        self.settings.sync();self.settings_applied.emit();QMessageBox.information(self,"Import complete","Settings were imported and applied. Reopen Settings to review them.");self.accept()
    def reset_current_section(self):
        row=self.categories.currentRow()
        if row<0:return
        name=self.SECTIONS[row];prefix=self.SECTION_PREFIXES[name]
        if QMessageBox.question(self,"Reset section",f"Reset all {name} settings to safe defaults?")!=QMessageBox.Yes:return
        for key in list(self.settings.allKeys()):
            if key.startswith(prefix):self.settings.remove(key)
        self.settings.sync();self.settings_applied.emit();self.accept()
    def combo(self,values,key,default):
        widget=QComboBox();widget.addItems(values);widget.setCurrentText(str(self.settings.value(key,default)));return widget
    def spin(self,key,default,minimum,maximum,suffix=""):
        widget=QSpinBox();widget.setRange(minimum,maximum);widget.setValue(int(self.settings.value(key,default)));widget.setSuffix(suffix);return widget
    def browse(self):
        value=QFileDialog.getExistingDirectory(self,"Download folder",self.folder.text())
        if value:self.folder.setText(value)
    def browse_temp(self):
        value=QFileDialog.getExistingDirectory(self,"Temporary fragments folder",self.temp_folder.text() or self.folder.text())
        if value:self.temp_folder.setText(value)
    def browse_archive(self):
        value,_=QFileDialog.getSaveFileName(self,"Select download archive",self.download_archive.text() or str(Path.home()/"download-archive.txt"),"Text files (*.txt)")
        if value:self.download_archive.setText(value)
    def browse_aria2(self):
        value,_=QFileDialog.getOpenFileName(self,"Select aria2c executable",self.aria2_location.text() or str(Path.home()),"aria2c (aria2c.exe aria2c);;All files (*)")
        if value:self.aria2_location.setText(value);self.aria2_status.setText(Aria2Service.version(value) or "Invalid or unavailable executable")
    def update_cookie_controls(self):
        enabled=self.cookies_enabled.isChecked();browser=self.cookie_browser.currentData();detected=detected_browsers();browser_mode=self.cookie_mode.currentData()=="browser";file_mode=self.cookie_mode.currentData()=="file"
        self.cookie_mode.setEnabled(enabled);self.cookie_browser.setEnabled(enabled and browser_mode);self.cookie_profile.setEnabled(enabled and browser_mode and bool(browser));self.cookie_profile_browse.setEnabled(enabled and browser_mode and bool(browser));self.firefox_container.setEnabled(enabled and browser_mode and browser=="firefox");self.cookie_keyring.setEnabled(enabled and browser_mode and browser in {"chrome","edge"});self.cookie_file.setEnabled(enabled and file_mode);self.cookie_file_browse.setEnabled(enabled and file_mode)
        if not enabled:self.cookie_status.setText("Disabled — public/anonymous extraction will be used.")
        elif file_mode:
            report=validate_netscape_cookie_file(self.cookie_file.text()) if self.cookie_file.text() else None
            self.cookie_status.setText(f"Valid Netscape cookie file · {report.cookie_count} record(s). Values remain hidden." if report and report.valid else (report.error if report else "Import a Netscape-format .txt file."))
        elif not browser:self.cookie_status.setText("Select Chrome, Firefox, or Edge.")
        elif browser in detected:self.cookie_status.setText("Browser installation detected. Cookies will be loaded only when yt-dlp runs.")
        else:self.cookie_status.setText("Browser was not detected in a standard location; a valid custom profile may still work.")
    def browse_cookie_profile(self):
        value=QFileDialog.getExistingDirectory(self,"Select browser profile",self.cookie_profile.text() or str(Path.home()))
        if value:self.cookie_profile.setText(value)
    def browse_cookie_file(self):
        value,_=QFileDialog.getOpenFileName(self,"Import Netscape cookies",self.cookie_file.text() or str(Path.home()),"Netscape cookies (*.txt)")
        if not value:return
        report=validate_netscape_cookie_file(value)
        if not report.valid:QMessageBox.warning(self,"Invalid cookie file",report.error);return
        self.cookie_file.setText(value);self.update_cookie_controls()
    def browse_ffmpeg(self):
        value,_=QFileDialog.getOpenFileName(self,"Select FFmpeg executable",self.ffmpeg_location.text() or str(Path.home()),"FFmpeg (ffmpeg.exe ffmpeg);;All files (*)")
        if value:self.ffmpeg_location.setText(value)
    def restore_defaults(self):
        if QMessageBox.question(self,"Restore defaults","Reset every application setting to its safe default now?")==QMessageBox.Yes:self.settings.clear();self.settings.sync();self.settings_applied.emit();self.accept()
    def save(self,close=True):
        if not self.folder.text().strip():QMessageBox.warning(self,"Download folder required","Choose a default download folder.");return
        if not validate_output_template(self.template.text()):QMessageBox.warning(self,"Invalid filename template","The filename template must contain a yt-dlp placeholder such as %(title)s.");return
        if self.proxy.text().strip() and "://" not in self.proxy.text():QMessageBox.warning(self,"Invalid proxy","Proxy must include a scheme, for example http:// or socks5://.");return
        if self.ffmpeg_location.text().strip() and not Path(self.ffmpeg_location.text().strip()).exists():QMessageBox.warning(self,"Invalid FFmpeg location","The selected FFmpeg executable or directory does not exist.");return
        if self.download_backend.currentText()=="aria2c":
            if not Aria2Service.safe_ytdlp():QMessageBox.warning(self,"Unsafe yt-dlp version","aria2c requires yt-dlp 2026.06.09 or newer because older releases contain a known external-downloader security vulnerability.");return
            if not Aria2Service.version(self.aria2_location.text()):QMessageBox.warning(self,"aria2c not available","Install aria2c, add it to PATH, or select a valid aria2c executable.");return
        languages=[value.strip() for value in self.subtitle_languages.text().split(",") if value.strip()]
        if not languages:QMessageBox.warning(self,"Subtitle language required","Enter 'all' or at least one subtitle language code.");return
        values={
            "general/clipboard_url":self.startup_clipboard.isChecked(),"general/confirm_exit":self.confirm_exit.isChecked(),"general/remember_window":self.remember_window.isChecked(),"general/default_download_type":self.default_download_type.currentText(),"general/auto_analyze_clipboard":self.auto_analyze_clipboard.isChecked(),"general/startup_tab":self.startup_tab.currentText(),
            "downloads/folder":self.folder.text().strip(),"downloads/concurrent":self.concurrent.value(),"downloads/template":self.template.text(),"downloads/verify_integrity":self.verify_integrity.isChecked(),"downloads/integrity_retries":self.integrity_retries.value(),"downloads/failure_retry_enabled":self.failure_retry_enabled.isChecked(),"downloads/failure_retries":self.failure_retries.value(),"downloads/retry_backoff_base":self.retry_backoff_base.value(),"downloads/retry_backoff_max":self.retry_backoff_max.value(),"downloads/retry_jitter_percent":self.retry_jitter.value(),"downloads/pause_when_idle":self.pause_when_idle.isChecked(),"downloads/idle_pause_minutes":self.idle_pause_minutes.value(),"downloads/pause_low_battery":self.pause_low_battery.isChecked(),"downloads/low_battery_percent":self.low_battery_percent.value(),"downloads/battery_resume_hysteresis":self.battery_resume_hysteresis.value(),"downloads/auto_resume_global":self.auto_resume_global.isChecked(),"downloads/system_monitor_seconds":self.system_monitor_seconds.value(),"downloads/overwrite":self.overwrite.isChecked(),"downloads/keep_fragments":self.keep_fragments.isChecked(),"downloads/auto_start":self.auto_start.isChecked(),"downloads/max_filename":self.max_filename.value(),"downloads/temp_folder":self.temp_folder.text().strip(),"downloads/minimum_free_mib":self.minimum_free_space.value(),"downloads/archive":self.download_archive.text().strip(),"downloads/backend":self.download_backend.currentText(),"downloads/aria2_location":self.aria2_location.text().strip(),"downloads/aria2_connections":self.aria2_connections.value(),"downloads/aria2_split":self.aria2_split.value(),"downloads/aria2_min_split_mib":self.aria2_min_split.value(),"downloads/aria2_max_tries":self.aria2_max_tries.value(),"downloads/aria2_retry_wait":self.aria2_retry_wait.value(),"downloads/aria2_timeout":self.aria2_timeout.value(),"downloads/aria2_file_allocation":self.aria2_allocation.currentText(),"downloads/aria2_fragments":self.aria2_fragments.isChecked(),
            "video/container":self.preferred_container.currentData(),"video/resolution":self.default_resolution.currentText(),"video/codec":self.default_video_codec.currentText(),"video/fps":self.default_fps.currentText(),"video/dynamic_range":self.default_dynamic_range.currentText(),"video/bit_depth":self.default_bit_depth.currentText(),"video/multiple_streams":self.multiple_video_streams.isChecked(),"video/embed_thumbnail":self.video_thumbnail.isChecked(),"video/embed_metadata":self.video_metadata.isChecked(),"video/thumbnail_format":self.video_poster_format.currentText(),"video/keep_thumbnail":self.video_keep_poster.isChecked(),"video/embed_chapters":self.video_chapters.isChecked(),"video/embed_infojson":self.video_infojson.isChecked(),
            "audio/format":self.default_audio_format.currentText(),"audio/quality":self.default_audio_quality.currentText(),"audio/codec":self.default_audio_codec.currentText(),"audio/embed_thumbnail":self.audio_thumbnail.isChecked(),"audio/multiple_streams":self.multiple_audio_streams.isChecked(),"audio/sample_rate":self.audio_sample_rate.currentText(),"audio/channels":self.audio_channels.currentText(),"audio/embed_metadata":self.audio_metadata.isChecked(),"audio/thumbnail_format":self.audio_cover_format.currentText(),"audio/keep_thumbnail":self.audio_keep_cover.isChecked(),"audio/embed_chapters":self.audio_chapters.isChecked(),"audio/embed_infojson":self.audio_infojson.isChecked(),
            "subtitles/languages":",".join(languages),"subtitles/automatic":self.subtitle_auto.isChecked(),"subtitles/embed":self.subtitle_embed.isChecked(),"subtitles/format":self.subtitle_format.currentText(),"subtitles/default_enabled":self.subtitle_default.isChecked(),"subtitles/manual":self.subtitle_manual.isChecked(),"subtitles/convert":self.subtitle_convert.currentText(),
            "network/proxy":self.proxy.text().strip(),"network/timeout":self.network_timeout.value(),"network/retries":self.network_retries.value(),"network/fragment_retries":self.fragment_retries.value(),"network/fragments":self.fragments.value(),"network/rate_limit_kib":self.rate_limit.value(),"network/ip_family":self.ip_family.currentText(),"network/http_chunk_kib":self.http_chunk.value(),"network/sleep_interval":self.sleep_interval.value(),"network/user_agent":self.user_agent.text().strip(),"network/geo_bypass":self.geo_bypass.isChecked(),
            "ffmpeg/location":self.ffmpeg_location.text().strip(),"ffmpeg/preserve_timestamps":self.preserve_timestamps.isChecked(),"ffmpeg/threads":self.ffmpeg_threads.value(),"ytdlp/flat_playlist":self.flat_playlist.isChecked(),"ytdlp/channel_analysis_limit":self.channel_analysis_limit.value(),"ytdlp/prefer_free_formats":self.prefer_free_formats.isChecked(),"ytdlp/check_formats":self.check_formats.isChecked(),"ytdlp/extractor_retries":self.extractor_retries.value(),"ytdlp/ignore_playlist_errors":self.ignore_playlist_errors.isChecked(),"ytdlp/show_warnings":self.show_ytdlp_warnings.isChecked(),
            "appearance/theme":self.theme.currentText(),"appearance/font_size":self.font_size.value(),"appearance/compact":self.compact_ui.isChecked(),"appearance/statusbar":self.show_statusbar.isChecked(),"appearance/alternating_rows":self.alternating_rows.isChecked(),"appearance/show_preview":self.show_preview.isChecked(),
            "notifications/completed":self.notify_complete.isChecked(),"notifications/failed":self.notify_failed.isChecked(),"notifications/sound":self.notification_sound.isChecked(),"notifications/cancelled":self.notify_cancelled.isChecked(),"notifications/duration_ms":self.alert_duration.value(),"notifications/background_only":self.notify_background_only.isChecked(),
            "advanced/restrict_filenames":self.restrict_filenames.isChecked(),"advanced/use_cache":self.use_cache.isChecked(),"advanced/write_info_json":self.write_info_default.isChecked(),"advanced/embed_metadata":self.embed_metadata_default.isChecked(),"advanced/log_level":self.log_level.currentText(),"advanced/use_part_files":self.use_part_files.isChecked(),"advanced/write_description":self.write_description.isChecked(),"advanced/write_xattrs":self.write_xattrs.isChecked(),
        }
        for key,value in values.items():self.settings.setValue(key,value)
        if hasattr(self,"cookies_enabled"):
            browser=self.cookie_browser.currentData();profile=self.cookie_profile.text().strip();container=self.firefox_container.text().strip();mode=self.cookie_mode.currentData()
            if self.cookies_enabled.isChecked() and mode=="browser" and not browser:QMessageBox.warning(self,"Browser required","Select a browser or disable cookie authentication.");return
            if self.cookies_enabled.isChecked() and mode=="file":
                report=validate_netscape_cookie_file(self.cookie_file.text())
                if not report.valid:QMessageBox.warning(self,"Invalid cookie file",report.error);return
            if "\0" in profile or len(profile)>4096:QMessageBox.warning(self,"Invalid profile","The browser profile value is invalid.");return
            self.settings.setValue("cookies/enabled",self.cookies_enabled.isChecked());self.settings.setValue("cookies/mode",mode);self.settings.setValue("cookies/browser",browser or "");self.settings.setValue("cookies/profile",profile);self.settings.setValue("cookies/firefox_container",container if browser=="firefox" else "");self.settings.setValue("cookies/keyring","" if self.cookie_keyring.currentText()=="Auto" else self.cookie_keyring.currentText());self.settings.setValue("cookies/file",self.cookie_file.text().strip())
        self.settings.sync()
        if self.settings.status()!=QSettings.NoError:QMessageBox.warning(self,"Settings error","The application could not persist settings. Check user-profile permissions.");return
        self.initial_values={key:self.settings.value(key) for key in self.settings.allKeys()};self.change_summary.setText("All changes applied");self.settings_applied.emit()
        if close:self.accept()

class AboutDialog(QMessageBox):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle(f"About {APP_NAME}"); self.setIcon(QMessageBox.Information)
        self.setText(f"<h2>{APP_NAME} {APP_VERSION}</h2><p>A modern desktop video and audio downloader powered by yt-dlp.</p><p>Python {platform.python_version()} · PySide6 {pyside_version}<br>yt-dlp {YTDLPService.version()}<br>{FFmpegService.version() or 'FFmpeg not detected'}<br>{platform.system()} {platform.release()}</p><p>Uses yt-dlp, FFmpeg, and Qt/PySide6. This is not an official yt-dlp application.</p><p>Use only for media you have permission or the right to download.</p>")

class HistoryDetailsDialog(QDialog):
    def __init__(self,data,parent=None):
        super().__init__(parent); self.setWindowTitle("Download Details"); self.resize(600,430); layout=QVBoxLayout(self); text=QTextBrowser(); text.setPlainText("\n".join(f"{k.replace('_',' ').title()}: {v or '—'}" for k,v in data.items())); layout.addWidget(text); box=QDialogButtonBox(QDialogButtonBox.Close); box.rejected.connect(self.reject); layout.addWidget(box)
