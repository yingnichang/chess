from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from tournament_data import (
    DEFAULT_CACHE_FILE,
    DEFAULT_COORD_CACHE_FILE,
    DEFAULT_MONTHS_AHEAD,
    event_table_rows,
    load_or_refresh_dataset,
    write_csv,
)


PAGES_SOURCE_DIR = Path("pages_src")
PAGES_BUILD_DIR = Path("site")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the static GitHub Pages site for the chess tournament finder."
    )
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--months-ahead", type=int, default=DEFAULT_MONTHS_AHEAD)
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

    build_dir = PAGES_BUILD_DIR
    if build_dir.exists():
        shutil.rmtree(build_dir)
    shutil.copytree(PAGES_SOURCE_DIR, build_dir)

    data_dir = build_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / ".nojekyll").write_text("", encoding="utf-8")

    payload = dataset.to_record()
    payload["rows"] = event_table_rows(dataset.events)
    payload["refreshed_this_run"] = refreshed
    (data_dir / "tournaments.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv(dataset.events, data_dir / "tournaments.csv")

    print(f"Built Pages site in {build_dir}")
    print(f"Data refreshed this run: {'yes' if refreshed else 'no'}")
    print(f"Dataset generated at: {dataset.generated_at:%Y-%m-%d %H:%M}")
    print(f"Event count: {len(dataset.events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
