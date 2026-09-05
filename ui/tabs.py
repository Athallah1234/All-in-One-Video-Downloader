import csv,json,os,time,shutil
from datetime import datetime,timedelta
from pathlib import Path
from PySide6.QtCore import Qt,QThreadPool,QTimer,QUrl,Signal
from PySide6.QtGui import QDesktopServices,QPixmap
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest,QNetworkReply
from PySide6.QtWidgets import *
from models.download import DownloadRequest
from services.ffmpeg_service import FFmpegService
from ui.dialogs import BatchUrlDialog,HistoryDetailsDialog,PlaylistDialog
from ui.log_highlighter import LogSyntaxHighlighter
from utils.formatters import format_duration,format_size,format_speed
from utils.validators import is_valid_url,validate_output_template
from utils.queue_eta import estimate_queue_eta
from utils.duplicates import canonicalize_url,find_duplicates,media_identity
from utils.containers import CONTAINER_PRESETS,check_container_compatibility
from utils.formats import AUDIO_CODEC_PRESETS,BIT_DEPTH_PRESETS,CODEC_PRESETS,DYNAMIC_RANGE_PRESETS,FPS_PRESETS,RESOLUTION_PRESETS,available_audio_codec_counts,available_bit_depth_counts,available_codec_counts,available_dynamic_range_counts,available_fps_counts,available_resolution_counts,build_explicit_video_selector,build_video_selector
from workers.tasks import DownloadWorker,MetadataWorker,SizeEstimateWorker

