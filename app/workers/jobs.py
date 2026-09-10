"""QThread jobs; no Qt widgets or database connections cross the boundary."""
import logging
import threading
import time
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from app.core.format_builder import build_options
from app.core.live import validate_live_info
from app.core.vr import validate_vr_info
from app.core.utils import friendly_error, redact

logger = logging.getLogger(__name__)


class Cancelled(Exception):
    """Cooperative cancellation at the next yt-dlp hook."""


class YDLLogger:
    def __init__(self, preferences=None):
        self.errors = []
        self.secrets = tuple((preferences or {}).get(k, "") for k in (
            "username", "password", "socks_username", "socks_password"))
        self.netrc_enabled = bool((preferences or {}).get("use_netrc"))

    def clean(self, message):
        if self.netrc_enabled:
            # Extractors reread the file; it may have changed since validation.
            # Never relay arbitrary extractor diagnostics while file login is active.
            return "Netrc authentication diagnostic omitted. Check the file, machine entry, credentials and site availability."
        return redact(message, self.secrets)

    def debug(self, message):
        logger.debug(self.clean(message))

    def info(self, message):
        logger.info(self.clean(message))

    def warning(self, message):
        logger.warning(self.clean(message))

    def error(self, message):
        self.errors.append(self.clean(message))
        logger.error(self.clean(message))


class FunctionWorker(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function())
        except Exception as error:
            logger.error("Background operation failed: %s", redact(error))
            self.failed.emit(friendly_error(error))


def analyze(url: str, preferences: dict) -> dict:
    logger.info("Analyze started")
    opts = build_options(preferences, analyze=True)
    ylog = YDLLogger(preferences)
    opts["logger"] = ylog
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError(ylog.errors[-1] if ylog.errors else "No metadata returned. The source may be unavailable.")
            if info.get("has_drm"):
                raise ValueError("This content uses DRM and cannot be downloaded.")
            result = ydl.sanitize_info(info)
            if "entries" in result:
                result["entries"] = list(result["entries"])
    except Exception as error:
        raise ValueError(ylog.clean(error)) from None
    logger.info("Analyze completed")
    return result


def analyze_outputs(url: str, preferences: dict) -> dict:
    """Resolve selected output metadata fully, without downloading media."""
    logger.info("Existing-file preflight started")
    opts = build_options(preferences)
    opts.update(skip_download=True, extract_flat=False)
    ylog = YDLLogger(preferences)
    opts["logger"] = ylog
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError(ylog.errors[-1] if ylog.errors else "No metadata returned for filename checking.")
            result = ydl.sanitize_info(info)
            if "entries" in result:
                result["entries"] = list(result["entries"])
    except Exception as error:
        raise ValueError(ylog.clean(error)) from None
    logger.info("Existing-file preflight completed")
    return result


