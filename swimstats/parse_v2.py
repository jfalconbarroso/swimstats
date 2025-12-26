import io
import re
import unicodedata
from typing import List, Dict, Optional, Tuple

import pdfplumber

from .stats import time_to_seconds
from .events import extract_event_and_category

PLACE_DATE_LINE = re.compile(r"^(?P<place>.+),\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*$", re.IGNORECASE)

EVENT_LINE = re.compile(
    r"^PRUEBA\s+(?P<num>\d+)\s+"
    r"(?P<sex>FEM\.|MASC\.)\s*,?\s*"
    r"(?P<rest>.+?)\s*$",
    re.IGNORECASE
)

TIME_AT_END = re.compile(
    r"("
    r"\d+:\d{2}(?:[.,]\s*\d{1,2})?"  # mm:ss or mm:ss.xx (allow spaces)
    r"|\d{1,3}[.,]\s*\d{1,2}"        # ss.xx (allow spaces)
    r")\s*$"
)

POS_PREFIX = re.compile(r"^\d{1,3}\.\s+")


# Detect start of a swimmer token in lines that contain multiple swimmers (e.g., relay/lane summaries)
NAME_START = re.compile(r"[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ ]+,\s*[A-Za-zÁÉÍÓÚÜÑ]")

def split_multi_swimmer_lines(ln: str) -> list[str]:
    """Split a single extracted line into multiple swimmer sub-lines when two (or more)
    comma-separated 'SURNAME, Name' patterns appear in the same line."""
    starts = [m.start() for m in NAME_START.finditer(ln)]
    if len(starts) <= 1:
        return [ln]
    starts.append(len(ln))
    return [ln[starts[i]:starts[i+1]].strip() for i in range(len(starts) - 1)]

# The numeric token is 2-digit birth-year (YY), not age.
MIN_YY = 0
MAX_YY = 99

# def normalize_name(s: str) -> str:
#     return re.sub(r"\s+", " ", (s or "").strip())

def _extract_name_yob2(prefix: str) -> Tuple[str, Optional[int]]:
    s = POS_PREFIX.sub("", prefix).strip()
    s = re.sub(r"\s+", " ", s)

    # NEW: fix PDF “glue” between columns, e.g. "Lola12A.D." -> "Lola 12 A.D."
    s = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[A-Za-zÁÉÍÓÚÜÑáéíóúüñ])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    nums = [(m.start(), int(m.group(1))) for m in re.finditer(r"\b(\d{1,2})\b", s)]
    yy = None
    cut = None
    for start, val in reversed(nums):
        if MIN_YY <= val <= MAX_YY:
            yy = val
            cut = start
            break

    if yy is not None and cut is not None and cut > 1:
        name = s[:cut].strip()
        return normalize_name(name), yy

    tokens = s.split(" ")
    out = []
    for t in tokens:
        if re.fullmatch(r"\d{1,3}", t):
            break
        out.append(t)
    return normalize_name(" ".join(out)), None

# def _extract_name_yob2(prefix: str) -> Tuple[str, Optional[int]]:
#     s = POS_PREFIX.sub("", prefix).strip()
#     s = re.sub(r"\s+", " ", s)

#     nums = [(m.start(), int(m.group(1))) for m in re.finditer(r"\b(\d{1,2})\b", s)]
#     yy = None
#     cut = None
#     for start, val in reversed(nums):
#         if MIN_YY <= val <= MAX_YY:
#             yy = val
#             cut = start
#             break

#     if yy is not None and cut is not None and cut > 1:
#         name = s[:cut].strip()
#         return normalize_name(name), yy

#     tokens = s.split(" ")
#     out = []
#     for t in tokens:
#         if re.fullmatch(r"\d{1,3}", t):
#             break
#         out.append(t)
#     return normalize_name(" ".join(out)), None

def parse_splash_results(pdf_bytes: bytes, category_path: str) -> List[Dict]:
    rows: List[Dict] = []

    meet_name = None
    meet_place = None
    meet_date = None
    current_event = None
    current_event_num = None
    current_sex = None
    current_cat = None

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            for ln in lines[:10]:
                if meet_name is None and ("LIGA" in ln.upper() or "CONTROL" in ln.upper() or "CAMPEON" in ln.upper()):
                    meet_name = ln.strip()
                m = PLACE_DATE_LINE.match(ln)
                if m and meet_date is None:
                    meet_place = m.group("place").strip()
                    meet_date = m.group("date").strip()

            for ln0 in lines:
                for ln in split_multi_swimmer_lines(ln0):
                    m = EVENT_LINE.match(ln.strip())
                    if m:
                        current_event_num = m.group("num")
                        current_sex = m.group("sex").replace(".", "").upper()
                        rest = (m.group("rest") or "").strip()
                        current_event, current_cat = extract_event_and_category(rest)
                        if current_cat:
                            current_cat = current_cat.upper()
                        continue

                    up = ln.upper()
                    if up.startswith(("DSQ", "NP", "BAJA")):
                        continue

                    # Remove trailing points / deltas (often formatted like times, e.g. '8,00' or '+0,72')
                    ln = re.sub(r"\s+\+\d{1,3},\d{2}\s*$", "", ln)
                    # Remove trailing integer points (e.g., AQUA/FINA points) after the time
                    ln = re.sub(r"\s+\d{1,5}\s*$", "", ln)
                    ln = re.sub(r"\s+\d{1,4},\d{2}\s*$", "", ln)
                    # Some Splash reports use '-' (or an en/em dash) as a placeholder (e.g., '34.73 -').
                    # Strip it so the time token remains at end-of-line for TIME_AT_END.
                    ln = re.sub(r"\s*[-–—]\s*$", "", ln)
                    mt = TIME_AT_END.search(ln)
                    if not mt:
                        continue
                    if not POS_PREFIX.match(ln):
                        continue

                    time_str = re.sub(r"\s+", "", mt.group(1)).replace(",", ".")
                    t_sec = time_to_seconds(time_str)
                    if t_sec is None:
                        continue

                    prefix = ln[:mt.start()].strip()
                    prefix = re.sub(r"\s+", " ", prefix)

                    swimmer, yob2 = _extract_name_yob2(prefix)

                    rows.append({
                        "category": category_path,
                        "meet_name": meet_name,
                        "meet_place": meet_place,
                        "meet_date": meet_date,
                        "event_num": current_event_num,
                        "sex": current_sex,
                        "event": current_event or "UNKNOWN",
                        "event_category": current_cat,
                        "swimmer": swimmer,
                        "age": yob2,  # YY (birth year last 2 digits)
                        "time_seconds": float(t_sec),
                        "raw_line": ln,
                    })

    return rows
def normalize_name(s: str) -> str:
    """Normalize display name: collapse spaces and remove accents."""
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)
