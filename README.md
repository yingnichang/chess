# New York Chess Tournament Finder

This repository builds a New York area chess tournament finder for parents and players. It collects tournament listings from several public sources, normalizes and deduplicates them, labels events for scholastic and beginner fit, and publishes the result as CSV/JSON exports plus a static GitHub Pages site.

The project has three main pieces:

- `tournament_data.py`: shared data pipeline for scraping, parsing, deduping, filtering, geocoding, caching, and exports
- `chess_tournament.py`: local CLI that writes filtered CSV and HTML reports
- `build_pages.py`: GitHub Pages build script that produces the static browser app in `site/`

## What It Does

The current pipeline:

1. Collects tournament listings from multiple chess event sites.
2. Parses event titles, dates, links, organizers, venues, addresses, sections, fees, and metadata.
3. Classifies events for scholastic fit and beginner-friendliness using keyword heuristics.
4. Deduplicates overlapping events by canonical URLs and semantic matching.
5. Preserves contributing sources when duplicates are merged.
6. Fills in missing city/state data when possible.
7. Geocodes event locations and estimates drive time from a home ZIP.
8. Caches tournament data in `data/tournaments_cache.json`.
9. Caches coordinates in `data/coordinate_cache.json`.
10. Publishes a filterable static site with downloadable CSV and JSON.

## Current Data Sources

`tournament_data.py` currently collects from:

- `officialchess.org`
- `littlehouseofchess.org`
- `new.uschess.org/upcoming-tournaments`
- `events4chess.com`
- `chessintheschools.org`
- `chessfather.com`
- `tristatechess.com`
- `icanj.net`
- `westchesterchessclub.com`

If Little House of Chess cannot be refreshed live, the pipeline can use the tracked fallback file at `seed_data/little_house_events.json`. If a full refresh fails but a previous combined cache exists, the app can serve stale cached data and record the refresh error.

## Requirements

Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

The pinned dependency list currently includes:

- `requests`
- `beautifulsoup4`
- `python-dateutil`
- `geopy`

The code also supports `pgeocode` as an optional ZIP/geocoding helper if it is installed.

## Local Export CLI

Use `chess_tournament.py` when you want local CSV and HTML reports without building the Pages site.

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

CLI options:

- `--months-ahead`
- `--force-refresh`
- `--max-age-hours`
- `--output-dir`
- `--home`
- `--max-drive-minutes`
- `--states`
- `--search`
- `--sort recently_updated|date|closest`
- `--scholastic-only`
- `--beginner-friendly`

## GitHub Pages Site

Use `build_pages.py` to generate the static site:

```bash
python build_pages.py --force-refresh
```

This copies `pages_src/` into `site/`, writes `.nojekyll`, and generates:

- `site/index.html`
- `site/data/tournaments.json`
- `site/data/tournaments.csv`

Preview locally:

```bash
python -m http.server 8000 -d site
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Browser Features

The static frontend in `pages_src/` supports:

- search across tournament, organizer, venue, city, state, summary, and source fields
- multi-select filters for states, cities, and sources
- date-range filtering
- scholastic-only and beginner-friendly toggles
- optional drive-limit filtering from a home ZIP
- sorting by tournament date, recently updated, or closest
- downloadable CSV and JSON exports
- source coverage counts
- URL query syncing for shareable filtered views

The browser resolves home ZIP codes through the public Zippopotam.us API and estimates drive time from straight-line distance.

## Visitor Tracking

The Pages site supports optional GoatCounter analytics through `pages_src/assets/analytics.js`. When configured, it records page views and shows a tracked total in the hero.

For a local build:

```bash
python build_pages.py --analytics-provider goatcounter --analytics-site YOUR_GOATCOUNTER_CODE
```

For GitHub Pages, create repository variables:

```text
ANALYTICS_PROVIDER=goatcounter
ANALYTICS_SITE=YOUR_GOATCOUNTER_CODE
```

Tracking starts only after the updated site is deployed. Past visits before analytics was enabled cannot be recovered from this static site. The public count display also depends on the visitor counter setting in the GoatCounter site.

## Deployment

GitHub Pages deployment is defined in `.github/workflows/deploy-pages.yml`.

The workflow:

- runs on pushes to `main`
- supports manual runs with `workflow_dispatch`
- runs daily at `0 12 * * *`
- installs Python 3.12
- installs `requirements.txt`
- runs `python build_pages.py --force-refresh`
- injects optional analytics settings from GitHub repository variables
- uploads and deploys the generated `site/` directory to GitHub Pages

## Important Defaults

Key defaults live near the top of `tournament_data.py`:

- `DEFAULT_MONTHS_AHEAD = 6`
- `TARGET_STATES = ("NY", "NJ", "CT")`
- `DEFAULT_CACHE_FILE = data/tournaments_cache.json`
- `DEFAULT_COORD_CACHE_FILE = data/coordinate_cache.json`
- `DEFAULT_OUTPUT_DIR = output`

Generated folders such as `data/`, `output/`, and `site/` are intentionally ignored by Git.

## Notes

- Dates and display times are handled in U.S. Eastern Time.
- The site is static; all interactive filtering happens in browser-side JavaScript.
- `from playwright.py` is an experimental scraping prototype and is not part of the production build pipeline.