class DownloadWorker(QThread):
    progress = Signal(str, object)
    metadata = Signal(str, object)
    completed = Signal(str, object)
    failed = Signal(str, str)
    cancelled = Signal(str)
    paused = Signal(str, int)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.stop = threading.Event()
        self.pause_condition = threading.Condition()
        self.pause_requested = False
        self.pause_generation = 0
        self.pause_acknowledged = 0
        self.last_emit = 0.0
        self.files = []

    def pause(self):
        with self.pause_condition:
            if not self.pause_requested:
                self.pause_generation += 1
                self.pause_requested = True
            return self.pause_generation

    def resume(self):
        with self.pause_condition:
            self.pause_requested = False
            self.pause_condition.notify_all()

    def cancel(self):
        with self.pause_condition:
            self.stop.set()
            self.pause_condition.notify_all()

    def check(self):
        with self.pause_condition:
            while self.pause_requested and not self.stop.is_set():
                if self.pause_acknowledged != self.pause_generation:
                    self.pause_acknowledged = self.pause_generation
                    self.paused.emit(self.task.id, self.pause_generation)
                self.pause_condition.wait()
            if self.stop.is_set():
                raise Cancelled()

    def hook(self, data):
        self.check()
        now = time.monotonic()
        if now - self.last_emit < .15 and data.get("status") == "downloading":
            return
        self.last_emit = now
        info = data.get("info_dict", {})
        self.metadata.emit(self.task.id, {k: info.get(k) for k in ("title", "extractor", "playlist_index", "playlist_count", "n_entries")})
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        downloaded = data.get("downloaded_bytes") or 0
        self.progress.emit(self.task.id, {
            "status": "Processing" if data.get("status") == "finished" else "Downloading",
            "progress": min(100, downloaded / total * 100) if total else 0,
            "speed": data.get("speed") or 0, "eta": data.get("eta"), "file_size": total,
            "downloaded": downloaded, "file_path": data.get("filename", ""),
            "fragment": f"{data.get('fragment_index', '—')} / {data.get('fragment_count', '—')}",
        })

    def post_hook(self, data):
        self.check()
        info = data.get("info_dict", {})
        self.progress.emit(self.task.id, {"status": "Processing", "file_path": info.get("filepath", "")})

    def run(self):
        ylog = YDLLogger(self.task.options)
        try:
            self.check()
            options = build_options(self.task.options)
            # Separate intermediate streams when jobs target the same title concurrently.
            temporary = Path(self.task.options["output"]) / ".svd-temp" / self.task.options.get("_temp_id", self.task.id)
            options["paths"]["temp"] = str(temporary)
            options.update(logger=ylog, progress_hooks=[self.hook], postprocessor_hooks=[self.post_hook])

            def guard(info, *, incomplete=False):
                self.check()
                if info.get("has_drm"):
                    raise DownloadError("This content uses DRM and cannot be downloaded.")
                if self.task.media_type == "Live Stream" and not incomplete:
                    validate_live_info(info)
                    self.metadata.emit(self.task.id, {k: info.get(k) for k in ("title", "extractor")})
                    self.progress.emit(self.task.id, {"status": "Downloading", "file_size": 0})
                if self.task.media_type == "360° / VR" and not incomplete:
                    validate_vr_info(info)
                if not incomplete and (self.task.media_type == "Audio" or self.task.options.get("format") == "Audio Only"):
                    existing = Path(ydl.prepare_filename(info))
                    if existing.is_file():
                        # yt-dlp can reuse an existing final video for audio conversion.
                        # Such a file belongs to the user and must never be deleted.
                        ydl.params["keepvideo"] = True
                return None

            options["match_filter"] = guard
            def final_path(path):
                self.check()
                self.files.append(path)
            options["post_hooks"] = [final_path]
            Path(self.task.options["output"]).mkdir(parents=True, exist_ok=True)
            with YoutubeDL(options) as ydl:
                if self.task.options.get("sponsorblock") and self.task.media_type not in {"Subtitle", "Metadata"}:
                    from yt_dlp.postprocessor import SponsorBlockPP

                    class OptionalSponsorBlockPP(SponsorBlockPP):
                        def run(self, info):
                            try:
                                return super().run(info)
                            except Exception as error:
                                logger.warning("SponsorBlock unavailable; keeping all segments: %s", ylog.clean(error))
                                info["sponsorblock_chapters"] = []
                                return [], info

                    ydl.add_post_processor(OptionalSponsorBlockPP(ydl, categories=["sponsor"]), when="after_filter")
                result = ydl.extract_info(self.task.url, download=True)
                self.check()
                if not result:
                    raise ValueError(ylog.errors[-1] if ylog.errors else "No media was downloaded. It may be unavailable or excluded by your selection.")
                if ylog.errors or ydl._download_retcode:
                    raise ValueError("One or more items failed. " + (ylog.errors[-1] if ylog.errors else "See Log for details."))
                self.metadata.emit(self.task.id, {k: result.get(k) for k in ("title", "extractor")})
                paths = [Path(p) for p in self.files if Path(p).is_file()]
                if self.task.media_type in {"Subtitle", "Metadata"}:
                    # Sidecar-only jobs never produce a media post_hook filename.
                    for entry in result.get("entries", [result]):
                        if not entry:
                            continue
                        if self.task.media_type == "Metadata":
                            path = Path(ydl.prepare_filename(entry, "infojson"))
                            if path.is_file():
                                paths.append(path)
                        for subtitle in (entry.get("requested_subtitles") or {}).values():
                            path = Path(subtitle.get("filepath") or "")
                            moved = Path(self.task.options["output"]) / path.name
                            if moved.is_file():
                                paths.append(moved)
                            elif path.is_file():
                                paths.append(path)
                    if self.task.media_type == "Subtitle" and not paths:
                        raise ValueError("No matching subtitles were saved. Analyze the URL and choose an available language and subtitle source.")
                paths = list(dict.fromkeys(paths))
                final = {"file_path": str(paths[-1]) if paths else "", "file_size": sum(p.stat().st_size for p in paths)}
            if temporary.is_dir() and not any(temporary.iterdir()):
                try:
                    temporary.rmdir()
                except OSError as error:
                    logger.warning("Could not remove empty temporary folder: %s", error)
            self.completed.emit(self.task.id, final)
        except Cancelled:
            self.cancelled.emit(self.task.id)
        except Exception as error:
            if self.stop.is_set():
                self.cancelled.emit(self.task.id)
            else:
                logger.error("Download failed: %s", ylog.clean(error))
                self.failed.emit(self.task.id, friendly_error(ylog.clean(error)))
