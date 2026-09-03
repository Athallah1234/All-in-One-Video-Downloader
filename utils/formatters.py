from datetime import timedelta

def format_size(value: int | float | None) -> str:
    if value is None or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return "—"

def format_duration(value: int | float | None) -> str:
    if value is None or value < 0:
        return "—"
    return str(timedelta(seconds=int(value)))

def format_speed(value: int | float | None) -> str:
    return "—" if not value else f"{format_size(value)}/s"

