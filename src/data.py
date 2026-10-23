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

from config import AREAS, END, FIELDS, GRID_API, RAW_DIR, REGION, RESULTS_DIR, START, TABLE_FILE


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


def _rows(areas: list[str], start, end, rng: str = "month", tries: int = 6) -> list[dict]:
    """The API sometimes answers a valid request with no rows, so an empty answer is retried
    with growing pauses; [] is returned only if every try is empty."""
    url = _url(areas, start, end, rng)
    last = None
    for attempt in range(tries):
        try:
            payload = json.loads(_fetch(url))
            rows = payload.get("Rows")
            if rows is None:
                raise ValueError(f"no Rows key: {str(payload)[:200]}")
            if rows:
                time.sleep(0.3)
                return rows
            last = None
        except (ValueError, OSError, subprocess.CalledProcessError) as e:
            last = e
        time.sleep(min(2 ** attempt, 20))
    if last:
        raise RuntimeError(f"no answer for {areas} {start:%d %b %Y}: {last}")
    return []


def probe(day: str = "2025-06-01") -> dict[str, str]:
    """Find a working area name for each series on one day, and log what the API returns."""
    d = pd.Timestamp(day)
    chosen, log = {}, []
    for key, names in AREAS.items():
        for name in names:
            try:
                rows = _rows([name], d, d, rng="day", tries=6)
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


def _window(rows: list[dict], start, end) -> list[dict]:
    """Keep only readings inside [start, end], because the API may return a wider period."""
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59)
    out = []
    for r in rows:
        t = pd.to_datetime(r.get("EffectiveTime"), format="%d-%b-%Y %H:%M:%S", errors="coerce")
        if t is not pd.NaT and lo <= t <= hi:
            out.append(r)
    return out


def _series_week(area: str, ws: pd.Timestamp, we: pd.Timestamp) -> list[dict]:
    """One series for one week; any day with too few readings is fetched again on its own."""
    rows = _window(_rows([area], ws, we, rng="week"), ws, we)
    per_day = pd.Series([r["EffectiveTime"][:11] for r in rows]).value_counts()
    full = per_day.max() if len(per_day) else 96
    full = 48 if full <= 50 else 96            # SNSP is half-hourly, the rest 15-minute
    keep = []
    for day in pd.date_range(ws, we, freq="D"):
        key = f"{day:%d-%b-%Y}"
        mine = [r for r in rows if r["EffectiveTime"].startswith(key)]
        if len(mine) < 0.9 * full:
            try:
                again = _window(_rows([area], day, day, rng="day", tries=2), day, day)
                if len(again) > len(mine):
                    mine = again
            except RuntimeError:
                pass
        keep += mine
    return keep


def download(folder: Path = RAW_DIR) -> list[str]:
    """Each series is fetched on its own, week by week (the API cuts long multi-series
    requests short). One file per series per month; finished months are fetched once."""
    from concurrent.futures import ThreadPoolExecutor

    folder.mkdir(parents=True, exist_ok=True)
    names = probe()
    today = pd.Timestamp.today().normalize()
    last_month = min(today.replace(day=1) - pd.DateOffset(months=1), pd.Timestamp(END).replace(day=1))
    months = list(pd.date_range(START, last_month, freq="MS"))

    def one_series(key: str) -> list[str]:
        failed = []
        for m in months:
            f = folder / f"{key}_{m:%Y-%m}.json"
            end = m + pd.offsets.MonthEnd(0)
            if f.exists() and f.stat().st_size > 1000:
                have = {r["EffectiveTime"][:11] for r in json.loads(f.read_text())}
                if len(have) >= end.day:
                    continue          # complete month: keep it
                print(f"  {key} {m:%b %Y}: {end.day - len(have)} days missing, fetching again", flush=True)
                old = json.loads(f.read_text())
            else:
                old = []
            rows = []
            try:
                for ws in pd.date_range(m, end, freq="7D"):
                    rows += _series_week(names[key], ws, min(ws + pd.Timedelta(days=6), end))
            except RuntimeError as e:
                failed.append(f"{key} {m:%Y-%m}")
                print(f"  {key} {m:%b %Y}: skipped ({e})")
                continue
            if old:   # keep whatever the earlier download had, add what is new
                seen = {(r["EffectiveTime"], r.get("FieldName")) for r in rows}
                rows += [r for r in old if (r["EffectiveTime"], r.get("FieldName")) not in seen]
            f.write_text(json.dumps(rows))
            days = len({r["EffectiveTime"][:11] for r in rows})
            print(f"  {key} {m:%b %Y}: {len(rows):,} readings on {days} days", flush=True)
        return failed

    with ThreadPoolExecutor(len(AREAS)) as ex:
        results = list(ex.map(one_series, list(AREAS)))
    return [x for r in results for x in r]


def _hourly(s: pd.Series) -> pd.Series:
    s = s[~s.index.isna()].sort_index()
    return s.groupby(s.index.floor("h")).mean()


def build_table(folder: Path = RAW_DIR) -> tuple[pd.DataFrame, dict]:
    rows = []
    for f in sorted(folder.glob("*_*.json")):
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
        sub = df.loc[df["FieldName"] == field]
        dup = int(sub["t"].duplicated().sum())
        s = sub.drop_duplicates(subset="t", keep="last").set_index("t")["v"]
        counts[col] = {"readings": int(len(s)), "duplicates": dup,
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
