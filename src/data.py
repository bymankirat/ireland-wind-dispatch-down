"""Download the four EirGrid series and build one hourly all-island table.

EirGrid times are Irish local time. Readings are averaged to the hour; at the autumn clock
change the repeated hour is averaged, and the missing spring hour is left empty (not invented).
The table starts at the first month in which all four series are published (SNSP is only
published from 2022 onwards).
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pandas as pd

from config import AREAS, FIELDS, GRID_API, RAW_DIR, REGION, RESULTS_DIR, START, TABLE_FILE


def _fetch(url: str, timeout: int = 120) -> bytes:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:  # noqa: BLE001  fall back to curl when Python lacks certificates
        return subprocess.run(["curl", "-sSL", "--max-time", str(timeout), url],
                              capture_output=True, check=True).stdout


def _url(areas: list[str], start: pd.Timestamp, end: pd.Timestamp, rng: str) -> str:
    return GRID_API.format(region=REGION, range=rng, start=f"{start:%d-%b-%Y}",
                           end=f"{end:%d-%b-%Y}", areas=",".join(areas))


def _rows(areas: list[str], start, end, rng: str = "month", tries: int = 5) -> list[dict]:
    url = _url(areas, start, end, rng)
    last = None
    for attempt in range(tries):
        try:
            payload = json.loads(_fetch(url))
            time.sleep(0.4)
            rows = payload.get("Rows")
            if rows is None:
                raise ValueError(f"no Rows key: {str(payload)[:200]}")
            if rows or attempt >= 1:   # the API sometimes answers empty once
                return rows
        except (ValueError, OSError, subprocess.CalledProcessError) as e:
            last = e
        time.sleep(3 * (attempt + 1) ** 2)
    if last:
        raise RuntimeError(f"no answer for {areas} {start:%b %Y}: {last}")
    return []


def probe(day: str = "2025-06-01") -> dict[str, str]:
    """Find a working area name for each series on one day, and log what the API returns."""
    d = pd.Timestamp(day)
    chosen, log = {}, []
    for key, names in AREAS.items():
        for name in names:
            try:
                rows = _rows([name], d, d, rng="day", tries=2)
            except RuntimeError as e:
                log.append(f"{key} {name}: error {e}")
                continue
            fields = sorted({r.get("FieldName") for r in rows})
            log.append(f"{key} {name}: {len(rows)} rows, fields {fields}, first {rows[:1]}")
            if rows:
                chosen[key] = name
                break
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "api_probe.txt").write_text("\n".join(log) + "\n")
    print("\n".join("  " + x for x in log))
    missing = [k for k in AREAS if k not in chosen]
    if missing:
        raise RuntimeError(f"no working area name for {missing}; see results/api_probe.txt")
    return chosen


def download(folder: Path = RAW_DIR) -> list[str]:
    """One JSON file per month with all four series; finished months are downloaded once."""
    folder.mkdir(parents=True, exist_ok=True)
    names = probe()
    areas = [names[k] for k in AREAS]
    today = pd.Timestamp.today().normalize()
    last_month = today.replace(day=1) - pd.DateOffset(months=1)
    failed = []
    for m in pd.date_range(START, last_month, freq="MS"):
        f = folder / f"grid_{m:%Y-%m}.json"
        if f.exists() and f.stat().st_size > 1000:
            continue
        end = m + pd.offsets.MonthEnd(0)
        try:
            rows = _rows(areas, m, end, rng="month")
            per_field = pd.Series([r.get("FieldName") for r in rows]).value_counts().to_dict()
            expected = ((end - m).days + 1) * 96
            if rows and min(per_field.values()) < 0.9 * expected and len(per_field) >= 3:
                rows = []   # cut short: fetch week by week
                for ws in pd.date_range(m, end, freq="7D"):
                    rows += _rows(areas, ws, min(ws + pd.Timedelta(days=6), end), rng="week")
        except RuntimeError as e:
            failed.append(f"{m:%Y-%m}")
            print(f"  {m:%b %Y}: skipped ({e})")
            continue
        f.write_text(json.dumps(rows))
        counts = pd.Series([r.get("FieldName") for r in rows]).value_counts().to_dict()
        print(f"  {m:%b %Y}: {len(rows):,} readings {counts}")
    return failed


def _hourly(s: pd.Series) -> pd.Series:
    s = s[~s.index.isna()].sort_index()
    return s.groupby(s.index.floor("h")).mean()


def build_table(folder: Path = RAW_DIR) -> tuple[pd.DataFrame, dict]:
    rows = []
    for f in sorted(folder.glob("grid_*.json")):
        rows += json.loads(f.read_text())
    if not rows:
        raise FileNotFoundError(f"no grid files in {folder}")
    df = pd.DataFrame(rows)
    seen = set(df["FieldName"].unique())
    missing = [f for f in FIELDS if f not in seen]
    if missing:
        raise KeyError(f"fields {missing} not in the downloaded rows; fields seen: {sorted(seen)}")
    df = df[df["FieldName"].isin(FIELDS)]
    df["t"] = pd.to_datetime(df["EffectiveTime"], format="%d-%b-%Y %H:%M:%S", errors="coerce")
    df["v"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df.dropna(subset=["t", "v"])
    series, counts = {}, {}
    for field, col in FIELDS.items():
        s = df.loc[df["FieldName"] == field].set_index("t")["v"]
        counts[col] = {"readings": int(len(s)), "duplicates": int(s.index.duplicated().sum()),
                       "first": str(s.index.min()), "last": str(s.index.max())}
        series[col] = _hourly(s)
    h = pd.DataFrame(series)[list(FIELDS.values())]
    # start where every series is published
    first = max(h[c].first_valid_index() for c in h.columns)
    h = h[h.index >= first.normalize()]
    h.index.name = "time"
    return h, counts


def save_table(h: pd.DataFrame, path: Path = TABLE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h.round(2).to_csv(path, compression="gzip")


def load_table(path: Path = TABLE_FILE) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)
