"""Real yt-dlp/FFmpeg integration against a temporary local HTTP fixture."""
import functools
import http.server
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.core.ffmpeg import detect
from app.core.models import Status
from app.core.queue_manager import QueueManager
from app.database.history import HistoryRepository
from app.services.settings import DEFAULTS, Settings
from app.services.logging_service import LogBus
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.workers.jobs import analyze


class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def copyfile(self, source, outputfile):
        if self.path.startswith("/slow.mp4"):
            try:
                while chunk := source.read(4096):
                    outputfile.write(chunk)
                    outputfile.flush()
                    time.sleep(.04)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        else:
            super().copyfile(source, outputfile)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        ffmpeg = detect()["ffmpeg"]
        if not ffmpeg:
            raise unittest.SkipTest("FFmpeg required to generate local video fixture")
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(cls.root / "sample.mp4")], check=True, capture_output=True)
        (cls.root / "second.mp4").write_bytes((cls.root / "sample.mp4").read_bytes())
        (cls.root / "slow.mp4").write_bytes((cls.root / "sample.mp4").read_bytes() * 80)
        (cls.root / "captions.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nLocal test caption\n", encoding="utf-8")
        (cls.root / "playlist.html").write_text('<html><head><title>Local Playlist</title></head><body><video controls src="sample.mp4"><track kind="subtitles" src="captions.vtt" srclang="en" label="English"></video><video controls src="second.mp4"></video></body></html>', encoding="utf-8")
        (cls.root / "subtitle.html").write_text('<html><head><title>Captioned video</title></head><body><video controls src="sample.mp4"><track kind="subtitles" src="captions.vtt" srclang="en" label="English"></video></body></html>', encoding="utf-8")
        handler = functools.partial(SilentHandler, directory=str(cls.root))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/sample.mp4"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temporary.cleanup()

    def spin(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(predicate(), "Timed out waiting for background jobs")

    def test_real_download_pause_resume_and_cancel(self):
        repository = HistoryRepository(self.root / "pause.db")
        manager = QueueManager(repository)
        prefs = DEFAULTS | {"output": str(self.root / "pause-results"), "proxy": ""}
        task = manager.add(self.url.replace("sample.mp4", "slow.mp4"), prefs, "Video")
        try:
            self.spin(lambda: task.downloaded > 0)
            worker = manager.workers[task.id]
            manager.pause(task.id)
            self.spin(lambda: task.status == Status.PAUSED)
            downloaded = task.downloaded
            deadline = time.monotonic() + .3
            while time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(task.downloaded, downloaded)
            self.assertEqual(task.speed, 0)
            manager.resume(task.id)
            self.assertIs(manager.workers[task.id], worker)
            self.spin(lambda: task.status in {Status.COMPLETED, Status.FAILED} and not manager.workers)
            self.assertEqual(task.status, Status.COMPLETED, task.error)
            self.assertEqual(Path(task.file_path).read_bytes(), (self.root / "slow.mp4").read_bytes())
            other = manager.add(task.url, prefs | {"output": str(self.root / "pause-cancel")}, "Video")
            self.spin(lambda: other.downloaded > 0)
            manager.pause(other.id)
            self.spin(lambda: other.status == Status.PAUSED)
            manager.cancel(other.id)
            self.spin(lambda: not manager.workers)
            self.assertEqual(other.status, Status.CANCELLED)
        finally:
            manager.shutdown()
            self.spin(lambda: not manager.workers)
            repository.close()


    def test_analysis_video_audio_history(self):
        prefs = DEFAULTS | {"output": str(self.root / "results"), "proxy": ""}
        info = analyze(self.url, prefs)
        self.assertEqual(info["id"], "sample")
        self.assertTrue(info["formats"])
        repository = HistoryRepository(self.root / "integration.db")
        self.addCleanup(repository.close)
        manager = QueueManager(repository, 2)
        updates = []
        manager.changed.connect(lambda: updates.append(True))
        video = manager.add(self.url, prefs | {"mode": "Video"}, "Video")
        audio = manager.add(self.url, prefs | {"mode": "Audio", "audio_format": "MP3"}, "Audio")
        self.spin(lambda: video.status in {Status.COMPLETED, Status.FAILED} and audio.status in {Status.COMPLETED, Status.FAILED} and not manager.workers)
        self.assertEqual(video.status, Status.COMPLETED, video.error)
        self.assertEqual(audio.status, Status.COMPLETED, audio.error)
        self.assertTrue(Path(video.file_path).is_file())
        self.assertEqual(Path(audio.file_path).suffix, ".mp3")
        self.assertTrue(Path(audio.file_path).is_file())
        self.assertGreater(len(updates), 5)
        self.assertEqual(len(repository.list(category="Completed")), 2)

    def test_window_modes_and_theme(self):
        settings = Settings(self.root / "ui-settings.json")
        settings.values.update(confirm_exit=False, output=str(self.root / "ui-downloads"))
        repo = HistoryRepository(self.root / "ui-history.db")
        manager = QueueManager(repo)
        window = MainWindow(settings, repo, manager, LogBus())
        window.show()
        self.app.processEvents()
        for mode in range(7):
            window.downloader.modes.setCurrentIndex(mode)
            self.app.processEvents()
        window.downloader.modes.setCurrentIndex(0)
        window.downloader.url.setText(self.url)
        window.downloader.analyze()
        self.spin(lambda: window.downloader.worker is None)
        self.assertIsNotNone(window.downloader.info)
        for theme in ["Dark", "Light", "System"]:
            apply_theme(self.app, theme)
            self.app.processEvents()
        window.close()
        self.app.processEvents()
        repo.close()

    def test_playlist_metadata_and_subtitles(self):
        base = self.url.rsplit("/", 1)[0]
        prefs = DEFAULTS | {"output": str(self.root / "sidecars")}
        info = analyze(base + "/playlist.html", prefs | {"mode": "Playlist"})
        self.assertEqual(len(info["entries"]), 2)
        repository = HistoryRepository(self.root / "sidecars.db")
        self.addCleanup(repository.close)
        manager = QueueManager(repository)
        playlist = manager.add(base + "/playlist.html", prefs | {"mode": "Playlist", "items": "2"}, "Playlist")
        metadata = manager.add(self.url, prefs | {"mode": "Metadata"}, "Metadata")
        subtitle = manager.add(base + "/subtitle.html", prefs | {"mode": "Subtitle", "subtitle_format": "SRT"}, "Subtitle")
        tasks = [playlist, metadata, subtitle]
        self.spin(lambda: all(t.status in {Status.COMPLETED, Status.FAILED} for t in tasks) and not manager.workers)
        for task in tasks:
            self.assertEqual(task.status, Status.COMPLETED, task.error)
        files = list(Path(prefs["output"]).rglob("*"))
        self.assertTrue(any(p.suffix == ".json" for p in files))
        self.assertTrue(any(p.suffix == ".srt" for p in files))
        self.assertEqual(len([p for p in files if p.suffix == ".mp4"]), 1)

    def test_cancellation_and_failure(self):
        base = self.url.rsplit("/", 1)[0]
        prefs = DEFAULTS | {"output": str(self.root / "cancelled"), "mode": "Video", "retries": 0}
        repository = HistoryRepository(self.root / "cancellation.db")
        self.addCleanup(repository.close)
        manager = QueueManager(repository)
        active = manager.add(base + "/slow.mp4", prefs, "Video")
        waiting = manager.add(self.url, prefs, "Video")
        manager.cancel(waiting.id)
        self.assertEqual(waiting.status, Status.CANCELLED)
        self.spin(lambda: active.downloaded > 0)
        manager.cancel(active.id)
        self.spin(lambda: active.status == Status.CANCELLED and not manager.workers)
        failed = manager.add(base + "/missing.mp4", prefs, "Video")
        self.spin(lambda: failed.status == Status.FAILED and not manager.workers)
        self.assertTrue(failed.error)
        self.assertEqual(len(repository.list(category="Cancelled")), 2)

    def test_settings_dialog_and_sites(self):
        from app.ui.dialogs import SettingsDialog, SupportedSitesDialog
        settings = Settings(self.root / "dialog-settings.json")
        dialog = SettingsDialog(settings)
        dialog.fields["theme"].setCurrentText("Dark")
        dialog.fields["concurrency"].setValue(2)
        dialog.save()
        loaded = Settings(settings.path)
        self.assertEqual(loaded["theme"], "Dark")
        self.assertEqual(loaded["concurrency"], 2)
        sites = SupportedSitesDialog()
        self.spin(lambda: sites.worker is None)
        sites.search.setText("yOuTuBe")
        self.assertGreater(sites.table.rowCount(), 0)
        self.assertLess(sites.table.rowCount(), len(sites.rows))
        sites.close()


if __name__ == "__main__":
    unittest.main()
