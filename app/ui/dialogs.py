"""Settings and extractor dialogs."""
import logging
import platform
import sys
from PySide6 import __version__ as qt_version
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
    QWidget, QLineEdit, QCheckBox, QSpinBox, QDialogButtonBox, QFileDialog, QLabel, QMessageBox, QScrollArea)
from yt_dlp.version import __version__ as ydl_version
from app import __version__
from app.core.ffmpeg import detect, version_status
from app.core.format_builder import FORMATS, QUALITIES, AUDIO_QUALITIES, extra_options, filename_preview, authentication_options
from app.core.proxy import PROXY_MODES, proxy_options
from app.core.aria2 import aria2_options, aria2_version_status, inspect_aria2c
from app.core.supported_sites import supported_sites, filter_sites
from app.services.settings import DEFAULTS
from app.ui.widgets import button, combo, table, fill_table, details
from app.workers.jobs import FunctionWorker


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(760, 650)
        self.settings = settings
        self.fields = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        general = self.section("General")
        self.field(general, "output", "Default download folder", "folder")
        self.field(general, "theme", "Theme", ["System", "Light", "Dark"])
        self.field(general, "language", "Interface language", ["English"])
        for key, label in [("confirm_exit", "Confirm before exit"), ("auto_open", "Open folder after download"), ("clipboard", "Detect clipboard URLs"), ("notifications", "Desktop notifications")]:
            self.field(general, key, label, bool)
        downloader = self.section("Downloader")
        for key, label, choices in [("format", "Default format", FORMATS), ("quality", "Video quality", QUALITIES), ("audio_quality", "Audio quality", AUDIO_QUALITIES), ("container", "Container", ["Auto", "MP4", "MKV", "WebM"])]:
            self.field(downloader, key, label, choices)
        for key, label, maximum in [("concurrency", "Concurrent downloads", 3), ("retries", "Retry count", 50), ("timeout", "Socket timeout (seconds)", 600)]:
            self.field(downloader, key, label, maximum)
        self.field(downloader, "auto_retry", "Auto-retry failed jobs", bool)
        for key, label, maximum in [
            ("auto_retry_attempts", "Auto-retry attempts", 20),
            ("auto_retry_base_delay", "Initial retry delay (seconds)", 3600),
            ("auto_retry_max_delay", "Maximum retry delay (seconds)", 86400),
        ]:
            self.field(downloader, key, label, maximum)
        retry_help = QLabel("Retries the whole job after yt-dlp exhausts its own retry count. Delay doubles after each failure up to the configured maximum. Backoff does not occupy a worker slot.")
        retry_help.setWordWrap(True)
        downloader.addRow(retry_help)
        def toggle_auto_retry(enabled):
            for key in ("auto_retry_attempts", "auto_retry_base_delay", "auto_retry_max_delay"):
                self.fields[key].setEnabled(enabled)
        self.fields["auto_retry"].toggled.connect(toggle_auto_retry)
        toggle_auto_retry(self.fields["auto_retry"].isChecked())
        self.field(downloader, "archive", "Use download archive (serializes jobs)", bool)
        naming = self.section("File Naming")
        presets = {"Title + ID": "%(title)s [%(id)s].%(ext)s", "Title only": "%(title)s.%(ext)s", "Uploader + Title": "%(uploader)s - %(title)s.%(ext)s", "Date + Title": "%(upload_date)s - %(title)s.%(ext)s", "Playlist Index + Title": "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s"}
        preset = combo([*presets, "Custom"], "Custom")
        naming.addRow("Preset", preset)
        self.field(naming, "template", "Output template", str)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        naming.addRow("Preview", self.preview)
        preset.currentTextChanged.connect(lambda value: self.fields["template"].setText(presets[value]) if value in presets else None)
        self.fields["template"].textChanged.connect(self.update_preview)
        self.update_preview()
        network = self.section("Network")
        self.field(network, "proxy_type", "Proxy type", PROXY_MODES)
        for key, label in [("proxy", "Proxy URL"), ("socks_host", "SOCKS5 host"),
                           ("socks_username", "SOCKS5 username (optional)"),
                           ("socks_password", "SOCKS5 password (optional)"),
                           ("rate_limit", "Rate limit, e.g. 2M"), ("source_address", "Source address")]:
            self.field(network, key, label, str)
        self.fields["proxy"].setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.fields["socks_password"].setEchoMode(QLineEdit.EchoMode.Password)
        self.field(network, "socks_port", "SOCKS5 port", 65535)
        proxy_help = QLabel("SOCKS5 resolves website DNS locally; SOCKS5h sends hostname resolution through the proxy. Credentials are percent-encoded before being passed to yt-dlp. The SOCKS password is kept for this application session only.")
        proxy_help.setWordWrap(True)
        network.addRow(proxy_help)
        def update_proxy_fields(mode):
            self.fields["proxy"].setEnabled(mode == "Proxy URL")
            socks = mode in {"SOCKS5", "SOCKS5h (remote DNS)"}
            for key in ("socks_host", "socks_port", "socks_username", "socks_password"):
                self.fields[key].setEnabled(socks)
        self.fields["proxy_type"].currentTextChanged.connect(update_proxy_fields)
        update_proxy_fields(self.fields["proxy_type"].currentText())
        self.field(network, "ip", "IP protocol", ["Auto", "IPv4", "IPv6"])
        cookies = self.section("Cookies")
        warning = QLabel("Cookies contain sensitive authentication data. Use only your own authorized session.\nCookie contents are never displayed or logged; settings store only the file path/browser choice.")
        warning.setWordWrap(True)
        cookies.addRow(warning)
        self.field(cookies, "cookies", "Cookie source", ["No Cookies", "Cookie File", "Cookies from Browser"])
        self.field(cookies, "cookie_file", "Netscape cookie file", "file")
        self.field(cookies, "browser", "Browser", ["chrome", "chromium", "edge", "firefox", "brave", "opera", "vivaldi"])
        auth = self.section("Authentication")
        note = QLabel("Site login maps to yt-dlp --username / --password. Support depends on the site; use Cookies for sites requiring a browser session or two-factor login.\nCredentials are kept in memory for this session only. They apply to new analyses and downloads, including batch URLs. Queued jobs keep their original credentials.")
        note.setWordWrap(True)
        auth.addRow(note)
        self.field(auth, "site_login", "Enable site login", bool)
        self.field(auth, "username", "Username / email (--username)", str)
        self.field(auth, "password", "Password (--password)", str)
        self.fields["password"].setEchoMode(QLineEdit.EchoMode.Password)
        show_password = QCheckBox("Show password")
        show_password.toggled.connect(lambda show: self.fields["password"].setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password))
        auth.addRow(show_password)
        def toggle_login(enabled):
            for key in ("username", "password"):
                self.fields[key].setEnabled(enabled)
            show_password.setChecked(False)
            show_password.setEnabled(enabled)
        self.fields["site_login"].toggled.connect(toggle_login)
        toggle_login(self.fields["site_login"].isChecked())
        def clear_login():
            self.fields["site_login"].setChecked(False)
            self.fields["username"].clear()
            self.fields["password"].clear()
            show_password.setChecked(False)
        auth.addRow(button("Clear credentials", clear_login))
        self.field(auth, "use_netrc", "Use netrc file (--netrc)", bool)
        self.field(auth, "netrc_location", "Netrc file (--netrc-location)", "netrc")
        self.fields["netrc_location"].setPlaceholderText("Leave blank for ~/.netrc")
        netrc_note = QLabel("Uses standard machine / login / password entries. Machine names follow yt-dlp extractor names, which may differ from website hostnames. A default entry is used when no machine matches. Only the path and enabled setting are saved; file contents are never copied into settings. The file is read again when a job runs.")
        netrc_note.setWordWrap(True)
        auth.addRow(netrc_note)
        def toggle_netrc(enabled):
            self.fields["netrc_location"].setEnabled(enabled)
            if enabled:
                self.fields["site_login"].setChecked(False)
        self.fields["use_netrc"].toggled.connect(toggle_netrc)
        self.fields["site_login"].toggled.connect(lambda enabled: self.fields["use_netrc"].setChecked(False) if enabled else None)
        toggle_netrc(self.fields["use_netrc"].isChecked())
        aria = self.section("aria2c")
        self.field(aria, "use_aria2c", "Use aria2c external downloader", bool)
        self.field(aria, "aria2c_path", "aria2c executable or folder", "executable")
        for key, label, maximum in [
            ("aria2c_connections", "Connections per server", 16),
            ("aria2c_splits", "Split count", 16),
            ("aria2c_min_split_mib", "Minimum split size (MiB)", 1024),
        ]:
            self.field(aria, key, label, maximum)
        self.field(aria, "aria2c_disable_ipv6", "Disable IPv6 in aria2c", bool)
        self.aria_status = QLabel()
        self.aria_status.setWordWrap(True)
        aria.addRow(self.aria_status)
        aria_help = QLabel("aria2c accelerates direct HTTP/HTTPS/FTP transfers using parallel connections. yt-dlp automatically falls back to its native downloader for unsupported protocols or formats. SOCKS proxies are not supported by aria2c; use HTTP/HTTPS proxy or the native downloader.")
        aria_help.setWordWrap(True)
        aria.addRow(aria_help)
        def update_aria(enabled):
            for key in ("aria2c_path", "aria2c_connections", "aria2c_splits", "aria2c_min_split_mib", "aria2c_disable_ipv6"):
                self.fields[key].setEnabled(enabled)
            self.refresh_aria2c()
        self.fields["use_aria2c"].toggled.connect(update_aria)
        self.fields["aria2c_path"].textChanged.connect(self.refresh_aria2c)
        aria.addRow(button("Refresh detection", self.refresh_aria2c))
        update_aria(self.fields["use_aria2c"].isChecked())
        ffmpeg = self.section("FFmpeg")
        self.field(ffmpeg, "ffmpeg", "FFmpeg folder", "folder")
        self.ff_status = QLabel()
        self.ff_status.setWordWrap(True)
        ffmpeg.addRow(self.ff_status)
        ffmpeg.addRow(button("Refresh detection", self.refresh_ffmpeg))
        self.fields["ffmpeg"].textChanged.connect(self.refresh_ffmpeg)
        self.refresh_ffmpeg()
        advanced = self.section("Advanced")
        self.field(advanced, "extra", "Additional yt-dlp arguments", str)
        help_text = QLabel("Safe allowlist: --retries, --fragment-retries, --socket-timeout, --sleep-interval, --max-sleep-interval, --limit-rate, --prefer-free-formats, --no-mtime. Other arguments are rejected.")
        help_text.setWordWrap(True)
        advanced.addRow(help_text)
        bottom = QHBoxLayout()
        bottom.addWidget(button("Reset Settings", self.reset))
        bottom.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.save)
        box.rejected.connect(self.reject)
        bottom.addWidget(box)
        layout.addLayout(bottom)

    def section(self, name):
        content = QWidget()
        form = QFormLayout(content)
        form.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, name)
        return form

    def field(self, form, key, label, kind):
        value = self.settings[key]
        if kind is bool:
            widget = QCheckBox(label)
            widget.setChecked(value)
            form.addRow(widget)
        elif isinstance(kind, list):
            widget = combo(kind, value)
            form.addRow(label, widget)
        elif isinstance(kind, int):
            widget = QSpinBox()
            widget.setRange(0 if key == "retries" else 1, kind)
            widget.setValue(value)
            form.addRow(label, widget)
        else:
            widget = QLineEdit(str(value))
            if kind in {"folder", "file", "netrc", "executable"}:
                row = QHBoxLayout()
                row.addWidget(widget)
                row.addWidget(button("Browse…", lambda: self.browse(widget, kind)))
                form.addRow(label, row)
            else:
                form.addRow(label, widget)
        self.fields[key] = widget

    def browse(self, field, kind):
        if kind == "folder":
            value = QFileDialog.getExistingDirectory(self, "Choose folder", field.text())
        else:
            title = "Choose aria2c executable" if kind == "executable" else "Choose netrc file" if kind == "netrc" else "Choose cookie file"
            file_filter = "Executables (aria2c.exe aria2c);;All files (*)" if kind == "executable" else "All files (*)" if kind == "netrc" else "Text (*.txt);;All files (*)"
            value = QFileDialog.getOpenFileName(self, title, "", file_filter)[0]
        if value:
            field.setText(value)

    def refresh_ffmpeg(self):
        info = detect(self.fields["ffmpeg"].text())
        lines = [f"Required baseline: FFmpeg {info['minimum_version']}+"]
        for name in ("ffmpeg", "ffprobe"):
            lines.append(f"{name}: {version_status(info, name)}")
            lines.append(f"Path: {info.get(name) or 'Not found'}")
            if info.get(f"{name}_error") and info.get(name):
                lines.append(f"Diagnostic: {info[f'{name}_error']}")
        self.ff_status.setText("\n".join(lines))

    def refresh_aria2c(self):
        info = inspect_aria2c(self.fields["aria2c_path"].text().strip())
        lines = [f"aria2c: {aria2_version_status(info)}", f"Path: {info.get('path') or 'Not found'}"]
        if info.get("error") and info.get("path"):
            lines.append(f"Diagnostic: {info['error']}")
        self.aria_status.setText("\n".join(lines))

    def update_preview(self):
        try:
            self.preview.setText(filename_preview(self.fields["template"].text()))
        except ValueError as error:
            self.preview.setText(str(error))

    def reset(self):
        for key, widget in self.fields.items():
            value = DEFAULTS[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QSpinBox):
                widget.setValue(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            else:
                widget.setCurrentText(value)

    def save(self):
        values = self.settings.values.copy()
        for key, widget in self.fields.items():
            values[key] = widget.isChecked() if isinstance(widget, QCheckBox) else widget.value() if isinstance(widget, QSpinBox) else (widget.text() if key in {"username", "password", "socks_username", "socks_password"} else widget.text().strip()) if isinstance(widget, QLineEdit) else widget.currentText()
        try:
            authentication_options(values)
            proxy_options(values)
            proxy = proxy_options(values).get("proxy")
            aria2_options(values, proxy)
            extra_options(values["extra"])
            filename_preview(values["template"])
            if values["auto_retry"] and values["auto_retry_max_delay"] < values["auto_retry_base_delay"]:
                raise ValueError("Maximum retry delay must be at least the initial retry delay.")
            if not values["output"]:
                raise ValueError("Choose a download folder.")
            previous = self.settings.values
            self.settings.values = values
            try:
                self.settings.save()
            except OSError:
                self.settings.values = previous
                raise
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Settings not saved", str(error))
            return
        logging.getLogger(__name__).info("Settings saved")
        self.accept()


class SupportedSitesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Supported Websites")
        self.resize(850, 600)
        self.rows = []
        self.worker = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search installed extractors — YouTube, Vimeo, SoundCloud…")
        layout.addWidget(self.search)
        self.count = QLabel("Loading extractors…")
        layout.addWidget(self.count)
        self.table = table(["Extractor", "Description", "Status"])
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 390)
        layout.addWidget(self.table)
        self.refresh_button = button("Refresh", self.refresh)
        layout.addWidget(self.refresh_button)
        layout.addWidget(QLabel("Listed support is not a guarantee: site changes, authentication and availability may affect downloads."))
        self.search.textChanged.connect(self.filter)
        self.table.cellDoubleClicked.connect(lambda r, c: details(self, "Extractor details", self.filtered[r]))
        self.refresh()

    def refresh(self):
        if self.worker:
            return
        self.refresh_button.setEnabled(False)
        self.worker = FunctionWorker(supported_sites, self)
        self.worker.result.connect(self.loaded)
        self.worker.failed.connect(lambda error: self.count.setText(error))
        self.worker.finished.connect(self.done_loading)
        self.worker.start()

    def done_loading(self):
        self.worker.deleteLater()
        self.worker = None
        self.refresh_button.setEnabled(True)

    def loaded(self, rows):
        self.rows = rows
        self.filter()

    def filter(self):
        self.filtered = filter_sites(self.rows, self.search.text())
        fill_table(self.table, [[r["name"], r["description"], r["working"]] for r in self.filtered])
        self.count.setText(f"{len(self.filtered):,} shown / {len(self.rows):,} installed extractors")

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.hide()
            self.worker.finished.connect(self.reject)
            return
        super().reject()


def show_about(parent, settings):
    details(parent, "About Simple Video Downloader", {
        "Application": "Simple Video Downloader", "Version": __version__, "Python": sys.version.split()[0],
        "PySide6": qt_version, "yt-dlp": ydl_version, "FFmpeg": detect(settings["ffmpeg"]),
        "OS": platform.platform(), "Description": "Simple Video Downloader is a desktop frontend for yt-dlp designed to simplify downloading media from websites supported by yt-dlp.",
        "Copyright": "© 2026 Your Name", "Disclaimer": "This application is not affiliated with yt-dlp or supported websites. Users are responsible for complying with copyright laws and website terms of service.",
        "Project": "https://github.com/yt-dlp/yt-dlp", "Supported sites": "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"})
