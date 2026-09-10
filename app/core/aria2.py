"""Locate, execute and configure aria2c as yt-dlp's external downloader."""
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess


def parse_aria2_version(output):
    """Parse the official first-line form: ``aria2 version X.Y.Z``."""
    if not isinstance(output, str):
        return None, None
    match = re.search(r"(?im)^\s*aria2\s+version\s+([0-9]+(?:\.[0-9]+){1,3})(?:[-+][^\s]+)?\s*$", output)
    if not match:
        return None, None
    display = match.group(1)
    return display, tuple(int(part) for part in display.split("."))


def _locate_aria2c(location=""):
    if location:
        try:
            path = Path(location).expanduser()
            if path.is_dir():
                path = next((item for item in (path / "aria2c.exe", path / "aria2c") if item.is_file()), path / "aria2c")
            if path.is_file() and path.stem.casefold() == "aria2c":
                return str(path.resolve())
            return None
        except (OSError, RuntimeError, ValueError):
            return None
    return shutil.which("aria2c")


@lru_cache(maxsize=16)
def _inspect_cached(path, modified_ns, file_size):
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [path, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            timeout=5, check=False, creationflags=creationflags)
    except subprocess.TimeoutExpired:
        return {"version": None, "version_tuple": None, "valid": False,
                "error": "Version check timed out after 5 seconds"}
    except (OSError, ValueError):
        return {"version": None, "version_tuple": None, "valid": False,
                "error": "Executable could not be started for version detection"}
    output = result.stdout[:64 * 1024] if isinstance(result.stdout, str) else ""
    version, parsed = parse_aria2_version(output)
    error = f"Version command exited with code {result.returncode}" if result.returncode else None
    if not error and not version:
        error = "Version output was not recognized as aria2c"
    return {"version": version, "version_tuple": parsed, "valid": error is None, "error": error}


def inspect_aria2c(location=""):
    """Return path, actual version and validation diagnostics."""
    path = _locate_aria2c(location)
    if not path:
        return {"path": None, "version": None, "version_tuple": None, "valid": False, "error": "Not found"}
    try:
        stat = Path(path).stat()
    except OSError:
        return {"path": path, "version": None, "version_tuple": None, "valid": False,
                "error": "Executable is no longer available"}
    return {"path": path, **_inspect_cached(path, stat.st_mtime_ns, stat.st_size).copy()}


def detect_aria2c(location=""):
    """Return the executable path only when ``aria2c --version`` validates it."""
    info = inspect_aria2c(location)
    return info["path"] if info["valid"] else None


def aria2_version_status(info):
    if not info.get("path"):
        return "Not found"
    if not info.get("valid"):
        return f"Invalid — {info.get('error') or 'version check failed'}"
    return f"{info['version']} — Valid aria2c executable"


def _bounded_int(value, name, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be between {minimum} and {maximum}.") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def aria2_options(preferences, proxy=None):
    """Return validated yt-dlp options for aria2c, or no options when disabled."""
    if not preferences.get("use_aria2c"):
        return {}
    location = preferences.get("aria2c_path", "")
    executable = detect_aria2c(location)
    if not executable:
        info = inspect_aria2c(location)
        if not info["path"]:
            raise ValueError("aria2c was not found. Select aria2c.exe in Settings > aria2c or install it on PATH.")
        raise ValueError(f"The selected aria2c executable is invalid: {info['error']}.")
    if isinstance(proxy, str) and proxy.lower().startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
        raise ValueError("aria2c does not support SOCKS proxies. Choose the native downloader, an HTTP/HTTPS proxy, or No Proxy.")
    connections = _bounded_int(preferences.get("aria2c_connections", 16), "aria2c connections", 1, 16)
    splits = _bounded_int(preferences.get("aria2c_splits", 16), "aria2c split count", 1, 16)
    minimum = _bounded_int(preferences.get("aria2c_min_split_mib", 1), "aria2c minimum split size", 1, 1024)
    args = [f"--max-connection-per-server={connections}", f"--split={splits}", f"--min-split-size={minimum}M"]
    if preferences.get("aria2c_disable_ipv6"):
        args.append("--disable-ipv6=true")
    return {"external_downloader": {"default": executable},
            "external_downloader_args": {"aria2c": args}}
