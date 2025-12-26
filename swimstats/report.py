import os
import re
from datetime import datetime
from typing import List, Tuple, Optional, Callable

import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .plots import plot_combined_event
from .stats import (
    compute_percentiles,
    seconds_to_time_str,
    estimate_percentile_positions,
)


def _safe_filename(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _-]+", "", s).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:120] if s else "report"


def _save_fig_to_png(fig, png_path: str) -> None:
    fig.savefig(png_path, dpi=160)
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass


def _wrap_text_by_chars(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = cur + " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _rank_estimate(all_times: List[float], best_time: float) -> Tuple[int, int, float]:
    arr = np.array(all_times, dtype=float)
    n = int(arr.size)
    rank_best = 1 + int(np.sum(arr < best_time))
    ties = int(np.sum(arr == best_time))
    tie_share = 100.0 * ties / n if n else 0.0
    return rank_best, n, tie_share


def _draw_table(
    c: canvas.Canvas,
    x0: float,
    y0: float,
    col_widths: List[float],
    header: List[str],
    rows: List[List[str]],
    row_h: float = 0.55 * cm,
    font: str = "Helvetica",
    font_bold: str = "Helvetica-Bold",
    font_size: int = 9,
    max_rows: Optional[int] = None,
) -> float:
    c.setFont(font_bold, font_size)
    x = x0
    for i, h in enumerate(header):
        c.drawString(x, y0, h)
        x += col_widths[i]

    y = y0 - row_h
    c.setFont(font, font_size)

    count = 0
    for r in rows:
        if max_rows is not None and count >= max_rows:
            break
        x = x0
        for i, cell in enumerate(r):
            c.drawString(x, y, str(cell)[:60])
            x += col_widths[i]
        y -= row_h
        count += 1

    return y


def generate_swimmer_report_pdf(
    out_pdf_path: str,
    swimmer_name: str,
    category_path: str,
    sex: str,
    age: int,
    events: List[str],
    get_event_data_fn: Callable[[str], Tuple[List[Tuple[str, float]], List[float]]],
    invert_y: bool = True,
    date_from_iso: Optional[str] = None,
    date_to_iso: Optional[str] = None,
    min_n_for_percentiles: int = 5,
    include_full_detail_pages: bool = False,
) -> str:
    os.makedirs(os.path.dirname(out_pdf_path) or ".", exist_ok=True)

    c = canvas.Canvas(out_pdf_path, pagesize=A4)
    w, h = A4

    # Portada
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, h - 2.5*cm, "Informe de resultados — Natación")

    c.setFont("Helvetica", 11)
    c.drawString(2*cm, h - 3.6*cm, f"Nadador/a: {swimmer_name}")
    c.drawString(2*cm, h - 4.3*cm, f"Ámbito (carpeta): {category_path}")
    c.drawString(2*cm, h - 5.0*cm, f"Grupo: {sex} {age}")

    if date_from_iso or date_to_iso:
        c.drawString(2*cm, h - 5.7*cm, f"Rango de fechas: {date_from_iso or '—'} a {date_to_iso or '—'}")

    c.drawString(2*cm, h - 6.4*cm, f"Eventos incluidos: {len(events)}")
    c.drawString(2*cm, h - 7.1*cm, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()

    tmp_dir = os.path.join(os.path.dirname(out_pdf_path) or ".", ".tmp_report_imgs")
    os.makedirs(tmp_dir, exist_ok=True)

    for idx, event in enumerate(events, start=1):
        swimmer_points, all_times = get_event_data_fn(event)

        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, h - 2.0*cm, f"{idx}. {event}")

        if not swimmer_points:
            c.setFont("Helvetica", 11)
            c.drawString(2*cm, h - 3.0*cm, "No hay resultados del nadador/a para este evento con el filtro aplicado.")
            c.showPage()
            continue

        if (not all_times) or (len(all_times) < min_n_for_percentiles):
            c.setFont("Helvetica", 11)
            c.drawString(2*cm, h - 3.0*cm, f"Datos globales insuficientes para percentiles (mínimo {min_n_for_percentiles}).")
            c.setFont("Helvetica-Bold", 11)
            c.drawString(2*cm, h - 4.2*cm, "Resultados del nadador/a (detalle)")
            rows = [[d, seconds_to_time_str(t), f"{t:.2f}"] for d, t in swimmer_points]
            _draw_table(
                c, x0=2*cm, y0=h - 5.0*cm,
                col_widths=[7*cm, 3*cm, 3*cm],
                header=["Fecha", "Tiempo", "Tiempo (s)"],
                rows=rows,
                row_h=0.55*cm,
                font_size=9,
                max_rows=22
            )
            c.showPage()
            continue

        # Figura
        title = f"{event} — {category_path} — {sex} {age}\n{swimmer_name}"
        fig = plot_combined_event(swimmer_points, all_times, title=title, invert_y=invert_y)

        png_name = _safe_filename(f"{idx}_{event}") + ".png"
        png_path = os.path.join(tmp_dir, png_name)
        _save_fig_to_png(fig, png_path)

        img_x = 2*cm
        img_y = h - 15.2*cm
        img_w = w - 4*cm
        img_h = 10.8*cm
        c.drawImage(png_path, img_x, img_y, width=img_w, height=img_h, preserveAspectRatio=True, anchor='c')

        p = compute_percentiles(all_times)
        n = len(all_times)
        mn = float(np.min(all_times))
        md = float(np.median(all_times))
        mx = float(np.max(all_times))

        ys = [t for _, t in swimmer_points]
        best_time = float(min(ys))
        last_time = float(ys[-1])

        best_p_time, best_faster_than = estimate_percentile_positions(all_times, best_time)
        last_p_time, last_faster_than = estimate_percentile_positions(all_times, last_time)

        rank_best, n_rank, tie_share = _rank_estimate(all_times, best_time)

        base_y = 5.6*cm

        c.setFont("Helvetica-Bold", 11)
        c.drawString(2*cm, base_y, "Percentiles (tiempo)")
        c.setFont("Helvetica", 10)

        perc_line = " | ".join([f"P{k}: {seconds_to_time_str(v)}" for k, v in sorted(p.items())])
        wrapped = _wrap_text_by_chars(perc_line, max_chars=105)
        y = base_y - 0.65*cm
        for line in wrapped[:2]:
            c.drawString(2*cm, y, line)
            y -= 0.55*cm

        c.setFont("Helvetica-Bold", 11)
        c.drawString(2*cm, y - 0.2*cm, "Distribución (grupo)")
        c.setFont("Helvetica", 10)
        c.drawString(2*cm, y - 0.85*cm,
                     f"N={n} | min={seconds_to_time_str(mn)} | mediana={seconds_to_time_str(md)} | max={seconds_to_time_str(mx)}")

        c.setFont("Helvetica-Bold", 11)
        c.drawString(2*cm, y - 1.65*cm, "Posición estimada (según mejor tiempo)")
        c.setFont("Helvetica", 10)
        c.drawString(2*cm, y - 2.30*cm,
                     f"Mejor tiempo: {seconds_to_time_str(best_time)} ({best_time:.2f}s) | "
                     f"Rank ≈ {rank_best}/{n_rank} | Empates: {tie_share:.1f}%")
        c.drawString(2*cm, y - 2.90*cm,
                     f"Percentil (tiempo): P{best_p_time:.1f} | Más rápido que: {best_faster_than:.1f}%")
        c.drawString(2*cm, y - 3.50*cm,
                     f"Último tiempo: {seconds_to_time_str(last_time)} ({last_time:.2f}s) | "
                     f"Percentil: P{last_p_time:.1f} | Más rápido que: {last_faster_than:.1f}%")

        # Tabla corta en la misma página
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2*cm, 2.2*cm, "Resultados del nadador/a (detalle)")

        rows = [[d, seconds_to_time_str(t), f"{t:.2f}"] for d, t in swimmer_points]
        _draw_table(
            c,
            x0=2*cm,
            y0=1.6*cm,
            col_widths=[7*cm, 3*cm, 3*cm],
            header=["Fecha", "Tiempo", "Tiempo (s)"],
            rows=rows,
            row_h=0.50*cm,
            font_size=9,
            max_rows=3,
        )

        c.showPage()

        # Detalle completo solo si se solicita (checkbox)
        if include_full_detail_pages and len(rows) > 3:
            c.setFont("Helvetica-Bold", 14)
            c.drawString(2*cm, h - 2.0*cm, f"{idx}. {event} — Detalle completo")
            c.setFont("Helvetica", 10)
            c.drawString(2*cm, h - 2.8*cm, f"Nadador/a: {swimmer_name} | Grupo: {sex} {age} | Ámbito: {category_path}")

            y0 = h - 4.0*cm
            per_page = 30
            start = 0
            while start < len(rows):
                page_rows = rows[start:start+per_page]
                _draw_table(
                    c,
                    x0=2*cm,
                    y0=y0,
                    col_widths=[7*cm, 3*cm, 3*cm],
                    header=["Fecha", "Tiempo", "Tiempo (s)"],
                    rows=page_rows,
                    row_h=0.55*cm,
                    font_size=9,
                    max_rows=per_page,
                )
                start += per_page
                if start < len(rows):
                    c.showPage()
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(2*cm, h - 2.0*cm, f"{idx}. {event} — Detalle completo (cont.)")
                    y0 = h - 3.2*cm
            c.showPage()

    c.save()
    return out_pdf_path
