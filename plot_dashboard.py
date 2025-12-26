import os
import sqlite3
from datetime import date
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from swimstats.ui_db import select_database
from swimstats import (
    init_db,
    ensure_migrations,
    compute_percentiles,
    seconds_to_time_str,
    plot_combined_event,
    generate_swimmer_report_pdf,
)


def db_connect(db_path: str) -> sqlite3.Connection:
    conn = init_db(db_path)
    ensure_migrations(conn)
    return conn


def iso_or_none(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def tag_filter(alias: str, tags: Tuple[str, ...]) -> Tuple[str, List[str]]:
    """Build an optional dataset_tag filter.

    When *tags* is empty, the caller wants the full historical series,
    so we return an empty condition and no parameters.
    """
    vals = [t for t in (tags or ()) if t]
    if not vals:
        return "", []
    in_sql = "(" + ",".join(["?"] * len(vals)) + ")"
    return f"AND {alias}.dataset_tag IN {in_sql}", vals


@st.cache_data(ttl=300)
def cached_tags(db_path: str) -> List[str]:
    conn = db_connect(db_path)
    q = """
      SELECT DISTINCT dataset_tag
      FROM results
      WHERE dataset_tag IS NOT NULL AND dataset_tag <> ''
      ORDER BY dataset_tag
    """
    return [r[0] for r in conn.execute(q).fetchall()]


@st.cache_data(ttl=300)
def cached_swimmers(db_path: str, tags: Tuple[str, ...], sex: str, yob2: int) -> pd.DataFrame:
    conn = db_connect(db_path)
    tag_sql, tag_params = tag_filter("results", tags)
    q = f"""
      SELECT
        swimmer_key,
        MIN(swimmer) AS swimmer,
        COUNT(*) AS n
      FROM results
      WHERE 1=1
        {tag_sql}
        AND sex=?
        AND age=?
      GROUP BY swimmer_key
      ORDER BY n DESC, swimmer ASC
    """
    params = tuple(tag_params + [sex, yob2])
    return pd.read_sql_query(q, conn, params=params)


@st.cache_data(ttl=300)
def cached_events(
    db_path: str,
    tags: Tuple[str, ...],
    sex: str,
    yob2: int,
    swimmer_key: str,
    date_from_iso: Optional[str],
    date_to_iso: Optional[str],
) -> List[str]:
    conn = db_connect(db_path)
    tag_sql, tag_params = tag_filter("r", tags)
    lo = date_from_iso or "0001-01-01"
    hi = date_to_iso or "9999-12-31"

    q = f"""
      SELECT DISTINCT r.event
      FROM results r
      LEFT JOIN files f ON f.path = r.file_path
      WHERE 1=1
        {tag_sql}
        AND r.sex = ?
        AND r.age = ?
        AND r.swimmer_key = ?
        AND r.time_seconds IS NOT NULL
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) >= ?)
        )
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) <= ?)
        )
      ORDER BY r.event
    """
    params = tuple(tag_params + [sex, yob2, swimmer_key, lo, hi])
    rows = conn.execute(q, params).fetchall()
    return [r[0] for r in rows if r and r[0]]


def get_swimmer_points(
    conn: sqlite3.Connection,
    tags: Tuple[str, ...],
    sex: str,
    yob2: int,
    swimmer_key: str,
    event: str,
    date_from_iso: Optional[str],
    date_to_iso: Optional[str],
) -> List[Tuple[str, float]]:
    tag_sql, tag_params = tag_filter("r", tags)
    lo = date_from_iso or "0001-01-01"
    hi = date_to_iso or "9999-12-31"

    q = f"""
      SELECT
        COALESCE(r.meet_date_iso, f.last_modified_iso) AS x_label,
        MIN(r.time_seconds) AS time_seconds
      FROM results r
      LEFT JOIN files f ON f.path = r.file_path
      WHERE 1=1
        {tag_sql}
        AND r.sex = ?
        AND r.age = ?
        AND r.swimmer_key = ?
        AND r.event = ?
        AND r.time_seconds IS NOT NULL
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) >= ?)
        )
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) <= ?)
        )
      GROUP BY COALESCE(r.meet_date_iso, f.last_modified_iso)
      ORDER BY COALESCE(r.meet_date_iso, f.last_modified_iso) ASC
    """
    params = tuple(tag_params + [sex, yob2, swimmer_key, event, lo, hi])
    rows = conn.execute(q, params).fetchall()
    return [(x or "", float(t)) for x, t in rows]


def get_all_times(
    conn: sqlite3.Connection,
    tags: Tuple[str, ...],
    sex: str,
    yob2: int,
    event: str,
    date_from_iso: Optional[str],
    date_to_iso: Optional[str],
) -> List[float]:
    tag_sql, tag_params = tag_filter("r", tags)
    lo = date_from_iso or "0001-01-01"
    hi = date_to_iso or "9999-12-31"

    q = f"""
      SELECT r.time_seconds
      FROM results r
      LEFT JOIN files f ON f.path = r.file_path
      WHERE 1=1
        {tag_sql}
        AND r.sex = ?
        AND r.age = ?
        AND r.event = ?
        AND r.time_seconds IS NOT NULL
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) >= ?)
        )
        AND (
          COALESCE(r.meet_date_iso, f.last_modified_iso) IS NULL
          OR (COALESCE(r.meet_date_iso, f.last_modified_iso) <= ?)
        )
    """
    params = tuple(tag_params + [sex, yob2, event, lo, hi])
    return [float(r[0]) for r in conn.execute(q, params).fetchall()]


st.set_page_config(page_title="Natación — Plots", layout="wide")
st.title("Swimstats — Análisis")

with st.sidebar:
    st.header("Base de datos")

    db_path_obj = select_database(key_prefix="plot")
    if not db_path_obj:
        st.stop()
    db_path = str(db_path_obj)


    st.subheader("Ámbito de datos")
    scope_mode = st.radio(
        "Selecciona el ámbito",
        options=["Todo el histórico", "Filtrar por etiqueta"],
        index=0,
    )

    selected_tags: List[str] = []
    existing_tags = cached_tags(db_path)
    if scope_mode == "Filtrar por etiqueta":
        default_tags = existing_tags[-1:] if existing_tags else []
        selected_tags = st.multiselect(
            "Etiquetas a incluir en el análisis",
            options=existing_tags,
            default=default_tags,
        )

    sex = st.selectbox("Sexo", options=["FEM", "MASC"])
    yob2 = int(st.number_input("Año nacimiento (2 dígitos, YY)", min_value=0, max_value=99, value=11, step=1))

    st.subheader("Rango de fechas")
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input("Desde", value=None)
    with c2:
        date_to = st.date_input("Hasta", value=None)
    date_from_iso = iso_or_none(date_from)
    date_to_iso = iso_or_none(date_to)

    # st.subheader("Gráfica")
    # invert_y = st.checkbox("Invertir eje Y (mejor arriba)", value=True)
    invert_y = False

    # st.subheader("Informe PDF")
    # include_full_detail_pages = st.checkbox("Añadir páginas de detalle completo", value=False)


conn = db_connect(db_path)

if scope_mode == "Filtrar por etiqueta" and not selected_tags:
    st.info("Selecciona al menos una etiqueta para analizar, o cambia a 'Todo el histórico'.")
    st.stop()

viz_tags = tuple(selected_tags)  # vacío => todo

swdf = cached_swimmers(db_path, viz_tags, sex, yob2)
if swdf.empty:
    st.info("No hay datos aún para ese filtro. Ajusta etiquetas/YY/sexo.")
    st.stop()

st.sidebar.subheader("Nadador/a")
swimmer = st.sidebar.selectbox(
    "Selecciona nadador/a (ordenado por registros)",
    options=swdf["swimmer"].tolist(),
    index=0,
)
swimmer_key = swdf.loc[swdf["swimmer"] == swimmer, "swimmer_key"].iloc[0]

events = cached_events(db_path, viz_tags, sex, yob2, swimmer_key, date_from_iso, date_to_iso)
if not events:
    st.warning("No hay eventos para este nadador/a con el rango de fechas seleccionado.")
    st.stop()

st.subheader("Selección de eventos")
selected_events = st.multiselect("Eventos", options=events, default=[events[0]])

scope_label = "Todo el histórico" if not viz_tags else " + ".join(viz_tags)

# if selected_events and st.button("Generar informe PDF (eventos seleccionados)"):
#     with st.spinner("Generando PDF..."):
#         out_dir = "reports"
#         os.makedirs(out_dir, exist_ok=True)
#         safe_scope = scope_label.replace(" ", "_").replace("/", "_")
#         safe_sw = "".join([c for c in swimmer if c.isalnum() or c in " _-"]).strip().replace(" ", "_")
#         out_pdf = os.path.join(out_dir, f"report_{safe_sw}_{sex}_YY{yob2:02d}_{safe_scope}.pdf")

#         def get_event_data(event_name: str):
#             all_times = get_all_times(conn, viz_tags, sex, yob2, event_name, date_from_iso, date_to_iso)
#             swimmer_points = get_swimmer_points(conn, viz_tags, sex, yob2, swimmer_key, event_name, date_from_iso, date_to_iso)
#             return swimmer_points, all_times

#         pdf_path = generate_swimmer_report_pdf(
#             out_pdf_path=out_pdf,
#             swimmer_name=swimmer,
#             category_path=scope_label,
#             sex=sex,
#             age=yob2,
#             events=selected_events,
#             get_event_data_fn=get_event_data,
#             invert_y=invert_y,
#             date_from_iso=date_from_iso,
#             date_to_iso=date_to_iso,
#             include_full_detail_pages=include_full_detail_pages,
#         )

#     # with open(pdf_path, "rb") as f:
#     #     st.download_button(
#     #         "Descargar informe PDF",
#     #         data=f.read(),
#     #         file_name=os.path.basename(pdf_path),
#     #         mime="application/pdf",
#     #     )

tabs = st.tabs(selected_events) if selected_events else []
for tab, event in zip(tabs, selected_events):
    with tab:
        colL, colR = st.columns([1, 2], gap="large")

        all_times = get_all_times(conn, viz_tags, sex, yob2, event, date_from_iso, date_to_iso)
        swimmer_points = get_swimmer_points(conn, viz_tags, sex, yob2, swimmer_key, event, date_from_iso, date_to_iso)

        with colL:
            st.markdown(f"### {event}")
            st.markdown(
                f"**Nadador/a:** {swimmer}  \n"
                f"**Grupo (YY):** {sex} {yob2:02d}  \n"
                f"**Etiquetas:** {scope_label}"
            )

            # if len(all_times) >= 5:
            #     p = compute_percentiles(all_times)
            #     df_p = pd.DataFrame(
            #         [{"percentil": k, "tiempo_s": v, "tiempo_fmt": seconds_to_time_str(v)} for k, v in p.items()]
            #     ).sort_values("percentil")
            #     st.markdown("**Percentiles del grupo (sexo + YY)**")
            #     st.dataframe(df_p, use_container_width=True)
            # else:
            #     st.info("Percentiles: no hay suficientes datos globales (mínimo 5).")

            # st.markdown("**Distribución (básico)**")
            # st.write(
            #     {
            #         "N": len(all_times),
            #         "min_s": float(np.min(all_times)) if all_times else None,
            #         "mediana_s": float(np.median(all_times)) if all_times else None,
            #         "max_s": float(np.max(all_times)) if all_times else None,
            #     }
            # )

            st.markdown("**Evolución de marcas**")
            df_sw = pd.DataFrame(swimmer_points, columns=["fecha", "tiempo_s"])
            df_sw["tiempo_fmt"] = df_sw["tiempo_s"].apply(seconds_to_time_str)
            st.dataframe(df_sw, use_container_width=True)

        with colR:
            # st.markdown("### Gráfica combinada")
            st.markdown(f"### {swimmer}")
            if len(all_times) < 5:
                st.warning("No hay suficientes datos globales para percentiles en este evento (mínimo 5).")
            elif len(swimmer_points) == 0:
                st.warning("No hay puntos del nadador/a para este evento con el rango de fechas.")
            else:
                title = f"{event} — {scope_label} — {sex} YY{yob2:02d}\n{swimmer}"
                fig = plot_combined_event(swimmer_points, all_times, title=title, invert_y=invert_y)
                st.pyplot(fig, clear_figure=True)
