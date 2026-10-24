"""Writes docs/index.html. Every number on the page is read from results/."""

from __future__ import annotations

import html
import json

import pandas as pd

from config import AT_CAP_MARGIN, DOCS_DIR, OFFICIAL_SOURCE, RESULTS_DIR

CSS = """
:root{--bg:#f7f6f2;--fg:#1d2733;--muted:#5b6672;--card:#fff;--line:#dcd9d2;--accent:#1f5f8b;--chip:#eceae4}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14181d;--fg:#e8ecf0;--muted:#9aa5b1;--card:#1c222a;--line:#313a45;--accent:#7fb6e0;--chip:#252d37;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#14181d;--fg:#e8ecf0;--muted:#9aa5b1;--card:#1c222a;--line:#313a45;--accent:#7fb6e0;--chip:#252d37;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 Georgia,'Iowan Old Style',serif;
 padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main{max-width:780px;margin:0 auto;padding-block:40px 64px}
h1,h2,h3{font-family:system-ui,'Segoe UI',Arial,sans-serif;text-wrap:balance;line-height:1.25}
h1{font-size:30px;margin:0 0 8px}h2{font-size:21px;margin:40px 0 8px}
.kicker{font:600 12px/1 system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.lede{font-size:18px;color:var(--fg)}
.meta{color:var(--muted);font:14px/1.5 system-ui,sans-serif}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:24px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:0}
.tile b{display:block;font:700 26px/1.1 system-ui,sans-serif;color:var(--accent)}
.tile span{font:13px/1.4 system-ui,sans-serif;color:var(--muted)}
figure{margin:20px 0;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}
figure img{width:100%;height:auto;display:block}
figcaption{font:13px/1.5 system-ui,sans-serif;color:#5b6672;margin-top:8px}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font:14px/1.4 system-ui,sans-serif;min-width:560px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right}
th:first-child,td:first-child{text-align:left}
th{background:var(--chip);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.note{background:var(--card);border-left:3px solid var(--accent);padding:12px 16px;border-radius:6px;font-size:15px}
a{color:var(--accent)}
code{font:13px ui-monospace,Menlo,monospace;background:var(--chip);padding:1px 5px;border-radius:4px}
"""


def _f(x, nd=1):
    return f"{x:,.{nd}f}"


