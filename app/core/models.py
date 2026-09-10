"""Serializable queue state; worker threads communicate using signal payloads."""
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class Status(StrEnum):
    WAITING = "Waiting"
    ANALYZING = "Analyzing"
    DOWNLOADING = "Downloading"
    PROCESSING = "Processing"
    PAUSING = "Pausing"
    PAUSED = "Paused"
    RETRYING = "Retrying"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


TERMINAL = {Status.COMPLETED, Status.FAILED, Status.CANCELLED}


@dataclass
class Task:
    url: str
    options: dict = field(repr=False)
    media_type: str = "Video"
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "Waiting for metadata"
    status: str = Status.WAITING
    progress: float = 0
    speed: float = 0
    eta: float | None = None
    file_size: int = 0
    downloaded: int = 0
    file_path: str = ""
    extractor: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: str = field(default="", repr=False)
    fragment: str = ""
    item: str = ""
    history_id: int | None = None
    retry_attempt: int = 0
    retry_limit: int = 0
    retry_delay: int = 0
    next_retry_at: str = ""
