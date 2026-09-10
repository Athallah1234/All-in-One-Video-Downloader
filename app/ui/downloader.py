"""Downloader workspace: shared configuration, collection selection and metadata."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QUrl, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPlainTextEdit, QTabBar, QGroupBox, QCheckBox, QSpinBox,
    QFileDialog, QMessageBox, QApplication, QScrollArea, QDialog, QDialogButtonBox,
    QTableWidgetItem, QSplitter)
from app.core.format_builder import FORMATS, QUALITIES, AUDIO_QUALITIES, AUDIO_FORMATS, build_options
from app.core.utils import valid_url, duration, size
from app.core.supported_sites import detect_url_type
from app.core.url_resolver import expand_short_url, is_short_url
from app.core.auth_detection import detect_auth_requirement
from app.core.existing_files import existing_output_files
from app.ui.widgets import button, combo, table, fill_table, details, open_path
from app.workers.jobs import FunctionWorker, analyze, analyze_outputs

MODES = ["Video", "Playlist", "Channel", "Audio", "Batch URL", "Subtitle", "Metadata", "Live Stream", "360° / VR"]


class URLText(QPlainTextEdit):
    """Accept plain URL text and local .txt files, never execute dropped content."""
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() == ".txt":
                        try:
                            if path.stat().st_size > 5 * 1024 * 1024:
                                raise ValueError("URL text files must be smaller than 5 MB.")
                            self.appendPlainText(path.read_text(encoding="utf-8-sig"))
                        except (OSError, UnicodeError, ValueError) as error:
                            QMessageBox.warning(self, "Import failed", str(error))
                elif valid_url(url.toString()):
                    self.appendPlainText(url.toString())
        elif event.mimeData().hasText():
            self.insertPlainText(event.mimeData().text())
        event.acceptProposedAction()


class DownloaderTab(QWidget):
    request_download = Signal(str, object, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.info = None
        self.analyzed_url = ""
        self.analyzed_mode = ""
        self.worker = None
        self.resolution_worker = None
        self.resolution_url = ""
        self.resolution_callbacks = []
        self.resolution_report_error = False
        self.resolution_cache = {}
        self.expanded_from = {}
        self.batch_validation_worker = None
        self.network = QNetworkAccessManager(self)
        self.thumbnail_reply = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 8)
        self.modes = QTabBar()
        self.modes.setExpanding(False)
        for mode in MODES:
            self.modes.addTab(mode)
        layout.addWidget(self.modes)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setSpacing(10)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        source = QGroupBox("01   Media source")
        source_layout = QVBoxLayout(source)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste a video URL to get started…")
        self.url.setClearButtonEnabled(True)
        row.addWidget(self.url, 1)
        self.paste_button = button("Paste", self.paste)
        row.addWidget(self.paste_button)
        self.analyze_button = button("Analyze URL", self.analyze, True)
        row.addWidget(self.analyze_button)
        source_layout.addLayout(row)
        self.url_detection = QLabel("Paste a URL to detect its website and source type.")
        self.url_detection.setObjectName("muted")
        self.url_detection.setWordWrap(True)
        source_layout.addWidget(self.url_detection)
        self.auth_detection = QLabel("Authentication: checked after a valid URL is entered.")
        self.auth_detection.setObjectName("muted")
        self.auth_detection.setWordWrap(True)
        source_layout.addWidget(self.auth_detection)
        self.batch_box = QWidget()
        batch_layout = QVBoxLayout(self.batch_box)
        batch_layout.setContentsMargins(0, 0, 0, 0)
        self.batch = URLText()
        self.batch.setPlaceholderText("One HTTP/HTTPS URL per line. You can also drop a .txt file here.")
        self.batch.setMaximumHeight(110)
        batch_layout.addWidget(self.batch)
        batch_buttons = QHBoxLayout()
        for label, callback in [("Paste", lambda: self.batch.appendPlainText(QApplication.clipboard().text())), ("Import TXT…", self.import_urls), ("Clear", self.batch.clear), ("Validate URLs", self.validate_batch)]:
            widget = button(label, callback)
            if label == "Validate URLs":
                self.batch_validate_button = widget
            batch_buttons.addWidget(widget)
        batch_buttons.addStretch()
        batch_layout.addLayout(batch_buttons)
        source_layout.addWidget(self.batch_box)
        body.addWidget(source)

        self.metadata_box = QGroupBox("Media preview")
        preview = QHBoxLayout(self.metadata_box)
        self.thumbnail = QLabel("▶")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setFixedSize(176, 99)
        self.thumbnail.setStyleSheet("background: #292842; color: #b5abff; border-radius: 8px; font-size: 30px;")
        preview.addWidget(self.thumbnail)
        text = QVBoxLayout()
        self.title = QLabel("Your next download starts here")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.summary = QLabel("Analyze a URL to preview metadata, formats and subtitles.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.summary)
        preview.addLayout(text, 1)
        self.formats_button = button("Available Formats", self.formats)
        self.formats_button.setEnabled(False)
        preview.addWidget(self.formats_button)
        body.addWidget(self.metadata_box)

        self.collection_box = QGroupBox("Playlist / channel items")
        collection_layout = QVBoxLayout(self.collection_box)
        self.collection_notice = QLabel("Analyze a playlist URL to view its items.")
        collection_layout.addWidget(self.collection_notice)
        self.items_table = table(["Select", "#", "Title", "Duration", "Availability", "Status"])
        self.items_table.setMinimumHeight(170)
        self.items_table.setMaximumHeight(260)
        self.items_table.setColumnWidth(0, 55)
        self.items_table.setColumnWidth(1, 45)
        self.items_table.setColumnWidth(2, 420)
        collection_layout.addWidget(self.items_table)
        selections = QHBoxLayout()
        for label, action in [("Select All", "all"), ("Deselect All", "none"), ("Invert Selection", "invert")]:
            selections.addWidget(button(label, lambda checked=False, action=action: self.select_items(action)))
        self.selected_button = button("Download Selected", self.download_selected)
        self.selected_button.setEnabled(False)
        selections.addWidget(self.selected_button)
        selections.addStretch()
        collection_layout.addLayout(selections)
        self.start = QSpinBox()
        self.start.setRange(1, 1000000)
        self.end = QSpinBox()
        self.end.setRange(0, 1000000)
        self.end.setSpecialValueText("Last")
        self.item_expression = QLineEdit()
        self.item_expression.setPlaceholderText("e.g. 1,3,5:10 (overrides start/end)")
        self.item_expression.setToolTip("yt-dlp playlist item expression; indices refer to source order.")
        limits = QHBoxLayout()
        for label, widget in [("Start", self.start), ("End", self.end), ("Items", self.item_expression)]:
            limits.addWidget(QLabel(label))
            limits.addWidget(widget)
        collection_layout.addLayout(limits)
        flags = QHBoxLayout()
        self.reverse = QCheckBox("Reverse playlist")
        self.random = QCheckBox("Random order")
        self.ignore = QCheckBox("Ignore unavailable videos")
        self.ignore.setChecked(True)
        for widget in [self.reverse, self.random, self.ignore]:
            flags.addWidget(widget)
        self.reverse.toggled.connect(lambda on: self.random.setChecked(False) if on else None)
        self.random.toggled.connect(lambda on: self.reverse.setChecked(False) if on else None)
        collection_layout.addLayout(flags)
        self.channel_controls = QWidget()
        channel_row = QHBoxLayout(self.channel_controls)
        channel_row.setContentsMargins(0, 0, 0, 0)
        self.channel_selection = combo(["All Videos", "Latest N Videos", "Oldest N Videos", "Date Range", "Custom Playlist Items"])
        self.number = QSpinBox()
        self.number.setRange(1, 1000000)
        self.number.setValue(10)
        self.date_from = QLineEdit()
        self.date_to = QLineEdit()
        self.date_from.setPlaceholderText("From YYYYMMDD")
        self.date_to.setPlaceholderText("To YYYYMMDD")
        for widget in [self.channel_selection, self.number, self.date_from, self.date_to]:
            channel_row.addWidget(widget)
        collection_layout.addWidget(self.channel_controls)
        body.addWidget(self.collection_box)

        self.options_box = QGroupBox("02   Download preferences")
        options = QVBoxLayout(self.options_box)
        grid = QGridLayout()
        self.format = combo(FORMATS, settings["format"])
        self.quality = combo(QUALITIES, settings["quality"])
        self.audio_quality = combo(AUDIO_QUALITIES, settings["audio_quality"])
        self.container = combo(["Auto", "MP4", "MKV", "WebM"], settings["container"])
        for column, (label, widget) in enumerate([("Format", self.format), ("Video quality", self.quality), ("Audio quality", self.audio_quality), ("Container", self.container)]):
            grid.addWidget(QLabel(label), 0, column)
            grid.addWidget(widget, 1, column)
        options.addLayout(grid)
        self.live_box = QGroupBox("Live recording duration")
        live_layout = QHBoxLayout(self.live_box)
        self.live_hours = QSpinBox()
        self.live_hours.setRange(0, 168)
        self.live_minutes = QSpinBox()
        self.live_minutes.setRange(0, 59)
        self.live_seconds = QSpinBox()
        self.live_seconds.setRange(0, 59)
        self.live_from_start = QCheckBox("From beginning when DVR is supported")
        for label, widget in (("Hours", self.live_hours), ("Minutes", self.live_minutes), ("Seconds", self.live_seconds)):
            live_layout.addWidget(QLabel(label))
            live_layout.addWidget(widget)
        live_layout.addWidget(self.live_from_start)
        live_layout.addStretch()
        options.addWidget(self.live_box)
        self.custom_format = QLineEdit()
        self.custom_format.setPlaceholderText("Custom yt-dlp format selector, e.g. 137+140 or best[height<=720]")
        self.custom_format.setVisible(self.format.currentText() == "Custom")
        self.format.currentTextChanged.connect(lambda value: self.custom_format.setVisible(value == "Custom"))
        self.format.currentTextChanged.connect(lambda value: self.audio_row.setVisible(self.mode == "Audio" or value == "Audio Only"))
        options.addWidget(self.custom_format)
        self.audio_row = QWidget()
        audio_layout = QHBoxLayout(self.audio_row)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_layout.addWidget(QLabel("Audio output"))
        self.audio_format = combo(AUDIO_FORMATS)
        audio_layout.addWidget(self.audio_format)
        audio_layout.addWidget(QLabel("Choose Best Audio to keep the original stream without conversion."))
        audio_layout.addStretch()
        options.addWidget(self.audio_row)
        flags = QGridLayout()
        self.flags = {}
        for i, (key, label) in enumerate([
            ("subtitles", "Download subtitles / lyrics"), ("auto_subtitles", "Automatic subtitles"),
            ("thumbnail", "Download thumbnail"), ("embed_thumbnail", "Embed thumbnail"),
            ("embed_subtitle", "Embed subtitles"), ("embed_metadata", "Embed metadata"),
            ("description", "Write description"), ("info_json", "Write info JSON"),
            ("keep_files", "Keep original / temporary files"), ("sponsorblock", "Remove SponsorBlock sponsor segments")]):
            checkbox = QCheckBox(label)
            checkbox.setChecked(settings.values.get(key, False))
            self.flags[key] = checkbox
            flags.addWidget(checkbox, i // 3, i % 3)
        self.flags["sponsorblock"].setToolTip("Uses yt-dlp's SponsorBlock integration; requires FFmpeg and a supported video. A service failure is logged by yt-dlp.")
        options.addLayout(flags)
        self.subtitle_row = QWidget()
        subtitles = QHBoxLayout(self.subtitle_row)
        subtitles.setContentsMargins(0, 0, 0, 0)
        self.languages = QLineEdit("en")
        self.languages.setPlaceholderText("Languages: en,id,ja")
        self.subtitle_format = combo(["Best available", "SRT", "VTT", "ASS"])
        self.manual_subtitles = QCheckBox("Manual subtitles")
        self.manual_subtitles.setChecked(True)
        self.all_languages = QCheckBox("All languages")
        self.convert_srt = QCheckBox("Convert to SRT")
        for widget in [QLabel("Languages"), self.languages, self.subtitle_format, self.manual_subtitles, self.all_languages, self.convert_srt]:
            subtitles.addWidget(widget)
        options.addWidget(self.subtitle_row)
        self.subtitle_list = QLabel("Analyze a URL to list available manual and automatic subtitle languages.")
        self.subtitle_list.setWordWrap(True)
        self.subtitle_list.setObjectName("muted")
        options.addWidget(self.subtitle_list)
        body.addWidget(self.options_box)

        self.json_box = QGroupBox("Metadata • JSON")
        json_layout = QVBoxLayout(self.json_box)
        self.json_view = QPlainTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setMinimumHeight(240)
        self.json_view.setPlaceholderText("Analyze a URL to inspect its metadata without downloading media.")
        json_layout.addWidget(self.json_view)
        json_buttons = QHBoxLayout()
        self.metadata_buttons = []
        for label, callback in [("Copy JSON", lambda: QApplication.clipboard().setText(self.json_view.toPlainText())), ("Save JSON…", self.save_json), ("Copy Metadata", self.copy_metadata)]:
            widget = button(label, callback)
            widget.setEnabled(False)
            self.metadata_buttons.append(widget)
            json_buttons.addWidget(widget)
        json_buttons.addStretch()
        json_layout.addLayout(json_buttons)
        body.addWidget(self.json_box)
        body.addStretch()

        destination = QHBoxLayout()
        destination.addWidget(QLabel("Save to"))
        self.output = QLineEdit(settings["output"])
        destination.addWidget(self.output, 1)
        destination.addWidget(button("Browse…", self.browse))
        destination.addWidget(button("Open Folder", lambda: open_path(self.output.text(), True)))
        self.download_button = button("↓  Download", self.download, True)
        destination.addWidget(self.download_button)
        layout.addLayout(destination)
        self.url.textChanged.connect(self.url_changed)
        self.batch.textChanged.connect(self.update_enabled)
        self.modes.currentChanged.connect(self.mode_changed)
        self.detection_timer = QTimer(self)
        self.detection_timer.setSingleShot(True)
        self.detection_timer.setInterval(200)
        self.detection_timer.timeout.connect(self.detect_source)
        for key in ["start", "end", "number"]:
            getattr(self, key).setValue(settings[key])
        for key in ["live_hours", "live_minutes", "live_seconds"]:
            getattr(self, key).setValue(settings[key])
        self.live_from_start.setChecked(settings["live_from_start"])
        for key in ["custom_format", "languages", "date_from", "date_to"]:
            getattr(self, key).setText(settings[key])
        self.item_expression.setText(settings["items"])
        for key in ["manual_subtitles", "all_languages", "convert_srt", "reverse", "random"]:
            getattr(self, key).setChecked(settings[key])
        self.ignore.setChecked(settings["ignore_unavailable"])
        for key in ["audio_format", "subtitle_format", "channel_selection"]:
            getattr(self, key).setCurrentText(settings[key])
        self.modes.setCurrentIndex(max(0, min(len(MODES) - 1, settings["mode_index"])))
        self.mode_changed()

    @property
    def mode(self):
        return MODES[self.modes.currentIndex()]

    def mode_changed(self):
        mode = self.mode
        self.batch_box.setVisible(mode == "Batch URL")
        self.url.setVisible(mode != "Batch URL")
        self.paste_button.setVisible(mode != "Batch URL")
        self.analyze_button.setVisible(mode != "Batch URL")
        self.url_detection.setVisible(mode != "Batch URL")
        self.auth_detection.setVisible(mode != "Batch URL")
        self.metadata_box.setVisible(mode != "Batch URL")
        self.collection_box.setVisible(mode in {"Playlist", "Channel"})
        self.live_box.setVisible(mode == "Live Stream")
        self.channel_controls.setVisible(mode == "Channel")
        self.audio_row.setVisible(mode == "Audio" or self.format.currentText() == "Audio Only")
        self.json_box.setVisible(mode == "Metadata")
        self.options_box.setVisible(mode != "Metadata")
        self.format.setEnabled(mode not in {"Audio", "Subtitle", "360° / VR"})
        self.quality.setEnabled(mode not in {"Audio", "Subtitle"})
        self.container.setEnabled(mode not in {"Audio", "Subtitle"})
        self.flags["embed_subtitle"].setEnabled(mode != "Subtitle")
        if mode == "Subtitle":
            self.flags["embed_subtitle"].setChecked(False)
        self.download_button.setText("◎  Download 360°" if mode == "360° / VR" else "●  Record Live" if mode == "Live Stream" else "↓  Download All" if mode in {"Playlist", "Channel", "Batch URL"} else "↓  Save Metadata" if mode == "Metadata" else "↓  Download")
        self.analyze_button.setText(f"Analyze {mode}" if mode in {"Playlist", "Channel"} else "Analyze URL")
        self.update_enabled()

    def update_enabled(self):
        lines = self.batch_urls()
        valid = bool(lines) and all(valid_url(url) for url in lines) if self.mode == "Batch URL" else valid_url(self.url.text())
        resolving = self.resolution_worker is not None
        self.download_button.setEnabled(valid and not resolving and self.worker is None)
        self.analyze_button.setEnabled(valid_url(self.url.text()) and self.worker is None and not resolving)
        self.batch_validate_button.setEnabled(self.batch_validation_worker is None)
        self.selected_button.setEnabled(self.info is not None and self.analyzed_url == self.url.text().strip() and self.analyzed_mode == self.mode and self.items_table.rowCount() > 0)

    def url_changed(self):
        self.info = None
        self.formats_button.setEnabled(False)
        for widget in self.metadata_buttons:
            widget.setEnabled(False)
        self.json_view.clear()
        self.items_table.setRowCount(0)
        self.title.setText("Ready to analyze")
        self.summary.setText("Analyze this URL to preview media information.")
        self.thumbnail.setText("▶")
        self.url_detection.setText("Detecting website and source type…" if valid_url(self.url.text()) else "Paste a valid HTTP/HTTPS URL to detect its source type.")
        self.auth_detection.setText("Authentication: waiting for URL detection…" if valid_url(self.url.text()) else "Authentication: checked after a valid URL is entered.")
        self.detection_timer.start()
        self.update_enabled()

    @staticmethod
    def detection_text(result):
        if not result["specific"]:
            return "Detected: Generic / unknown website • Type will be confirmed during analysis"
        status = "working" if result["working"] is True else "currently marked broken" if result["working"] is False else "status unknown"
        return f'Detected: {result["description"]} • {result["kind"]} • Extractor: {result["extractor"]} • {status}'

    def detect_source(self):
        url = self.url.text().strip()
        if valid_url(url):
            if is_short_url(url) and url not in self.resolution_cache:
                self.resolve_source()
                return None
            result = detect_url_type(url)
            prefix = ""
            if url in self.expanded_from:
                source_host = QUrl(self.expanded_from[url]).host()
                prefix = f"Expanded from {source_host} • "
            self.url_detection.setText(prefix + self.detection_text(result))
            self.url_detection.setToolTip(self.url_detection.text())
            assessment = detect_auth_requirement(url, result, self.settings.values)
            self.auth_detection.setText(self.authentication_detection_text(assessment))
            self.auth_detection.setToolTip("\n".join(assessment["reasons"]))
            return result
        return None

    @staticmethod
    def authentication_detection_text(assessment):
        likelihood = assessment["likelihood"].capitalize()
        reason = assessment["reasons"][0] if assessment["reasons"] else "No login-specific URL pattern was detected."
        if assessment["auth_configured"]:
            methods = ", ".join(assessment["configured_methods"])
            readiness = f"Configured: {methods}."
        elif assessment["likelihood"] == "likely":
            readiness = "No credentials configured; check Settings > Authentication."
        else:
            readiness = "No credentials configured."
        return f"Authentication likelihood: {likelihood} • {reason} • {readiness}"

    def resolve_source(self, callback=None, report_error=False):
        url = self.url.text().strip()
        if not is_short_url(url) or url in self.resolution_cache:
            if callback:
                callback()
            return
        if self.resolution_worker:
            if self.resolution_url == url and callback:
                self.resolution_callbacks.append(callback)
            self.resolution_report_error = self.resolution_report_error or report_error
            return
        self.resolution_url = url
        self.resolution_callbacks = [callback] if callback else []
        self.resolution_report_error = report_error
        self.url_detection.setText(f"Expanding short URL from {QUrl(url).host()}…")
        self.auth_detection.setText("Authentication: waiting for the short URL destination…")
        worker = FunctionWorker(lambda: expand_short_url(url), self)
        self.resolution_worker = worker
        worker.result.connect(lambda result: self.short_url_resolved(result, url))
        worker.failed.connect(lambda error: self.short_url_failed(error, url, self.resolution_report_error))
        worker.finished.connect(self.short_url_resolution_finished)
        worker.start()
        self.update_enabled()

    def short_url_resolved(self, result, original):
        self.resolution_cache[original] = result.final_url
        if self.url.text().strip() != original:
            self.resolution_callbacks.clear()
            return
        final = result.final_url
        if final != original:
            self.expanded_from[final] = original
            self.url.setText(final)
        else:
            self.detect_source()
        callbacks, self.resolution_callbacks = self.resolution_callbacks, []
        for callback in callbacks:
            QTimer.singleShot(0, callback)

    def short_url_failed(self, error, original, report_error):
        if self.url.text().strip() == original:
            self.url_detection.setText(f"Short URL could not be expanded • {error}")
            if report_error:
                QMessageBox.warning(self, "Short URL expansion failed", error)
        self.resolution_callbacks.clear()

    def short_url_resolution_finished(self):
        self.resolution_worker.deleteLater()
        self.resolution_worker = None
        self.resolution_url = ""
        self.resolution_report_error = False
        self.update_enabled()

    def confirm_detected_mode(self, result):
        """Offer the matching collection mode while preserving intentional choices."""
        if not result or not result["specific"] or self.mode not in {"Video", "Playlist", "Channel"}:
            return True
        suggested = result["suggested_mode"]
        if suggested == self.mode or suggested not in {"Video", "Playlist", "Channel"}:
            return True
        prompt = QMessageBox(self)
        prompt.setWindowTitle(f'{result["kind"]} detected')
        prompt.setText(f'{result["description"]} matches extractor “{result["extractor"]}”.\nRecommended mode: {suggested}.')
        keep = prompt.addButton(f"Keep {self.mode} Mode", QMessageBox.ButtonRole.AcceptRole)
        switch = prompt.addButton(f"Switch to {suggested} Mode", QMessageBox.ButtonRole.ActionRole)
        prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.exec()
        if prompt.clickedButton() == switch:
            self.modes.setCurrentIndex(MODES.index(suggested))
            return True
        return prompt.clickedButton() == keep

    def preferences(self):
        result = self.settings.values.copy()
        result.update(mode=self.mode, output=self.output.text().strip(), format=self.format.currentText(),
                      quality=self.quality.currentText(), audio_quality=self.audio_quality.currentText(),
                      container=self.container.currentText(), custom_format=self.custom_format.text().strip(),
                      audio_format=self.audio_format.currentText(), languages=self.languages.text().strip(),
                      subtitle_format=self.subtitle_format.currentText(), manual_subtitles=self.manual_subtitles.isChecked(),
                      all_languages=self.all_languages.isChecked(), convert_srt=self.convert_srt.isChecked(),
                      start=self.start.value(), end=self.end.value(), items=self.item_expression.text(),
                      reverse=self.reverse.isChecked(), random=self.random.isChecked(), ignore_unavailable=self.ignore.isChecked(),
                      channel_selection=self.channel_selection.currentText(), number=self.number.value(),
                      date_from=self.date_from.text().strip(), date_to=self.date_to.text().strip(),
                      live_hours=self.live_hours.value(), live_minutes=self.live_minutes.value(),
                      live_seconds=self.live_seconds.value(), live_from_start=self.live_from_start.isChecked())
        result.update({key: widget.isChecked() for key, widget in self.flags.items()})
        return result

    def paste(self):
        self.url.setText(QApplication.clipboard().text().strip())

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Download folder", self.output.text())
        if folder:
            self.output.setText(folder)

    def batch_urls(self):
        return list(dict.fromkeys(line.strip() for line in self.batch.toPlainText().splitlines() if line.strip()))

    def import_urls(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import URLs", "", "Text (*.txt)")
        if path:
            try:
                if Path(path).stat().st_size > 5 * 1024 * 1024:
                    raise ValueError("URL text files must be smaller than 5 MB.")
                self.batch.appendPlainText(Path(path).read_text(encoding="utf-8-sig"))
                self.modes.setCurrentIndex(MODES.index("Batch URL"))
            except (OSError, UnicodeError, ValueError) as error:
                QMessageBox.warning(self, "Import failed", str(error))

    def validate_batch(self):
        urls = self.batch_urls()
        short_urls = [url for url in urls if valid_url(url) and is_short_url(url)]
        if short_urls and self.batch_validation_worker is None:
            self.batch_validate_button.setText("Expanding…")
            worker = FunctionWorker(lambda: self.expand_batch_urls(urls), self)
            self.batch_validation_worker = worker
            worker.result.connect(self.batch_urls_expanded)
            worker.failed.connect(lambda error: QMessageBox.warning(self, "Short URL expansion failed", error))
            worker.finished.connect(self.batch_expansion_finished)
            worker.start()
            self.update_enabled()
            return
        self.show_batch_validation(urls)

    @staticmethod
    def expand_batch_urls(urls):
        expanded, errors = [], []
        for index, url in enumerate(urls, 1):
            if valid_url(url) and is_short_url(url):
                try:
                    result = expand_short_url(url)
                    expanded.append(result.final_url)
                except ValueError as error:
                    expanded.append(url)
                    errors.append(f"#{index}: {error}")
            else:
                expanded.append(url)
        return expanded, errors

    def batch_urls_expanded(self, payload):
        urls, errors = payload
        self.batch.setPlainText("\n".join(urls))
        self.show_batch_validation(urls, errors)

    def batch_expansion_finished(self):
        self.batch_validation_worker.deleteLater()
        self.batch_validation_worker = None
        self.batch_validate_button.setText("Validate URLs")
        self.update_enabled()

    def show_batch_validation(self, urls, expansion_errors=()):
        invalid = [str(i + 1) for i, url in enumerate(urls) if not valid_url(url)]
        detected = {}
        authentication = {"likely": 0, "possible": 0, "unlikely": 0}
        for url in urls:
            if valid_url(url):
                result = detect_url_type(url)
                key = f'{result["description"]} — {result["kind"]}'
                detected[key] = detected.get(key, 0) + 1
                assessment = detect_auth_requirement(url, result, self.settings.values)
                authentication[assessment["likelihood"]] += 1
        summary = "\n".join(f"• {name}: {count}" for name, count in sorted(detected.items())) or "• No valid URLs to detect"
        validity = "Invalid entries: " + ", ".join(invalid) if invalid else "All entries are valid HTTP/HTTPS URLs."
        expansion = ""
        if expansion_errors:
            expansion = "\n\nShort URLs that could not be expanded:\n" + "\n".join(expansion_errors)
        auth_summary = f'Likely: {authentication["likely"]} • Possible: {authentication["possible"]} • Unlikely: {authentication["unlikely"]}'
        QMessageBox.information(self, "URL validation", f"{len(urls)} unique URLs. {validity}\n\nDetected sources:\n{summary}\n\nAuthentication likelihood:\n{auth_summary}{expansion}\n\nFinal availability and login requirements are checked during extraction.")

    def analyze(self):
        if self.worker or not valid_url(self.url.text()):
            return
        if is_short_url(self.url.text().strip()) and self.url.text().strip() not in self.resolution_cache:
            self.resolve_source(self.analyze, True)
            return
        url, preferences = self.url.text().strip(), self.preferences()
        detection = self.detect_source()
        if not self.confirm_detected_mode(detection):
            return
        preferences = self.preferences()
        self.analyzed_url, self.analyzed_mode = url, self.mode
        self.worker = FunctionWorker(lambda: analyze(url, preferences), self)
        self.worker.result.connect(lambda info: self.analyzed(info, url, preferences["mode"]))
        self.worker.failed.connect(lambda error: QMessageBox.warning(self, "Analysis failed", error))
        self.worker.finished.connect(self.analysis_finished)
        self.title.setText("Analyzing source…")
        self.summary.setText("Fetching metadata in the background. Large channels may take longer.")
        self.worker.start()
        self.update_enabled()

    def analysis_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.update_enabled()

    def analyzed(self, info, url, mode):
        if self.url.text().strip() != url or self.mode != mode:
            return
        self.info = info
        if mode == "360° / VR":
            from app.core.vr import validate_vr_info
            try:
                validate_vr_info(info)
            except ValueError as error:
                QMessageBox.warning(self, "360° format unavailable", str(error))
        if mode == "Live Stream":
            from app.core.live import validate_live_info
            try:
                validate_live_info(info)
            except ValueError as error:
                QMessageBox.warning(self, "Live stream unavailable", str(error))
        if info.get("entries") is not None and mode == "Video":
            if QMessageBox.question(self, "Playlist source", "The source returned a playlist. Switch to Playlist mode to select its items?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.modes.setCurrentIndex(MODES.index("Playlist"))
                self.analyzed_mode = "Playlist"
        self.title.setText(info.get("title") or info.get("channel") or "Untitled media")
        entries = info.get("entries")
        text = [str(info.get("uploader") or info.get("channel") or "Unknown uploader"),
                str(info.get("extractor") or "Unknown extractor"), duration(info.get("duration")),
                f"{info.get('view_count') or '—'} views", str(info.get("upload_date") or "")]
        if entries is not None:
            text.append(f"{len(entries)} available entries")
        if info.get("channel_id"):
            text.append("Channel ID: " + info["channel_id"])
        self.summary.setText("  •  ".join(text) + "\n" + (info.get("description") or "")[:220])
        self.formats_button.setEnabled(bool(info.get("formats")))
        self.json_view.setPlainText(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        for widget in self.metadata_buttons:
            widget.setEnabled(True)
        manual = sorted((info.get("subtitles") or {}).keys())
        automatic = sorted((info.get("automatic_captions") or {}).keys())
        self.subtitle_list.setText("Manual: " + (", ".join(manual) or "none") + "\nAutomatic: " + (", ".join(automatic) or "none"))
        self.subtitle_list.setMaximumHeight(90)
        self.subtitle_list.setToolTip(self.subtitle_list.text())
        if manual and self.languages.text() == "en" and "en" not in manual:
            self.languages.setText(manual[0])
        if entries is not None:
            fill_table(self.items_table, [["", i + 1, (entry or {}).get("title", "Unavailable"), duration((entry or {}).get("duration")), (entry or {}).get("availability") or ("Available" if entry else "Unavailable"), "Ready" if entry else "Unavailable"] for i, entry in enumerate(entries)])
            for row, entry in enumerate(entries):
                checkbox = QTableWidgetItem()
                checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                checkbox.setCheckState(Qt.CheckState.Checked if entry else Qt.CheckState.Unchecked)
                self.items_table.setItem(row, 0, checkbox)
            self.collection_notice.setText(f"{len(entries)} items • Selection refers to source playlist order")
        thumb = info.get("thumbnail") or next((x.get("url") for x in reversed(info.get("thumbnails") or []) if x.get("url")), "")
        if thumb and valid_url(thumb):
            if self.thumbnail_reply:
                self.thumbnail_reply.abort()
            request = QNetworkRequest(QUrl(thumb))
            request.setTransferTimeout(15000)
            reply = self.network.get(request)
            self.thumbnail_reply = reply
            reply.downloadProgress.connect(lambda received, total: reply.abort() if received > 5 * 1024 * 1024 else None)
            reply.finished.connect(lambda: self.thumbnail_loaded(reply, url))
        self.update_enabled()

    def thumbnail_loaded(self, reply, url):
        if self.url.text().strip() == url:
            pixmap = QPixmap()
            if pixmap.loadFromData(reply.readAll()):
                self.thumbnail.setPixmap(pixmap.scaled(self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if self.thumbnail_reply is reply:
            self.thumbnail_reply = None
        reply.deleteLater()

    def select_items(self, action):
        for row in range(self.items_table.rowCount()):
            item = self.items_table.item(row, 0)
            checked = action == "all" or action == "invert" and item.checkState() != Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def download_selected(self):
        selected = [str(row + 1) for row in range(self.items_table.rowCount()) if self.items_table.item(row, 0).checkState() == Qt.CheckState.Checked]
        if not selected:
            QMessageBox.information(self, "No selection", "Select at least one item.")
            return
        self.download(items=",".join(selected))

    def download(self, checked=False, items=None):
        preferences = self.preferences()
        if items is not None:
            preferences.update(items=items, channel_selection="Custom Playlist Items")
        if not preferences["output"]:
            QMessageBox.warning(self, "Choose destination", "Select a download folder.")
            return
        urls = self.batch_urls() if self.mode == "Batch URL" else [self.url.text().strip()]
        if not urls or not all(valid_url(url) for url in urls):
            QMessageBox.warning(self, "Invalid URL", "Enter valid HTTP/HTTPS URLs.")
            return
        if self.mode != "Batch URL" and is_short_url(urls[0]) and urls[0] not in self.resolution_cache:
            self.resolve_source(lambda: self.download(items=items), True)
            return
        if self.mode in {"Video", "Playlist", "Channel"} and self.analyzed_url != urls[0]:
            if not self.confirm_detected_mode(detect_url_type(urls[0])):
                return
            preferences = self.preferences()
        if self.mode == "Channel":
            count = len((self.info or {}).get("entries", [])) if self.analyzed_url == urls[0] else 0
            limit = len(items.split(",")) if items else preferences["number"] if preferences["channel_selection"] in {"Latest N Videos", "Oldest N Videos"} else count
            if limit > 100 or not count and preferences["channel_selection"] not in {"Latest N Videos", "Oldest N Videos"}:
                if QMessageBox.question(self, "Large channel", "Channel contains a large or unknown number of videos. Continue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
        if self.mode == "Subtitle" and not (preferences["manual_subtitles"] or preferences["auto_subtitles"]):
            QMessageBox.warning(self, "Subtitle source", "Select manual or automatic subtitles.")
            return
        try:
            build_options(preferences)
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Check preferences", str(error))
            return
        try:
            folder_has_files = Path(preferences["output"]).is_dir() and any(Path(preferences["output"]).iterdir())
        except OSError as error:
            QMessageBox.warning(self, "Cannot inspect destination", str(error))
            return
        if folder_has_files:
            if len(urls) == 1 and self.mode not in {"Playlist", "Channel"} and self.info is not None and self.analyzed_url == urls[0] and self.analyzed_mode == self.mode:
                self.finish_existing_file_preflight([(urls[0], self.info)], urls, preferences, self.mode)
            else:
                self.start_existing_file_preflight(urls, preferences, self.mode)
            return
        self.enqueue_download(urls, preferences, self.mode)

    def start_existing_file_preflight(self, urls, preferences, mode):
        if self.worker:
            return
        self.worker = FunctionWorker(lambda: [(url, analyze_outputs(url, preferences)) for url in urls], self)
        self.worker.result.connect(lambda infos: self.finish_existing_file_preflight(infos, urls, preferences, mode))
        self.worker.failed.connect(lambda error: QMessageBox.warning(
            self, "Existing-file check failed", "The destination contains files, but output names could not be checked before download.\n\n" + error))
        self.worker.finished.connect(self.analysis_finished)
        self.title.setText("Checking existing filenames…")
        self.summary.setText("Fetching metadata before queueing so existing output files can be reported explicitly.")
        self.worker.start()
        self.update_enabled()

    def finish_existing_file_preflight(self, infos, urls, preferences, mode):
        current_urls = self.batch_urls() if self.mode == "Batch URL" else [self.url.text().strip()]
        if mode != self.mode or urls != current_urls:
            return
        conflicts = []
        try:
            for _, info in infos:
                conflicts.extend(existing_output_files(info, preferences))
        except (ValueError, OSError, TypeError) as error:
            QMessageBox.warning(self, "Existing-file check failed", str(error))
            return
        conflicts = list(dict.fromkeys(conflicts))
        if conflicts:
            shown = "\n".join(f"• {path.name}" for path in conflicts[:12])
            remaining = f"\n• …and {len(conflicts) - 12} more" if len(conflicts) > 12 else ""
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Existing files detected")
            prompt.setIcon(QMessageBox.Icon.Warning)
            prompt.setText(f"{len(conflicts)} output file(s) already exist:\n\n{shown}{remaining}\n\nExisting files will be skipped and will not be overwritten.")
            proceed = prompt.addButton("Continue and Skip Existing", QMessageBox.ButtonRole.AcceptRole)
            prompt.addButton(QMessageBox.StandardButton.Cancel)
            prompt.exec()
            if prompt.clickedButton() != proceed:
                return
        self.enqueue_download(urls, preferences, mode)

    def enqueue_download(self, urls, preferences, mode):
        for url in urls:
            self.request_download.emit(url, preferences, mode)
        self.persist_preferences()

    def persist_preferences(self):
        preferences = self.preferences()
        for key in ["output", "format", "quality", "audio_quality", "container", "custom_format", "audio_format", "languages", "subtitle_format", "manual_subtitles", "all_languages", "convert_srt", "start", "end", "items", "reverse", "random", "ignore_unavailable", "channel_selection", "number", "date_from", "date_to", "live_hours", "live_minutes", "live_seconds", "live_from_start", *self.flags]:
            self.settings.values[key] = preferences[key]
        self.settings.values["mode_index"] = self.modes.currentIndex()
        self.settings.save()

    def formats(self):
        if not self.info:
            return
        formats = self.info.get("formats") or []
        dialog = QDialog(self)
        dialog.setWindowTitle("Available Formats")
        dialog.resize(1000, 560)
        layout = QVBoxLayout(dialog)
        view = table(["ID", "Extension", "Resolution", "FPS", "Video codec", "Audio codec", "Bitrate", "Size", "Protocol"])
        fill_table(view, [[f.get("format_id"), f.get("ext"), f.get("resolution"), f.get("fps"), f.get("vcodec"), f.get("acodec"), f.get("tbr"), size(f.get("filesize") or f.get("filesize_approx")), f.get("protocol")] for f in formats])
        view.setSortingEnabled(True)
        layout.addWidget(view)
        use = button("Use Selected Format", lambda: use_format())
        use.setEnabled(False)
        view.itemSelectionChanged.connect(lambda: use.setEnabled(view.currentRow() >= 0))
        def use_format():
            self.format.setCurrentText("Custom")
            self.custom_format.setText(view.item(view.currentRow(), 0).text())
            dialog.accept()
        layout.addWidget(QLabel("A single format ID may contain video only or audio only. Choose a combined preset to merge streams."))
        layout.addWidget(use)
        dialog.exec()

    def save_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save metadata", "metadata.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(self.json_view.toPlainText(), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, "Save failed", str(error))

    def copy_metadata(self):
        if self.info:
            QApplication.clipboard().setText("\n".join(f"{key}: {self.info.get(key, '—')}" for key in ["title", "id", "webpage_url", "extractor", "uploader", "channel", "duration", "upload_date", "view_count", "description", "tags", "categories"]))
