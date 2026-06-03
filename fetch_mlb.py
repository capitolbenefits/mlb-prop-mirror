#!/usr/bin/env python3
"""
MLB prop-top3 data mirror.

Runs inside a GitHub Action (which has normal outbound internet), fetches the
MLB statsapi endpoints the prop-top3 scheduled task needs, and writes them as
JSON files into data/. The Cowork scheduled task then `git clone`s this repo
(github.com is reachable from the Cowork sandbox) and reads these files, with no
direct statsapi access required on the Cowork side.

Files written:
  data/manifest.json                     run metadata + freshness timestamp
  data/schedule-today.json               today's slate (hydrated)
  data/schedule-week.json                league-wide trailing-7-day schedule
  data/gamelog/<playerId>-pitching.json  season pitching gameLog for every
                                         probable pitcher seen in a rolling
                                         4-day window (covers grading)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BASE = "https://statsapi.mlb.com/api/v1"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
GAMELOG_DIR = os.path.join(DATA, "gamelog")

# Days back to hydrate slates so prior pending picks always have their
# probable pitcher's gameLog mirrored before the next-morning grade.
LOOKBACK_DAYS = 4


def fetch(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "prop-top3-mirror/1.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url} :: {last}")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))


def probable_pitcher_ids(schedule_json):
    ids = set()
    for d in schedule_json.get("dates", []):
        for g in d.get("games", []):
            for side in ("away", "home"):
                pp = g.get("teams", {}).get(side, {}).get("probablePitcher") or {}
                pid = pp.get("id")
                if pid:
                    ids.add(int(pid))
    return ids


def main():
    now_utc = datetime.now(timezone.utc)
    today_et = now_utc.astimezone(ET).date()
    yesterday_et = today_et - timedelta(days=1)
    week_start = today_et - timedelta(days=7)
    season = today_et.year

    os.makedirs(GAMELOG_DIR, exist_ok=True)
    errors = []

    today_url = (
        f"{BASE}/schedule?sportId=1&date={today_et.isoformat()}"
        f"&hydrate=probablePitcher,team,venue,officials"
    )
    sched_today = fetch(today_url)
    write_json(os.path.join(DATA, "schedule-today.json"), sched_today)

    week_url = (
        f"{BASE}/schedule?sportId=1"
        f"&startDate={week_start.isoformat()}&endDate={yesterday_et.isoformat()}"
        f"&hydrate=team"
    )
    sched_week = fetch(week_url)
    write_json(os.path.join(DATA, "schedule-week.json"), sched_week)

    pitcher_ids = set(probable_pitcher_ids(sched_today))
    for back in range(1, LOOKBACK_DAYS + 1):
        d = today_et - timedelta(days=back)
        url = (
            f"{BASE}/schedule?sportId=1&date={d.isoformat()}"
            f"&hydrate=probablePitcher"
        )
        try:
            pitcher_ids |= probable_pitcher_ids(fetch(url))
        except Exception as e:  # noqa: BLE001
            errors.append(f"lookback {d.isoformat()}: {e}")

    written_logs = []
    for pid in sorted(pitcher_ids):
        url = (
            f"{BASE}/people/{pid}/stats?stats=gameLog"
            f"&season={season}&group=pitching"
        )
        try:
            gl = fetch(url)
            write_json(os.path.join(GAMELOG_DIR, f"{pid}-pitching.json"), gl)
            written_logs.append(pid)
        except Exception as e:  # noqa: BLE001
            errors.append(f"gamelog {pid}: {e}")

    manifest = {
        "generated_at": now_utc.isoformat(),
        "generated_at_epoch": int(now_utc.timestamp()),
        "et_date": today_et.isoformat(),
        "et_yesterday": yesterday_et.isoformat(),
        "season": season,
        "schedule_today": "data/schedule-today.json",
        "schedule_week": "data/schedule-week.json",
        "gamelog_dir": "data/gamelog",
        "pitcher_gamelogs": [f"data/gamelog/{p}-pitching.json" for p in written_logs],
        "pitcher_count": len(written_logs),
        "errors": errors,
    }
    write_json(os.path.join(DATA, "manifest.json"), manifest)

    print(json.dumps({
        "et_date": today_et.isoformat(),
        "pitcher_gamelogs": len(written_logs),
        "errors": len(errors),
    }))
    if errors:
        print("WARN errors:", *errors, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
