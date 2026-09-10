"""Bounded HTTP redirect resolution for well-known URL shorteners."""
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.utils import valid_url


SHORTENER_HOSTS = frozenset({
    "amzn.to", "bit.ly", "buff.ly", "cutt.ly", "dlvr.it", "fb.me", "goo.gl", "is.gd",
    "lnkd.in", "ow.ly", "rb.gy", "rebrand.ly", "shorturl.at", "t.co", "tiny.cc",
    "tinyurl.com", "trib.al", "youtu.be",
})


def _host(url):
    try:
        return (urlsplit(url).hostname or "").casefold().rstrip(".")
    except ValueError:
        return ""


def is_short_url(url):
    """Return whether the URL host is a supported short-link service."""
    host = _host(url)
    return host in SHORTENER_HOSTS or any(host.endswith("." + item) for item in SHORTENER_HOSTS)


def _without_credentials(url):
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Short URLs containing embedded credentials are not allowed.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _redirect_destination(url):
    """Reject redirect targets that could turn a public shortener into a local-file/network probe."""
    clean = _without_credentials(url)
    if not valid_url(clean):
        raise ValueError("The shortener redirected to an invalid or unsupported URL.")
    host = _host(clean)
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Short URLs may not redirect to a local network address.")
    try:
        address = ip_address(host.strip("[]"))
    except ValueError:
        return clean
    if not address.is_global:
        raise ValueError("Short URLs may not redirect to a local or reserved network address.")
    return clean


@dataclass(frozen=True)
class URLResolution:
    original_url: str
    final_url: str
    redirects: tuple[str, ...]

    @property
    def expanded(self):
        return self.final_url != self.original_url


class _BoundedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, original, max_redirects):
        super().__init__()
        self.visited = [original]
        self.max_redirects = max_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = _redirect_destination(urljoin(req.full_url, newurl))
        normalized = target.split("#", 1)[0]
        if normalized in {item.split("#", 1)[0] for item in self.visited}:
            raise ValueError("The short URL contains a redirect loop.")
        if len(self.visited) > self.max_redirects:
            raise ValueError(f"The short URL exceeded the {self.max_redirects}-redirect limit.")
        self.visited.append(target)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None:
            redirected.remove_header("Authorization")
            redirected.remove_header("Cookie")
        return redirected


def expand_short_url(url, timeout=10, max_redirects=8, opener_factory=build_opener):
    """Resolve a known short URL without reading the response body."""
    original = _without_credentials(url.strip())
    if not valid_url(original):
        raise ValueError("Enter a valid HTTP/HTTPS short URL.")
    if not is_short_url(original):
        return URLResolution(original, original, ())
    if not 1 <= int(max_redirects) <= 20:
        raise ValueError("Redirect limit must be between 1 and 20.")
    handler = _BoundedRedirectHandler(original, int(max_redirects))
    opener = opener_factory(handler)
    headers = {"User-Agent": "Mozilla/5.0 VideoDownloader/1.0", "Accept": "*/*"}
    try:
        response = opener.open(Request(original, headers=headers, method="HEAD"), timeout=timeout)
    except HTTPError as error:
        if error.code not in {400, 403, 405, 501}:
            raise ValueError(f"Short URL resolution failed with HTTP {error.code}.") from None
        error.close()
        try:
            response = opener.open(Request(original, headers=headers | {"Range": "bytes=0-0"}, method="GET"), timeout=timeout)
        except (HTTPError, URLError, TimeoutError, OSError) as retry_error:
            raise ValueError(f"Unable to expand the short URL: {retry_error}") from None
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError(f"Unable to expand the short URL: {error}") from None
    with response:
        final = _redirect_destination(response.geturl())
    redirects = tuple(handler.visited[1:])
    return URLResolution(original, final, redirects)
