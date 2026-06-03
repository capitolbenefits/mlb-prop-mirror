# mlb-prop-mirror

A tiny data mirror that lets the Cowork **prop-top3** scheduled task get live
MLB statsapi data **without the Chrome extension**.

## Why this exists

The Cowork run environment cannot reach `statsapi.mlb.com`:

- the workspace web-fetch tool only accepts URLs a human pastes into chat (it
  rejects any URL the assistant constructs, so it cannot run unattended);
- the sandbox network is allow-listed to `github.com`, `pypi.org`, and
  `registry.npmjs.org` only, and `statsapi.mlb.com` has no DNS route there.

The one thing the sandbox **can** do unattended is `git clone` from
`github.com`. So this repo acts as the bridge:

1. A GitHub Action (this repo) runs on GitHub's network, which **can** reach
   statsapi, and commits the data as JSON into `data/`.
2. The prop-top3 task `git clone`s this repo into its sandbox and reads the JSON.

No money, no betting integration, no scraping of anything but the public MLB
statsapi JSON feed.

## One-time setup

1. Create a new **public** GitHub repo (public so the clone needs no auth),
   e.g. `mlb-prop-mirror`.
2. Add these files at the repo root:
   - `fetch_mlb.py`
   - `.github/workflows/mlb-mirror.yml`
   - `README.md` (this file)
3. Push to GitHub. In the repo: **Settings -> Actions -> General -> Workflow
   permissions -> Read and write permissions** (so the Action can commit).
4. Open the **Actions** tab, pick **mlb-prop-mirror**, click **Run workflow**
   once to seed `data/`.
5. Put the repo's clone URL into the prop-top3 SKILL.md as `MIRROR_REPO`
   (e.g. `https://github.com/<your-username>/mlb-prop-mirror.git`).

After that it refreshes automatically on the cron schedule below.

## Schedule

Crons are in UTC (GitHub Actions does not honor local time / DST):

| Cron (UTC)    | Approx ET (EDT) | Purpose                                   |
|---------------|-----------------|-------------------------------------------|
| `30 7 * * *`  | ~03:30          | capture West Coast night-game finals      |
| `50 9 * * *`  | ~05:50          | fresh before the 6 AM ET task run         |
| `50 18 * * *` | ~14:50          | fresh before the 3 PM ET task run         |

During EST (offseason) shift the ET column back one hour; not relevant in
baseball season.

## What gets written

| File | Contents |
|------|----------|
| `data/manifest.json` | `generated_at` timestamp, ET date, season, file list, any fetch errors |
| `data/schedule-today.json` | today's hydrated slate (probablePitcher, team, venue, officials) |
| `data/schedule-week.json` | league-wide trailing-7-day schedule (rest / travel) |
| `data/gamelog/<playerId>-pitching.json` | season pitching gameLog for each probable pitcher in a rolling 4-day window (used to grade K props) |
| `data/bullpen-summary.json` | per-team reliever usage over the trailing 3 days: pitch counts, back-to-back flags, fatigue notes (powers the bullpen factor) |

## Extending

Only **pitching** gameLogs are mirrored today (the model is pitcher-strikeout
focused). To grade hitter props, add hitter gameLog fetches in `fetch_mlb.py`
for the relevant `personId`s and `group=hitting`.

Bullpen usage is summarized from active-roster pitchers' gameLogs (no boxscore
fetches needed): each team playing today gets its relievers' trailing-3-day
appearances, pitch counts, and back-to-back flags precomputed into
`data/bullpen-summary.json`.
