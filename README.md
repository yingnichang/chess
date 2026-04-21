# US Chess Tournament Data Export

This project fetches US Chess tournament history and game history for one or more players, then exports the results to CSV files.

The current script also builds a rating-improvement plan for a target player by comparing that player's progress against the current top finishers from a standings page.

## Current Behavior

Running `tournament_data.py` currently does the following:

1. Scrapes the top `10` player IDs from the standings page at `https://chessevents.com/event/nyscholastics/2026/standings/kcc`
2. Pulls tournament history from the US Chess member events API
3. Pulls section-based rating changes from the US Chess sections API
4. Pulls game history from the US Chess games API
5. Writes combined CSV exports for all selected players
6. Builds a 365-day monthly target plan for player `32496478`

## Files

- `tournament_data.py`: main data collection and planning script
- `requirements.txt`: Python dependencies
- `uschess_players_tournament_history.csv`: combined tournament history export
- `uschess_players_games.csv`: combined games export
- `uschess_target_player_32496478_plan.csv`: generated target-player rating plan

## Outputs

### Tournament History CSV

`uschess_players_tournament_history.csv` includes event metadata plus rating details when available, including fields such as:

- `playerId`
- `id`
- `name`
- `startDate`
- `endDate`
- `stateCode`
- `historySection`
- `ratingSummary`
- `regularRatingBefore`
- `regularRatingAfter`
- `regularRatingChange`
- `quickRatingBefore`
- `quickRatingAfter`
- `blitzRatingBefore`
- `blitzRatingAfter`

### Games CSV

`uschess_players_games.csv` includes fields such as:

- `playerId`
- `eventId`
- `eventName`
- `eventStartDate`
- `eventEndDate`
- `sectionName`
- `sectionNumber`
- `ratingSystem`
- `gameDate`
- `color`
- `result`
- `opponentId`
- `opponentName`

Note: the US Chess games API does not provide per-game rating changes, so `ratingBefore` and `ratingAfter` are left blank.

### Target Plan CSV

`uschess_target_player_32496478_plan.csv` includes the target player's planned rating checkpoints, with fields such as:

- `targetPlayerId`
- `referenceTopPlayerId`
- `referenceTopPlayerName`
- `frequency`
- `periodStart`
- `periodEnd`
- `targetRegularRating`
- `periodGainNeeded`
- `eventPeriod`
- `suggestedPattern`

## Setup

Install the Python packages:

```bash
pip install -r requirements.txt
```

Install the Playwright browser used for standings-page scraping:

```bash
python -m playwright install chromium
```

## Run

```bash
python tournament_data.py
```

## Configuration

The script is currently configured through constants near the top of `tournament_data.py`.

Important defaults:

- `STANDINGS_URL = "https://chessevents.com/event/nyscholastics/2026/standings/kcc"`
- `TOP_N = 10`
- `TARGET_PLAYER_ID = "32496478"`
- `TARGET_PLAN_DAYS = 365`
- `TARGET_PLAN_FREQUENCY = "monthly"`
- `TARGET_TOP_GROUP_BLEND = 0.75`

If you do not want to scrape the standings page, you can clear `STANDINGS_URL` and populate `PLAYER_IDS` manually.
