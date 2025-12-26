import os
import sqlite3
import time
from typing import List, Optional

import streamlit as st

from swimstats.ui_db import select_or_create_database
from swimstats.webdav import list_directories_recursive
from swimstats import (
    init_db,
    ensure_migrations,
    sync_multiple_categories,
    list_included_categories,
    add_included_categories,
    remove_included_categories,
)


def db_connect(db_path: str) -> sqlite3.Connection:
    conn = init_db(db_path)
    ensure_migrations(conn)
    return conn


def fmt_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0 or seconds != seconds:
        return "—"
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    if m > 0:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


st.set_page_config(page_title="Natación — Sync", layout="wide")
st.title("Natación — SYNC (gestión de carpetas por base de datos)")

with st.sidebar:
    st.header("Base de datos")

    db_path_obj = select_or_create_database(key_prefix="sync")
    if not db_path_obj:
        st.stop()
    db_path = str(db_path_obj)

conn = db_connect(db_path)

st.subheader("Carpetas incluidas en esta DB")
included = list_included_categories(conn, enabled_only=False)

if included:
    st.write("Estas carpetas se consideran parte de la base de datos seleccionada.")
    st.code("\n".join(included), language="text")
else:
    st.info("Aún no hay carpetas incluidas. Añade una o más desde el panel inferior.")

colA, colB = st.columns(2, gap="large")

with colA:
    st.markdown("### Añadir carpetas")
    # base_root = st.text_input("Ruta raíz para listar directorios", value="").strip("/")
    # max_depth = int(st.number_input("Profundidad máxima de listado", min_value=1, max_value=12, value=6, step=1))
    base_root = ""
    max_depth = 1

    with st.spinner("Cargando lista de directorios..."):
        all_dirs = list_directories_recursive(base_root, max_depth=max_depth)

    if not all_dirs:
        st.warning("No se han encontrado directorios bajo esa raíz. Prueba con raíz vacía o menor profundidad.")
        all_dirs = []

    to_add = st.multiselect(
        "Selecciona directorios para añadir",
        options=all_dirs,
        default=[d for d in all_dirs if "2. TENERIFE" in d][:1],
    )

    if st.button("Añadir a esta DB"):
        if not to_add:
            st.error("Selecciona al menos un directorio para añadir.")
        else:
            add_included_categories(conn, to_add)
            st.success(f"Añadidos: {len(to_add)}")
            st.rerun()

with colB:
    st.markdown("### Quitar carpetas")
    to_remove = st.multiselect("Selecciona directorios para eliminar", options=included, default=[])
    if st.button("Eliminar de esta DB"):
        if not to_remove:
            st.error("Selecciona al menos un directorio para eliminar.")
        else:
            remove_included_categories(conn, to_remove)
            st.success(f"Eliminados: {len(to_remove)}")
            st.rerun()

st.divider()
st.subheader("SYNC incremental")

dataset_tag = st.text_input(
    "Etiqueta manual (dataset_tag) para este sync (ej: 2024-25, control_noviembre)",
    value="",
).strip()

included_enabled = list_included_categories(conn, enabled_only=True)
st.caption(f"Carpetas habilitadas: {len(included_enabled)}")

do_sync = st.button("SYNC (todas las carpetas incluidas)")

if do_sync:
    if not dataset_tag:
        st.error("Debes introducir una etiqueta (dataset_tag) antes de sincronizar.")
        st.stop()
    if not included_enabled:
        st.error("No hay carpetas incluidas para sincronizar.")
        st.stop()

    progress = st.progress(0.0)
    status = st.empty()
    t0 = time.time()

    def _cb(done: int, total: int, path: str, stage: str) -> None:
        now = time.time()
        elapsed = max(now - t0, 1e-6)
        if total and total > 0:
            progress.progress(min(done / total, 1.0))
            rate = done / elapsed
            remaining = total - done
            eta = (remaining / rate) if rate > 0 else None
        else:
            progress.progress(0.0)
            eta = None
        status.write(f"**{stage}** — {done}/{total} — ETA: {fmt_eta(eta)} — `{path}`")

    with st.spinner("Sincronizando..."):
        stats = sync_multiple_categories(conn, included_enabled, progress_cb=_cb, dataset_tag=dataset_tag)

    progress.progress(1.0)
    status.write("SYNC completado.")
    st.success("SYNC completado")
    st.json(stats)