class DownloaderTab(QWidget):
    status=Signal(str); history_changed=Signal(); active_changed=Signal(int)

    def __init__(self,service,repo,settings,logger,parent=None):
        super().__init__(parent); self.service=service; self.repo=repo; self.settings=settings; self.logger=logger; self.pool=QThreadPool.globalInstance(); self.estimate_pool=QThreadPool(self); self.estimate_pool.setMaxThreadCount(3); self.info=None; self.analyzed_url=""; self.playlist_selection=[]; self.workers={}; self.estimators={}; self.queue=[]; self.queue_run_enabled=str(settings.value("downloads/auto_start",True)).lower() in {"true","1","yes"}; self.speed_ema=None; self.postprocess_ema=10.0; self.net=QNetworkAccessManager(self); self.eta_timer=QTimer(self); self.eta_timer.setInterval(1000); self.eta_timer.timeout.connect(self.update_queue_eta); self.eta_timer.start()
        root=QVBoxLayout(self); urlrow=QHBoxLayout(); self.url=QLineEdit(); self.url.setPlaceholderText("Paste a media, playlist, channel, or collection URL…"); self.url.setAcceptDrops(False); paste=QPushButton("Paste"); batch=QPushButton("Batch URLs…"); analyze=QPushButton("Analyze"); analyze.setObjectName("primary"); clear=QPushButton("Clear"); openurl=QPushButton("Open URL"); urlrow.addWidget(self.url,1); [urlrow.addWidget(x) for x in (paste,batch,analyze,clear,openurl)]; root.addLayout(urlrow)
        split=QSplitter(); root.addWidget(split,1); left=QWidget();self.preview_panel=left; ll=QVBoxLayout(left); self.thumb=QLabel("No thumbnail"); self.thumb.setAlignment(Qt.AlignCenter); self.thumb.setMinimumHeight(180); self.thumb.setStyleSheet("border:1px dashed #687083;border-radius:8px"); ll.addWidget(self.thumb); self.title=QLabel("Enter a URL and select Analyze"); self.title.setWordWrap(True); self.title.setStyleSheet("font-size:14pt;font-weight:600"); ll.addWidget(self.title); self.meta=QTextBrowser(); ll.addWidget(self.meta,1); split.addWidget(left)
        right=QWidget(); form=QFormLayout(right); self.kind=QComboBox(); self.kind.addItems(["Video","Audio Only","Video Only","Thumbnail Only","Subtitle Only","Metadata Only"]); form.addRow("Download type",self.kind); self.resolution=QComboBox(); self.resolution.setToolTip("Single video: exact source height. Playlist: best height not exceeding the preset."); form.addRow("Video resolution",self.resolution); self.populate_resolutions([],True); self.codec=QComboBox(); self.codec.setToolTip("Strict source codec preference; unavailable codec/resolution combinations are disabled for analyzed single videos."); form.addRow("Video codec",self.codec); self.populate_codecs([],True); self.fps=QComboBox(); self.fps.setToolTip("Selects an existing source frame-rate family. It does not synthesize or interpolate frames."); form.addRow("Frame rate",self.fps); self.populate_fps([],True); self.bit_depth=QComboBox(); self.bit_depth.setToolTip("Uses explicit/profile-level evidence from the analyzed format. HDR label alone is not treated as proof of 12-bit."); form.addRow("Video bit depth",self.bit_depth); self.populate_bit_depths([],True); self.dynamic_range=QComboBox(); self.dynamic_range.setToolTip("Strict source dynamic range: SDR, HDR10/10+/12, HLG, or Dolby Vision. No tone mapping is performed."); form.addRow("Dynamic range",self.dynamic_range); self.populate_dynamic_ranges([],True); self.audio_codec=QComboBox(); self.audio_codec.setToolTip("Video: strict source audio codec. Audio Only: FFmpeg output codec."); form.addRow("Audio codec",self.audio_codec); self.populate_audio_codecs([],True); self.container=QComboBox(); self.container.setToolTip("Final video container. Specific choices remux with FFmpeg without re-encoding; incompatible known codec/HDR combinations are disabled."); form.addRow("Output container",self.container); self.populate_containers(); self.format=QComboBox(); self.format.addItem("Best video + audio","bestvideo*+bestaudio/best"); self.format.setToolTip("Used only when resolution, frame rate, bit depth, dynamic range, and codecs are Auto. Select a concrete Format ID for advanced control."); form.addRow("Advanced format",self.format); self.audio=QComboBox(); self.audio.addItems(["mp3","m4a","aac","flac","wav","opus","vorbis"]); form.addRow("Audio format",self.audio); self.quality=QComboBox(); self.quality.addItems(["320","256","192","160","128","96","64"]); self.quality.setCurrentText("192"); form.addRow("Audio bitrate",self.quality); self.subtitles=QCheckBox("Download subtitles / automatic captions"); form.addRow(self.subtitles); self.metadata=QCheckBox("Embed metadata"); self.metadata.setChecked(True); form.addRow(self.metadata); self.thumbnail=QCheckBox("Embed/write thumbnail"); form.addRow(self.thumbnail); self.infojson=QCheckBox("Write info JSON"); form.addRow(self.infojson)
        self.audio_cover_format=QComboBox();self.audio_cover_format.addItem("Automatic / source artwork","auto");self.audio_cover_format.addItem("JPEG","jpg");self.audio_cover_format.addItem("PNG","png");self.audio_cover_format.addItem("WebP","webp");form.addRow("Audio cover format",self.audio_cover_format)
        self.audio_keep_cover=QCheckBox("Keep cover image beside the audio file");form.addRow(self.audio_keep_cover)
        self.audio_embed_chapters=QCheckBox("Embed chapters into Audio Only output");self.audio_embed_chapters.setChecked(True);form.addRow(self.audio_embed_chapters)
        self.audio_embed_infojson=QCheckBox("Embed full media info JSON as metadata attachment");self.audio_embed_infojson.setToolTip("Adds the yt-dlp info dictionary to the audio container; this is separate from writing a .info.json sidecar.");form.addRow(self.audio_embed_infojson)
        self.video_poster_format=QComboBox();self.video_poster_format.addItem("Automatic / source artwork","auto");self.video_poster_format.addItem("JPEG","jpg");self.video_poster_format.addItem("PNG","png");self.video_poster_format.addItem("WebP","webp");form.addRow("Video poster format",self.video_poster_format)
        self.video_keep_poster=QCheckBox("Keep poster image beside the video file");form.addRow(self.video_keep_poster)
        self.video_embed_chapters=QCheckBox("Embed chapters into video output");self.video_embed_chapters.setChecked(True);form.addRow(self.video_embed_chapters)
        self.video_embed_infojson=QCheckBox("Embed full media info JSON into video metadata");form.addRow(self.video_embed_infojson)
        self.playlist_button=QPushButton("Choose Playlist Items…"); self.playlist_button.setEnabled(False); self.playlist_label=QLabel("Not a playlist"); playlist_row=QHBoxLayout(); playlist_row.addWidget(self.playlist_button); playlist_row.addWidget(self.playlist_label,1); form.addRow("Playlist",playlist_row)
        folderrow=QHBoxLayout(); self.folder=QLineEdit(self.settings.value("downloads/folder",str(Path.home()/"Downloads"/"Video Downloader"))); browse=QPushButton("Browse"); folderrow.addWidget(self.folder); folderrow.addWidget(browse); form.addRow("Download folder",folderrow); self.template=QComboBox(); self.template.setEditable(True); self.template.addItems(["%(title)s [%(id)s].%(ext)s","%(title)s.%(ext)s","%(uploader)s - %(title)s.%(ext)s","%(playlist)s/%(playlist_index)03d - %(title)s.%(ext)s"]); form.addRow("Filename",self.template); add=QPushButton("Add to Queue"); add.setObjectName("primary"); form.addRow(add); self.settings_scroll=QScrollArea(); self.settings_scroll.setWidgetResizable(True); self.settings_scroll.setFrameShape(QFrame.NoFrame); self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded); self.settings_scroll.setWidget(right); split.addWidget(self.settings_scroll); self.configure_dropdown_scrollbars(); split.setSizes([520,450])
        # Only the dropdown rows scroll. Checkboxes and the remaining actions
        # stay fixed and continuously visible beneath them.
        for checkbox in (self.subtitles,self.metadata,self.thumbnail,self.infojson):form.takeRow(checkbox)
        fixed_start=form.getLayoutPosition(playlist_row)[0]; fixed_rows=[]
        while form.rowCount()>fixed_start:fixed_rows.append(form.takeRow(fixed_start))
        settings_wrapper=QWidget(); settings_layout=QVBoxLayout(settings_wrapper); settings_layout.setContentsMargins(0,0,0,0); fixed_panel=QWidget(); fixed_form=QFormLayout(fixed_panel); fixed_form.setContentsMargins(9,0,9,0)
        for checkbox in (self.subtitles,self.metadata,self.thumbnail,self.infojson):fixed_form.addRow(checkbox)
        for row in fixed_rows:
            label=row.labelItem.widget() if row.labelItem else None; field=row.fieldItem.widget() or row.fieldItem.layout()
            if label:fixed_form.addRow(label,field)
            else:fixed_form.addRow(field)
        self.settings_scroll.setParent(settings_wrapper); settings_layout.addWidget(self.settings_scroll,1); settings_layout.addWidget(fixed_panel); split.addWidget(settings_wrapper)
        queuebar=QHBoxLayout(); queuebar.addWidget(QLabel("<b>Download Queue</b>")); self.queue_total_label=QLabel("Total estimate: —"); self.queue_eta_label=QLabel("Queue ETA: —"); startall=QPushButton("Start All"); cancelall=QPushButton("Cancel All"); clearcompleted=QPushButton("Clear Completed"); queuebar.addWidget(self.queue_total_label); queuebar.addWidget(self.queue_eta_label); queuebar.addStretch(); [queuebar.addWidget(x) for x in (startall,cancelall,clearcompleted)]; root.addLayout(queuebar)
        self.table=QTableWidget(0,10); self.table.setHorizontalHeaderLabels(["Title","Source","Format","Status","Progress","Speed / ETA","Estimated Size","Integrity","Output","Controls"]); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.table.horizontalHeader().setSectionResizeMode(9,QHeaderView.ResizeToContents); self.table.setContextMenuPolicy(Qt.CustomContextMenu); root.addWidget(self.table)
        paste.clicked.connect(self.paste); batch.clicked.connect(self.open_batch); analyze.clicked.connect(self.analyze); clear.clicked.connect(lambda:self.url.clear()); openurl.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(self.url.text()))); browse.clicked.connect(self.browse); self.playlist_button.clicked.connect(self.choose_playlist_items); self.kind.currentTextChanged.connect(self.refresh_media_controls); self.kind.currentTextChanged.connect(self.refresh_audio_embedding_controls);self.kind.currentTextChanged.connect(self.refresh_video_embedding_controls); self.resolution.currentIndexChanged.connect(self.refresh_codec_availability); self.codec.currentIndexChanged.connect(self.refresh_fps_availability); self.codec.currentIndexChanged.connect(self.refresh_container_compatibility); self.fps.currentIndexChanged.connect(self.refresh_bit_depth_availability); self.bit_depth.currentIndexChanged.connect(self.refresh_dynamic_range_availability); self.dynamic_range.currentIndexChanged.connect(self.refresh_container_compatibility); self.audio_codec.currentIndexChanged.connect(self.sync_audio_output); self.audio_codec.currentIndexChanged.connect(self.refresh_container_compatibility);self.audio.currentTextChanged.connect(self.refresh_audio_embedding_controls);self.container.currentIndexChanged.connect(self.refresh_video_embedding_controls);self.thumbnail.toggled.connect(self.refresh_audio_embedding_controls);self.thumbnail.toggled.connect(self.refresh_video_embedding_controls);self.metadata.toggled.connect(self.refresh_audio_embedding_controls);self.metadata.toggled.connect(self.refresh_video_embedding_controls); add.clicked.connect(self.add_queue); startall.clicked.connect(self.start_all); cancelall.clicked.connect(self.cancel_all); clearcompleted.clicked.connect(self.clear_completed); self.table.customContextMenuRequested.connect(self.queue_menu); self.url.returnPressed.connect(self.analyze);self.apply_saved_defaults();self.refresh_audio_embedding_controls();self.refresh_video_embedding_controls()
        if str(self.settings.value("general/clipboard_url",True)).lower() in {"true","1","yes"}:
            clipboard=QApplication.clipboard().text().strip()
            if is_valid_url(clipboard):
                self.url.setText(clipboard)
                if str(self.settings.value("general/auto_analyze_clipboard",False)).lower() in {"true","1","yes"}:QTimer.singleShot(0,self.analyze)
    def apply_saved_defaults(self):
        self.queue_run_enabled=str(self.settings.value("downloads/auto_start",True)).lower() in {"true","1","yes"};self.folder.setText(str(self.settings.value("downloads/folder",self.folder.text()) or self.folder.text()));template=str(self.settings.value("downloads/template",self.template.currentText()) or self.template.currentText());self.template.setCurrentText(template);self.kind.setCurrentText(str(self.settings.value("general/default_download_type","Video")))
        self.audio.setCurrentText(str(self.settings.value("audio/format","mp3")));self.quality.setCurrentText(str(self.settings.value("audio/quality","192")));metadata_key="audio/embed_metadata" if self.kind.currentText()=="Audio Only" else "video/embed_metadata";self.metadata.setChecked(str(self.settings.value(metadata_key,self.settings.value("advanced/embed_metadata",True))).lower() in {"true","1","yes"});self.infojson.setChecked(str(self.settings.value("advanced/write_info_json",False)).lower() in {"true","1","yes"});self.subtitles.setChecked(str(self.settings.value("subtitles/default_enabled",False)).lower() in {"true","1","yes"});thumb_key="audio/embed_thumbnail" if self.kind.currentText()=="Audio Only" else "video/embed_thumbnail";self.thumbnail.setChecked(str(self.settings.value(thumb_key,False)).lower() in {"true","1","yes"});cover=str(self.settings.value("audio/thumbnail_format","auto"));index=self.audio_cover_format.findData(cover);self.audio_cover_format.setCurrentIndex(index if index>=0 else 0);self.audio_keep_cover.setChecked(str(self.settings.value("audio/keep_thumbnail",False)).lower() in {"true","1","yes"});self.audio_embed_chapters.setChecked(str(self.settings.value("audio/embed_chapters",True)).lower() in {"true","1","yes"});self.audio_embed_infojson.setChecked(str(self.settings.value("audio/embed_infojson",False)).lower() in {"true","1","yes"});poster=str(self.settings.value("video/thumbnail_format","auto"));index=self.video_poster_format.findData(poster);self.video_poster_format.setCurrentIndex(index if index>=0 else 0);self.video_keep_poster.setChecked(str(self.settings.value("video/keep_thumbnail",False)).lower() in {"true","1","yes"});self.video_embed_chapters.setChecked(str(self.settings.value("video/embed_chapters",True)).lower() in {"true","1","yes"});self.video_embed_infojson.setChecked(str(self.settings.value("video/embed_infojson",False)).lower() in {"true","1","yes"})
        maps=((self.resolution,"video/resolution",{"144p":144,"240p":240,"360p":360,"480p":480,"720p":720,"1080p":1080,"1440p":1440,"2160p / 4K":2160,"4320p / 8K":4320}),(self.codec,"video/codec",{"H.264":"h264","H.265 / HEVC":"h265","VP9":"vp9","AV1":"av1"}),(self.fps,"video/fps",{str(value):value for value in (24,25,30,48,50,60,100,120,144,240)}),(self.bit_depth,"video/bit_depth",{"8-bit":8,"10-bit":10,"12-bit":12}),(self.dynamic_range,"video/dynamic_range",{"SDR":"SDR","HDR":"HDR","HDR10":"HDR10","HDR10+":"HDR10+","HDR12":"HDR12","HLG":"HLG","Dolby Vision":"DV"}),(self.audio_codec,"audio/codec",{"AAC":"aac","Opus":"opus","Vorbis":"vorbis","MP3":"mp3","FLAC":"flac"}))
        for widget,key,mapping in maps:
            value=mapping.get(str(self.settings.value(key,"Auto")));index=widget.findData(value)
            if index>=0 and widget.model().item(index).isEnabled():widget.setCurrentIndex(index)
        preferred=self.settings.value("video/container","auto");index=self.container.findData(None if preferred=="auto" else preferred)
        if index>=0 and self.container.model().item(index).isEnabled():self.container.setCurrentIndex(index)
    def configure_dropdown_scrollbars(self):
        # Dropdown popups use the platform's standard behaviour.
        pass

    def paste(self): self.url.setText(QApplication.clipboard().text().strip())
    def open_batch(self):
        dialog=BatchUrlDialog(self.service,self)
        clipboard=QApplication.clipboard().text().strip()
        if "\n" in clipboard: dialog.input.setPlainText(clipboard)
        if dialog.exec()!=QDialog.Accepted:return
        results=dialog.results(); added=0
        for result in results:added+=bool(self.enqueue_request(result["url"],result["info"],result["playlist_items"],start=False))
        self.render_queue(); self.start_available(); self.status.emit(f"Added {added} of {len(results)} analyzed batch URL(s) to queue")
    def analyze(self):
        url=self.url.text().strip()
        if not is_valid_url(url): QMessageBox.warning(self,"Invalid URL","Enter a valid HTTP or HTTPS URL."); return
        self.info=None; self.analyzed_url=url; self.playlist_selection=[]; self.playlist_button.setEnabled(False); self.playlist_label.setText("Analyzing…")
        self.status.emit("Analyzing…"); self.title.setText("Analyzing…"); worker=MetadataWorker(self.service,url); worker.signals.metadata.connect(self.show_info); worker.signals.failed.connect(self.fail_analysis); self.pool.start(worker)
    def fail_analysis(self,error): self.status.emit("Analysis failed"); self.title.setText("Unable to analyze URL"); QMessageBox.warning(self,"Analysis failed",self.friendly_error(error)); self.logger.error(error)
    def friendly_error(self,e):
        low=e.lower()
        if "drm" in low:return "This content appears to be DRM-protected and cannot be downloaded by this application."
        if "unsupported url" in low:return "This URL is not supported by the installed yt-dlp version."
        if "sign in" in low or "login" in low:return "Authentication is required for this media. Configure cookies in Settings."
        if "geo" in low:return "This media appears to be restricted in your region."
        if "private" in low:return "This media is private or unavailable."
        return e[:700]
    def show_info(self,info):
        self.info=info; entries=info.get("entries"); count=len(entries) if isinstance(entries,list) else info.get("playlist_count")
        is_playlist=isinstance(entries,list) and bool(entries)
        self.playlist_button.setEnabled(is_playlist)
        self.playlist_label.setText(f"{count} items · selection required" if is_playlist else "Not a playlist")
        self.title.setText(info.get("title") or "Untitled media"); fields=[("Uploader",info.get("uploader") or info.get("channel")),("Extractor",info.get("extractor_key") or info.get("extractor")),("Duration",format_duration(info.get("duration"))),("Views",info.get("view_count")),("Upload date",info.get("upload_date")),("Media ID",info.get("id")),("Playlist items",count),("Availability",info.get("availability"))]; self.meta.setPlainText("\n".join(f"{k}: {v if v is not None else '—'}" for k,v in fields)+"\n\n"+(info.get("description") or ""))
        self.current_formats=info.get("formats") or []; self.current_is_playlist=is_playlist; self.populate_formats(self.current_formats); self.populate_resolutions(self.current_formats,is_playlist); self.populate_codecs(self.current_formats,is_playlist); self.populate_fps(self.current_formats,is_playlist); self.populate_bit_depths(self.current_formats,is_playlist); self.populate_dynamic_ranges(self.current_formats,is_playlist); self.populate_audio_codecs(self.current_formats,is_playlist);self.apply_saved_defaults(); thumb=info.get("thumbnail");
        if thumb:
            reply=self.net.get(QNetworkRequest(QUrl(thumb))); reply.finished.connect(lambda r=reply:self.thumb_ready(r))
        self.status.emit("Analysis completed")
    def choose_playlist_items(self):
        entries=(self.info or {}).get("entries")
        if not isinstance(entries,list) or not entries:return False
        dialog=PlaylistDialog(self.info,self.playlist_selection,self)
        if dialog.exec()!=QDialog.Accepted:return False
        self.playlist_selection=dialog.selection(); total=len(entries)
        self.playlist_label.setText(f"{len(self.playlist_selection)} of {total} selected")
        if "%(playlist" not in self.template.currentText(): self.template.setCurrentText("%(playlist)s/%(playlist_index)03d - %(title)s.%(ext)s")
        return True
    def thumb_ready(self,reply):
        if reply.error()==QNetworkReply.NoError:
            pix=QPixmap(); pix.loadFromData(reply.readAll()); self.thumb.setPixmap(pix.scaled(self.thumb.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation))
        reply.deleteLater()
    def populate_formats(self,formats):
        self.format.clear(); self.format.addItem("Best video + audio","bestvideo*+bestaudio/best"); self.format.addItem("Best available","best"); self.format.addItem("Worst","worst")
        for f in formats:
            fid=str(f.get("format_id") or ""); ext=f.get("ext") or "?"; res=f.get("resolution") or (f"{f.get('height')}p" if f.get("height") else "audio"); note=f.get("format_note") or ""; size=format_size(f.get("filesize") or f.get("filesize_approx")); self.format.addItem(f"{fid} · {ext} · {res} · {note} · {size}",fid)
    def populate_resolutions(self,formats,is_playlist):
        previous=self.resolution.currentData() if self.resolution.count() else None; counts=available_resolution_counts(formats); self.resolution.clear()
        for label,height in RESOLUTION_PRESETS:
            count=counts.get(height,0) if height else 0; text=label if height is None or is_playlist else (f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable"); self.resolution.addItem(text,height); item=self.resolution.model().item(self.resolution.count()-1); item.setEnabled(height is None or is_playlist or count>0)
        target=self.resolution.findData(previous); self.resolution.setCurrentIndex(target if target>=0 and self.resolution.model().item(target).isEnabled() else 0); self.update_video_controls()
    def populate_codecs(self,formats,is_playlist):
        previous=self.codec.currentData() if self.codec.count() else None; height=self.resolution.currentData(); counts=available_codec_counts(formats,height); self.codec.blockSignals(True); self.codec.clear()
        for label,codec in CODEC_PRESETS:
            count=counts.get(codec,0) if codec else 0; text=label if codec is None or is_playlist else (f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable"); self.codec.addItem(text,codec); self.codec.model().item(self.codec.count()-1).setEnabled(codec is None or is_playlist or count>0)
        target=self.codec.findData(previous); self.codec.setCurrentIndex(target if target>=0 and self.codec.model().item(target).isEnabled() else 0); self.codec.blockSignals(False); self.update_video_controls()
    def refresh_codec_availability(self):self.populate_codecs(getattr(self,"current_formats",[]),getattr(self,"current_is_playlist",True));self.refresh_fps_availability()
    def populate_fps(self,formats,is_playlist):
        previous=self.fps.currentData() if self.fps.count() else None;height=self.resolution.currentData();codec=self.codec.currentData();counts=available_fps_counts(formats,height,codec);self.fps.blockSignals(True);self.fps.clear()
        for label,target in FPS_PRESETS:
            count=counts.get(target,0) if target else 0;text=label if target is None or is_playlist else (f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable");self.fps.addItem(text,target);self.fps.model().item(self.fps.count()-1).setEnabled(target is None or is_playlist or count>0)
        selected=self.fps.findData(previous);self.fps.setCurrentIndex(selected if selected>=0 and self.fps.model().item(selected).isEnabled() else 0);self.fps.blockSignals(False);self.update_video_controls()
    def refresh_fps_availability(self):
        if hasattr(self,"fps"):self.populate_fps(getattr(self,"current_formats",[]),getattr(self,"current_is_playlist",True));self.refresh_bit_depth_availability()
    def populate_bit_depths(self,formats,is_playlist):
        previous=self.bit_depth.currentData() if self.bit_depth.count() else None;height=self.resolution.currentData();codec=self.codec.currentData();fps=self.fps.currentData();counts=available_bit_depth_counts(formats,height,codec,fps);self.bit_depth.blockSignals(True);self.bit_depth.clear()
        for label,depth in BIT_DEPTH_PRESETS:
            count=counts.get(depth,0) if depth else 0;text=label if depth is None else (f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable");self.bit_depth.addItem(text,depth);self.bit_depth.model().item(self.bit_depth.count()-1).setEnabled(depth is None or (not is_playlist and count>0))
        selected=self.bit_depth.findData(previous);self.bit_depth.setCurrentIndex(selected if selected>=0 and self.bit_depth.model().item(selected).isEnabled() else 0);self.bit_depth.blockSignals(False);self.update_video_controls()
    def refresh_bit_depth_availability(self):
        if hasattr(self,"bit_depth"):self.populate_bit_depths(getattr(self,"current_formats",[]),getattr(self,"current_is_playlist",True));self.refresh_dynamic_range_availability()
    def populate_dynamic_ranges(self,formats,is_playlist):
        previous=self.dynamic_range.currentData() if self.dynamic_range.count() else None;height=self.resolution.currentData();codec=self.codec.currentData();fps=self.fps.currentData();depth=self.bit_depth.currentData();counts=available_dynamic_range_counts(formats,height,codec,fps,depth);self.dynamic_range.blockSignals(True);self.dynamic_range.clear()
        for label,dynamic in DYNAMIC_RANGE_PRESETS:
            count=counts.get(dynamic,0) if dynamic else 0;text=label if dynamic is None or is_playlist else (f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable");self.dynamic_range.addItem(text,dynamic);self.dynamic_range.model().item(self.dynamic_range.count()-1).setEnabled(dynamic is None or is_playlist or count>0)
        selected=self.dynamic_range.findData(previous);self.dynamic_range.setCurrentIndex(selected if selected>=0 and self.dynamic_range.model().item(selected).isEnabled() else 0);self.dynamic_range.blockSignals(False);self.update_video_controls()
    def refresh_dynamic_range_availability(self):
        if hasattr(self,"dynamic_range"):self.populate_dynamic_ranges(getattr(self,"current_formats",[]),getattr(self,"current_is_playlist",True))
    def populate_audio_codecs(self,formats,is_playlist):
        previous=self.audio_codec.currentData() if self.audio_codec.count() else None; counts=available_audio_codec_counts(formats); audio_only=self.kind.currentText()=="Audio Only"; conversion_available=FFmpegService.available(); self.audio_codec.blockSignals(True); self.audio_codec.clear()
        for label,codec in AUDIO_CODEC_PRESETS:
            count=counts.get(codec,0) if codec else 0
            if codec is None:text=label;enabled=True
            elif audio_only:text=f"{label} (FFmpeg output)";enabled=conversion_available
            elif is_playlist:text=label;enabled=True
            else:text=f"{label} ({count} format{'s' if count!=1 else ''})" if count else f"{label} — unavailable";enabled=count>0
            self.audio_codec.addItem(text,codec);self.audio_codec.model().item(self.audio_codec.count()-1).setEnabled(enabled)
        target=self.audio_codec.findData(previous);self.audio_codec.setCurrentIndex(target if target>=0 and self.audio_codec.model().item(target).isEnabled() else 0);self.audio_codec.blockSignals(False);self.update_video_controls()
    def refresh_media_controls(self):self.populate_audio_codecs(getattr(self,"current_formats",[]),getattr(self,"current_is_playlist",True));self.update_video_controls();self.sync_audio_output()
    def sync_audio_output(self):
        codec=self.audio_codec.currentData()
        if self.kind.currentText()=="Audio Only" and codec:self.audio.setCurrentText(codec)
    def refresh_audio_embedding_controls(self):
        audio_only=self.kind.currentText()=="Audio Only";format_supports_cover=self.audio.currentText() in {"mp3","m4a","flac","opus"};ffmpeg=FFmpegService.available()
        self.metadata.setText("Embed audio tags / metadata" if audio_only else "Embed metadata");self.thumbnail.setText("Embed thumbnail as audio cover art" if audio_only else "Embed/write thumbnail")
        if audio_only and (not format_supports_cover or not ffmpeg) and self.thumbnail.isChecked():self.thumbnail.blockSignals(True);self.thumbnail.setChecked(False);self.thumbnail.blockSignals(False)
        self.thumbnail.setEnabled(not audio_only or (ffmpeg and format_supports_cover));self.metadata.setEnabled(not audio_only or ffmpeg)
        self.thumbnail.setToolTip("Cover embedding supports MP3, M4A, FLAC, and Opus outputs." if audio_only and not format_supports_cover else ("FFmpeg and FFprobe are required." if audio_only and not ffmpeg else ""))
        self.audio_cover_format.setEnabled(audio_only and (self.thumbnail.isChecked() or self.audio_keep_cover.isChecked()));self.audio_keep_cover.setEnabled(audio_only);self.audio_embed_chapters.setEnabled(audio_only and ffmpeg);self.audio_embed_infojson.setEnabled(audio_only and self.metadata.isChecked() and ffmpeg)
    def refresh_video_embedding_controls(self):
        video=self.kind.currentText() in {"Video","Video Only"};container=self.container.currentData();supported=container not in {"webm","avi"};ffmpeg=FFmpegService.available()
        if video and (not supported or not ffmpeg) and self.thumbnail.isChecked():self.thumbnail.blockSignals(True);self.thumbnail.setChecked(False);self.thumbnail.blockSignals(False)
        if video:self.thumbnail.setEnabled(ffmpeg and supported);self.metadata.setEnabled(ffmpeg)
        self.video_poster_format.setEnabled(video and (self.thumbnail.isChecked() or self.video_keep_poster.isChecked()));self.video_keep_poster.setEnabled(video);self.video_embed_chapters.setEnabled(video and ffmpeg);self.video_embed_infojson.setEnabled(video and self.metadata.isChecked() and ffmpeg)
        if video:self.thumbnail.setToolTip("WebM and AVI do not support embedded cover art in yt-dlp." if not supported else ("FFmpeg and FFprobe are required." if not ffmpeg else ""))
    def populate_containers(self):
        if not hasattr(self,"container"):return
        previous=self.container.currentData() if self.container.count() else self.settings.value("video/container","auto")
        previous=None if previous=="auto" else previous
        video=self.kind.currentText() in {"Video","Video Only"}; ffmpeg=FFmpegService.available()
        vcodec=self.codec.currentData() if hasattr(self,"codec") else None; acodec=self.audio_codec.currentData() if hasattr(self,"audio_codec") and self.kind.currentText()=="Video" else None; dynamic=self.dynamic_range.currentData() if hasattr(self,"dynamic_range") else None
        self.container.blockSignals(True);self.container.clear()
        for label,value in CONTAINER_PRESETS:
            result=check_container_compatibility(value,vcodec,acodec,dynamic,self.kind.currentText()=="Video Only")
            enabled=value is None or (video and ffmpeg and result.compatible)
            suffix="" if enabled or value is None else (" — FFmpeg required" if not ffmpeg else " — incompatible")
            self.container.addItem(label+suffix,value);item=self.container.model().item(self.container.count()-1);item.setEnabled(enabled);item.setToolTip(result.reason or ("FFmpeg is required to force a final container" if value and not ffmpeg else ""))
        target=self.container.findData(previous);self.container.setCurrentIndex(target if target>=0 and self.container.model().item(target).isEnabled() else 0);self.container.blockSignals(False);self.container.setEnabled(video)
    def refresh_container_compatibility(self):self.populate_containers()
    def update_video_controls(self):
        enabled=self.kind.currentText() in {"Video","Video Only"}; self.resolution.setEnabled(enabled)
        if hasattr(self,"codec"):self.codec.setEnabled(enabled)
        if hasattr(self,"fps"):self.fps.setEnabled(enabled)
        if hasattr(self,"bit_depth"):self.bit_depth.setEnabled(enabled and not getattr(self,"current_is_playlist",False))
        if hasattr(self,"dynamic_range"):self.dynamic_range.setEnabled(enabled)
        if hasattr(self,"audio_codec"):self.audio_codec.setEnabled(self.kind.currentText() in {"Video","Audio Only"})
        if hasattr(self,"container"):self.populate_containers()
        if hasattr(self,"audio"):self.audio.setEnabled(self.kind.currentText()=="Audio Only")
    def selected_format_selector(self,info,playlist_items):
        height=self.resolution.currentData(); codec=self.codec.currentData();fps=self.fps.currentData();depth=self.bit_depth.currentData();dynamic=self.dynamic_range.currentData();audio_codec=self.audio_codec.currentData() if self.kind.currentText()=="Video" else None
        if (depth is not None or dynamic is not None) and not isinstance((info or {}).get("entries"),list):return build_explicit_video_selector((info or {}).get("formats") or [],int(height) if height is not None else None,codec,int(fps) if fps is not None else None,int(depth) if depth is not None else None,dynamic,audio_codec,self.kind.currentText()=="Video Only")
        if height is None and codec is None and audio_codec is None and fps is None and dynamic is None:return self.format.currentData() or "bestvideo*+bestaudio/best"
        is_playlist=bool(playlist_items) or isinstance((info or {}).get("entries"),list)
        return build_video_selector(int(height) if height is not None else None,codec,audio_codec,self.kind.currentText()=="Video Only",is_playlist,int(fps) if fps is not None else None,dynamic)
    def browse(self):
        p=QFileDialog.getExistingDirectory(self,"Download folder",self.folder.text())
        if p:self.folder.setText(p)
    def add_queue(self):
        if not self.info: QMessageBox.information(self,"Analyze first","Analyze a URL before adding it to the queue."); return
        entries=self.info.get("entries")
        if isinstance(entries,list) and entries and not self.playlist_selection:
            if not self.choose_playlist_items(): return
        if not self.enqueue_request(self.analyzed_url,self.info,self.playlist_selection):return
    def enqueue_request(self,url,info,playlist_items,start=True):
        playlist_items=list(playlist_items)
        duplicate=find_duplicates(self.queue,url,info,playlist_items)
        if duplicate.matching_rows:
            decision=self.resolve_duplicate(duplicate,url,playlist_items)
            if decision is None:return False
            playlist_items=decision
        template=self.template.currentText()
        if playlist_items and "%(playlist" not in template:template="%(playlist)s/%(playlist_index)03d - %(title)s.%(ext)s"
        if not validate_output_template(template): QMessageBox.warning(self,"Invalid template","Filename template must contain a yt-dlp placeholder such as %(title)s."); return False
        title=info.get("title") or "Untitled"
        if playlist_items:title=f"{title} ({len(playlist_items)} selected items)"
        selector=self.selected_format_selector(info,playlist_items)
        if not selector:QMessageBox.warning(self,"Unavailable format combination","No source format matches the selected resolution, video codec, frame rate, bit depth, and dynamic range.");return False
        if self.kind.currentText()=="Audio Only" and not FFmpegService.available():QMessageBox.warning(self,"FFmpeg required","Audio conversion and metadata/cover embedding require FFmpeg and FFprobe.");return False
        if self.kind.currentText() in {"Video","Video Only"} and (self.thumbnail.isChecked() or self.metadata.isChecked() or self.video_embed_chapters.isChecked() or self.video_embed_infojson.isChecked()) and not FFmpegService.available():QMessageBox.warning(self,"FFmpeg required","Video metadata, chapters, info JSON, and poster embedding require FFmpeg and FFprobe.");return False
        quality_label=(self.resolution.currentText().split(" (")[0].replace(" — unavailable","") if self.resolution.currentData() is not None else "Advanced / Best") if self.kind.currentText() in {"Video","Video Only"} else self.kind.currentText(); codec_label=self.codec.currentText().split(" (")[0].replace(" — unavailable","") if self.kind.currentText() in {"Video","Video Only"} else "N/A"; fps_label=self.fps.currentText().split(" (")[0].replace(" — unavailable","") if self.kind.currentText() in {"Video","Video Only"} else "N/A";depth_label=self.bit_depth.currentText().split(" (")[0].replace(" — unavailable","") if self.kind.currentText() in {"Video","Video Only"} else "N/A";dynamic_label=self.dynamic_range.currentText().split(" (")[0].replace(" — unavailable","") if self.kind.currentText() in {"Video","Video Only"} else "N/A";audio_codec=self.audio_codec.currentData() or "auto";audio_codec_label=self.audio_codec.currentText().split(" (")[0].replace(" — unavailable","")
        output_container=self.container.currentData() if self.kind.currentText() in {"Video","Video Only"} else None;compatibility=check_container_compatibility(output_container,self.codec.currentData(),self.audio_codec.currentData() if self.kind.currentText()=="Video" else None,self.dynamic_range.currentData(),self.kind.currentText()=="Video Only")
        if output_container and not FFmpegService.available():QMessageBox.warning(self,"FFmpeg required","FFmpeg is required to force or remux the output container.");return False
        if not compatibility.compatible:QMessageBox.warning(self,"Incompatible container",compatibility.reason);return False
        container_label=self.container.currentText().split(" —")[0]
        sample_rate=str(self.settings.value("audio/sample_rate","Source"));channels=str(self.settings.value("audio/channels","Source"));req=DownloadRequest(url=url,title=title,folder=self.folder.text(),format_selector=selector,download_type=self.kind.currentText(),output_template=template,audio_format=self.audio.currentText(),audio_quality=self.quality.currentText(),audio_sample_rate=0 if sample_rate=="Source" else int(sample_rate),audio_channels=0 if channels=="Source" else int(channels),audio_thumbnail_format=self.audio_cover_format.currentData(),audio_keep_thumbnail=self.audio_keep_cover.isChecked(),audio_embed_chapters=self.audio_embed_chapters.isChecked(),audio_embed_infojson=self.audio_embed_infojson.isChecked(),video_thumbnail_format=self.video_poster_format.currentData(),video_keep_thumbnail=self.video_keep_poster.isChecked(),video_embed_chapters=self.video_embed_chapters.isChecked(),video_embed_infojson=self.video_embed_infojson.isChecked(),subtitles=self.subtitles.isChecked(),embed_metadata=self.metadata.isChecked(),embed_thumbnail=self.thumbnail.isChecked(),write_info_json=self.infojson.isChecked(),playlist_items=list(playlist_items),video_quality=quality_label,video_codec=codec_label,audio_codec=audio_codec,audio_codec_label=audio_codec_label,video_fps=fps_label,video_bit_depth=depth_label,dynamic_range=dynamic_label,output_container=output_container or "auto",output_container_label=container_label)
        try:Path(req.folder).mkdir(parents=True,exist_ok=True)
        except OSError as exc:QMessageBox.warning(self,"Invalid download folder",str(exc));return False
        item={"request":req,"status":"Estimating size…","progress":0,"output":"","estimated_size":"Calculating…","integrity_label":"Pending","canonical_url":canonicalize_url(url),"media_identity":media_identity(info)}; self.queue.append(item); self.start_estimate(item)
        if start:self.render_queue();self.start_available()
        return True
    def resolve_duplicate(self,report,url,playlist_items):
        rows=", ".join(str(row+1) for row in report.matching_rows); dialog=QMessageBox(self); dialog.setIcon(QMessageBox.Warning); dialog.setWindowTitle("Duplicate URL detected")
        if playlist_items and report.new_items and not report.overlapping_items:
            dialog.setText(f"The same playlist URL exists in queue row(s) {rows}, but the selected videos do not overlap."); dialog.setInformativeText(f"All {len(report.new_items)} selected item(s) are new.")
            add=dialog.addButton("Add Disjoint Selection",QMessageBox.AcceptRole); cancel=dialog.addButton(QMessageBox.Cancel); dialog.setDefaultButton(add); dialog.exec()
            return list(report.new_items) if dialog.clickedButton()==add else None
        if playlist_items and report.overlapping_items and report.new_items:
            dialog.setText(f"This playlist overlaps queue row(s) {rows}."); dialog.setInformativeText(f"{len(report.overlapping_items)} selected item(s) are already queued; {len(report.new_items)} item(s) are new.")
            new_only=dialog.addButton("Add New Items Only",QMessageBox.AcceptRole); anyway=dialog.addButton("Add Anyway",QMessageBox.DestructiveRole); cancel=dialog.addButton(QMessageBox.Cancel); dialog.setDefaultButton(new_only); dialog.exec()
            if dialog.clickedButton()==new_only:return list(report.new_items)
            if dialog.clickedButton()==anyway:return list(playlist_items)
            return None
        existing=self.queue[report.matching_rows[0]]; dialog.setText("This URL or media is already present in the download queue."); dialog.setInformativeText(f"Existing row: {report.matching_rows[0]+1}\nTitle: {existing['request'].title}\nStatus: {existing['status']}")
        focus=dialog.addButton("Show Existing",QMessageBox.AcceptRole); anyway=dialog.addButton("Add Anyway",QMessageBox.DestructiveRole); cancel=dialog.addButton("Skip",QMessageBox.RejectRole); dialog.setDefaultButton(cancel); dialog.exec()
        if dialog.clickedButton()==focus:self.table.selectRow(report.matching_rows[0]);self.table.scrollToItem(self.table.item(report.matching_rows[0],0));return None
        if dialog.clickedButton()==anyway:return list(playlist_items)
        return None
    def render_queue(self):
        self.table.setRowCount(len(self.queue))
        for row,item in enumerate(self.queue):
            req=item["request"]; format_display=req.video_quality if req.video_quality!="Advanced / Best" else req.format_selector; format_display+=f" · {req.video_codec}" if req.video_codec not in {"Auto / Any codec","N/A"} else ""; format_display+=f" · {req.video_fps}" if req.video_fps not in {"Auto / Any FPS","N/A"} else ""; format_display+=f" · {req.video_bit_depth}" if req.video_bit_depth not in {"Auto / Any bit depth","N/A"} else ""; format_display+=f" · {req.dynamic_range}" if req.dynamic_range not in {"Auto / Any dynamic range","N/A"} else ""; format_display+=f" · {req.audio_codec_label}" if req.audio_codec_label!="Auto / Best audio" and req.download_type in {"Video","Audio Only"} else ""; format_display+=f" · {req.output_container_label}" if req.output_container!="auto" else ""; values=[req.title,req.url,format_display,item["status"],f"{item['progress']:.1f}%",item.get("speed",""),item.get("estimated_size","Unknown"),item.get("integrity_label","Pending"),item.get("output","")]
            for col,val in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(str(val)))
            if item.get("estimate_error"):self.table.item(row,6).setToolTip(f"Estimation unavailable: {item['estimate_error']}")
            elif item.get("estimate"):self.table.item(row,6).setToolTip(f"Confidence: {item['estimate'].get('confidence','unknown')} · known components/items: {item['estimate'].get('known_items',0)}/{item['estimate'].get('total_items',0)}")
            if item.get("integrity_error"):self.table.item(row,7).setToolTip(item["integrity_error"])
            controls=QWidget(); buttons=QHBoxLayout(controls); buttons.setContentsMargins(2,2,2,2); pause=QPushButton("Resume" if item["status"] in ("Paused","Pausing…") else "Pause"); cancel=QPushButton("Cancel"); pause.setToolTip("Cooperatively pause this download at the next yt-dlp progress boundary"); cancel.setToolTip("Cancel this download and keep resumable partial data")
            active=req.id in self.workers; pause.setEnabled(active and (item["status"].startswith("Downloading") or item["status"] in ("Paused","Pausing…"))); cancel.setEnabled(active); pause.clicked.connect(lambda _checked=False,i=item:self.toggle_pause(i)); cancel.clicked.connect(lambda _checked=False,i=item:self.cancel_item(i)); buttons.addWidget(pause); buttons.addWidget(cancel); self.table.setCellWidget(row,9,controls)
        known=[item.get("estimate") for item in self.queue if (item.get("estimate") or {}).get("bytes") is not None]; unknown=sum((item.get("estimate") or {}).get("bytes") is None for item in self.queue); total=sum(result["bytes"] for result in known); exact=bool(known) and not unknown and all(result.get("confidence")=="exact" for result in known); prefix="" if exact else "~"; suffix=f" + {unknown} unknown" if unknown else ""; self.queue_total_label.setText(f"Total estimate: {prefix}{format_size(total)}{suffix}" if known else f"Total estimate: —{suffix}")
        self.update_queue_eta()
    def update_queue_eta(self):
        result=estimate_queue_eta(self.queue,int(self.settings.value("downloads/concurrent",2)),self.speed_ema,self.postprocess_ema,time.monotonic())
        if result.paused_items:
            text=f"Queue ETA: paused ({result.paused_items})"; tooltip="Resume all paused downloads before a total completion time can be calculated."
        elif result.seconds is None:
            text="Queue ETA: waiting for speed" if result.waiting_for_speed else "Queue ETA: —"; tooltip="A transfer speed sample and known media size are required."
        elif not any(item.get("status") not in {"Completed","Failed","Cancelled"} for item in self.queue):
            text="Queue ETA: complete"; tooltip="No unfinished queue items."
        else:
            duration=format_duration(result.seconds); finish=(datetime.now()+timedelta(seconds=result.seconds)).strftime("%H:%M:%S"); marker="≥" if result.confidence=="lower_bound" else ("~" if result.confidence=="approximate" else ""); unknown=f" + {result.unknown_items} unknown" if result.unknown_items else ""; text=f"Queue ETA: {marker}{duration} · finish {finish}{unknown}"; tooltip=f"Scheduler estimate using {self.settings.value('downloads/concurrent',2)} concurrent slot(s). Confidence: {result.confidence}."
        self.queue_eta_label.setText(text); self.queue_eta_label.setToolTip(tooltip)
    def start_estimate(self,item):
        req=item["request"]; worker=SizeEstimateWorker(self.service,req); self.estimators[req.id]=worker; worker.signals.estimate.connect(lambda result,i=item:self.estimate_ready(i,result)); worker.signals.failed.connect(lambda error,i=item:self.estimate_failed(i,error)); self.estimate_pool.start(worker)
    def estimate_ready(self,item,result):
        req=item["request"]; self.estimators.pop(req.id,None)
        if item.get("status")=="Cancelled":self.render_queue();return
        confidence=result.get("confidence","unknown"); size=result.get("bytes")
        if size is None:item["estimated_size"]="Unknown"
        elif confidence=="exact":item["estimated_size"]=f"{format_size(size)} (exact)"
        elif confidence=="partial":item["estimated_size"]=f"~{format_size(size)} (partial {result.get('known_items',0)}/{result.get('total_items',0)})"
        else:item["estimated_size"]=f"~{format_size(size)}"
        item["estimate"] = result; item["status"]="Waiting"; self.logger.info("Estimated size for %s: %s",req.title,item["estimated_size"]); self.render_queue(); self.start_available()
    def estimate_failed(self,item,error):
        req=item["request"]; self.estimators.pop(req.id,None)
        if item.get("status")=="Cancelled":self.render_queue();return
        item["estimated_size"]="Unknown"; item["estimate_error"]=error; item["status"]="Waiting"; self.logger.warning("Size estimate unavailable for %s: %s",req.title,error); self.render_queue(); self.start_available()
    def start_all(self):
        for item in self.queue:
            if item["status"] in {"Failed","Cancelled"} and item["request"].id not in self.estimators:item["status"]="Waiting"
        self.queue_run_enabled=True;self.start_available()
    def start_available(self):
        if not self.queue_run_enabled:return
        limit=int(self.settings.value("downloads/concurrent",2)); active=len(self.workers)
        for item in self.queue:
            if active>=limit:break
            if item["status"]=="Waiting":active+=bool(self.start_item(item))
    def start_item(self,item):
        reserve=max(0,int(self.settings.value("downloads/minimum_free_mib",256)))*1024*1024;estimated=int((item.get("estimate") or {}).get("bytes") or 0)
        try:free=shutil.disk_usage(item["request"].folder).free
        except OSError:free=0
        if reserve and free and free<reserve+estimated:
            item["status"]="Failed";item["output"]="Insufficient free disk space";self.logger.error("Download blocked: insufficient free disk space for %s",item["request"].title);self.render_queue();return False
        req=item["request"]; item.update(status="Downloading",started=datetime.now().isoformat(timespec="seconds"),started_monotonic=time.monotonic()); verify=str(self.settings.value("downloads/verify_integrity",True)).lower() not in {"false","0","no"}; retries=int(self.settings.value("downloads/integrity_retries",2)); worker=DownloadWorker(self.service,req,verify,retries); self.workers[req.id]=worker
        worker.signals.progress.connect(lambda d,i=item:self.on_progress(i,d)); worker.signals.phase.connect(lambda p,i=item:self.set_status(i,p)); worker.signals.pause_state.connect(lambda paused,i=item:self.on_pause_state(i,paused)); worker.signals.integrity.connect(lambda report,i=item:self.on_integrity(i,report)); worker.signals.retry.connect(lambda attempt,reason,i=item:self.on_integrity_retry(i,attempt,reason)); worker.signals.completed.connect(lambda d,i=item:self.finish(i,d)); worker.signals.failed.connect(lambda e,i=item:self.fail(i,e)); worker.signals.cancelled.connect(lambda i=item:self.cancelled(i)); self.pool.start(worker); self.render_queue(); self.active_changed.emit(len(self.workers));return True
    def on_progress(self,item,data):
        total=data.get("total_bytes") or data.get("total_bytes_estimate") or 0; done=data.get("downloaded_bytes") or 0; part=(done/total) if total else 0
        position=data.get("selected_item_position"); count=data.get("selected_item_count")
        estimate=(item.get("estimate") or {}).get("bytes")
        component_key=data.get("filename") or (data.get("info_dict") or {}).get("format_id") or "current"
        item.setdefault("transfer_components",{})[component_key]=max(0,int(done or 0))
        cumulative=sum(item["transfer_components"].values())
        if estimate:item["progress"]=min(99.9,cumulative/estimate*100)
        elif position and count:item["progress"]=(position-1+part)/count*100
        elif total:item["progress"]=part*100
        if not estimate and not item["request"].playlist_items:
            inferred=self.service.estimate_info_size(data.get("info_dict") or {})
            inferred_size=inferred.get("bytes") or total
            if inferred_size:
                confidence=inferred.get("confidence","approximate") if inferred.get("bytes") else ("exact" if data.get("total_bytes") else "approximate"); item["estimate"]={"bytes":int(inferred_size),"confidence":confidence,"known_items":1,"total_items":1}; item["estimated_size"]=("" if confidence=="exact" else "~")+format_size(inferred_size)
        speed=data.get("speed"); item["speed_bytes"]=float(speed) if isinstance(speed,(int,float)) and speed>0 else item.get("speed_bytes");
        if item.get("speed_bytes"):self.speed_ema=item["speed_bytes"] if self.speed_ema is None else self.speed_ema*0.8+item["speed_bytes"]*0.2
        item["download_status"]=f"Downloading playlist item {position}/{count}" if position and count else "Downloading"; item["status"]=item["download_status"]; item["speed"]=f"{format_speed(data.get('speed'))} · ETA {format_duration(data.get('eta'))}"; item["output"]=data.get("filename") or item["output"]; self.render_queue()
    def set_status(self,item,phase):
        if phase=="Verifying integrity":item["status"]="Verifying integrity…";self.render_queue();return
        if not item.get("postprocessing"):item["postprocess_started"]=time.monotonic()
        item["status"]=f"Post-processing: {phase}"; item["postprocessing"]=True; self.render_queue()
    def on_integrity(self,item,report):
        item["integrity"]=report; confidence=report.get("confidence","unknown")
        if report.get("valid") and report.get("conclusive"):item["integrity_label"]=f"Verified ({confidence})";item.pop("integrity_error",None)
        elif report.get("valid"):item["integrity_label"]="Unavailable";item["integrity_error"]="; ".join(report.get("errors") or [])
        else:item["integrity_label"]="Corrupt";item["integrity_error"]="; ".join(report.get("errors") or [])
        self.render_queue()
    def on_integrity_retry(self,item,attempt,reason):
        maximum=int(self.settings.value("downloads/integrity_retries",2)); item["status"]=f"Re-downloading corrupt file ({attempt}/{maximum})"; item["integrity_label"]=f"Retry {attempt}/{maximum}"; item["integrity_error"]=reason; item["progress"]=0; item["transfer_components"]={}; item["postprocessing"]=False; item.pop("postprocess_started",None); self.logger.warning("Integrity retry %s/%s for %s: %s",attempt,maximum,item["request"].title,reason); self.render_queue()
    def on_pause_state(self,item,paused):
        item["status"]="Paused" if paused else item.get("download_status","Downloading"); self.logger.info("Download %s: %s", "paused" if paused else "resumed", item["request"].title); self.render_queue()
    def toggle_pause(self,item):
        worker=self.workers.get(item["request"].id)
        if not worker:return
        if item["status"] in ("Paused","Pausing…"):
            if worker.resume():item["status"]=item.get("download_status","Downloading");self.logger.info("Resume requested: %s",item["request"].title);self.render_queue()
        elif item["status"].startswith("Downloading"):
            if worker.pause():item["status"]="Pausing…";self.logger.info("Pause requested: %s",item["request"].title);self.render_queue()
    def cancel_item(self,item):
        worker=self.workers.get(item["request"].id)
        if worker:worker.cancel();item["status"]="Cancelling…";self.render_queue()
    def finish(self,item,data):
        req=item["request"]; self.workers.pop(req.id,None); item.update(status="Completed",progress=100); path=data.get("requested_downloads",[{}])[0].get("filepath") if data.get("requested_downloads") else data.get("_filename"); item["output"]=path or item["output"]
        if item.get("postprocess_started"):
            elapsed=max(0.1,time.monotonic()-item["postprocess_started"]);self.postprocess_ema=self.postprocess_ema*0.7+elapsed*0.3
        self.repo.add(task_id=req.id,title=req.title,original_url=req.url,webpage_url=data.get("webpage_url"),extractor=data.get("extractor"),uploader=data.get("uploader"),duration=data.get("duration"),format=req.format_selector,resolution=data.get("resolution"),output_format=data.get("ext"),filesize=data.get("filesize") or (item.get("estimate") or {}).get("bytes"),download_folder=req.folder,final_filepath=item["output"],started_at=item.get("started"),completed_at=datetime.now().isoformat(timespec="seconds"),status="Completed",error=None); self.logger.info("Download completed: %s",req.title);self.notify_user("completed",f"Completed: {req.title}"); self.history_changed.emit(); self.render_queue(); self.active_changed.emit(len(self.workers)); self.start_available()
    def fail(self,item,error):
        req=item["request"]; self.workers.pop(req.id,None); item["status"]="Failed"; self.repo.add(task_id=req.id,title=req.title,original_url=req.url,format=req.format_selector,download_folder=req.folder,started_at=item.get("started"),completed_at=datetime.now().isoformat(timespec="seconds"),status="Failed",error=error); self.logger.error(error);self.notify_user("failed",f"Failed: {req.title}"); self.history_changed.emit(); self.render_queue(); self.active_changed.emit(len(self.workers)); self.start_available()
    def notify_user(self,event,message):
        if str(self.settings.value(f"notifications/{event}",True)).lower() not in {"true","1","yes"}:return
        self.status.emit(message)
        if str(self.settings.value("notifications/background_only",False)).lower() in {"true","1","yes"} and QApplication.activeWindow()==self.window():return
        QApplication.alert(self.window(),int(self.settings.value("notifications/duration_ms",3000)))
        if str(self.settings.value("notifications/sound",False)).lower() in {"true","1","yes"}:QApplication.beep()
    def cancelled(self,item): self.workers.pop(item["request"].id,None); item["status"]="Cancelled";self.notify_user("cancelled",f"Cancelled: {item['request'].title}"); self.render_queue(); self.active_changed.emit(len(self.workers)); self.start_available()
    def cancel_all(self):
        self.queue_run_enabled=False
        for item in self.queue:
            if item["request"].id in self.workers:self.cancel_item(item)
            elif item["status"] not in {"Completed","Failed","Cancelled"}:item["status"]="Cancelled"
        self.render_queue()
    def clear_completed(self): self.queue[:]=[i for i in self.queue if i["status"]!="Completed"]; self.render_queue()
    def queue_menu(self,pos):
        row=self.table.rowAt(pos.y());
        if row<0:return
        menu=QMenu(self); item=self.queue[row]; active=item["request"].id in self.workers; estimating=item["request"].id in self.estimators; pause_resume=menu.addAction("Resume" if item["status"] in ("Paused","Pausing…") else "Pause"); pause_resume.setEnabled(active and (item["status"].startswith("Downloading") or item["status"] in ("Paused","Pausing…"))); cancel=menu.addAction("Cancel"); cancel.setEnabled(active); retry=menu.addAction("Retry"); retry.setEnabled(not active and not estimating and item["status"] in ("Failed","Cancelled")); copy=menu.addAction("Copy URL"); folder=menu.addAction("Open Folder"); remove=menu.addAction("Remove"); remove.setEnabled(not active and not estimating); action=menu.exec(self.table.viewport().mapToGlobal(pos))
        if action==pause_resume:self.toggle_pause(item)
        elif action==cancel and item["request"].id in self.workers:self.cancel_item(item)
        elif action==retry:item["status"]="Waiting";self.start_available()
        elif action==copy:QApplication.clipboard().setText(item["request"].url)
        elif action==folder:QDesktopServices.openUrl(QUrl.fromLocalFile(item["request"].folder))
        elif action==remove and item["request"].id not in self.workers:self.queue.pop(row);self.render_queue()

class HistoryTab(QWidget):
    def __init__(self,repo,parent=None):
        super().__init__(parent); self.repo=repo; root=QVBoxLayout(self); bar=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("Search history…"); self.filter=QComboBox(); self.filter.addItems(["All","Completed","Failed","Cancelled"]); refresh=QPushButton("Refresh"); export=QPushButton("Export"); clear=QPushButton("Clear History"); [bar.addWidget(x) for x in (self.search,self.filter,refresh,export,clear)]; root.addLayout(bar); self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["#","Title","Website","Format","Size","Date","Status"]); self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch); self.table.setContextMenuPolicy(Qt.CustomContextMenu); root.addWidget(self.table); self.rows=[]; self.search.textChanged.connect(self.refresh); self.filter.currentTextChanged.connect(self.refresh); refresh.clicked.connect(self.refresh); export.clicked.connect(self.export); clear.clicked.connect(self.clear); self.table.customContextMenuRequested.connect(self.menu); self.table.doubleClicked.connect(self.details); self.refresh()
    def refresh(self):
        self.rows=self.repo.get_all(self.search.text(),self.filter.currentText()); self.table.setRowCount(len(self.rows))
        for r,x in enumerate(self.rows):
            vals=[x["id"],x["title"],x["extractor"] or "—",x["format"] or "—",format_size(x["filesize"]),x["completed_at"] or x["started_at"] or "—",x["status"]]
            for c,v in enumerate(vals):self.table.setItem(r,c,QTableWidgetItem(str(v)))
    def clear(self):
        if QMessageBox.question(self,"Clear history","Delete all history records? Files will not be removed.")==QMessageBox.Yes:self.repo.clear();self.refresh()
    def export(self):
        path,kind=QFileDialog.getSaveFileName(self,"Export history","history.json","JSON (*.json);;CSV (*.csv)")
        if not path:return
        if path.lower().endswith(".csv"):
            with open(path,"w",newline="",encoding="utf-8-sig") as f:
                w=csv.DictWriter(f,fieldnames=self.rows[0].keys() if self.rows else []); w.writeheader(); w.writerows(self.rows)
        else:Path(path).write_text(json.dumps(self.rows,indent=2,ensure_ascii=False),encoding="utf-8")
    def details(self,index=None):
        row=self.table.currentRow()
        if row>=0:HistoryDetailsDialog(self.rows[row],self).exec()
    def menu(self,pos):
        row=self.table.rowAt(pos.y());
        if row<0:return
        menu=QMenu(self); details=menu.addAction("View Details"); openfile=menu.addAction("Open File"); openfolder=menu.addAction("Open Folder"); openurl=menu.addAction("Open Original URL"); copy=menu.addAction("Copy URL"); delete=menu.addAction("Delete History Entry"); action=menu.exec(self.table.viewport().mapToGlobal(pos)); data=self.rows[row]
        if action==details:self.details()
        elif action==openfile:
            if data["final_filepath"] and Path(data["final_filepath"]).exists():QDesktopServices.openUrl(QUrl.fromLocalFile(data["final_filepath"]))
            else:QMessageBox.information(self,"File not found","File not found. It may have been moved or deleted.")
        elif action==openfolder:QDesktopServices.openUrl(QUrl.fromLocalFile(data["download_folder"] or ""))
        elif action==openurl:QDesktopServices.openUrl(QUrl(data["original_url"] or ""))
        elif action==copy:QApplication.clipboard().setText(data["original_url"] or "")
        elif action==delete:self.repo.delete(data["id"]);self.refresh()

class LogTab(QWidget):
    def __init__(self,emitter,log_path,parent=None):
        super().__init__(parent); root=QVBoxLayout(self); bar=QHBoxLayout(); self.search=QLineEdit(); self.search.setClearButtonEnabled(True); self.search.setPlaceholderText("Search log…"); self.level=QComboBox(); self.level.addItems(["ALL","DEBUG","INFO","WARNING","ERROR","CRITICAL"]); clear=QPushButton("Clear View"); copy=QPushButton("Copy"); export=QPushButton("Export Log"); openfolder=QPushButton("Open Log Folder"); self.colors=QCheckBox("Color levels"); self.colors.setChecked(True); self.auto=QCheckBox("Auto scroll"); self.auto.setChecked(True); [bar.addWidget(x) for x in (self.search,self.level,clear,copy,export,openfolder,self.colors,self.auto)]; root.addLayout(bar)
        legend=QLabel("<span style='color:#ff3b6b'>● CRITICAL</span>&nbsp;&nbsp; <span style='color:#ff5c5c'>● ERROR</span>&nbsp;&nbsp; <span style='color:#f2c94c'>● WARNING</span>&nbsp;&nbsp; <span style='color:#35c77a'>● INFO</span>&nbsp;&nbsp; <span style='color:#8b95a7'>● DEBUG</span>"); root.addWidget(legend)
        self.view=QPlainTextEdit(); self.view.setReadOnly(True); self.view.setLineWrapMode(QPlainTextEdit.NoWrap); self.highlighter=LogSyntaxHighlighter(self.view.document()); root.addWidget(self.view); self.summary=QLabel("0 visible · 0 total"); root.addWidget(self.summary)
        self.lines=[]; emitter.message.connect(self.add); self.search.textChanged.connect(self.render); self.level.currentTextChanged.connect(self.render); self.colors.toggled.connect(self.highlighter.set_colors_enabled); clear.clicked.connect(self.clear_view); copy.clicked.connect(self.copy_log); export.clicked.connect(self.export); openfolder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.parent))))
    def add(self,level,text):
        was_full=len(self.lines)>=5000; self.lines.append((level,text)); self.lines=self.lines[-5000:]
        term=self.search.text().casefold(); matches=(self.level.currentText()=="ALL" or self.level.currentText()==level) and term in text.casefold()
        if was_full:self.render()
        elif matches:
            self.view.appendPlainText(text); visible=sum(1 for l,t in self.lines if (self.level.currentText()=="ALL" or l==self.level.currentText()) and term in t.casefold()); self.summary.setText(f"{visible} visible · {len(self.lines)} total")
            if self.auto.isChecked():self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
    def render(self):
        term=self.search.text().casefold(); level=self.level.currentText(); visible=[t for l,t in self.lines if (level=="ALL" or l==level) and term in t.casefold()]; self.view.setPlainText("\n".join(visible)); self.highlighter.set_search_term(self.search.text()); self.summary.setText(f"{len(visible)} visible · {len(self.lines)} total")
        if self.auto.isChecked():self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
    def copy_log(self):
        cursor=self.view.textCursor(); QApplication.clipboard().setText(cursor.selectedText().replace("\u2029","\n") if cursor.hasSelection() else self.view.toPlainText())
    def clear_view(self):self.view.clear();self.summary.setText(f"0 visible · {len(self.lines)} retained")
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,"Export log","app-log.txt","Text (*.txt)")
        if path:Path(path).write_text(self.view.toPlainText(),encoding="utf-8")