def _table(df: pd.DataFrame, cols: list[tuple[str, str, int]]) -> str:
    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl, _ in cols)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c, _, nd in cols:
            v = r[c]
            cells.append(f"<td>{int(v) if nd < 0 else _f(v, nd)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def write():
    R = json.loads((RESULTS_DIR / "summary.json").read_text())
    m = pd.read_csv(RESULTS_DIR / "yearly_vs_official.csv")
    pla = pd.read_csv(RESULTS_DIR / "placebo_by_year.csv")
    alt = pd.read_csv(RESULTS_DIR / "robustness_year_quarters.csv")
    rt = pd.read_csv(RESULTS_DIR / "ratio_by_wind_and_demand.csv", index_col=0)
    qc = pd.read_csv(RESULTS_DIR / "quality_checks.csv")
    hr = pd.read_csv(RESULTS_DIR / "by_hour.csv")
    cmp_ = R["comparison"]
    recent = R["recent_years"]
    L = R["latest"]

    r = cmp_.get("pearson_r", float("nan"))
    mad = cmp_.get("mean_abs_diff_pts", float("nan"))
    md = cmp_.get("mean_diff_pts", float("nan"))
    inside = cmp_.get("years_official_inside_ci", 0)
    worst = m.loc[m["difference_pts"].abs().idxmax()]
    pmax = float(pla["lost_pct"].abs().max())
    hi_band = rt.index[-2]
    gap = 100 * (1 - rt.loc[hi_band, "Lowest demand"] / rt.loc[hi_band, "Highest demand"])
    night = float(hr.loc[hr["hour"].isin(list(range(0, 7)) + [23]), "lost_share_pct"].sum())
    peak_cap = hr.loc[hr["at_cap_pct"].idxmax()]
    first_at, last_at = m.iloc[0]["share_of_hours_pct"], m.iloc[-1]["share_of_hours_pct"]

    tiles = [
        (f"{L['lost_pct']:.1f}%", f"of available wind turned down when demand was low in {L['year']}, "
                                  f"estimated from public data (95% interval {L['ci_low']:.1f}–{L['ci_high']:.1f}%)"),
        (f"{L['official_curtailment_pct']:.1f}%", f"EirGrid's published curtailment for {L['year']}"),
        (f"{_f(L['lost_gwh'], 0)} GWh", f"estimated wind energy turned down in {L['year']}; correlation with EirGrid's yearly figures r = {r:.2f}"),
        (f"{first_at:.1f}% → {last_at:.1f}%", f"share of hours within {AT_CAP_MARGIN:.0f} points of the SNSP limit, "
                                              f"{R['first_year']} to {R['last_year']}"),
    ]
    tile_html = "".join(f'<div class="tile"><b>{a}</b><span>{html.escape(b)}</span></div>' for a, b in tiles)
    tbl = _table(m, [("year", "Year", -1), ("lost_gwh", "Turned down, GWh", 0), ("lost_pct", "Estimate, %", 1),
                     ("ci_low", "95% low", 1), ("ci_high", "95% high", 1),
                     ("official_curtailment_pct", "EirGrid curtailment, %", 1),
                     ("official_total_pct", "EirGrid total dispatch-down, %", 1),
                     ("share_of_hours_pct", "Hours at SNSP limit, %", 1)])
    rob = ", ".join(f"{int(y)}: {v:.1f}%" for y, v in zip(alt["year"], alt["lost_pct"]))
    qc_rows = "".join(f"<tr><td>{html.escape(c)}</td><td>{html.escape(res)}</td><td>{html.escape(str(dt))}</td></tr>"
                      for c, res, dt in qc[["check", "result", "detail"]].itertuples(index=False))
    caps = ", ".join(f"{y}: {c:.0f}%" for y, c in R["caps"].items())

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Wind Lost to Grid Limits</title><style>{CSS}</style></head><body><main>
<p class="kicker">Ireland and Northern Ireland · {R['first_year']}–{R['last_year']} · public EirGrid data</p>
<h1>How much wind does the all-island grid turn away, and when?</h1>
<p class="lede">EirGrid reports once a year how much wind energy was turned down because of system-wide
limits. This analysis rebuilds that figure hour by hour from the public 15-minute data on the Smart Grid
Dashboard, checks it against the official numbers, and shows when the limits bind.</p>
<p class="meta">Mankirat Singh · Independent analysis, not an EirGrid or SONI publication ·
<a href="https://github.com/bymankirat/ireland-wind-dispatch-down">Code</a> ·
<a href="https://bymankirat.github.io/myportfolio/">Portfolio</a> · Data {R['first_year']}–{R['last_year']}</p>
<div class="tiles">{tile_html}</div>

<h2>1. The footprint: on quiet days, the same wind gives less power</h2>
<p>EirGrid's forecast over-predicts in windy hours, so actual output falls below the forecast as wind rises
in every hour. But among hours with the <em>same</em> forecast wind, output is lower still when demand is
low, which is when system-wide limits bind. At {html.escape(hi_band)} MW of forecast wind, the quietest
quarter of hours produced {gap:.0f}% less than the busiest quarter. Forecast errors do not depend on
demand; system limits do. That gap is what this analysis measures.</p>
<figure><img src="figures/0_ratio_lines.png" alt="Line chart: actual divided by forecast wind falls with forecast wind, and falls further in the quietest quarter of hours">
<figcaption>Actual ÷ forecast wind, all hours {R['first_year']}–{R['last_year']}, for the busiest and quietest quarter of hours by demand.</figcaption></figure>

<h2>2. The estimate against EirGrid's published figures</h2>
<p>Within each year, season and 500 MW band of forecast wind, the busiest quarter of hours is the baseline.
The shortfall of every other hour below it is counted as demand-linked turn-down: wind that was available
but not used because demand was low. Across
{cmp_['years']} years the estimate differs from EirGrid's published curtailment by {mad:.1f} percentage points on
average (it sits {abs(md):.1f} points {"above" if md > 0 else "below"} it), and the official figure falls inside the 95%
interval in {inside} of {cmp_['years']} years. The largest gap is {int(worst['year'])}
({worst['lost_pct']:.1f}% against {worst['official_curtailment_pct']:.1f}%), a year in which EirGrid's local
<em>constraints</em> also jumped, and some constraints are likely to follow demand too.</p>
<figure><img src="figures/1_yearly_vs_official.png" alt="Bar chart of the yearly estimate beside EirGrid's published curtailment">
<figcaption>Blue: this estimate with a 95% interval from resampling whole days. Grey: {html.escape(OFFICIAL_SOURCE)}.</figcaption></figure>
{tbl}
<p>Robustness: with demand quarters defined within each year rather than each season, the estimate is {rob}.</p>

<h2>3. Does the method invent losses? A placebo test</h2>
<p>When forecast wind is under 1,000 MW, system-wide limits essentially never bind, so the same calculation
should find nothing there. It finds at most {pmax:.1f}% in any year
{"— close to zero, so the method is not turning forecast noise into losses." if pmax < 1.0 else "— not negligible, so part of the estimate may be forecast behaviour."}</p>
<figure><img src="figures/5_placebo.png" alt="Bar chart comparing the placebo with the estimate per year"></figure>

<h2>4. When the limit binds</h2>
<p>The share of hours within {AT_CAP_MARGIN:.0f} points of the SNSP limit rose from {first_at:.1f}% in {R['first_year']}
to {last_at:.1f}% in {R['last_year']}. Those hours peak around {int(peak_cap['hour']):02d}:00 ({peak_cap['at_cap_pct']:.0f}% of hours in
{recent[0]}–{recent[-1]}), consistent with solar adding to the non-synchronous share at midday. The wind that is
turned down, though, is mostly a night-time loss: about {night:.0f}% of the estimated lost energy fell between
11 pm and 7 am, when demand is lowest. Two different limits are at work. Demand that can move into those hours (electric-vehicle
charging, storage, heating) is the cheapest way to use more of this wind.</p>
<figure><img src="figures/2_monthly_at_cap.png" alt="Line chart of the monthly share of hours at the SNSP limit"></figure>
<figure><img src="figures/3_hour_profile.png" alt="Bar chart of the share of estimated lost energy by hour of day"></figure>
<figure><img src="figures/4_driver_heatmap.png" alt="Heatmap of the chance of being at the SNSP limit by demand and forecast wind">
<figcaption>Chance that an hour is at the SNSP limit, by demand and forecast wind, {recent[0]}–{recent[-1]}.</figcaption></figure>

<h2>Method</h2>
<p>Four EirGrid Smart Grid Dashboard series for the whole island (actual wind, forecast wind, SNSP, demand),
15-minute readings averaged to the hour, {R['first_year']}–{R['last_year']}. Each hour is placed in a year, a season,
a 500 MW band of forecast wind and a quarter of demand within its year and season. The busiest quarter's
actual ÷ forecast ratio in each band is the baseline; bands without baseline hours borrow the nearest band.
Lost energy is the baseline ratio times forecast, minus actual, summed over the other three quarters. The
percentage divides by actual wind plus the loss. Intervals come from resampling whole days 1,000 times.
SNSP limits read from the data (99.5th percentile): {caps}.</p>

<h2>Limitations</h2>
<p class="note">The busiest hours are not free of curtailment, so for curtailment that follows the SNSP rule
this is a lower bound: on synthetic data where the limit also binds in busy hours, it recovers under half
of the planted loss (see <code>tests/run_tests.py</code>). That it nonetheless reaches EirGrid's figure on real data
means it also counts other turn-down that follows demand, such as minimum conventional generation and some
local constraints, so it is best read as an independent indicator of the same size, not a reconstruction. Season and forecast band absorb most differences in forecast
behaviour, but not all. EirGrid's figures use each wind farm's own availability signal, which is not public.
Solar is not included. This is an independent estimate, not a replacement for the official figures.</p>

<h2>Data quality checks</h2>
<div class="tbl"><table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>{qc_rows}</tbody></table></div>

<h2>Reproduce it</h2>
<p><code>pip install -r requirements.txt</code>, then <code>python run_pipeline.py</code> downloads the data and rebuilds
every number and figure; <code>python tests/run_tests.py</code> checks the method on synthetic data with known answers.</p>
<p class="meta">Data: EirGrid Smart Grid Dashboard; {html.escape(OFFICIAL_SOURCE)}.</p>
</main></body></html>"""
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")
