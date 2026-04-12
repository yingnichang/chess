from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from tournament_data import (
    CoordinateResolver,
    DEFAULT_CACHE_FILE,
    DEFAULT_COORD_CACHE_FILE,
    DEFAULT_MONTHS_AHEAD,
    DEFAULT_OUTPUT_DIR,
    TARGET_STATES,
    filter_events,
    load_or_refresh_dataset,
    sort_events,
    with_home_distances,
    write_csv,
    write_html_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the tournament dataset and export filtered chess tournament listings."
    )
    parser.add_argument("--months-ahead", type=int, default=DEFAULT_MONTHS_AHEAD)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--home", default="")
    parser.add_argument("--max-drive-minutes", type=int, default=120)
    parser.add_argument("--states", default=",".join(TARGET_STATES))
    parser.add_argument("--search", default="")
    parser.add_argument("--sort", choices=("recently_updated", "date", "closest"), default="recently_updated")
    parser.add_argument("--scholastic-only", action="store_true")
    parser.add_argument("--beginner-friendly", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset, refreshed = load_or_refresh_dataset(
        force_refresh=args.force_refresh,
        max_age_hours=args.max_age_hours,
        months_ahead=args.months_ahead,
        cache_file=DEFAULT_CACHE_FILE,
        coord_cache_file=DEFAULT_COORD_CACHE_FILE,
    )

    events = dataset.events
    resolver = CoordinateResolver(cache_path=DEFAULT_COORD_CACHE_FILE)
    home_label = clean_home_label(args.home)
    if home_label:
        events, _ = with_home_distances(events, home_label, resolver)

    states = [value.strip() for value in args.states.split(",") if value.strip()]
    default_end = date.today() + timedelta(days=31 * args.months_ahead)
    events = filter_events(
        events,
        search_text=args.search,
        start_on=date.today(),
        end_on=default_end,
        states=states,
        scholastic_only=args.scholastic_only,
        beginner_friendly=args.beginner_friendly,
        max_drive_minutes=args.max_drive_minutes if home_label else None,
    )
    events = sort_events(events, mode=args.sort)

    csv_path = args.output_dir / "nearby_chess_tournaments.csv"
    html_path = args.output_dir / "nearby_chess_tournaments.html"
    write_csv(events, csv_path)
    write_html_report(
        events,
        html_path,
        generated_at=dataset.generated_at,
        home_label=home_label,
    )

    print(f"Data refreshed this run: {'yes' if refreshed else 'no'}")
    print(f"Generated dataset timestamp: {dataset.generated_at:%Y-%m-%d %H:%M}")
    if dataset.stale and dataset.refresh_error:
        print(f"Warning: using stale cached data because refresh failed: {dataset.refresh_error}")
    print(f"Saved {len(events)} events")
    print(f"CSV: {csv_path}")
    print(f"HTML: {html_path}")
    for event in events[:12]:
        drive = (
            f"{event.estimated_drive_minutes} min"
            if event.estimated_drive_minutes is not None
            else "n/a"
        )
        start = event.start.strftime("%Y-%m-%d %H:%M") if event.start else "TBD"
        print(f"- {start} | {event.title} | {event.source} | {drive}")
    return 0


def clean_home_label(value: str) -> str:
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
