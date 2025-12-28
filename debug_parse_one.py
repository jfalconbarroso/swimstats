import json
import sys
from pathlib import Path

from swimstats.parse import parse_splash_results

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_parse_one.py /path/to/file.pdf")
        raise SystemExit(2)

    pdf_path = Path(sys.argv[1])
    rows = parse_splash_results(pdf_path.read_bytes(), category_path=str(pdf_path))

    print(f"Parsed rows: {len(rows)}")
    # quick sanity: show distinct events recovered
    events = sorted({r.get("event") for r in rows if r.get("event")})
    print(f"Distinct events: {len(events)}")
    for e in events[:20]:
        print("  -", e)

    print("\nFirst 30 rows:")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()
