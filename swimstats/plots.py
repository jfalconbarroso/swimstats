import numpy as np
from typing import List, Tuple
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable


from .stats import compute_percentiles, estimate_percentile_positions, seconds_to_time_str

def clean_values(times):

    times = np.asarray(times) 

    # Filtering out potentially wrong values in the histogramming
    median = np.median(times)
    mad = np.median(np.abs(times - median))
    z = 0.6745 * (times - median) / mad
    good = (np.abs(z) <= 3.5)
    good_times = times[good]

    return good_times

def plot_combined_event(
    swimmer_points: List[Tuple[str, float]],
    all_times: List[float],
    title: str,
    invert_y: bool = False
) -> plt.Figure:

    xs = list(range(len(swimmer_points)))
    xlabels = [pt[0] for pt in swimmer_points]
    ys = [pt[1] for pt in swimmer_points]

    n = len(all_times)
    best_time = min(ys)
    best_idx = ys.index(best_time)

    fig = plt.figure()
    ax = plt.gca()

    ax.plot(xs, ys, marker="o", label="Nadador/a", mec='black', zorder=2)
    ax.scatter([best_idx], [best_time], s=80, label="Mejor marca", ec='black',zorder=3)

    all_times = clean_values(all_times)
    p = compute_percentiles(all_times)


    col = ['green','yellow','orange','red']
    perc = [0.01, 25, 50, 75, 99.9]
    nperc = len(perc)-1
    lims = ax.get_xlim()
    for i in range(nperc):
        ax.fill_between(lims, [p[perc[i]],p[perc[i]]], [p[perc[i+1]],p[perc[i+1]]], color=col[i], alpha=0.10, zorder=1)

    for perc in (0.01, 25, 50, 75, 99.9):
        ax.hlines(p[perc], xmin=lims[0], xmax=lims[1], linestyles="--", label=f"P{perc}", color='black',zorder=0, alpha=0.5)

    # Create divider
    divider = make_axes_locatable(ax)

    # Append histogram axis on the right
    ax_hist = divider.append_axes(
        "right",
        size="25%",   # width relative to main axes
        pad=0.1,
        sharey=ax
    )

    # Histogram (horizontal!)
    ax_hist.hist(
        all_times,
        bins=30,
        orientation="horizontal",
        alpha=0.4
    )

    ax_hist.set_xlabel("Nº nadadores")

    # Cosmetic cleanup
    plt.setp(ax_hist.get_yticklabels(), visible=False)
    ax_hist.tick_params(axis="y", length=0)
    ax_hist.tick_params(axis="x", length=0)





    # ax.set_title(title)
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Tiempo (s)")
    ax.set_xticks(xs)
    ax.set_xticklabels(xlabels, rotation=45, ha="right")

    if invert_y:
        ax.invert_yaxis()

    # summary = (
    #     f"N (muestra): {n}\n"
    #     f"Mejor tiempo: {seconds_to_time_str(best_time)} ({best_time:.2f}s)\n"
    #     f"  Percentil (tiempo): P{best_p_time:.1f}\n"
    #     f"  Más rápido que: {best_faster_than:.1f}%\n"
    #     f"Último tiempo: {seconds_to_time_str(last_time)} ({last_time:.2f}s)\n"
    #     f"  Percentil (tiempo): P{last_p_time:.1f}\n"
    #     f"  Más rápido que: {last_faster_than:.1f}%"
    # )

    # ax.text(
    #     0.02, 0.98, summary,
    #     transform=ax.transAxes,
    #     va="top", ha="left",
    #     bbox=dict(boxstyle="round", pad=0.4, alpha=0.85)
    # )
    # ax.legend()

    # fig.tight_layout()
    return fig
