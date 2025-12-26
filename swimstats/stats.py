import math
import re
from typing import Optional, Dict, List

import numpy as np

_TIME_PATTERNS = [
    re.compile(r"^(?P<m>\d+):(?P<s>\d{2})[.,](?P<cs>\d{1,2})$"),
    re.compile(r"^(?P<m>\d+):(?P<s>\d{2})$"),
    re.compile(r"^(?P<s>\d{1,2})[.,](?P<cs>\d{1,2})$"),
]

def time_to_seconds(t: str) -> Optional[float]:
    t = t.strip()
    for p in _TIME_PATTERNS:
        m = p.match(t)
        if not m:
            continue
        gd = m.groupdict()
        minutes = int(gd.get("m") or 0)
        seconds = int(gd["s"])
        centis = int(gd.get("cs") or 0)
        if gd.get("cs") is None:
            return minutes * 60 + seconds
        if len(gd["cs"]) == 1:
            centis *= 10
        return minutes * 60 + seconds + centis / 100.0
    return None

def compute_percentiles(times: List[float], ps=(0.01, 25, 50, 75, 99.9)) -> Dict[int, float]:
    arr = np.array(times, dtype=float)
    qs = np.array(ps) / 100.0
    vals = np.quantile(arr, qs, method="linear")
    return {p: float(v) for p, v in zip(ps, vals)}

def estimate_percentile_positions(all_times: List[float], value: float) -> tuple[float, float]:
    arr = np.array(all_times, dtype=float)
    n = arr.size
    le = float(np.sum(arr <= value))
    ge = float(np.sum(arr >= value))
    p_time = 100.0 * le / n
    faster_than = 100.0 * ge / n
    return p_time, faster_than

def seconds_to_time_str(sec: float) -> str:
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return ""
    m = int(sec // 60)
    s = sec - 60 * m
    if m > 0:
        return f"{m}:{s:05.2f}"
    return f"{s:.2f}"
