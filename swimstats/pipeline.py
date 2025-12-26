import sqlite3
from typing import Callable, Dict, Optional

from .db import file_is_new_or_changed, upsert_file, replace_results_for_file
from .detect import is_results_pdf
from .parse import parse_splash_results
from .webdav import walk_pdfs, download_file

ProgressCB = Callable[[int, int, str, str], None]


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
    pdfs = list(walk_pdfs(category_path))
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
        pdf_bytes = download_file(e.path)

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
