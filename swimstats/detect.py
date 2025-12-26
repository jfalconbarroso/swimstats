import io
import re
import pdfplumber

RANK_LINE = re.compile(
    r"^\s*(\d{1,3})\.\s+.+\s+(\d+:\d{2}[.,]\d{1,2}|\d+:\d{2})\s*$"
)

def score_results_pdf(pdf_bytes: bytes, max_pages: int = 2) -> int:
    score = 0
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            blob = "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
    except Exception:
        return 0

    up = blob.upper()

    if "SPLASH MEET MANAGER" in up:
        score += 3
    if "RESULTADOS" in up:
        score += 2
    if re.search(r"\bPRUEBA\s+\d+\b", up):
        score += 2
    if "CLASIFICACIÓN" in up and "TIEMPO" in up:
        score += 2

    hits = 0
    for line in blob.splitlines():
        if RANK_LINE.match(line.strip()):
            hits += 1
    score += min(hits, 6)

    return score

def is_results_pdf(pdf_bytes: bytes, threshold: int = 6) -> tuple[bool, int]:
    s = score_results_pdf(pdf_bytes)
    return (s >= threshold), s
