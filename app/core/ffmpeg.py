"""Locate FFmpeg tools and safely report their versions."""
from datetime import date
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess

MINIMUM_VERSION = (4, 4)
MINIMUM_LABEL = ".".join(map(str, MINIMUM_VERSION))
FFMPEG_44_RELEASE_DATE = date(2021, 4, 8)


def parse_version_line(line):
    if not isinstance(line, str):
        return None, None, "unknown"
    match = re.search(r"\b(?:ffmpeg|ffprobe) version\s+([^\s]+)", line, re.IGNORECASE)
    if not match:
        return None, None, "unknown"
    display = match.group(1)
    release = re.search(r"(?:^|[^\d])n?(\d+)\.(\d+)(?:\.(\d+))?", display, re.IGNORECASE)
    if release:
        return display, tuple(int(value or 0) for value in release.groups()), "release"
    dated = re.search(r"(20\d{2})[-.]([01]\d)[-.]([0-3]\d)", display)
    if dated:
        try:
            build_date = date(*map(int, dated.groups()))
        except ValueError:
            return display, None, "unknown"
        strategy = "date" if build_date >= FFMPEG_44_RELEASE_DATE else "old-date"
        return display, (build_date.year, build_date.month, build_date.day), strategy
    return display, None, "unknown"


def compatibility(version, strategy):
    if version is None:
        return None
    if strategy == "date":
        return True
    if strategy == "old-date":
        return False
    if strategy == "release":
        return version[:2] >= MINIMUM_VERSION
    return None


@lru_cache(maxsize=16)
def _inspect_cached(path, modified_ns, file_size):
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [path, "-version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            timeout=5, check=False, creationflags=creationflags)
    except subprocess.TimeoutExpired:
        return {"version": None, "version_tuple": None, "strategy": "unknown",
                "compatible": None, "error": "Version check timed out after 5 seconds"}
    except (OSError, ValueError):
        return {"version": None, "version_tuple": None, "strategy": "unknown",
                "compatible": None, "error": "Executable could not be started for version detection"}
    first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    display, parsed, strategy = parse_version_line(first_line)
    error = f"Version command exited with code {result.returncode}" if result.returncode else None
    if not error and not display:
        error = "Version output was not recognized"
    return {"version": display, "version_tuple": parsed, "strategy": strategy,
            "compatible": compatibility(parsed, strategy), "error": error}


def inspect_binary(path):
    try:
        stat = Path(path).stat()
        return _inspect_cached(str(path), stat.st_mtime_ns, stat.st_size).copy()
    except OSError:
        return {"version": None, "version_tuple": None, "strategy": "unknown",
                "compatible": None, "error": "Executable is no longer available"}


def _locate(folder, name):
    if folder:
        try:
            candidate = Path(folder).expanduser()
            if candidate.is_file() and candidate.stem.lower() == name:
                return str(candidate.resolve())
            local = next((item for item in (candidate / f"{name}.exe", candidate / name) if item.is_file()), None)
            return str(local.resolve()) if local else None
        except (OSError, RuntimeError, ValueError):
            return None
    return shutil.which(name)


def detect(folder=""):
    result = {name: _locate(folder, name) for name in ("ffmpeg", "ffprobe")}
    for name in ("ffmpeg", "ffprobe"):
        info = inspect_binary(result[name]) if result[name] else {
            "version": None, "version_tuple": None, "strategy": "unknown",
            "compatible": None, "error": "Not found"}
        result.update({f"{name}_{key}": value for key, value in info.items()})
    result["minimum_version"] = MINIMUM_LABEL
    return result


def version_status(info, name="ffmpeg"):
    if not info.get(name):
        return "Not found"
    version = info.get(f"{name}_version") or "unknown version"
    compatible = info.get(f"{name}_compatible")
    verdict = "Compatible" if compatible is True else f"Too old (need {MINIMUM_LABEL}+)" if compatible is False else "Compatibility unknown"
    return f"{version} — {verdict}"
