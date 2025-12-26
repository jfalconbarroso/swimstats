import re
from typing import Optional, Tuple

STROKES = {
    "LIBRE": ["LIBRE", "LIBRES", "CROL", "CRAWL", "FREE", "FREESTYLE"],
    "ESPALDA": ["ESPALDA", "BACK", "BACKSTROKE"],
    "BRAZA": ["BRAZA", "BRASA", "BREAST", "BREASTSTROKE"],
    "MARIPOSA": ["MARIPOSA", "FLY", "BUTTERFLY"],
    "ESTILOS": ["ESTILOS", "MEDLEY", "IM"],
}

_VARIANTS = [(canon, v) for canon, vs in STROKES.items() for v in vs]
_STROKE_TOKEN_RE = r"|".join(sorted({re.escape(v) for _, v in _VARIANTS}, key=len, reverse=True))

_EVENT_RE = re.compile(
    rf"\b(?P<dist>\d{{2,4}})\s*(?:m\b|M\b)?\s*(?P<stroke>{_STROKE_TOKEN_RE})\b",
    re.IGNORECASE
)

def _canonical_stroke(token: str) -> Optional[str]:
    t = token.strip().upper()
    for canon, v in _VARIANTS:
        if t == v.upper():
            return canon
    return None

def normalize_event_name(raw_event: str) -> Tuple[str, Optional[int], Optional[str]]:
    s = (raw_event or "").strip()
    s = re.sub(r"\s+", " ", s)
    m = _EVENT_RE.search(s)
    if m:
        dist = int(m.group("dist"))
        stroke = _canonical_stroke(m.group("stroke"))
        if stroke:
            disp = "Libre" if stroke == "LIBRE" else stroke.capitalize()
            return f"{dist}m {disp}", dist, stroke
    m2 = re.search(r"\b(\d{2,4})\b", s)
    dist = int(m2.group(1)) if m2 else None
    return s, dist, None

def extract_event_and_category(rest: str) -> Tuple[str, Optional[str]]:
    s = (rest or "").strip()
    s = re.sub(r"\s+", " ", s)
    m = _EVENT_RE.search(s)
    if not m:
        ev, _, _ = normalize_event_name(s)
        return ev, None
    dist = int(m.group("dist"))
    stroke = _canonical_stroke(m.group("stroke")) or "UNKNOWN"
    disp = "Libre" if stroke == "LIBRE" else stroke.capitalize()
    event = f"{dist}m {disp}"
    cat = (s[:m.start()] + " " + s[m.end():]).strip()
    cat = re.sub(r"\s+", " ", cat).strip() or None
    return event, cat
