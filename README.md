# Wind lost at the SNSP limit: an all-island estimate from public EirGrid data

The all-island grid can only run with a limited share of wind, solar and imports at any moment: the
**SNSP limit** (75% since 2022). When it is reached, wind farms are turned down. EirGrid publishes the
yearly total in its *Annual Renewable Constraint and Curtailment Report*. This project rebuilds an
estimate of the system-wide part (curtailment) **hour by hour from public 15-minute data**, checks it
against the official figures, and shows when the limit binds.

**[Read the report →](https://bymankirat.github.io/ireland-wind-dispatch-down/)**

> Independent analysis. Not an EirGrid or SONI publication.

## Method in brief

1. **Data.** EirGrid Smart Grid Dashboard, whole island, 2020 onwards: actual wind, forecast wind,
   SNSP and demand, downloaded month by month and averaged to the hour.
2. **Limit from the data.** Each year's operating limit is the 99.5th percentile of SNSP, so no rule
   date is assumed.
3. **Normal ratio.** In hours at least 10 points under the limit, actual / forecast wind gives the
   usual relationship, including local constraints and forecast error.
4. **Lost energy.** In hours within 2 points of the limit, expected output = normal ratio × forecast;
   the shortfall is counted as lost to the limit.
5. **Baseline and checks.** Compared with EirGrid's published curtailment for 2020–2025; a placebo band
   of hours just under the limit must show about zero loss; 95% intervals from resampling whole days.
6. **Tested.** `tests/run_tests.py` plants a known loss in synthetic data and checks it is recovered,
   that no loss gives zero, that the placebo finds nothing, and that the quality checks catch bad data.

## Run it

```bash
pip install -r requirements.txt
python tests/run_tests.py      # offline, about a second
python run_pipeline.py         # downloads EirGrid data, then rebuilds every number and figure
python run_pipeline.py --demo  # synthetic data, offline
```

A GitHub Actions workflow (`.github/workflows/pipeline.yml`) runs the tests and the pipeline and
commits the results monthly.

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
