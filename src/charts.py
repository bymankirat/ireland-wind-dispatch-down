"""Figures for the report. Two colours: blue for this estimate, grey for EirGrid's figures."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BLUE, GREY, INK, MUTED, GRID = "#1f5f8b", "#9aa3ab", "#1d2733", "#5b6672", "#e3e6e9"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.dpi": 150, "savefig.bbox": "tight",
})


def yearly_vs_official(m: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(m))
    ax.bar(x - 0.18, m["official_curtailment_pct"], 0.34, color=GREY, label="EirGrid published curtailment")
    err = np.vstack([m["lost_pct"] - m["ci_low"], m["ci_high"] - m["lost_pct"]])
    ax.bar(x + 0.18, m["lost_pct"], 0.34, color=BLUE, label="This estimate (95% interval)")
    ax.errorbar(x + 0.18, m["lost_pct"], yerr=err, fmt="none", ecolor=INK, elinewidth=1.2, capsize=3)
    ax.set_xticks(x, m["year"].astype(str))
    ax.set_ylabel("% of available wind energy")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)


def monthly_at_cap(mo: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    t = pd.to_datetime(mo["month"])
    ax.plot(t, mo["at_cap_pct"], color=BLUE, lw=2)
    ax.set_ylabel("% of hours at the SNSP limit")
    ax.set_ylim(bottom=0)
    ax.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)


def hour_profile(hr: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.bar(hr["hour"], hr["lost_share_pct"], color=BLUE, width=0.8)
    ax.set_xlabel("Hour of day (Irish time)")
    ax.set_ylabel("% of estimated lost energy")
    ax.set_xticks(range(0, 24, 3))
    ax.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)


def driver_heatmap(t: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    im = ax.imshow(t.values, cmap="Blues", origin="lower", vmin=0, aspect="auto")
    for i in range(t.shape[0]):
        for j in range(t.shape[1]):
            v = t.values[i, j]
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                    color="white" if v > 0.55 * np.nanmax(t.values) else INK)
    e = t.attrs.get("edges", {})
    wl = [f"{e['wind_fc_mw'][k]:,.0f}–{e['wind_fc_mw'][k + 1]:,.0f}" for k in range(5)] if e else range(1, 6)
    dl = [f"{e['demand_mw'][k]:,.0f}–{e['demand_mw'][k + 1]:,.0f}" for k in range(5)] if e else range(1, 6)
    ax.set_xticks(range(5), wl, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(5), dl, fontsize=8)
    ax.set_xlabel("Forecast wind (MW, fifths of hours)")
    ax.set_ylabel("Demand (MW, fifths of hours)")
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="% of hours at the limit", shrink=0.85)
    fig.savefig(path)
    plt.close(fig)


def placebo(est: pd.DataFrame, pla: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    x = np.arange(len(est))
    ax.bar(x - 0.18, pla["lost_pct"], 0.34, color=GREY, label="Placebo: hours with under 1,000 MW of forecast wind")
    ax.bar(x + 0.18, est["lost_pct"], 0.34, color=BLUE, label="All hours (the estimate)")
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(x, est["year"].astype(str))
    ax.set_ylabel("Estimated lost wind, %")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)


def ratio_lines(t: pd.DataFrame, path):
    """Actual / forecast wind by forecast band, for the lowest and highest demand quarters."""
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(t))
    ax.plot(x, t["Highest demand"], "-o", color=GREY, lw=2, ms=5, label="Busiest quarter of hours (baseline)")
    ax.plot(x, t["Lowest demand"], "-o", color=BLUE, lw=2, ms=5, label="Quietest quarter of hours")
    ax.fill_between(x, t["Lowest demand"], t["Highest demand"], color=BLUE, alpha=0.12, lw=0)
    ax.axhline(1, color=INK, lw=0.8)
    ax.set_xticks(x, [s.split("–")[0] for s in t.index], rotation=0, fontsize=8)
    ax.set_xlabel("Forecast wind, MW (start of each 500 MW band)")
    ax.set_ylabel("Actual ÷ forecast wind")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    ax.grid(axis="x", visible=False)
    fig.savefig(path)
    plt.close(fig)
