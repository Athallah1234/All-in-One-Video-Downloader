"""Validation, presentation and privacy helpers."""
import re
from urllib.parse import urlsplit, urlunsplit


def valid_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname) and not any(c.isspace() for c in value.strip())
    except ValueError:
        return False


def private_url(value: str) -> str:
    """History needs a source, but never persists URL credentials or query tokens."""
    try:
        p = urlsplit(value)
        host = p.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if p.port:
            host += f":{p.port}"
        from urllib.parse import parse_qsl, urlencode
        safe = [(k, v) for k, v in parse_qsl(p.query) if k.lower() in {"v", "list", "index", "t"}]
        return urlunsplit((p.scheme, host, p.path, urlencode(safe), ""))
    except ValueError:
        return "[invalid URL]"


def redact(message: object, secrets=()) -> str:
    value = str(message)
    from urllib.parse import quote, quote_plus
    variants = {variant for secret in secrets if secret for variant in (secret, quote(secret, safe=""), quote_plus(secret))}
    for secret in sorted(variants, key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    value = re.sub(r"https?://[^\s<>\"']+", lambda m: private_url(m.group()), value)
    value = re.sub(r"(?i)(cookie|authorization|password|token|secret)(\s*[:=]\s*)[^\s,;]+", r"\1\2[redacted]", value)
    if re.search(r"(?i)(cookie|authorization).*(:|=)", value):
        return "[Sensitive authentication diagnostic omitted]"
    return value


def size(value: int | float | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(number) < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024
    return "—"


def duration(value: int | float | None) -> str:
    if value is None:
        return "—"
    seconds = max(0, int(value))
    return f"{seconds // 3600:d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def friendly_error(error: object) -> str:
    message = redact(error)
    lower = message.lower()
    for keys, hint in [
        (("signature solving failed", "n challenge solving failed", "challenge solver", "page needs to be reloaded"), "YouTube extraction failed. Update dependencies with python -m pip install --upgrade -r requirements.txt, verify deno --version, then restart the application and retry. See Log for details."),
        (("drm",), "This content appears to use DRM and cannot be downloaded by this application."),
        (("unsupported url",), "This URL is not currently supported by your installed yt-dlp version."),
        (("sign in", "login", "private video", "authentication"), "This media requires authentication. Check Settings > Authentication for site username/password or a netrc file, or configure Cookies for browser-session login."),
        (("timed out", "unable to connect", "urlopen error"), "Unable to connect to the source. Check your internet connection and try again."),
        (("ffmpeg", "ffprobe"), "FFmpeg is required for this operation. Configure its folder in Settings."),
        (("aria2c", "aria2"), "aria2c failed or is unavailable. Check Settings > aria2c, verify the executable, or disable the external downloader."),
        (("equirectangular", "360° format"), "No equirectangular 360° stream was available. Confirm the source is VR/360° and update yt-dlp."),
    ]:
        if any(key in lower for key in keys):
            return hint + "\n" + message[:700]
    return message[:1000]
