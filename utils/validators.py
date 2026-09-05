import re
from urllib.parse import urlparse
from utils.duplicates import canonicalize_url

def is_valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and " " not in value
    except (TypeError, ValueError):
        return False

def validate_output_template(value: str) -> bool:
    if not isinstance(value,str):return False
    template=value.strip()
    if not template or len(template)>4096 or "\0" in template:return False
    if template.startswith(("/","\\")) or re.match(r"^[A-Za-z]:",template):return False
    if any(part==".." for part in template.replace("\\","/").split("/")):return False
    return bool(re.search(r"%\([^)]+\)[#0+\- .\d]*[a-zA-Z]",template))

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
