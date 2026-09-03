from urllib.parse import urlparse
from utils.duplicates import canonicalize_url

def is_valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and " " not in value
    except (TypeError, ValueError):
        return False

def validate_output_template(value: str) -> bool:
    return bool(value.strip()) and "%(" in value and ")s" in value

def parse_batch_urls(text: str) -> tuple[list[str], list[str], int]:
    """Return valid unique URLs, invalid non-comment lines, and duplicate count."""
    valid, invalid, seen = [], [], set()
    duplicates = 0
    for raw_line in text.splitlines():
        value = raw_line.strip().lstrip("\ufeff")
        if not value or value.startswith("#"):
            continue
        if not is_valid_url(value):
            invalid.append(value)
            continue
        key = canonicalize_url(value)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key); valid.append(value)
    return valid, invalid, duplicates
