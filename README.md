# New York Chess Tournament Finder

This project is now a parent-facing web app for finding chess tournaments in the New York area. It refreshes live tournament data, keeps source and registration links, and lets you filter by date, location, source, scholastic fit, and estimated drive time from home.

## What the app does

- Pulls upcoming tournament listings from live web sources
- Sorts by most recently updated source listings by default
- Keeps direct registration links and source listing links
- Lets you filter by date range, state, city, search terms, scholastic fit, and beginner-friendliness
- Lets you enter a home ZIP/address and optionally limit results to a drive-time estimate
- Refreshes automatically when the local cache is older than 24 hours
- Can be deployed as a public hosted app on Render

## Current data sources

- `officialchess.org` via its live events API
- `westchesterchessclub.com` schedule page

`Official Chess` is the primary source because it exposes event creation and modification timestamps, venue details, organizers, and direct source URLs for many New York area scholastic events.

## Setup

```powershell
.\.venv\bin\pip.exe install -r requirements.txt
```

If you are not using the repo virtual environment:

```powershell
python -m pip install -r requirements.txt
```

## Run the app

```powershell
.\.venv\bin\python.exe web_app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

The app automatically uses the cached dataset if it was refreshed within the last 24 hours.

## Deploy as a hosted web app

This repo now includes a Render Blueprint in `render.yaml`.

What it creates:

- A public Flask web service running behind `gunicorn`
- A daily refresh cron job that calls the app's private refresh endpoint

To deploy:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint and connect the repo.
3. Render will detect `render.yaml` and create:
   - `ny-chess-tournament-finder`
   - `ny-chess-tournament-refresh`
4. After deploy, Render gives the web service a public `onrender.com` URL that you can share with anyone.

Important details:

- The included Blueprint uses `starter` plans for both the web service and the cron job.
- The cron schedule is set to `0 12 * * *`, which is `8:00 AM` in New York during daylight saving time (`EDT`) on April 11, 2026.
- Render cron schedules use UTC. That means this exact schedule will run at `7:00 AM` during standard time (`EST`) unless you change it seasonally.
- If you want the cheapest possible public deployment, you can remove the cron service and change the web service plan, but then daily pre-refresh and always-on behavior are not guaranteed.

## Refresh and export without the UI

```powershell
.\.venv\bin\python.exe chess_tournament.py --force-refresh
```

This generates:

- `output/nearby_chess_tournaments.csv`
- `output/nearby_chess_tournaments.html`

Useful examples:

```powershell
.\.venv\bin\python.exe chess_tournament.py --home 10583 --max-drive-minutes 120
.\.venv\bin\python.exe chess_tournament.py --search Brooklyn --scholastic-only
.\.venv\bin\python.exe chess_tournament.py --states NY,NJ,CT --sort date
```

## Notes

- Drive time is an estimate based on geographic distance. It is useful for screening events, but you should still check a real navigation app before registering.
- The cache lives in `data/tournaments_cache.json`.
- Coordinate lookups are cached in `data/coordinate_cache.json`.
- If a live refresh fails, the app falls back to the latest cached dataset and shows a warning.
- The hosted app exposes `/healthz` for platform health checks.
- The hosted app exposes `/admin/refresh`, protected by a refresh token, so the cron job can warm the cache without making the action public.
