"""Read standard netrc files without exposing parser diagnostics or credentials."""
import netrc
from pathlib import Path


def read_netrc(preferences):
    """Resolve a file (or directory), returning its path and parsed authenticators."""
    location = preferences.get("netrc_location", "")
    if not isinstance(location, str) or "\x00" in location:
        raise ValueError("Choose a valid netrc file in Settings > Authentication.")
    try:
        path = Path(location).expanduser() if location else Path.home() / ".netrc"
        if path.is_dir():
            path = path / ".netrc"
        path = path.resolve()
        if not path.is_file():
            raise ValueError("Netrc file not found. Select an existing file in Settings > Authentication.")
        parsed = netrc.netrc(str(path))
    except netrc.NetrcParseError:
        # NetrcParseError can include an unexpected token containing a password.
        raise ValueError("Invalid netrc syntax. Check machine, login and password entries in your file.") from None
    except (OSError, RuntimeError, UnicodeError):
        raise ValueError("Cannot read netrc file. Check its location, encoding and read permissions.") from None
    return str(path), parsed
