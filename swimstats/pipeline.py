import sqlite3
from typing import Callable, Dict, Optional

from .db import file_is_new_or_changed, upsert_file, replace_results_for_file
from .detect import is_results_pdf
from .parse import parse_splash_results
from .webdav import walk_pdfs as walk_pdfs_webdav, download_file as download_file_webdav

ProgressCB = Callable[[int, int, str, str], None]


# --- Local filesystem support -------------------------------------------------
# The pipeline historically synced PDFs via WebDAV. For local-directory sync we
# treat absolute filesystem paths as "categories" and walk/read PDFs directly.
from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import datetime
from typing import Iterator


def _normalize_category_path(p: str) -> str:
    """Normalize a potentially-local category path.

    This is intentionally forgiving because some stored paths may be missing a
    leading '/' (e.g., 'Users/…' instead of '/Users/…').
    """
    if not p:
        return p
    p2 = os.path.expanduser(p.strip())
    # If it looks like a macOS home path missing a leading slash, fix it.
    if not p2.startswith(("/", "\\")) and (p2.startswith("Users/") or p2.startswith("Users\\") or p2.startswith("private/var/") or p2.startswith("private\\var\\") ):
        p2 = "/" + p2
    # If it exists as-is, resolve it to an absolute canonical path.
    try:
        pp = Path(p2)
        if pp.exists():
            return str(pp.resolve())
        # If it doesn't exist but adding a leading '/' makes it exist, use that.
        if not p2.startswith("/") and Path("/" + p2).exists():
            return str(Path("/" + p2).resolve())
    except Exception:
        pass
    return p2


def _is_local_path(p: str) -> bool:
    """True if `p` points to something that exists on the local filesystem.

    Falls back to simple heuristics when the path does not exist (e.g., when the
    user configured a path that is temporarily offline).
    """
    if not p:
        return False
    p2 = _normalize_category_path(p)
    try:
        if Path(p2).exists():
            return True
    except Exception:
        pass
    # Heuristic: absolute POSIX path (/...), or Windows drive path (C:\...).
    if p2.startswith("/"):
        return True
    return len(p2) >= 3 and p2[1] == ":" and p2[2] in ("\\", "/")

@dataclass(frozen=True)
class _FileEntry:
    """
    Minimal file metadata shim compatible with db.file_is_new_or_changed and
    db.upsert_file, which historically consumed the WebDAV entry shape.

    We include a few common attribute names (path/etag/size/mtime/modified/href)
    to maximize compatibility with existing DB code.
    """
    path: str
    etag: str
    size: int
    mtime: int  # unix epoch seconds
    modified: str  # RFC3339-ish string
    href: str  # alias of path (for WebDAV parity)


def _local_etag(path: Path, size: int, mtime: int) -> str:
    # Stable, cheap fingerprint; avoids hashing entire file.
    h = hashlib.sha1()
    h.update(str(path).encode("utf-8", "ignore"))
    h.update(b"\x00")
    h.update(str(size).encode("ascii"))
    h.update(b"\x00")
    h.update(str(mtime).encode("ascii"))
    return h.hexdigest()


def walk_pdfs_local(root_dir: str) -> Iterator[_FileEntry]:
    root = Path(root_dir)
    if not root.exists() or not root.is_dir():
        return
    # Match both .pdf and .PDF
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".pdf":
            st = p.stat()
            size = int(st.st_size)
            mtime = int(st.st_mtime)
            yield _FileEntry(
                path=str(p),
                etag=_local_etag(p, size, mtime),
                size=size,
                mtime=mtime,
                modified=datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).isoformat(),
                href=str(p),
            )


def download_file_local(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
# ------------------------------------------------------------------------------

def sync_category(
    conn: sqlite3.Connection,
    category_path: str,
    progress_cb: Optional[ProgressCB] = None,
    dataset_tag: str = "",
) -> Dict[str, int]:
    """Incrementally sync a WebDAV directory into the database.

    - Only new/changed PDFs are reprocessed (etag/size tracked in `files`).
    - `dataset_tag` is stored both in `files.dataset_tag` and `results.dataset_tag`.
    - progress_cb(done, total, path, stage) is called periodically.
    """
    category_path = _normalize_category_path(category_path)
    is_local = _is_local_path(category_path)
    pdfs = list(walk_pdfs_local(category_path) if is_local else walk_pdfs_webdav(category_path))
    total = len(pdfs)

    processed = 0
    skipped = 0
    non_results = 0
    results_files = 0
    results_but_zero_rows = 0

    done = 0
    if progress_cb:
        progress_cb(done, total, category_path, "scan")

    for e in pdfs:
        if not file_is_new_or_changed(conn, e):
            skipped += 1
            done += 1
            if progress_cb:
                progress_cb(done, total, e.path, "skip_unchanged")
            continue

        if progress_cb:
            progress_cb(done, total, e.path, "download")
        pdf_bytes = download_file_local(e.path) if is_local else download_file_webdav(e.path)

        if progress_cb:
            progress_cb(done, total, e.path, "detect")

        is_res, score = is_results_pdf(pdf_bytes)
        upsert_file(conn, e, is_results=int(is_res), results_score=int(score), dataset_tag=dataset_tag)

        if is_res:
            if progress_cb:
                progress_cb(done, total, e.path, "parse_store")
            rows = parse_splash_results(pdf_bytes, category_path=category_path)
            for r in rows:
                r["dataset_tag"] = dataset_tag
            if not rows:
                results_but_zero_rows += 1
            replace_results_for_file(conn, e.path, rows)
            results_files += 1
        else:
            non_results += 1

        processed += 1
        done += 1
        if progress_cb:
            progress_cb(done, total, e.path, "done")

    return {
        "pdfs_encontrados": total,
        "procesados": processed,
        "omitidos_sin_cambios": skipped,
        "pdfs_resultados": results_files,
        "pdfs_no_resultados": non_results,
        "resultados_detectados_sin_filas": results_but_zero_rows,
    }


def sync_multiple_categories(
    conn: sqlite3.Connection,
    category_paths,
    progress_cb: Optional[ProgressCB] = None,
    dataset_tag: str = "",
) -> Dict[str, int]:
    """Sync multiple directories into the same DB with the same dataset_tag."""
    category_paths = list(category_paths or [])
    total_dirs = len(category_paths)

    agg = {
        "dirs": total_dirs,
        "pdfs_encontrados": 0,
        "procesados": 0,
        "omitidos_sin_cambios": 0,
        "pdfs_resultados": 0,
        "pdfs_no_resultados": 0,
        "resultados_detectados_sin_filas": 0,
    }

    for i, cat in enumerate(category_paths, start=1):
        if progress_cb:
            progress_cb(i - 1, total_dirs, cat, "dir_start")
        stats = sync_category(
            conn,
            cat,
            progress_cb=progress_cb,
            dataset_tag=dataset_tag,
        )
        for k in ("pdfs_encontrados","procesados","omitidos_sin_cambios","pdfs_resultados","pdfs_no_resultados","resultados_detectados_sin_filas"):
            agg[k] += int(stats.get(k, 0))
        if progress_cb:
            progress_cb(i, total_dirs, cat, "dir_done")

    return agg
