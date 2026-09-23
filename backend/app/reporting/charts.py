"""Chart rendering (matplotlib, headless) for the DOCX report. Every renderer returns PNG bytes."""
from __future__ import annotations

import io
import textwrap

import matplotlib

matplotlib.use("Agg")  # headless - no display needed on the server

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from app.reporting.models import ChartData

PALETTE = ["#1F3864", "#2E75B6", "#9DC3E6", "#ED7D31", "#70AD47", "#FFC000", "#7F7F7F", "#C00000", "#5B9BD5", "#A5A5A5"]
FIG_W, FIG_H, DPI = 6.4, 3.3, 200


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#8C8C8C",
            "axes.labelcolor": "#404040",
            "xtick.color": "#404040",
            "ytick.color": "#404040",
            "axes.grid": True,
            "grid.color": "#E3E3E3",
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
        }
    )


def _wrap(label: str, width: int = 22) -> str:
    return "\n".join(textwrap.wrap(str(label), width)[:3]) or str(label)


def _fmt(value: float, unit: str) -> str:
    text = f"{value:,.0f}" if abs(value) >= 100 or float(value).is_integer() else f"{value:,.2f}"
    return f"{text}{unit}" if unit in {"%", "x"} else (f"{text} {unit}".strip() if unit else text)


def render_chart(chart: ChartData) -> bytes:
    _style()
    renderers = {"bar": _bar, "hbar": _hbar, "pie": _pie, "line": _line, "heatmap": _heatmap}
    fig = renderers[chart.kind](chart)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buffer.getvalue()


def _bar(chart: ChartData):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(chart.values))]
    bars = ax.bar(range(len(chart.values)), chart.values, color=colors, width=0.62)
    ax.set_xticks(range(len(chart.labels)))
    ax.set_xticklabels([_wrap(x, 14) for x in chart.labels], fontsize=7.5)
    ax.set_xlabel(chart.x_label)
    ax.set_ylabel(chart.y_label or chart.unit)
    ax.grid(axis="x", visible=False)
    top = max(chart.values) if chart.values else 1
    for rect, value in zip(bars, chart.values):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + top * 0.015, _fmt(value, chart.unit),
                ha="center", va="bottom", fontsize=7.5, color="#202020")
    ax.set_ylim(0, top * 1.15 if top > 0 else 1)
    return fig


def _hbar(chart: ChartData):
    height = max(FIG_H, 0.42 * len(chart.values) + 1.0)
    fig, ax = plt.subplots(figsize=(FIG_W, min(height, 5.2)))
    labels = [_wrap(x, 34) for x in chart.labels]
    positions = range(len(chart.values))
    bars = ax.barh(positions, chart.values, color=PALETTE[1], height=0.6)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel(chart.x_label or chart.unit)
    ax.grid(axis="y", visible=False)
    top = max(chart.values) if chart.values else 1
    for rect, value in zip(bars, chart.values):
        ax.text(rect.get_width() + top * 0.01, rect.get_y() + rect.get_height() / 2, _fmt(value, chart.unit),
                va="center", fontsize=7.5, color="#202020")
    ax.set_xlim(0, top * 1.15 if top > 0 else 1)
    return fig


def _pie(chart: ChartData):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(chart.values))]
    total = sum(chart.values) or 1
    wedges, _ = ax.pie(chart.values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.5})
    ax.legend(
        wedges,
        [f"{_wrap(label, 30)}  ({value / total:.0%})" for label, value in zip(chart.labels, chart.values)],
        loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8,
    )
    ax.set_aspect("equal")
    ax.grid(False)
    return fig


def _line(chart: ChartData):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.plot(range(len(chart.values)), chart.values, color=PALETTE[1], marker="o", linewidth=2, markersize=5)
    ax.set_xticks(range(len(chart.labels)))
    ax.set_xticklabels([_wrap(x, 12) for x in chart.labels], fontsize=7.5)
    ax.set_xlabel(chart.x_label)
    ax.set_ylabel(chart.y_label or chart.unit)
    for i, value in enumerate(chart.values):
        ax.annotate(_fmt(value, chart.unit), (i, value), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7.5)
    ax.margins(y=0.15)
    return fig


def _heatmap(chart: ChartData):
    """5x5 likelihood x impact risk matrix with risk ids placed in their cells."""
    fig, ax = plt.subplots(figsize=(FIG_W * 0.8, FIG_W * 0.62))
    cmap = LinearSegmentedColormap.from_list("risk", ["#C6E0B4", "#FFE699", "#F4B183", "#E06666"])
    grid = [[(likelihood * impact) for likelihood in range(1, 6)] for impact in range(1, 6)]
    ax.imshow(grid, cmap=cmap, origin="lower", extent=(0.5, 5.5, 0.5, 5.5), vmin=1, vmax=25, aspect="auto")
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xticklabels(["Rare", "Unlikely", "Possible", "Likely", "Almost\ncertain"], fontsize=7.5)
    ax.set_yticklabels(["Minor", "Moderate", "Significant", "Major", "Severe"], fontsize=7.5)
    ax.set_xlabel("Likelihood")
    ax.set_ylabel("Impact")
    ax.grid(True, color="white", linewidth=1.5)
    ax.set_axisbelow(False)
    cells: dict[tuple[int, int], list[str]] = {}
    for risk_id, likelihood, impact in chart.points:
        cells.setdefault((likelihood, impact), []).append(risk_id)
    for (likelihood, impact), ids in cells.items():
        ax.text(likelihood, impact, "\n".join(", ".join(ids[i : i + 2]) for i in range(0, len(ids), 2)),
                ha="center", va="center", fontsize=8, fontweight="bold", color="#1A1A1A")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return fig
