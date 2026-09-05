from dataclasses import dataclass
import random

PERMANENT_MARKERS=(
    "drm", "unsupported url", "not a valid url", "private video", "video is private",
    "sign in to confirm", "login required", "authentication required", "members-only",
    "not available in your country", "geo-restricted", "no source format matches",
    "requested format is not available", "invalid sponsorblock", "invalid ffmpeg filter",
    "http error 400", "http error 401", "http error 404", "http error 410",
    "permission denied", "no space left", "insufficient free disk", "filename too long",
    "integrity verification failed after automatic retries", "download cancelled",
)

@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    reason: str

def classify_failure(error:BaseException|str) -> RetryDecision:
    message=str(error).strip();lower=message.casefold()
    marker=next((value for value in PERMANENT_MARKERS if value in lower),None)
    if marker:return RetryDecision(False,f"Permanent failure ({marker})")
    return RetryDecision(True,"Transient or unclassified failure")

def exponential_backoff(attempt:int,base_seconds:float,max_seconds:float,jitter_percent:int=0,rng=None) -> float:
    if attempt<1:raise ValueError("attempt must be at least 1")
    if base_seconds<0 or max_seconds<0 or not 0<=jitter_percent<=100:raise ValueError("invalid backoff configuration")
    delay=min(float(max_seconds),float(base_seconds)*(2**(attempt-1)))
    if delay and jitter_percent:
        generator=rng or random;spread=delay*jitter_percent/100;delay=generator.uniform(max(0,delay-spread),delay+spread)
    return max(0.0,delay)
