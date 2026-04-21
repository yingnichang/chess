# New York Chess Tournament Finder

This repo builds a New York area chess tournament finder that aggregates live event listings, deduplicates overlapping sources, classifies parent-friendly fit, and publishes the results as both export files and a GitHub Pages site.

The codebase is centered on a shared Python data pipeline in `tournament_data.py`, with two entry points:

- `chess_tournament.py` for local CSV and HTML exports
- `build_pages.py` for the static site deployed to GitHub Pages

## What The Project Does

The current repo:

1. Collects tournament listings from multiple live source sites
2. Normalizes titles, dates, links, organizers, locations, and metadata
3. Tags events for scholastic fit and beginner-friendliness using heuristic rules
4. Deduplicates overlapping events across providers by URL and semantic matching
5. Fills in missing city and state data when possible
6. Geocodes events and supports distance and drive-time estimates from a home ZIP
7. Caches the combined dataset and coordinate lookups locally
8. Publishes a static browser UI with filtering, sorting, and export downloads
9. Rebuilds and deploys the site daily through GitHub Actions

## Current Data Sources

The shared collector in `tournament_data.py` currently pulls from:

- `officialchess.org`
- `littlehouseofchess.org`
- `new.uschess.org/upcoming-tournaments`
- `events4chess.com`
- `chessintheschools.org`
- `chessfather.com`
- `tristatechess.com`
- `icanj.net`
- `westchesterchessclub.com`

If a live refresh fails for Little House of Chess, the repo can fall back to the tracked seed file at `seed_data/little_house_events.json`. If a refresh fails after a cached combined dataset already exists, the app can continue serving stale cached data and record the refresh error.

## Repo Structure

- `tournament_data.py`: shared collection, normalization, dedupe, filtering, geocoding, and export helpers
- `chess_tournament.py`: local export CLI for CSV and HTML output
- `build_pages.py`: static-site build script for GitHub Pages
- `pages_src/`: source HTML, CSS, and browser-side JavaScript for the site
- `.github/workflows/deploy-pages.yml`: scheduled Pages build and deploy workflow
- `seed_data/little_house_events.json`: tracked fallback snapshot for one source
- `from playwright.py`: an experimental Playwright scraping prototype, not part of the main build pipeline

## Data Pipeline Details

`tournament_data.py` builds a single `TournamentDataset` that powers both the export CLI and the Pages site.

Key behaviors in the current version:

- Uses a shared `requests` session for source fetching
- Parses provider-specific formats including WordPress Tribe APIs, HTML calendars, JSON-LD, RSS-like content, and detail pages
- Computes source quality and merges duplicate events instead of keeping raw duplicates
- Preserves `contributing_sources` and `contributing_providers` for merged events
- Stores cached datasets in `data/tournaments_cache.json`
- Stores coordinate lookups in `data/coordinate_cache.json`
- Uses Zippopotam.us for ZIP lookups and optionally uses `pgeocode` and `geopy` when available
- Sorts by `recently_updated`, `date`, or `closest`

## Local Export CLI

Use `chess_tournament.py` when you want a filtered export without building the Pages site.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run a refresh and export:

```bash
python chess_tournament.py --force-refresh
```

This writes:

- `output/nearby_chess_tournaments.csv`
- `output/nearby_chess_tournaments.html`

Useful examples:

```bash
python chess_tournament.py --home 10583 --max-drive-minutes 120
python chess_tournament.py --search Brooklyn --scholastic-only
python chess_tournament.py --states NY,NJ,CT --sort closest
python chess_tournament.py --beginner-friendly --months-ahead 3
```

Current CLI options include:

- `--months-ahead`
- `--force-refresh`
- `--max-age-hours`
- `--output-dir`
- `--home`
- `--max-drive-minutes`
- `--states`
- `--search`
- `--sort` with `recently_updated`, `date`, or `closest`
- `--scholastic-only`
- `--beginner-friendly`

## GitHub Pages Site

Use `build_pages.py` to generate the static site.

```bash
python build_pages.py --force-refresh
```

This copies `pages_src/` into `site/`, writes a `.nojekyll` file, and generates:

- `site/index.html`
- `site/data/tournaments.json`
- `site/data/tournaments.csv`

To preview locally:

```bash
python -m http.server 8000 -d site
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Browser Features

The current frontend supports:

- search by tournament, organizer, venue, city, state, summary, and source
- multi-select filters for states, cities, and sources
- date-range filtering
- scholastic-only and beginner-friendly toggles
- optional drive-limit filtering from a home ZIP
- sort modes for tournament date, recently updated, and closest
- downloadable CSV and JSON exports
- source coverage counts
- URL query syncing for shareable filtered views

The browser resolves home ZIP codes through the public Zippopotam.us API and estimates drive time from straight-line distance.

## Deployment

GitHub Pages deployment is defined in `.github/workflows/deploy-pages.yml`.

The workflow:

- runs on pushes to `main`
- supports manual runs through `workflow_dispatch`
- runs daily on the cron schedule `0 12 * * *`
- installs Python 3.12
- installs `requirements.txt`
- runs `python build_pages.py --force-refresh`
- uploads the built `site/` directory and deploys it to GitHub Pages

Because the workflow runs on GitHub-hosted infrastructure, a failed live refresh does not overwrite the last successful published Pages deployment.

## Requirements

The repo currently declares these Python dependencies in `requirements.txt`:

- `requests`
- `beautifulsoup4`
- `python-dateutil`
- `geopy`

`pgeocode` is supported by the code as an optional extra fallback for ZIP resolution, but it is not currently pinned in `requirements.txt`.

## Notes

- The default target region in code is `NY`, `NJ`, and `CT`.
- The shared pipeline defaults to looking `6` months ahead.
- Generated folders such as `data/`, `output/`, and `site/` are gitignored.
- The experimental file `from playwright.py` is separate from the current production pipeline and is not used by the GitHub Pages workflow.
