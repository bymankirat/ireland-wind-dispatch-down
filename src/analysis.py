"""How much wind is turned down for system-wide reasons, estimated from public data.

Idea in one paragraph. EirGrid publishes a forecast of wind output and the actual output. The
forecast's own errors depend on how windy it is (it over-predicts in windy hours), not on how
much electricity people are using. System-wide limits (the SNSP limit, minimum numbers of
conventional units) bind when demand is low. So, among hours with the same forecast wind, in
the same year and season, a lower actual/forecast ratio in low-demand hours than in high-demand
hours is the footprint of system-wide curtailment. The busiest quarter of hours is the baseline;
the shortfall of the other hours below it is the estimate. Hours with little forecast wind,
where system limits cannot bind, act as a placebo: the same calculation there should give ~0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import AT_CAP_MARGIN, CAP_QUANTILE, FC_BIN_MW, N_BOOT, OFFICIAL_ALL_ISLAND, SEED

N_BINS = 11          # forecast wind bands of 500 MW; the last is open-ended (5,000 MW and above)
N_SEASONS = 4        # Dec-Feb, Mar-May, Jun-Aug, Sep-Nov
PLACEBO_MAX_BIN = 1  # forecast under 1,000 MW: system limits essentially never bind


def yearly_caps(h: pd.DataFrame) -> dict[int, float]:
    """The SNSP operating limit each year, read from the data (99.5th percentile, rounded)."""
    q = h["snsp_pct"].groupby(h.index.year).quantile(CAP_QUANTILE)
    return {int(y): float(np.round(v)) for y, v in q.items()}


def fc_bin(fc) -> np.ndarray:
    return np.clip((np.asarray(fc, dtype=float) // FC_BIN_MW).astype(int), 0, N_BINS - 1)


def classify(h: pd.DataFrame, caps: dict[int, float], seasonal: bool = True) -> pd.DataFrame:
    """Adds year, season, forecast band, demand quarter (within year and season) and whether the
    hour is within 2 points of the SNSP limit (used only to describe when the limit binds)."""
    d = h.dropna(subset=["wind_mw", "wind_fc_mw", "demand_mw"]).copy()
    d["year"] = d.index.year
    d["season"] = (d.index.month % 12) // 3 if seasonal else 0
    d["bin"] = fc_bin(d["wind_fc_mw"])
    d["dq"] = d.groupby(["year", "season"])["demand_mw"].transform(lambda s: pd.qcut(s, 4, labels=False))
    d["cap"] = d["year"].map(caps)
    d["at_cap"] = d["snsp_pct"].notna() & (d["snsp_pct"] >= d["cap"] - AT_CAP_MARGIN)
    d["usable"] = True
    return d


def _fill_bins(r: np.ndarray) -> np.ndarray:
    """Forecast bands with no baseline hours take the ratio of the nearest band with data."""
    r = r.copy()
    for k in range(1, r.shape[-1]):
        r[..., k] = np.where(np.isnan(r[..., k]), r[..., k - 1], r[..., k])
    for k in range(r.shape[-1] - 2, -1, -1):
        r[..., k] = np.where(np.isnan(r[..., k]), r[..., k + 1], r[..., k])
    return r


def _daily_parts(g: pd.DataFrame, max_bin: int | None = None) -> np.ndarray:
    """Per-day sums for one year, by season x forecast band, so days resample as whole units.
    Layout: [w_top, f_top, w_rest, f_rest] each of size S*B, then w_all, n_hours."""
    S, B = N_SEASONS, N_BINS
    cell = g["season"].to_numpy() * B + g["bin"].to_numpy()
    top = g["dq"].to_numpy() == 3
    use = np.ones(len(g), bool) if max_bin is None else g["bin"].to_numpy() <= max_bin
    w, f = g["wind_mw"].to_numpy(), g["wind_fc_mw"].to_numpy()
    day = pd.factorize(g.index.normalize())[0]
    nd = day.max() + 1
    out = np.zeros((nd, 4 * S * B + 2))
    for j, (vals, mask) in enumerate([(w, top), (f, top), (w, ~top & use), (f, ~top & use)]):
        idx = day * (4 * S * B + 2) + j * S * B + cell
        np.add.at(out.ravel(), idx[mask], vals[mask])
    np.add.at(out[:, -2], day, w)
    np.add.at(out[:, -1], day, 1.0)
    return out


def _estimate(s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """s: summed parts. Returns (lost MWh, % of available wind)."""
    S, B = N_SEASONS, N_BINS
    n = S * B
    w_top, f_top = s[..., 0:n], s[..., n:2 * n]
    w_rest, f_rest = s[..., 2 * n:3 * n], s[..., 3 * n:4 * n]
    w_all = s[..., 4 * n]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(f_top > 0, w_top / f_top, np.nan)
    r = _fill_bins(r.reshape(r.shape[:-1] + (S, B))).reshape(r.shape)
    lost = np.nansum(r * f_rest, axis=-1) - w_rest.sum(axis=-1)
    pct = 100 * lost / (w_all + lost)
    return lost, pct


def lost_energy(d: pd.DataFrame, placebo: bool = False, n_boot: int = N_BOOT, seed: int = SEED) -> pd.DataFrame:
    """Per year: estimated wind turned down for system-wide reasons (GWh and % of available),
    with a 95% interval from resampling whole days. placebo=True counts only low-wind hours."""
    rng = np.random.default_rng(seed)
    out = []
    for y, g in d.groupby("year"):
        parts = _daily_parts(g, PLACEBO_MAX_BIN if placebo else None)
        n = len(parts)
        if n < 20:
            continue
        total = parts.sum(axis=0)
        lost, pct = _estimate(total)
        idx = rng.integers(0, n, size=(n_boot, n))
        _, bpct = _estimate(parts[idx].sum(axis=1))
        out.append({"year": int(y), "lost_gwh": float(lost) / 1000, "lost_pct": float(pct),
                    "ci_low": float(np.nanpercentile(bpct, 2.5)), "ci_high": float(np.nanpercentile(bpct, 97.5)),
                    "wind_gwh": float(total[-2]) / 1000, "days": int(n),
                    "share_of_hours_pct": float(100 * g["at_cap"].mean())})
    return pd.DataFrame(out)


def ratio_table(d: pd.DataFrame) -> pd.DataFrame:
    """Actual / forecast wind by forecast band and demand quarter, all years: the evidence."""
    t = d.groupby(["bin", "dq"]).apply(lambda g: g["wind_mw"].sum() / g["wind_fc_mw"].sum(),
                                       include_groups=False).unstack()
    t.index = [f"{int(b * FC_BIN_MW):,}–{int((b + 1) * FC_BIN_MW):,}" if b < N_BINS - 1 else f"{int(b * FC_BIN_MW):,}+"
               for b in t.index]
    t.columns = ["Lowest demand", "Second", "Third", "Highest demand"]
    return t


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
    """Share of hours at the SNSP limit, and share of the estimated lost energy, by hour of day."""
    g = d[d["year"].isin(years)].copy()
    S, B = N_SEASONS, N_BINS
    g["expected"] = np.nan
    for y, gy in g.groupby("year"):
        top = gy[gy["dq"] == 3]
        w = top.groupby(["season", "bin"])["wind_mw"].sum()
        f = top.groupby(["season", "bin"])["wind_fc_mw"].sum()
        r = np.full((S, B), np.nan)
        for (se, b), v in (w / f).items():
            r[int(se), int(b)] = v
        r = _fill_bins(r)
        g.loc[gy.index, "expected"] = r[gy["season"].to_numpy(), gy["bin"].to_numpy()] * gy["wind_fc_mw"].to_numpy()
    g["lost"] = (g["expected"] - g["wind_mw"]).where(g["dq"] < 3, 0.0)
    hr = g.groupby(g.index.hour).agg(at_cap=("at_cap", "mean"), lost=("lost", "sum"))
    hr["at_cap_pct"] = 100 * hr["at_cap"]
    hr["lost_share_pct"] = 100 * hr["lost"] / hr["lost"].sum()
    hr.index.name = "hour"
    return hr[["at_cap_pct", "lost_share_pct"]].reset_index()


def drivers(d: pd.DataFrame, years: list[int], bins: int = 5) -> pd.DataFrame:
    """Chance of being at the limit by demand quintile and wind-forecast quintile."""
    g = d[d["year"].isin(years)].copy()
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
