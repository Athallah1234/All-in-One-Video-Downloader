"""Run with python main.py; no packaging runtime is required."""
import importlib.util
import sys


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        return 1
    missing = [name for name in ("PySide6", "yt_dlp") if importlib.util.find_spec(name) is None]
    if missing:
        message = "Missing dependencies: " + ", ".join(missing) + "\nRun: python -m pip install -r requirements.txt"
        print(message, file=sys.stderr)
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Simple Video Downloader", 0x10)
        return 1
    from app.application import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
