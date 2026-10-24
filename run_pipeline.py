"""download -> table -> quality checks -> analysis -> figures -> report.

python run_pipeline.py          real data (downloads on first run)
python run_pipeline.py --demo   synthetic data, offline, to check the pipeline runs
python run_pipeline.py --cached use data/hourly_all_island.csv.gz without downloading
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd  # noqa: E402

import analysis as A  # noqa: E402
import charts as C  # noqa: E402
import data as D  # noqa: E402
import demo  # noqa: E402
import quality as Q  # noqa: E402
import report  # noqa: E402
from config import FIG_DIR, LAST_FULL_YEAR, MIN_DAYS, RESULTS_DIR, TABLE_FILE  # noqa: E402


def main(argv):
    RESULTS_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    counts = None
    if "--demo" in argv:
        h, _ = demo.make(years=(2020, 2021, 2022, 2023, 2024, 2025))
    elif "--cached" in argv and TABLE_FILE.exists():
        h = D.load_table()
    else:
        print("1. Downloading EirGrid data")
        failed = D.download()
        if failed:
            print(f"   {len(failed)} months could not be downloaded: {failed[:10]}")
        h, counts = D.build_table()
        D.save_table(h)
    print(f"   {len(h):,} hours, {h.index.min()} to {h.index.max()}")

    print("2. Quality checks")
    h, notes = Q.fix_units(h)
    checks, ok = Q.run_checks(h, counts)
    for n in notes:
        checks.append({"check": "unit note", "result": "pass", "detail": n})
    pd.DataFrame(checks).to_csv(RESULTS_DIR / "quality_checks.csv", index=False)
    for c in checks:
        print(f"   {c['result']:5s} {c['check']}: {c['detail']}")
    if not ok:
        raise SystemExit("A quality check failed; see results/quality_checks.csv")

    print("3. Analysis")
    h = h[h.index.year <= LAST_FULL_YEAR] if "--keep-partial" not in argv else h
    caps = A.yearly_caps(h)
    d = A.classify(h, caps)
    est = A.lost_energy(d)
    pla = A.lost_energy(d, placebo=True)
    alt = A.lost_energy(A.classify(h, caps, seasonal=False))   # robustness: demand quarters within year only
    short = est.loc[est["days"] < MIN_DAYS, "year"].tolist()
    if short:
        print(f"   years left out (fewer than {MIN_DAYS} days of data): {short}")
    est = est[est["days"] >= MIN_DAYS].reset_index(drop=True)
    pla = pla[pla["year"].isin(est["year"])].reset_index(drop=True)
    alt = alt[alt["year"].isin(est["year"])].reset_index(drop=True)
    d = d[d["year"].isin(est["year"])]
    m, cmp_ = A.compare_official(est)
    years = sorted(est["year"].tolist())
    recent = [y for y in years if y >= years[-1] - 1]
    hr = A.by_hour(d, recent)
    drv = A.drivers(d, recent)
    mo = A.monthly(d)

    m.to_csv(RESULTS_DIR / "yearly_vs_official.csv", index=False)
    pla.to_csv(RESULTS_DIR / "placebo_by_year.csv", index=False)
    alt.to_csv(RESULTS_DIR / "robustness_year_quarters.csv", index=False)
    A.ratio_table(d).to_csv(RESULTS_DIR / "ratio_by_wind_and_demand.csv")
    hr.to_csv(RESULTS_DIR / "by_hour.csv", index=False)
    drv.to_csv(RESULTS_DIR / "drivers_demand_by_wind.csv")
    mo.to_csv(RESULTS_DIR / "monthly.csv", index=False)
    latest = m.sort_values("year").iloc[-1].to_dict()
    latest = {k: (int(v) if k == "year" else float(v)) for k, v in latest.items()}
    summary = {"caps": {str(k): v for k, v in caps.items()}, "comparison": cmp_, "latest": latest,
               "first_year": years[0], "last_year": years[-1], "recent_years": recent,
               "data_end": str(h.index.max().date()), "demo": "--demo" in argv,
               "hours": int(len(h))}
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(m[["year", "share_of_hours_pct", "lost_gwh", "lost_pct", "ci_low", "ci_high",
             "official_curtailment_pct"]].round(2).to_string(index=False))
    print("   placebo (forecast under 1,000 MW):", pla["lost_pct"].round(2).tolist())
    print("   robustness (quarters within year):", alt["lost_pct"].round(2).tolist())
    print("   comparison:", cmp_)

    print("4. Figures and report")
    C.yearly_vs_official(m, FIG_DIR / "1_yearly_vs_official.png")
    C.monthly_at_cap(mo, FIG_DIR / "2_monthly_at_cap.png")
    C.hour_profile(hr, FIG_DIR / "3_hour_profile.png")
    C.driver_heatmap(drv, FIG_DIR / "4_driver_heatmap.png")
    C.placebo(est, pla, FIG_DIR / "5_placebo.png")
    C.ratio_lines(A.ratio_table(d), FIG_DIR / "0_ratio_lines.png")
    report.write()
    print("   docs/index.html written")


if __name__ == "__main__":
    main(sys.argv[1:])
