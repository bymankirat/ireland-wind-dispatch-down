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


def overall(est):
    return 100 * est["lost_gwh"].sum() / (est["wind_gwh"].sum() + est["lost_gwh"].sum())


# 1. the SNSP limit is found from the data
h, true_pct = demo.make()
caps = A.yearly_caps(h)
check("limit detected at 75%", all(abs(c - 75) <= 1 for c in caps.values()), str(caps))

# 2. a planted SNSP-style loss (wind cut just enough to hold the limit) is detected. The busiest
#    hours are curtailed too, so the method is a lower bound: positive, and not above the truth.
d = A.classify(h, caps)
est = A.lost_energy(d, n_boot=200)
o = overall(est)
check("planted loss detected as a lower bound (20-105% of truth)", 0.20 * true_pct <= o <= 1.05 * true_pct,
      f"estimated {o:.2f}% vs planted {true_pct:.2f}%")
check("estimate interval excludes zero every year", (est["ci_low"] > 0).all(), est["ci_low"].round(2).tolist())

# 3. no planted loss -> about zero, even when the forecast over-predicts in windy hours
for bias in (0.0, 0.25):
    h0, t0 = demo.make(planted_loss=0.0, seed=3, fc_bias=bias)
    e0 = A.lost_energy(A.classify(h0, A.yearly_caps(h0)), n_boot=100)
    check(f"no loss planted, forecast bias {bias}: estimate about zero", (e0["lost_pct"].abs() < 0.4).all(),
          e0["lost_pct"].round(3).tolist())

# 4. windy-hour forecast bias does not change a planted loss much
hu, tu = demo.make(seed=6)
hb, tb = demo.make(seed=6, fc_bias=0.25)
ou = overall(A.lost_energy(A.classify(hu, A.yearly_caps(hu)), n_boot=100))
ob = overall(A.lost_energy(A.classify(hb, A.yearly_caps(hb)), n_boot=100))
check("windy-hour forecast bias barely moves the estimate (within 0.3 points)", abs(ob - ou) < 0.3,
      f"{ob:.2f}% with bias vs {ou:.2f}% without")

# 5. placebo (low forecast wind) finds about nothing on data with a planted loss
pl = A.lost_energy(d, placebo=True, n_boot=100)
check("placebo about zero", (pl["lost_pct"].abs() < 0.4).all(), pl["lost_pct"].round(3).tolist())

# 6. hand-checked arithmetic: one cell with baseline ratio 0.9; other hours forecast 50, actual 40;
#    1000 MWh of wind in all -> lost 5, % = 5/1005
S, B = A.N_SEASONS, A.N_BINS
n = S * B
s = np.zeros(4 * n + 2)
c = 0 * B + 3                       # season 0, band 3
s[c], s[n + c] = 90.0, 100.0        # busiest hours: actual 90, forecast 100
s[2 * n + c], s[3 * n + c] = 40.0, 50.0
s[4 * n], s[4 * n + 1] = 1000.0, 1.0
lost, pct = A._estimate(s)
check("arithmetic: lost = 0.9 x 50 - 40 = 5", abs(lost - 5) < 1e-9)
check("arithmetic: % = 5 / 1005", abs(pct - 100 * 5 / 1005) < 1e-9)
s2 = s.copy()
s2[2 * n + c], s2[3 * n + c] = 0.0, 0.0
s2[2 * n + c + 2], s2[3 * n + c + 2] = 40.0, 50.0   # other hours in a band with no baseline hours
check("band without baseline borrows the nearest band", abs(A._estimate(s2)[0] - 5) < 1e-9)

# 7. comparison with official figures
fake = pd.DataFrame({"year": [2023, 2024, 2025], "lost_pct": [4.0, 5.0, 4.0],
                     "ci_low": [3.0, 4.0, 3.0], "ci_high": [5.0, 6.0, 5.0]})
m, sm = A.compare_official(fake)
check("official comparison merges three years", sm["years"] == 3 and "pearson_r" in sm)
check("official inside interval counted", sm["years_official_inside_ci"] == 3)

# 8. quality checks pass on clean data and fail on broken data
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

# 9. hour-of-day shares add to 100; demand quarters are balanced within year and season
hr = A.by_hour(d, [2023, 2024])
check("hourly loss shares sum to 100", abs(hr["lost_share_pct"].sum() - 100) < 1e-6)
share = d.groupby(["year", "season"])["dq"].apply(lambda x: (x == 3).mean())
check("busiest quarter is a quarter of hours in each season", share.between(0.24, 0.26).all())

print(f"\nAll {passed} tests passed.")
