from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "Video Downloader"

def ensure_directories() -> None:
    for path in (DATA_DIR, LOG_DIR, DEFAULT_DOWNLOAD_DIR):
        path.mkdir(parents=True, exist_ok=True)

