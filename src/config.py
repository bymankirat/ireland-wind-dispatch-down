"""Project settings. Every choice that changes a result lives here."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
TABLE_FILE = ROOT / "data" / "hourly_all_island.csv.gz"
RESULTS_DIR = ROOT / "results"
DOCS_DIR = ROOT / "docs"
FIG_DIR = DOCS_DIR / "figures"

# EirGrid Smart Grid Dashboard, 15-minute data. The SNSP limit applies to the whole island,
# so every series is taken for the all-island system (region ALL) to match it.
# The dashboard moved to this chart API in 2025; it returns up to four series per request.
GRID_API = ("https://www.smartgriddashboard.com/api/chart/?region={region}&chartType=default"
            "&dateRange={range}&dateFrom={start}&dateTo={end}&areas={areas}")
REGION = "ALL"
# Several spellings are tried for each series, because the dashboard has renamed some of them.
AREAS = {
    "wind": ["windactual"],
    "wind_fc": ["windforecast"],
    "snsp": ["SnspALL", "snspall", "snsp"],
    "demand": ["demandactual"],
}
# Field names in the API's rows, and the column each becomes
FIELDS = {"WIND_ACTUAL": "wind_mw", "WIND_FCAST": "wind_fc_mw", "SNSP_ALL": "snsp_pct",
          "SYSTEM_DEMAND": "demand_mw"}
START = "2021-01-01"          # SNSP is published from 2021; earlier years cannot be classed
MIN_DAYS = 330                # a year enters the comparison only with this many days of data
LAST_FULL_YEAR = 2025         # official EirGrid figures exist up to this year

# How hours are classed. The operating limit is found from the data each year (99.5th
# percentile of SNSP, rounded), so no limit date has to be assumed.
CAP_QUANTILE = 0.995
AT_CAP_MARGIN = 2.0           # an hour is "at the limit" within 2 percentage points of it
FREE_MARGIN = 10.0            # an hour is "well below the limit" 10 points or more under it
MIN_FC_MW = 100.0             # hours with almost no forecast wind carry no information
N_BOOT = 1000                 # day-level bootstrap resamples for confidence intervals
SEED = 42

# EirGrid, Annual Renewable Constraint and Curtailment Report 2025 (V1.0), Table 3:
# all-island wind dispatch-down, % of available wind energy. Used only as a benchmark.
OFFICIAL_ALL_ISLAND = {
    # year: (curtailment %, constraint %, total %)
    2020: (5.9, 6.2, 12.1),
    2021: (3.0, 4.4, 7.4),
    2022: (3.5, 5.0, 8.5),
    2023: (4.7, 6.1, 10.7),
    2024: (4.7, 9.3, 14.0),
    2025: (4.5, 8.9, 13.4),
}
OFFICIAL_SOURCE = ("EirGrid and SONI, Annual Renewable Constraint and Curtailment Report 2025, "
                   "Table 3 (all-island wind)")
