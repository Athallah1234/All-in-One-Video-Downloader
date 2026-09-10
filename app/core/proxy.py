"""Validate and translate dedicated proxy settings into yt-dlp options."""
import ipaddress
from urllib.parse import quote, urlsplit


PROXY_MODES = ["System / environment", "No Proxy", "Proxy URL", "SOCKS5", "SOCKS5h (remote DNS)"]
SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks4", "socks4a", "socks5", "socks5h"}


def _clean_host(value):
    if not isinstance(value, str):
        raise ValueError("Enter a valid SOCKS5 proxy host.")
    host = value.strip()
    if not host or any(c.isspace() for c in host) or any(c in host for c in "/?#@[]"):
        raise ValueError("SOCKS5 host must be a hostname or IP address without a scheme, path, or port.")
    if ":" in host:
        try:
            return f"[{ipaddress.IPv6Address(host).compressed}]"
        except ipaddress.AddressValueError:
            raise ValueError("Enter a valid IPv6 address without brackets in the SOCKS5 host field.") from None
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("Enter a valid SOCKS5 hostname.") from None
    if len(ascii_host) > 253 or any(not label or len(label) > 63 for label in ascii_host.rstrip(".").split(".")):
        raise ValueError("Enter a valid SOCKS5 hostname.")
    if any(not (c.isalnum() or c in "-.") for c in ascii_host):
        raise ValueError("Enter a valid SOCKS5 hostname or IP address.")
    return ascii_host


def _proxy_url(value):
    if not isinstance(value, str) or any(c in value for c in ("\x00", "\r", "\n")):
        raise ValueError("Enter a valid proxy URL.")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in SUPPORTED_PROXY_SCHEMES or not parsed.hostname:
            raise ValueError
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Proxy URL must use http, https, socks4, socks4a, socks5, or socks5h and contain a valid host and port.") from None
    return value


def proxy_options(preferences):
    """Return a validated yt-dlp proxy option for the selected mode."""
    mode = preferences.get("proxy_type", PROXY_MODES[0])
    if mode == "System / environment":
        return {}
    if mode == "No Proxy":
        return {"proxy": ""}
    if mode == "Proxy URL":
        return {"proxy": _proxy_url(preferences.get("proxy", ""))}
    if mode not in {"SOCKS5", "SOCKS5h (remote DNS)"}:
        raise ValueError("Choose a valid proxy type in Settings > Network.")

    host = _clean_host(preferences.get("socks_host", ""))
    try:
        port = int(preferences.get("socks_port", 1080))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("SOCKS5 proxy port must be between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("SOCKS5 proxy port must be between 1 and 65535.")
    username = preferences.get("socks_username", "")
    password = preferences.get("socks_password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("SOCKS5 credentials must be text.")
    if any(c in username + password for c in ("\x00", "\r", "\n")):
        raise ValueError("SOCKS5 credentials cannot contain NUL or line breaks.")
    if password and not username:
        raise ValueError("Enter a SOCKS5 username when a proxy password is set.")
    credentials = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
    scheme = "socks5h" if mode.startswith("SOCKS5h") else "socks5"
    return {"proxy": f"{scheme}://{credentials}{host}:{port}"}
