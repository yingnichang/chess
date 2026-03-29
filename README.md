# Nearby Chess Tournament Scraper

This script collects future chess tournaments from several Northeast chess calendars, filters them to events roughly within 2 hours of driving from Scarsdale, NY 10583, and exports:

- `output/nearby_chess_tournaments.csv`
- `output/nearby_chess_tournaments.html`

The HTML file is designed to be easy to share. The script can also upload both files to a Google Drive folder.

## Sources included

- `https://officialchess.org/events/list/`
- `https://littlehouseofchess.org/calendar/`
- `https://www.westchesterchessclub.com/schedule`
- `https://tristatechess.com/onlineregistration/`
- `https://www.icanj.net/p.php?p=2122&Tournaments%20Calendar=`

## What the script does

- Scrapes upcoming events from the sites above
- Tries to geocode each venue
- Estimates travel time from Scarsdale using straight-line distance plus a conservative road factor
- Flags events that look beginner-friendly or scholastic
- Keeps the original registration/details URL so you can register on the source site
- Optionally uploads the generated CSV and HTML files to Google Drive

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run locally

```powershell
python chess_tournament.py
```

Useful options:

```powershell
python chess_tournament.py --months-ahead 6
python chess_tournament.py --max-drive-minutes 135
python chess_tournament.py --max-air-miles 80
```

## Publish to Google Drive

1. Create a Google Cloud project.
2. Enable the Google Drive API.
3. Create a service account and download the JSON credentials file.
4. Create or choose a Google Drive folder.
5. Share that folder with the service account email.
6. Run:

```powershell
python chess_tournament.py `
  --publish-drive `
  --google-drive-folder-id YOUR_FOLDER_ID `
  --google-service-account-json .\service-account.json `
  --make-public
```

If you use `--make-public`, the uploaded files get public read permissions.

## Notes

- The drive-time filter is an estimate, not live navigation. For final plans, check Google Maps before registering.
- Some calendars change their HTML over time. If one source stops parsing correctly, update that parser in `chess_tournament.py`.
- The script stores venue geocoding results in `.geocode_cache.json` so later runs are faster and gentler on the geocoder.
