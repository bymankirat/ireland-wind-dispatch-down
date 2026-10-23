"""Automatic checks. A failed check stops the run, and every check is written to a log."""

from __future__ import annotations

import pandas as pd


def fix_units(h: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes = []
    if h["snsp_pct"].dropna().quantile(0.99) <= 1.5:  # published as a fraction, not a percent
        h = h.copy()
        h["snsp_pct"] *= 100
        notes.append("SNSP arrived as a fraction and was converted to percent")
    return h, notes


def run_checks(h: pd.DataFrame, counts: dict | None = None) -> tuple[list[dict], bool]:
    checks = []

    def add(name, ok, detail, hard=True):
        checks.append({"check": name, "result": "pass" if ok else ("FAIL" if hard else "warn"),
                       "detail": detail})

    full = pd.date_range(h.index.min(), h.index.max(), freq="h")
    for c in h.columns:
        cov = h[c].reindex(full).notna().mean()
        add(f"coverage {c}", cov >= 0.97, f"{100 * cov:.2f}% of hours present")
    w, f, s, dm = h["wind_mw"], h["wind_fc_mw"], h["snsp_pct"], h["demand_mw"]
    add("wind in plausible range", w.between(-50, 7000).mean() > 0.999,
        f"min {w.min():.0f} MW, max {w.max():.0f} MW")
    add("wind forecast in plausible range", f.between(-50, 8000).mean() > 0.999,
        f"min {f.min():.0f} MW, max {f.max():.0f} MW")
    add("SNSP in 0-100%", s.between(0, 100).mean() > 0.999, f"min {s.min():.1f}%, max {s.max():.1f}%")
    add("demand in plausible range", dm.between(2000, 9000).mean() > 0.995,
        f"min {dm.min():.0f} MW, max {dm.max():.0f} MW")
    corr = w.corr(f)
    add("forecast tracks actual wind", corr > 0.85, f"correlation {corr:.3f}")
    stuck = (w.diff().abs() < 1e-9).rolling(6).sum().ge(6).sum()
    add("no stuck wind readings (6+ identical hours)", stuck < 24, f"{int(stuck)} stuck hours", hard=False)
    if counts:
        for k, v in counts.items():
            add(f"duplicates {k}", v["duplicates"] < 0.001 * max(v["readings"], 1),
                f"{v['duplicates']} duplicate timestamps of {v['readings']:,}", hard=False)
    ok = all(c["result"] != "FAIL" for c in checks)
    return checks, ok
