"""Synthetic hourly data with a planted loss, for tests and an offline dry run.

Available wind follows a seasonal, autocorrelated pattern; the forecast is available wind with
noise. SNSP rises with wind and falls with demand, and is clipped at the limit. In hours at the
limit, a known share of available wind is removed. The pipeline should find that share again.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make(years=(2023, 2024), cap=75.0, planted_loss=1.0, seed=1, fc_bias=0.0) -> tuple[pd.DataFrame, float]:
    """fc_bias > 0 makes the forecast over-predict more in windy hours, as EirGrid's does."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-31 23:00", freq="h")
    n = len(idx)
    doy = idx.dayofyear.to_numpy()
    hour = idx.hour.to_numpy()
    season = 1 + 0.35 * np.cos(2 * np.pi * (doy - 15) / 365)
    z = np.zeros(n)
    e = rng.normal(0, 1, n)
    for i in range(1, n):
        z[i] = 0.97 * z[i - 1] + 0.25 * e[i]
    avail = np.clip(2200 * season * np.exp(0.55 * z) - 300, 0, 5500)
    demand = 4500 + 900 * np.sin(np.pi * (hour - 6) / 16).clip(0) + 500 * (season - 1) + rng.normal(0, 120, n)
    possible = avail * (0.97 + rng.normal(0, 0.01, n))       # 3% normal shortfall (local constraints)
    # the SNSP limit: wind is cut just enough to bring (wind + 300) / (demand + 600) down to the cap;
    # planted_loss scales how much of that cut happens (0 = none, 1 = all)
    allowed = cap / 100 * (demand + 600) - 300
    excess = np.clip(possible - allowed, 0, None)
    wind = possible - planted_loss * excess
    snsp = (100 * (wind + 300) / (demand + 600) - rng.uniform(0, 1.5, n) * (excess > 0)).clip(0, 100)
    fc = avail * (1 + fc_bias * avail / 5000) * (1 + rng.normal(0, 0.08, n))
    h = pd.DataFrame({"wind_mw": wind, "wind_fc_mw": fc, "snsp_pct": snsp, "demand_mw": demand}, index=idx)
    h.index.name = "time"
    lost = (planted_loss * excess).sum()
    true_pct = 100 * lost / (wind.sum() + lost)
    return h, float(true_pct)
