from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class QueueEtaResult:
    seconds: float | None
    confidence: str
    unknown_items: int = 0
    paused_items: int = 0
    waiting_for_speed: bool = False
    postprocessing_items: int = 0


def estimate_queue_eta(items: list[dict[str, Any]], concurrency: int, fallback_speed: float | None, postprocess_seconds: float = 10.0, now: float = 0.0) -> QueueEtaResult:
    """Estimate queue makespan using active slots and FIFO future scheduling."""
    concurrency=max(1,int(concurrency)); relevant=[item for item in items if item.get("status") not in {"Completed","Failed","Cancelled"}]
    paused=sum(item.get("status") in {"Paused","Pausing…"} for item in relevant)
    if paused:return QueueEtaResult(None,"paused",paused_items=paused)
    slots=[]; unknown=0; known_sizes=0; waiting_for_speed=False; processing=0
    active=[item for item in relevant if item.get("request") is not None and item.get("status","").startswith(("Downloading","Post-processing"))]
    for item in active:
        status=item.get("status","")
        if status.startswith("Post-processing"):
            processing+=1; elapsed=max(0.0,now-float(item.get("postprocess_started") or now)); slots.append(max(1.0,postprocess_seconds-elapsed)); continue
        estimate=(item.get("estimate") or {}).get("bytes"); progress=max(0.0,min(100.0,float(item.get("progress") or 0))); speed=item.get("speed_bytes") or fallback_speed
        if estimate is None:unknown+=1; slots.append(0.0); continue
        known_sizes+=1
        if not speed or speed<=0:waiting_for_speed=True; slots.append(0.0); continue
        slots.append(max(0.0,float(estimate)*(1-progress/100.0)/float(speed)))
    while len(slots)<concurrency:slots.append(0.0)
    future=[item for item in relevant if item.get("status") in {"Waiting","Estimating size…"}]
    for item in future:
        estimate=(item.get("estimate") or {}).get("bytes")
        if estimate is None:unknown+=1; continue
        known_sizes+=1
        if not fallback_speed or fallback_speed<=0:waiting_for_speed=True; continue
        slot=min(range(len(slots)),key=slots.__getitem__); slots[slot]+=float(estimate)/float(fallback_speed)
    if waiting_for_speed:return QueueEtaResult(None,"unknown",unknown,waiting_for_speed=True,postprocessing_items=processing)
    if unknown and not known_sizes and not processing:return QueueEtaResult(None,"unknown",unknown,postprocessing_items=processing)
    seconds=max(slots,default=0.0)
    if not isfinite(seconds):return QueueEtaResult(None,"unknown",unknown,waiting_for_speed=True,postprocessing_items=processing)
    confidence="lower_bound" if unknown else ("approximate" if processing or any((item.get("estimate") or {}).get("confidence")!="exact" for item in relevant if (item.get("estimate") or {}).get("bytes") is not None) else "exact")
    return QueueEtaResult(seconds,confidence,unknown,waiting_for_speed=waiting_for_speed,postprocessing_items=processing)
