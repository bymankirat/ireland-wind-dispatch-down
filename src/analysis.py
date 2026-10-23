"""How much wind is lost to the all-island SNSP limit, estimated from public data.

Idea in one paragraph. EirGrid publishes a forecast of wind output and the actual output. In
hours when the system is well below its SNSP limit, the ratio actual / forecast shows how the
forecast normally relates to what is generated, including local constraints and ordinary
forecast error. In hours at the limit, wind has to be turned down for system-wide reasons. If
actual output in those hours falls below what the normal ratio predicts, the gap estimates the
energy lost to system-wide curtailment. A placebo band of hours just under the limit, where no
system-wide curtailment should occur, tests whether the method invents losses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import (AT_CAP_MARGIN, CAP_QUANTILE, FREE_MARGIN, MIN_FC_MW, N_BOOT,
                    OFFICIAL_ALL_ISLAND, SEED)

PLACEBO_BAND = (12.0, 6.0)   # hours 6 to 12 points under the limit: close to it, not at it


def yearly_caps(h: pd.DataFrame) -> dict[int, float]:
    """The operating limit each year, read from the data (99.5th percentile, rounded)."""
    q = h["snsp_pct"].groupby(h.index.year).quantile(CAP_QUANTILE)
    return {int(y): float(np.round(v)) for y, v in q.items()}


def classify(h: pd.DataFrame, caps: dict[int, float]) -> pd.DataFrame:
    d = h.copy()
    d["year"] = d.index.year
    d["cap"] = d["year"].map(caps)
    ok = d[["wind_mw", "wind_fc_mw", "snsp_pct"]].notna().all(axis=1) & (d["wind_fc_mw"] >= MIN_FC_MW)
    d["usable"] = ok
    d["at_cap"] = ok & (d["snsp_pct"] >= d["cap"] - AT_CAP_MARGIN)
    d["free"] = ok & (d["snsp_pct"] <= d["cap"] - FREE_MARGIN)
    lo, hi = PLACEBO_BAND
    d["placebo"] = ok & (d["snsp_pct"] > d["cap"] - lo) & (d["snsp_pct"] <= d["cap"] - hi)
    return d


def _daily_parts(d: pd.DataFrame, band: str) -> pd.DataFrame:
    """Per-day sums the estimate is built from, so days can be resampled as whole units."""
    day = d.index.normalize()
    f = d["free"]
    b = d[band]
    parts = pd.DataFrame({
        "w_free": d["wind_mw"].where(f, 0.0), "f_free": d["wind_fc_mw"].where(f, 0.0),
        "w_band": d["wind_mw"].where(b, 0.0), "f_band": d["wind_fc_mw"].where(b, 0.0),
        "w_all": d["wind_mw"].fillna(0.0), "n_band": b.astype(float),
    })
    return parts.groupby(day).sum()


def _estimate(s: np.ndarray) -> tuple[float, float]:
    """s columns: w_free, f_free, w_band, f_band, w_all, n_band (summed). Returns (lost MWh, %)."""
    w_free, f_free, w_band, f_band, w_all = s[..., 0], s[..., 1], s[..., 2], s[..., 3], s[..., 4]
    ratio = np.divide(w_free, f_free, out=np.full_like(w_free, np.nan), where=f_free > 0)
    lost = ratio * f_band - w_band
    pct = 100 * lost / (w_all + lost)
    return lost, pct


def lost_energy(d: pd.DataFrame, band: str = "at_cap", n_boot: int = N_BOOT,
                seed: int = SEED) -> pd.DataFrame:
    """Per year: hours in the band, normal ratio, lost energy (GWh) and % of available wind,
    with a 95% interval from resampling whole days."""
    rng = np.random.default_rng(seed)
    out = []
    for y, g in d.groupby("year"):
        parts = _daily_parts(g, band).to_numpy()
        n = len(parts)
        if n < 20:
            continue
        total = parts.sum(axis=0)
        lost, pct = _estimate(total)
        idx = rng.integers(0, n, size=(n_boot, n))
        boot = parts[idx].sum(axis=1)
        _, bpct = _estimate(boot)
        hours_usable = int(g["usable"].sum())
        out.append({
            "year": int(y), "hours_in_band": int(total[5]),
            "share_of_hours_pct": 100 * total[5] / max(hours_usable, 1),
            "normal_ratio": total[0] / total[1] if total[1] else np.nan,
            "band_ratio": total[2] / total[3] if total[3] else np.nan,
            "lost_gwh": lost / 1000, "lost_pct": pct,
            "ci_low": float(np.nanpercentile(bpct, 2.5)), "ci_high": float(np.nanpercentile(bpct, 97.5)),
            "wind_gwh": total[4] / 1000, "days": int(n),
        })
    return pd.DataFrame(out)


def compare_official(est: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    off = pd.DataFrame([{"year": y, "official_curtailment_pct": v[0], "official_constraint_pct": v[1],
                         "official_total_pct": v[2]} for y, v in OFFICIAL_ALL_ISLAND.items()])
    m = est.merge(off, on="year", how="inner")
    m["difference_pts"] = m["lost_pct"] - m["official_curtailment_pct"]
    summary = {"years": int(len(m))}
    if len(m) >= 3:
        summary["pearson_r"] = float(np.corrcoef(m["lost_pct"], m["official_curtailment_pct"])[0, 1])
        summary["mean_abs_diff_pts"] = float(m["difference_pts"].abs().mean())
        summary["mean_diff_pts"] = float(m["difference_pts"].mean())
        summary["years_official_inside_ci"] = int(((m["official_curtailment_pct"] >= m["ci_low"]) &
                                                    (m["official_curtailment_pct"] <= m["ci_high"])).sum())
    return m, summary


def by_hour(d: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Share of hours at the limit and share of the estimated lost energy, by hour of day."""
    g = d[d["year"].isin(years)].copy()
    ratio = {}
    for y, gy in g.groupby("year"):
        f = gy["free"]
        ratio[y] = gy.loc[f, "wind_mw"].sum() / gy.loc[f, "wind_fc_mw"].sum()
    g["expected"] = g["year"].map(ratio) * g["wind_fc_mw"]
    g["lost"] = (g["expected"] - g["wind_mw"]).where(g["at_cap"], 0.0)
    hr = g.groupby(g.index.hour).agg(at_cap=("at_cap", "mean"), lost=("lost", "sum"))
    hr["at_cap_pct"] = 100 * hr["at_cap"]
    hr["lost_share_pct"] = 100 * hr["lost"] / hr["lost"].sum()
    hr.index.name = "hour"
    return hr[["at_cap_pct", "lost_share_pct"]].reset_index()


