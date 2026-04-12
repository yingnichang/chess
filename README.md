# New York Chess Tournament Finder

This project now builds a free public GitHub Pages site for finding chess tournaments in the New York area. It refreshes live tournament data, keeps source and registration links, and lets parents filter by date, location, source, scholastic fit, beginner-friendliness, and estimated driving range from a home ZIP code.

## What the site does

- Pulls upcoming tournament listings from live web sources
- Sorts by most recently updated source listings by default
- Keeps direct registration links and source listing links
- Lets visitors filter by date range, state, city, source, and search text
- Supports a home ZIP code drive filter in the browser
- Publishes as a free public GitHub Pages site
- Refreshes automatically every day through GitHub Actions

## Current data sources

- `officialchess.org` via its live events API
- `westchesterchessclub.com` schedule page

`Official Chess` is the primary source because it exposes event creation and modification timestamps, venue details, organizers, and direct source URLs for many New York area scholastic events.

## Install dependencies

```powershell
.\.venv\bin\pip.exe install -r requirements.txt
```

Or without the repo virtual environment:

```powershell
python -m pip install -r requirements.txt
```

## Build the static site locally

```powershell
.\.venv\bin\python.exe build_pages.py --force-refresh
```

This generates:

- `site/index.html`
- `site/data/tournaments.json`
- `site/data/tournaments.csv`

## Preview locally

After building the site:

```powershell
python -m http.server 8000 -d site
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Refresh and export without building Pages

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

## Publish on GitHub Pages

This repo includes a GitHub Actions workflow at `.github/workflows/deploy-pages.yml`.

It will:

- Build the static site
- Upload the built `site/` folder as the Pages artifact
- Deploy it to GitHub Pages
- Rebuild it daily on a schedule

### One-time GitHub setup

1. Push the repo to GitHub.
2. In GitHub, open `Settings` -> `Pages`.
3. Under **Build and deployment**, choose **GitHub Actions** as the source.
4. Make sure the workflow file is on the default branch, typically `main`.

After that, GitHub Actions will publish the site to:

`https://<your-github-username>.github.io/<repo-name>/`

For this repo, the public URL will be:

`https://yingnichang.github.io/chess/`

once the workflow runs successfully from `main`.

## Daily refresh schedule

The workflow uses this cron schedule:

```text
0 12 * * *
```

GitHub Actions schedules are in UTC. On **April 11, 2026**, New York is on EDT, so that schedule is **8:00 AM New York time**.

Two practical notes:

- GitHub Actions schedules are best-effort and may run a little late.
- During standard time in winter, `12:00 UTC` becomes `7:00 AM` in New York unless you change the workflow seasonally.

## Notes

- Drive time is an estimate based on geographic distance. It is useful for screening events, but you should still check a real navigation app before registering.
- The browser-side drive filter works best with a 5-digit US ZIP code.
- The cache lives in `data/tournaments_cache.json`.
- Coordinate lookups are cached in `data/coordinate_cache.json`.
- If a live refresh fails during a workflow run, the currently published GitHub Pages site stays on the previous successful deployment.
