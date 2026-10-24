# Wind lost at the SNSP limit: an all-island estimate from public EirGrid data

The all-island grid can only run with a limited share of wind, solar and imports at any moment: the
**SNSP limit** (75% since 2022). When it is reached, wind farms are turned down. EirGrid publishes the
yearly total in its *Annual Renewable Constraint and Curtailment Report*. This project rebuilds an
estimate of the system-wide part (curtailment) **hour by hour from public 15-minute data**, checks it
against the official figures, and shows when the limit binds.

**[Read the report →](https://bymankirat.github.io/ireland-wind-dispatch-down/)**

> Independent analysis. Not an EirGrid or SONI publication.

## Method in brief

1. **Data.** EirGrid Smart Grid Dashboard, whole island, 2022–2025: actual wind, forecast wind, SNSP
   and demand, 15-minute readings averaged to the hour (99.96% coverage after automatic checks).
2. **The footprint.** The forecast over-predicts in windy hours, but forecast errors do not depend on
   demand, while system-wide limits bind when demand is low. Among hours with the same forecast wind,
   the quietest quarter produced up to 23% less than the busiest.
3. **Estimate.** Within each year, season and 500 MW band of forecast wind, the busiest quarter of hours
   is the baseline; the shortfall of all other hours below it is demand-linked turn-down.
4. **Checks.** Compared with EirGrid's published curtailment for 2022–2025 (r = 0.86, mean difference
   0.9 points, official figure inside the 95% interval in 3 of 4 years); a placebo on hours with under
   1,000 MW of forecast wind finds about zero; demand quarters within year instead of season as a
   robustness check; 95% intervals from resampling whole days.
5. **Tested.** `tests/run_tests.py` checks that no loss gives zero even with a biased forecast, that a
   planted SNSP-style loss is detected as a lower bound, the placebo, the arithmetic and the quality checks.

An earlier version compared hours at the SNSP limit with hours below it. Its own placebo test failed
(it found "losses" where none should exist), because SNSP is calculated from actual wind and the forecast
over-predicts in windy hours. That version was replaced by the demand comparison above.

## Run it

```bash
pip install -r requirements.txt
python tests/run_tests.py      # offline, about a second
python run_pipeline.py         # downloads EirGrid data, then rebuilds every number and figure
python run_pipeline.py --cached  # rebuild from data/hourly_all_island.csv.gz without downloading
python run_pipeline.py --demo  # synthetic data, offline
```

The download takes about an hour because the dashboard answers one series and one week at a time;
the hourly table is saved in `data/`, so later runs use `--cached`. A GitHub Actions workflow can be
started by hand from the Actions tab.

## Layout

```
run_pipeline.py   download -> quality checks -> analysis -> figures -> report
src/config.py     every setting, and the official benchmark figures with their source
src/data.py       EirGrid download (cached by month) and the hourly table
src/quality.py    automatic checks; a failure stops the run
src/analysis.py   limit detection, lost-energy estimate, bootstrap, placebo, comparison
src/charts.py     figures
src/report.py     docs/index.html, every number read from results/
tests/            offline tests on synthetic data
```

## Data and credit

EirGrid Smart Grid Dashboard. Benchmark: EirGrid and SONI, *Annual Renewable Constraint and
Curtailment Report 2025*, Table 3. Mankirat Singh ·
[Portfolio](https://bymankirat.github.io/myportfolio/) ·
[LinkedIn](https://linkedin.com/in/mankirat-singh-694440177)
