import os,shutil
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_COOKIE_BROWSERS=(
    ("Disabled",None),
    ("Google Chrome","chrome"),
    ("Mozilla Firefox","firefox"),
    ("Microsoft Edge","edge"),
)


@dataclass(frozen=True)
class BrowserCookieSource:
    browser: str
    profile: str | None = None
    firefox_container: str | None = None
    keyring: str | None = None

    def __post_init__(self):
        if self.browser not in {value for _label,value in SUPPORTED_COOKIE_BROWSERS if value}:
            raise ValueError(f"Unsupported cookies browser: {self.browser}")
        if self.profile and ("\0" in self.profile or len(self.profile)>4096):
            raise ValueError("Invalid browser profile")
        if self.firefox_container and self.browser!="firefox":
            raise ValueError("Firefox containers can only be used with Firefox")
        if self.keyring not in {None,"basictext","gnomekeyring","kwallet","kwallet5","kwallet6"}:raise ValueError("Unsupported Chromium keyring")

    def as_ytdlp_tuple(self) -> tuple[str,str | None,None,str | None]:
        return self.browser,self.profile or None,self.keyring or None,self.firefox_container or None


def cookie_source_from_settings(settings) -> BrowserCookieSource | None:
    enabled=str(settings.value("cookies/enabled",False)).lower() in {"true","1","yes"}
    mode=str(settings.value("cookies/mode","browser") or "browser").lower()
    browser=str(settings.value("cookies/browser","") or "").lower().strip()
    if not enabled or mode!="browser" or not browser:return None
    profile=str(settings.value("cookies/profile","") or "").strip() or None
    container=str(settings.value("cookies/firefox_container","") or "").strip() or None
    keyring=str(settings.value("cookies/keyring","") or "").strip() or None
    return BrowserCookieSource(browser,profile,container if browser=="firefox" else None,keyring if browser in {"chrome","edge"} else None)


@dataclass(frozen=True)
class NetscapeCookieFileReport:
    valid: bool
    cookie_count: int = 0
    error: str = ""


def validate_netscape_cookie_file(path: str | Path) -> NetscapeCookieFileReport:
    """Validate structure without returning or logging any cookie values."""
    candidate=Path(path)
    if candidate.suffix.lower()!=".txt":return NetscapeCookieFileReport(False,error="Cookie file must use the .txt extension")
    try:
        if not candidate.is_file():return NetscapeCookieFileReport(False,error="Cookie file does not exist")
        if candidate.stat().st_size>32*1024*1024:return NetscapeCookieFileReport(False,error="Cookie file is larger than the 32 MiB safety limit")
        count=0;header=False
        with candidate.open("r",encoding="utf-8-sig",errors="replace") as stream:
            for line_number,raw in enumerate(stream,1):
                line=raw.rstrip("\r\n")
                if not line.strip():continue
                if line.startswith("# Netscape HTTP Cookie File") or line.startswith("# HTTP Cookie File"):header=True;continue
                if line.startswith("#") and not line.startswith("#HttpOnly_"):continue
                fields=line.split("\t")
                if len(fields)!=7:return NetscapeCookieFileReport(False,error=f"Invalid Netscape row at line {line_number}: expected 7 tab-separated fields")
                domain,include_subdomains,cookie_path,secure,expires,name,_value=fields
                if not domain or not cookie_path or not name:return NetscapeCookieFileReport(False,error=f"Missing required field at line {line_number}")
                if include_subdomains.upper() not in {"TRUE","FALSE"} or secure.upper() not in {"TRUE","FALSE"}:return NetscapeCookieFileReport(False,error=f"Invalid TRUE/FALSE flag at line {line_number}")
                if expires and not expires.isdigit():return NetscapeCookieFileReport(False,error=f"Invalid expiry timestamp at line {line_number}")
                count+=1
        if not header:return NetscapeCookieFileReport(False,error="Missing Netscape cookie-file header")
        if not count:return NetscapeCookieFileReport(False,error="Cookie file contains no cookie records")
        return NetscapeCookieFileReport(True,count)
    except (OSError,UnicodeError):return NetscapeCookieFileReport(False,error="Cookie file cannot be read")


def cookie_file_from_settings(settings) -> str | None:
    enabled=str(settings.value("cookies/enabled",False)).lower() in {"true","1","yes"}
    mode=str(settings.value("cookies/mode","browser") or "browser").lower()
    path=str(settings.value("cookies/file","") or "").strip()
    if not enabled or mode!="file" or not path:return None
    report=validate_netscape_cookie_file(path)
    if not report.valid:raise ValueError(report.error)
    return str(Path(path).resolve())


def detected_browsers() -> set[str]:
    """Best-effort installation detection; never opens or reads a browser profile."""
    roots=[Path(value) for key in ("PROGRAMFILES","PROGRAMFILES(X86)","LOCALAPPDATA") if (value:=os.environ.get(key))]
    candidates={
        "chrome":[Path("Google/Chrome/Application/chrome.exe")],
        "edge":[Path("Microsoft/Edge/Application/msedge.exe")],
        "firefox":[Path("Mozilla Firefox/firefox.exe")],
    }
    found=set()
    for browser,relative_paths in candidates.items():
        executable="msedge" if browser=="edge" else browser
        if shutil.which(executable) or any((root/relative).is_file() for root in roots for relative in relative_paths):found.add(browser)
    return found
