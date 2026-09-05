import re

_PATTERNS = [
    (re.compile(r"(?im)(extractor[_ -]?args\s*[:=]\s*)[^\r\n]+"), r"\1<redacted>"),
    (re.compile(r"(?im)\b(cookie|set-cookie|authorization)\s*:\s*[^\r\n]+"), r"\1: <redacted>"),
    (re.compile(r"(?i)(authorization|cookie|token|password|api[_-]?key)\s*[:=]\s*([^\s,;]+)"), r"\1=<redacted>"),
    (re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@"), r"\1<redacted>@"),
]

def redact(text: object) -> str:
    result = str(text)
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result
