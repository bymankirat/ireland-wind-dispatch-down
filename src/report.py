"""Writes docs/index.html. Every number on the page is read from results/."""

from __future__ import annotations

import html
import json

import pandas as pd

from config import AT_CAP_MARGIN, DOCS_DIR, FREE_MARGIN, OFFICIAL_SOURCE, RESULTS_DIR

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
    qc = pd.read_csv(RESULTS_DIR / "quality_checks.csv")
    hr = pd.read_csv(RESULTS_DIR / "by_hour.csv")
    cmp_ = R["comparison"]
    recent = R["recent_years"]

    r = cmp_.get("pearson_r", float("nan"))
    mad = cmp_.get("mean_abs_diff_pts", float("nan"))
    md = cmp_.get("mean_diff_pts", float("nan"))
    if r >= 0.7 and mad <= 1.0:
        verdict = (f"The estimate tracks EirGrid's published curtailment closely: across {cmp_['years']} years the "
                   f"two series correlate at r = {r:.2f} and differ by {mad:.1f} percentage points on average.")
    elif mad <= 2.0:
        verdict = (f"The estimate is of the same size as EirGrid's published curtailment (average difference "
                   f"{mad:.1f} points), but follows its year-to-year changes only loosely (r = {r:.2f}).")
    else:
        verdict = (f"The estimate differs from EirGrid's published curtailment by {mad:.1f} points on average "
                   f"(r = {r:.2f}), so public 15-minute data alone does not reproduce the official figure; "
                   "the limitations below say why.")
    direction = "above" if md > 0 else "below"
    pmax = float(pla["lost_pct"].abs().max())
    placebo_txt = (f"In the placebo hours the method finds at most {pmax:.1f}% lost wind in any year, "
                   + ("close to zero, so it is not inventing losses where none should exist."
                      if pmax < 0.75 else "which is not negligible, so part of the at-limit estimate may be forecast "
                      "behaviour rather than curtailment."))
    peak = hr.sort_values("lost_share_pct", ascending=False).head(6)["hour"].tolist()
    night = float(hr.loc[hr["hour"].isin(list(range(0, 7)) + [23]), "lost_share_pct"].sum())

    tiles = [
        (f"{R['latest']['lost_pct']:.1f}%", f"of available wind lost at the SNSP limit in {R['latest']['year']} "
                                             f"(95% interval {R['latest']['ci_low']:.1f}–{R['latest']['ci_high']:.1f}%)"),
        (f"{R['latest']['official_curtailment_pct']:.1f}%", f"EirGrid's published curtailment for {R['latest']['year']}"),
        (f"{_f(R['latest']['lost_gwh'], 0)} GWh", f"estimated wind energy lost at the limit in {R['latest']['year']}"),
        (f"{R['latest']['share_of_hours_pct']:.0f}%", f"of hours with wind were at the limit in {R['latest']['year']}"),
    ]
    tile_html = "".join(f'<div class="tile"><b>{a}</b><span>{html.escape(b)}</span></div>' for a, b in tiles)

    tbl = _table(m, [("year", "Year", -1), ("share_of_hours_pct", "Hours at limit, %", 1),
                     ("lost_gwh", "Lost, GWh", 0), ("lost_pct", "Estimate, %", 1),
                     ("ci_low", "95% low", 1), ("ci_high", "95% high", 1),
                     ("official_curtailment_pct", "EirGrid curtailment, %", 1),
                     ("official_total_pct", "EirGrid total dispatch-down, %", 1)])
    qc_rows = "".join(f"<tr><td>{html.escape(c)}</td><td>{html.escape(res)}</td><td>{html.escape(str(dt))}</td></tr>"
                      for c, res, dt in qc[["check", "result", "detail"]].itertuples(index=False))
    caps = ", ".join(f"{y}: {c:.0f}%" for y, c in R["caps"].items())

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Wind Lost at the SNSP Limit</title><style>{CSS}</style></head><body><main>
<p class="kicker">Ireland and Northern Ireland · {R['first_year']}–{R['last_year']} · public EirGrid data</p>
<h1>How much wind does the all-island grid turn away at its SNSP limit?</h1>
<p class="lede">The grid can only run with a limited share of wind, solar and imports at any moment
(the SNSP limit, {R['caps'][str(R['latest']['year'])]:.0f}% in {R['latest']['year']}). When that share is reached, wind farms are turned down. EirGrid publishes
the yearly total. This analysis rebuilds an estimate of it from public 15-minute data, hour by hour,
to show <em>when</em> the limit binds and how much energy it costs.</p>
<p class="meta">Mankirat Singh · Independent analysis, not an EirGrid or SONI publication ·
<a href="https://github.com/bymankirat/ireland-wind-dispatch-down">Code</a> ·
<a href="https://bymankirat.github.io/myportfolio/">Portfolio</a> · Data to {html.escape(R['data_end'])}</p>

