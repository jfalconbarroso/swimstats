import re
import unicodedata

def strip_accents(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s

def norm_key(s: str) -> str:
    """Stable key for swimmer names: remove accents, normalize whitespace/punctuation, uppercase."""
    s = strip_accents(s or "")
    s = s.upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