def drivers(d: pd.DataFrame, years: list[int], bins: int = 5) -> pd.DataFrame:
    """Chance of being at the limit by demand quintile and wind-forecast quintile."""
    g = d[d["year"].isin(years) & d["usable"] & d["demand_mw"].notna()].copy()
    g["demand_q"] = pd.qcut(g["demand_mw"], bins, labels=False) + 1
    g["wind_q"] = pd.qcut(g["wind_fc_mw"], bins, labels=False) + 1
    t = g.groupby(["demand_q", "wind_q"])["at_cap"].mean().mul(100).unstack()
    edges = {"demand_mw": pd.qcut(g["demand_mw"], bins, retbins=True)[1].round(0).tolist(),
             "wind_fc_mw": pd.qcut(g["wind_fc_mw"], bins, retbins=True)[1].round(0).tolist()}
    t.attrs["edges"] = edges
    return t


def monthly(d: pd.DataFrame) -> pd.DataFrame:
    m = d.groupby(d.index.to_period("M")).agg(
        at_cap_pct=("at_cap", "mean"), snsp_mean=("snsp_pct", "mean"),
        wind_gwh=("wind_mw", "sum"))
    m["at_cap_pct"] *= 100
    m["wind_gwh"] /= 1000
    m.index = m.index.astype(str)
    m.index.name = "month"
    return m.reset_index()
