"""Offline tests: run with `python tests/run_tests.py`. No downloads needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import analysis as A  # noqa: E402
import demo  # noqa: E402
import quality as Q  # noqa: E402

passed = 0


def check(name, cond, detail=""):
    global passed
    if not cond:
        raise AssertionError(f"FAILED: {name} {detail}")
    passed += 1
    print(f"  ok  {name} {detail}")


# 1. the limit is found from the data
h, true_pct = demo.make()
caps = A.yearly_caps(h)
check("limit detected at 75%", all(abs(c - 75) <= 1 for c in caps.values()), str(caps))

# 2. the planted loss is recovered, inside its interval
d = A.classify(h, caps)
est = A.lost_energy(d, n_boot=300)
overall = 100 * est["lost_gwh"].sum() / (est["wind_gwh"].sum() + est["lost_gwh"].sum())
check("planted loss recovered within 0.5 points", abs(overall - true_pct) < 0.5,
      f"estimated {overall:.2f}% vs planted {true_pct:.2f}%")
check("planted loss inside each year's 95% interval",
      ((est["ci_low"] <= true_pct + 0.6) & (est["ci_high"] >= true_pct - 0.6)).all(),
      est[["year", "lost_pct", "ci_low", "ci_high"]].round(2).to_dict("records"))

# 3. no loss planted -> estimate near zero
h0, t0 = demo.make(planted_loss=0.0, seed=3)
e0 = A.lost_energy(A.classify(h0, A.yearly_caps(h0)), n_boot=200)
check("no planted loss gives about zero", (e0["lost_pct"].abs() < 0.3).all() and t0 == 0,
      e0["lost_pct"].round(3).tolist())

# 4. placebo band finds nothing on data with a planted loss
ep = A.lost_energy(d, band="placebo", n_boot=200)
check("placebo band about zero", (ep["lost_pct"].abs() < 0.3).all(), ep["lost_pct"].round(3).tolist())

# 5. hand-checked arithmetic on a tiny table
s = np.array([90.0, 100.0, 40.0, 50.0, 1000.0, 1.0])
lost, pct = A._estimate(s)
check("arithmetic: lost = 0.9*50 - 40 = 5", abs(lost - 5) < 1e-9)
check("arithmetic: % = 5 / 1005", abs(pct - 100 * 5 / 1005) < 1e-9)

# 6. comparison with official figures
fake = pd.DataFrame({"year": [2023, 2024, 2025], "lost_pct": [4.0, 5.0, 4.0],
                     "ci_low": [3.0, 4.0, 3.0], "ci_high": [5.0, 6.0, 5.0]})
m, sm = A.compare_official(fake)
check("official comparison merges three years", sm["years"] == 3 and "pearson_r" in sm)
check("official inside interval counted", sm["years_official_inside_ci"] == 3)

# 7. quality checks pass on clean data and fail on broken data
checks, ok = Q.run_checks(h)
check("QC passes on clean data", ok)
bad = h.copy()
bad.loc[bad.index[:2000], "snsp_pct"] = 250
_, ok_bad = Q.run_checks(bad)
check("QC fails on impossible SNSP", not ok_bad)
frac = h.copy()
frac["snsp_pct"] /= 100
fixed, notes = Q.fix_units(frac)
check("fractional SNSP converted to percent", abs(fixed["snsp_pct"].max() - h["snsp_pct"].max()) < 1e-9 and notes)

# 8. hour-of-day shares add to 100
hr = A.by_hour(d, [2023, 2024])
check("hourly loss shares sum to 100", abs(hr["lost_share_pct"].sum() - 100) < 1e-6)

print(f"\nAll {passed} tests passed.")