<div class="tiles">{tile_html}</div>

<h2>1. The estimate against EirGrid's published figures</h2>
<p>{verdict} On average the estimate sits {abs(md):.1f} points {direction} the official curtailment figure.
EirGrid's <em>total</em> dispatch-down is larger because it also includes local network constraints,
which happen at any SNSP level and which this method deliberately does not count.</p>
<figure><img src="figures/1_yearly_vs_official.png" alt="Bar chart: yearly estimate of wind lost at the SNSP limit beside EirGrid's published curtailment">
<figcaption>Blue: this estimate, with a 95% interval from resampling whole days. Grey: {html.escape(OFFICIAL_SOURCE)}.</figcaption></figure>
{tbl}

<h2>2. Does the method invent losses? A placebo test</h2>
<p>The same calculation was run on hours 6 to 12 points under the limit, where system-wide curtailment
should not be needed. {placebo_txt}</p>
<figure><img src="figures/5_placebo.png" alt="Bar chart comparing estimated losses in placebo hours with hours at the limit">
<figcaption>Grey: placebo hours under the limit. Blue: hours at the limit.</figcaption></figure>

<h2>3. When the limit binds</h2>
<p>In {recent[0]}–{recent[-1]}, about {night:.0f}% of the estimated lost energy fell between 11 pm and 7 am,
when demand is lowest. The six hours with the largest share were {", ".join(f"{h:02d}:00" for h in sorted(peak))}.
That points to demand that can move into the night (electric-vehicle charging, storage, heating) as the
cheapest way to use more of this wind.</p>
<figure><img src="figures/3_hour_profile.png" alt="Bar chart of the share of estimated lost wind energy by hour of day">
<figcaption>Share of the estimated lost energy in each hour of the day, {recent[0]}–{recent[-1]}.</figcaption></figure>
<figure><img src="figures/4_driver_heatmap.png" alt="Heatmap of the chance of being at the SNSP limit by demand and forecast wind">
<figcaption>Chance that an hour is at the limit, by demand and forecast wind (each split into fifths of hours), {recent[0]}–{recent[-1]}.</figcaption></figure>
<figure><img src="figures/2_monthly_at_cap.png" alt="Line chart of the monthly share of hours at the SNSP limit">
<figcaption>Share of hours each month within {AT_CAP_MARGIN:.0f} points of that year's limit.</figcaption></figure>

<h2>Method</h2>
<p>All four series are EirGrid Smart Grid Dashboard 15-minute data for the whole island (actual wind,
forecast wind, SNSP and demand), averaged to the hour. The limit each year is read from the data
(99.5th percentile of SNSP: {caps}), so no rule date has to be assumed.</p>
<p>In hours at least {FREE_MARGIN:.0f} points under the limit, actual wind divided by forecast wind gives the normal
ratio between them; it already includes local constraints and ordinary forecast error. In hours within
{AT_CAP_MARGIN:.0f} points of the limit, the expected output is that ratio times the forecast; the shortfall below it
is counted as energy lost to the limit. The percentage is that loss divided by actual wind plus the loss.
Intervals come from resampling whole days 1,000 times. Hours with under 100 MW of forecast wind are left out.</p>

<h2>Limitations</h2>
<p class="note">This is an estimate from public data, not a replacement for EirGrid's figures, which use
each wind farm's own availability signal. It assumes the forecast relates to output in the same way at
the limit as below it; if forecasts are less accurate in very windy hours, part of the gap is forecast error.
SNSP is not the only system-wide limit (minimum numbers of conventional units and inertia also apply), so
curtailment outside SNSP-limit hours is missed. Solar is not included.</p>

<h2>Data quality checks</h2>
<div class="tbl"><table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead><tbody>{qc_rows}</tbody></table></div>

<h2>Reproduce it</h2>
<p><code>pip install -r requirements.txt</code>, then <code>python run_pipeline.py</code> downloads the data month by
month and rebuilds every number and figure; <code>python tests/run_tests.py</code> checks the method on synthetic
data with a planted loss. A GitHub Actions workflow reruns it monthly.</p>
<p class="meta">Data: EirGrid Smart Grid Dashboard; {html.escape(OFFICIAL_SOURCE)}.</p>
</main></body></html>"""
    (DOCS_DIR / "index.html").write_text(page, encoding="utf-8")
