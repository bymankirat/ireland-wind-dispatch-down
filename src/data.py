"""Download the four EirGrid series and build one hourly all-island table.

EirGrid times are Irish local time. Readings are averaged to the hour; at the autumn clock
change the repeated hour is averaged, and the missing spring hour is left empty (not invented).
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pandas as pd

from config import AREAS, GRID_API, RAW_DIR, REGION, START, TABLE_FILE


def _fetch(url: str, timeout: int = 120) -> bytes:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:  # noqa: BLE001  fall back to curl when Python lacks certificates
        return subprocess.run(["curl", "-sSL", "--max-time", str(timeout), url],
                              capture_output=True, check=True).stdout


def _rows(area: str, start: pd.Timestamp, end: pd.Timestamp, tries: int = 5) -> list[dict]:
    url = GRID_API.format(area=area, region=REGION, start=f"{start:%d-%b-%Y}+00:00",
                          end=f"{end:%d-%b-%Y}+23:59")
    for attempt in range(tries):
        try:
            payload = json.loads(_fetch(url))
            time.sleep(0.4)
            if payload.get("Status") == "Error":
                msg = str(payload.get("ErrorMessage", "")).lower()
                if "no data" in msg:
                    return []
                raise ValueError(msg)
            return payload.get("Rows") or []
        except (ValueError, OSError, subprocess.CalledProcessError):
            time.sleep(3 * (attempt + 1) ** 2)
    raise RuntimeError(f"no answer for {area} {start:%b %Y}")


def find_area_names(probe_day: str = "2025-06-01") -> dict[str, str]:
    """Try each spelling on one day and keep the first that returns readings."""
    day = pd.Timestamp(probe_day)
    chosen = {}
    for key, names in AREAS.items():
        for name in names:
            try:
                if _rows(name, day, day, tries=2):
                    chosen[key] = name
                    break
            except RuntimeError:
                continue
        if key not in chosen:
            raise RuntimeError(f"none of {names} returned data for {key}")
        print(f"  {key:8s} -> area '{chosen[key]}'")
    return chosen


def download(folder: Path = RAW_DIR) -> list[str]:
    """One CSV per series per month; finished months are downloaded once."""
    folder.mkdir(parents=True, exist_ok=True)
    names = find_area_names()
    today = pd.Timestamp.today().normalize()
    last_month = (today.replace(day=1) - pd.DateOffset(months=1))
    months = pd.date_range(START, last_month, freq="MS")
    failed = []
    for key, area in names.items():
        for m in months:
            f = folder / f"{key}_{m:%Y-%m}.csv"
            if f.exists() and f.stat().st_size > 100:
                continue
            end = m + pd.offsets.MonthEnd(0)
            expected = ((end - m).days + 1) * 96
            try:
                rows = _rows(area, m, end)
                if len(rows) < 0.9 * expected:  # long requests are sometimes cut: go week by week
                    rows = []
                    for ws in pd.date_range(m, end, freq="7D"):
                        rows += _rows(area, ws, min(ws + pd.Timedelta(days=6), end))
            except RuntimeError as e:
                failed.append(f"{key} {m:%Y-%m}")
                print(f"  {key} {m:%b %Y}: skipped ({e})")
                continue
            pd.DataFrame(rows).to_csv(f, index=False)
            print(f"  {key} {m:%b %Y}: {len(rows):,} readings")
    return failed


def _hourly(s: pd.Series) -> pd.Series:
    s = s[~s.index.isna()].sort_index()
    return s.groupby(s.index.floor("h")).mean()


def build_table(folder: Path = RAW_DIR) -> tuple[pd.DataFrame, dict]:
    """Hourly table with wind, wind forecast, SNSP and demand, plus raw counts for QC."""
    series, counts = {}, {}
    for key in AREAS:
        files = sorted(folder.glob(f"{key}_*.csv"))
        parts = [pd.read_csv(f) for f in files if f.stat().st_size > 5]
        parts = [p for p in parts if len(p)]
        if not parts:
            raise FileNotFoundError(f"no {key} files in {folder}")
        df = pd.concat(parts, ignore_index=True)
        t = pd.to_datetime(df["EffectiveTime"], format="%d-%b-%Y %H:%M:%S", errors="coerce")
        v = pd.to_numeric(df["Value"], errors="coerce")
        s = pd.Series(v.values, index=t).dropna()
        counts[key] = {"readings": int(len(s)), "duplicates": int(s.index.duplicated().sum()),
                       "first": str(s.index.min()), "last": str(s.index.max())}
        series[key] = _hourly(s)
    h = pd.DataFrame(series)
    h.columns = ["wind_mw", "wind_fc_mw", "snsp_pct", "demand_mw"]
    h.index.name = "time"
    return h, counts


def save_table(h: pd.DataFrame, path: Path = TABLE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h.round(2).to_csv(path, compression="gzip")


def load_table(path: Path = TABLE_FILE) -> pd.DataFrame:
    return pd.read_csv(path, index_col=0, parse_dates=True)
