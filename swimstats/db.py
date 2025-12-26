import sqlite3
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, Optional

from .normalize import norm_key


def _normalize_iso(value: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD from either an ISO string or an RFC 2822 date string."""
    if not value:
        return None
    v = str(value).strip()
    # Already ISO-like
    if len(v) >= 10 and v[4] == "-" and v[7] == "-":
        return v[:10]
    # Try RFC 2822 (HTTP-date)
    try:
        dt = parsedate_to_datetime(v)
        return dt.date().isoformat()
    except Exception:
        return None


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            etag TEXT,
            size INTEGER,
            last_modified TEXT,
            last_modified_iso TEXT,
            is_results INTEGER DEFAULT 0,
            results_score INTEGER DEFAULT 0,
            dataset_tag TEXT DEFAULT ''
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT,
            category TEXT,
            event TEXT,
            swimmer TEXT,
            swimmer_key TEXT,
            sex TEXT,
            age INTEGER,
            dataset_tag TEXT DEFAULT '',
            time_seconds REAL,
            raw_line TEXT,
            meet_date_iso TEXT,
            FOREIGN KEY(file_path) REFERENCES files(path) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_results_lookup
        ON results (dataset_tag, sex, age, event, swimmer_key)
        """
    )

    # User-managed list of WebDAV directories that belong to this database.
    # This enables a dedicated "sync" UI that manages folders separately from
    # the analysis/plotting UI.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS included_categories (
            category_path TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            added_at_iso TEXT DEFAULT (DATE('now')),
            note TEXT DEFAULT ''
        )
        """
    )


MIGRATIONS = [
    "ALTER TABLE files ADD COLUMN dataset_tag TEXT DEFAULT ''",
    "ALTER TABLE results ADD COLUMN dataset_tag TEXT DEFAULT ''",
]


def ensure_migrations(conn: sqlite3.Connection) -> None:
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            # Column already exists (or other harmless schema mismatch)
            pass


def file_is_new_or_changed(conn: sqlite3.Connection, e) -> bool:
    row = conn.execute(
        "SELECT etag, size FROM files WHERE path = ?", (e.path,)
    ).fetchone()
    if not row:
        return True
    return row[0] != e.etag or row[1] != e.size


def upsert_file(
    conn: sqlite3.Connection,
    e,
    is_results: int,
    results_score: int,
    dataset_tag: str = "",
) -> None:
    # Some DavEntry variants expose last_modified_iso, others last_modified (HTTP date).
    last_mod_iso = _normalize_iso(getattr(e, "last_modified_iso", None) or getattr(e, "last_modified", None))

    conn.execute(
        """
        INSERT INTO files
            (path, etag, size, last_modified, last_modified_iso,
             is_results, results_score, dataset_tag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            etag=excluded.etag,
            size=excluded.size,
            last_modified=excluded.last_modified,
            last_modified_iso=excluded.last_modified_iso,
            is_results=excluded.is_results,
            results_score=excluded.results_score,
            dataset_tag=excluded.dataset_tag
        """,
        (
            e.path,
            getattr(e, "etag", None),
            getattr(e, "size", None),
            getattr(e, "last_modified", None),
            last_mod_iso,
            is_results,
            results_score,
            dataset_tag,
        ),
    )


def replace_results_for_file(
    conn: sqlite3.Connection,
    file_path: str,
    rows: Iterable[Dict],
) -> None:
    conn.execute("DELETE FROM results WHERE file_path = ?", (file_path,))

    for r in rows:
        conn.execute(
            """
            INSERT INTO results (
                file_path, category, event, swimmer, swimmer_key,
                sex, age, dataset_tag, time_seconds, raw_line, meet_date_iso
            )
            VALUES (
                :file_path, :category, :event, :swimmer, :swimmer_key,
                :sex, :age, :dataset_tag, :time_seconds, :raw_line, :meet_date_iso
            )
            """,
            {
                "file_path": file_path,
                "category": r.get("category", ""),
                "event": r.get("event"),
                "swimmer": r.get("swimmer"),
                "swimmer_key": norm_key(r.get("swimmer")),
                "sex": r.get("sex"),
                "age": r.get("age"),
                "dataset_tag": r.get("dataset_tag", ""),
                "time_seconds": r.get("time_seconds"),
                "raw_line": r.get("raw_line"),
                "meet_date_iso": r.get("meet_date_iso"),
            },
        )

    conn.commit()


def list_included_categories(conn: sqlite3.Connection, enabled_only: bool = True):
    q = "SELECT category_path FROM included_categories"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY category_path"
    return [r[0] for r in conn.execute(q).fetchall()]


def add_included_categories(conn: sqlite3.Connection, category_paths):
    paths = [p.strip("/") for p in (category_paths or []) if p and str(p).strip()]
    for p in paths:
        conn.execute(
            """
            INSERT INTO included_categories (category_path, enabled)
            VALUES (?, 1)
            ON CONFLICT(category_path) DO UPDATE SET enabled=1
            """,
            (p,),
        )
    conn.commit()


def remove_included_categories(conn: sqlite3.Connection, category_paths):
    paths = [p.strip("/") for p in (category_paths or []) if p and str(p).strip()]
    for p in paths:
        conn.execute("DELETE FROM included_categories WHERE category_path = ?", (p,))
    conn.commit()


def set_category_enabled(conn: sqlite3.Connection, category_path: str, enabled: bool) -> None:
    conn.execute(
        "UPDATE included_categories SET enabled=? WHERE category_path=?",
        (1 if enabled else 0, category_path.strip("/")),
    )
    conn.commit()
