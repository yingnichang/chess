from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from geopy.geocoders import Nominatim

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    service_account = None
    build = None
    MediaFileUpload = None


HOME_ZIP = "10583"
HOME_LABEL = "Scarsdale, NY 10583"
HOME_LAT = 40.9899
HOME_LON = -73.7976
USER_AGENT = "ScarsdaleChessFinder/1.0 (+https://example.invalid)"
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_MONTHS_AHEAD = 4
DEFAULT_MAX_AIR_MILES = 70.0
DEFAULT_MAX_DRIVE_MINUTES = 120
GEOCODE_CACHE_FILE = Path(".geocode_cache.json")


KEYWORD_RECOMMENDED = (
    "scholastic",
    "youth",
    "kids",
    "junior",
    "elementary",
    "primary",
    "grades",
    "k-",
    "k ",
    "u300",
    "u400",
    "u500",
    "u600",
    "u700",
    "u800",
    "u900",
    "u1000",
    "novice",
    "beginner",
)

KEYWORD_CAUTION = (
    "championship",
    "open championship",
    "masters",
    "expert",
    "under 1800",
    "under 2000",
)


@dataclass
class Event:
    source: str
    title: str
    start: datetime | None = None
    end: datetime | None = None
    venue_name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    registration_url: str = ""
    source_url: str = ""
    details_url: str = ""
    organizer: str = ""
    notes: str = ""
    raw_date_text: str = ""
    age_fit: str = ""
    beginner_fit: str = ""
    distance_air_miles: float | None = None
    estimated_drive_minutes: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    include: bool = True
    dedupe_key: str = field(default="", repr=False)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def fetch_text(session: requests.Session, url: str, timeout: int = 25) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def safe_parse_date(value: str | None, default_year: int | None = None) -> datetime | None:
    if not value:
        return None
    try:
        default = datetime(default_year or date.today().year, 1, 1)
        return date_parser.parse(value, fuzzy=True, default=default)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return safe_parse_date(value)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def to_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_dedupe_key(event: Event) -> str:
    parts = [
        to_slug(event.title),
        (event.start.date().isoformat() if event.start else ""),
        to_slug(event.venue_name or event.address or event.city),
    ]
    return "|".join(parts)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_miles * math.asin(math.sqrt(a))


def estimate_drive_minutes(air_miles: float) -> int:
    road_miles = air_miles * 1.25
    avg_speed_mph = 38
    return int(round((road_miles / avg_speed_mph) * 60))


def load_geocode_cache(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_geocode_cache(path: Path, cache: dict[str, dict[str, float]]) -> None:
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def geocode_events(events: list[Event], cache_path: Path, pause_seconds: float = 1.1) -> None:
    cache = load_geocode_cache(cache_path)
    geolocator = Nominatim(user_agent=USER_AGENT, timeout=15)

    for event in events:
        address = compose_full_address(event)
        if not address:
            continue
        cache_key = hashlib.sha1(address.encode("utf-8")).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            event.latitude = cached["lat"]
            event.longitude = cached["lon"]
            continue

        try:
            result = geolocator.geocode(address)
        except Exception:
            result = None

        if result:
            event.latitude = float(result.latitude)
            event.longitude = float(result.longitude)
            cache[cache_key] = {"lat": event.latitude, "lon": event.longitude}
            save_geocode_cache(cache_path, cache)
            time.sleep(pause_seconds)


def compose_full_address(event: Event) -> str:
    parts = [event.venue_name, event.address, event.city, event.state, event.postal_code]
    return ", ".join([clean_text(part) for part in parts if clean_text(part)])


def assign_distance_fields(events: list[Event]) -> None:
    for event in events:
        if event.latitude is None or event.longitude is None:
            continue
        air_miles = haversine_miles(HOME_LAT, HOME_LON, event.latitude, event.longitude)
        event.distance_air_miles = round(air_miles, 1)
        event.estimated_drive_minutes = estimate_drive_minutes(air_miles)


def score_event_fit(event: Event) -> None:
    haystack = " ".join(
        [
            event.title,
            event.notes,
            event.venue_name,
            event.organizer,
            event.raw_date_text,
        ]
    ).lower()
    event.age_fit = "good" if any(keyword in haystack for keyword in KEYWORD_RECOMMENDED) else "unclear"
    event.beginner_fit = "good" if any(keyword in haystack for keyword in KEYWORD_RECOMMENDED) else "unclear"
    if any(keyword in haystack for keyword in KEYWORD_CAUTION):
        if event.beginner_fit == "good":
            event.beginner_fit = "mixed"
        elif event.beginner_fit == "unclear":
            event.beginner_fit = "maybe-hard"


def keep_event(
    event: Event,
    earliest_date: date,
    latest_date: date,
    max_air_miles: float,
    max_drive_minutes: int,
) -> bool:
    if not event.start:
        return False
    event_day = event.start.date()
    if event_day < earliest_date or event_day > latest_date:
        return False
    if event.distance_air_miles is None or event.estimated_drive_minutes is None:
        return True
    return (
        event.distance_air_miles <= max_air_miles
        and event.estimated_drive_minutes <= max_drive_minutes
    )


def dedupe_events(events: list[Event]) -> list[Event]:
    best_by_key: dict[str, Event] = {}
    for event in events:
        event.dedupe_key = build_dedupe_key(event)
        existing = best_by_key.get(event.dedupe_key)
        if not existing:
            best_by_key[event.dedupe_key] = event
            continue
        existing_links = sum(bool(value) for value in [existing.registration_url, existing.details_url, existing.address])
        new_links = sum(bool(value) for value in [event.registration_url, event.details_url, event.address])
        if new_links > existing_links:
            best_by_key[event.dedupe_key] = event
    return list(best_by_key.values())


def parse_tribe_events_api(
    session: requests.Session,
    site_root: str,
    source_name: str,
    months_ahead: int,
) -> list[Event]:
    events: list[Event] = []
    start_day = date.today()
    end_day = start_day + timedelta(days=31 * months_ahead)
    params = {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "per_page": "100",
        "page": "1",
    }
    api_url = urljoin(site_root, f"/wp-json/tribe/events/v1/events?{urlencode(params)}")

    while api_url:
        try:
            payload = session.get(api_url, timeout=25).json()
        except Exception:
            break

        for item in payload.get("events", []):
            venue = item.get("venue") or {}
            event = Event(
                source=source_name,
                title=clean_text(item.get("title")),
                start=parse_iso_date(item.get("start_date")),
                end=parse_iso_date(item.get("end_date")),
                venue_name=clean_text(venue.get("venue")),
                address=clean_text(venue.get("address")),
                city=clean_text(venue.get("city")),
                state=clean_text(venue.get("state")),
                postal_code=clean_text(venue.get("zip")),
                source_url=site_root,
                details_url=item.get("url", ""),
                registration_url=find_registration_url_from_text(item.get("description", "")) or item.get("website", ""),
                organizer=clean_text(((item.get("organizer") or [{}])[0]).get("organizer")),
                notes=clean_text(strip_html(item.get("description", ""))),
                raw_date_text=clean_text(item.get("start_date_details", {}).get("month", "")),
            )
            score_event_fit(event)
            events.append(event)

        next_rest_url = payload.get("next_rest_url")
        api_url = next_rest_url or ""

    return events


def strip_html(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def find_registration_url_from_text(text: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", text or "")
    return match.group(0) if match else ""


def parse_westchester_schedule(session: requests.Session, url: str) -> list[Event]:
    html = fetch_text(session, url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    current_year = date.today().year
    events: list[Event] = []

    date_line_re = re.compile(
        r"^(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:,\s*(?P<year>\d{4}))?\s*[:\-]?\s*(?P<title>.+)$"
    )

    for line in lines:
        match = date_line_re.match(line)
        if not match:
            continue
        year = int(match.group("year") or current_year)
        dt = safe_parse_date(f"{match.group('month')} {match.group('day')} {year}")
        if not dt:
            continue
        event = Event(
            source="Westchester Chess Club",
            title=match.group("title"),
            start=dt.replace(hour=19, minute=30),
            venue_name="Trinity Lutheran Church",
            address="25 Crane Rd",
            city="Scarsdale",
            state="NY",
            postal_code="10583",
            source_url=url,
            details_url=url,
            registration_url=url,
            notes="Local club schedule entry. Confirm format and registration with the club before attending.",
            raw_date_text=line,
        )
        score_event_fit(event)
        if "scholastic" in event.title.lower() or "beginner" in event.title.lower():
            event.age_fit = "good"
        events.append(event)

    return events


def parse_tristate(session: requests.Session, url: str) -> list[Event]:
    html = fetch_text(session, url)
    soup = BeautifulSoup(html, "html.parser")
    events: list[Event] = []

    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(url, link.get("href", ""))
        if not title or len(title) < 6:
            continue
        if "register" not in title.lower() and "chess" not in title.lower():
            continue

        date_match = re.search(
            r"((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?)",
            title,
            flags=re.IGNORECASE,
        )
        start = safe_parse_date(date_match.group(1), default_year=date.today().year) if date_match else None
        event = Event(
            source="Tri-State Chess",
            title=title,
            start=start,
            source_url=url,
            details_url=href,
            registration_url=href,
            notes="Scraped from Tri-State Chess online registration page.",
            raw_date_text=date_match.group(1) if date_match else "",
        )
        score_event_fit(event)
        events.append(event)

    return events


def parse_icanj_calendar(session: requests.Session, url: str) -> list[Event]:
    html = fetch_text(session, url)
    soup = BeautifulSoup(html, "html.parser")
    events: list[Event] = []
    current_year = date.today().year

    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(url, link.get("href", ""))
        if not title:
            continue
        if "tournament" not in title.lower() and "quad" not in title.lower() and "championship" not in title.lower():
            continue
        if "calendar" in title.lower():
            continue

        date_match = re.search(
            r"((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:[-/]\d{1,2})?(?:,\s*\d{4})?)",
            title,
            flags=re.IGNORECASE,
        )
        start = safe_parse_date(date_match.group(1), default_year=current_year) if date_match else None
        event = Event(
            source="ICA NJ",
            title=title,
            start=start,
            source_url=url,
            details_url=href,
            registration_url=href,
            notes="Scraped from ICA NJ tournament calendar links.",
            raw_date_text=date_match.group(1) if date_match else "",
        )
        score_event_fit(event)
        events.append(event)

    return events


def merge_and_enrich(
    events: list[Event],
    months_ahead: int,
    max_air_miles: float,
    max_drive_minutes: int,
) -> list[Event]:
    geocode_events(events, GEOCODE_CACHE_FILE)
    assign_distance_fields(events)

    earliest = date.today()
    latest = earliest + timedelta(days=31 * months_ahead)
    filtered = [
        event
        for event in events
        if keep_event(event, earliest, latest, max_air_miles, max_drive_minutes)
    ]
    deduped = dedupe_events(filtered)
    deduped.sort(
        key=lambda event: (
            0 if event.age_fit == "good" else 1,
            0 if event.beginner_fit == "good" else 1,
            event.estimated_drive_minutes if event.estimated_drive_minutes is not None else 9999,
            event.start or datetime.max,
            event.title.lower(),
        )
    )
    return deduped


def write_csv(events: list[Event], path: Path) -> None:
    fieldnames = [
        "source",
        "title",
        "start",
        "end",
        "venue_name",
        "address",
        "city",
        "state",
        "postal_code",
        "distance_air_miles",
        "estimated_drive_minutes",
        "age_fit",
        "beginner_fit",
        "registration_url",
        "details_url",
        "source_url",
        "organizer",
        "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            row = asdict(event)
            row["start"] = event.start.isoformat(sep=" ") if event.start else ""
            row["end"] = event.end.isoformat(sep=" ") if event.end else ""
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_html_report(events: list[Event], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for event in events:
        start_text = event.start.strftime("%a %b %d, %Y %I:%M %p") if event.start else "Date TBD"
        distance_text = (
            f"{event.distance_air_miles} air miles, est. {event.estimated_drive_minutes} min drive"
            if event.distance_air_miles is not None and event.estimated_drive_minutes is not None
            else "Distance not available"
        )
        location = ", ".join(
            part for part in [event.venue_name, event.address, event.city, event.state] if part
        )
        cards.append(
            f"""
            <article class="card">
              <div class="meta">{event.source}</div>
              <h2>{html_escape(event.title)}</h2>
              <p><strong>When:</strong> {html_escape(start_text)}</p>
              <p><strong>Where:</strong> {html_escape(location or "TBD")}</p>
              <p><strong>Fit:</strong> age={html_escape(event.age_fit)}, beginner={html_escape(event.beginner_fit)}</p>
              <p><strong>Distance:</strong> {html_escape(distance_text)}</p>
              <p><a href="{html_escape(event.registration_url or event.details_url or event.source_url)}">Register / details</a></p>
            </article>
            """
        )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Nearby Chess Tournaments</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --card: #fffdf7;
      --ink: #1c1b18;
      --accent: #7a2e1f;
      --border: #d8ccb8;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background:
        radial-gradient(circle at top left, #fff5df 0%, transparent 25%),
        linear-gradient(180deg, #f0eadf 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 960px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      font-size: 2.2rem;
      margin-bottom: 0.25rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 10px 28px rgba(33, 23, 10, 0.08);
    }}
    .meta {{
      color: var(--accent);
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    a {{
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <main>
    <h1>Nearby Chess Tournaments</h1>
    <p>Home base: {html_escape(HOME_LABEL)}. Filter: future events within about 2 hours driving distance.</p>
    <p>Generated: {html_escape(generated)}</p>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def drive_service(credentials_path: Path):
    if service_account is None or build is None or MediaFileUpload is None:
        raise RuntimeError(
            "Google Drive libraries are not installed. Add google-api-python-client and google-auth."
        )
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials)


def upload_to_google_drive(
    files: list[Path],
    credentials_path: Path,
    folder_id: str,
    make_public: bool,
) -> list[dict[str, str]]:
    service = drive_service(credentials_path)
    uploaded: list[dict[str, str]] = []

    for file_path in files:
        query = (
            f"name = '{file_path.name}' and '{folder_id}' in parents and trashed = false"
        )
        existing = (
            service.files()
            .list(q=query, fields="files(id, name, webViewLink)", pageSize=1)
            .execute()
            .get("files", [])
        )
        media = MediaFileUpload(str(file_path), resumable=False)

        if existing:
            file_id = existing[0]["id"]
            result = (
                service.files()
                .update(fileId=file_id, media_body=media, fields="id, name, webViewLink")
                .execute()
            )
        else:
            metadata = {"name": file_path.name, "parents": [folder_id]}
            result = (
                service.files()
                .create(body=metadata, media_body=media, fields="id, name, webViewLink")
                .execute()
            )

        if make_public:
            service.permissions().create(
                fileId=result["id"],
                body={"role": "reader", "type": "anyone"},
            ).execute()

        uploaded.append(
            {
                "name": result["name"],
                "id": result["id"],
                "webViewLink": result.get("webViewLink", ""),
            }
        )

    return uploaded


def collect_events(
    session: requests.Session,
    months_ahead: int,
) -> list[Event]:
    events: list[Event] = []
    events.extend(
        parse_tribe_events_api(
            session,
            "https://officialchess.org",
            "Official Chess",
            months_ahead,
        )
    )
    events.extend(
        parse_tribe_events_api(
            session,
            "https://littlehouseofchess.org",
            "Little House of Chess",
            months_ahead,
        )
    )
    events.extend(parse_westchester_schedule(session, "https://www.westchesterchessclub.com/schedule"))
    events.extend(parse_tristate(session, "https://tristatechess.com/onlineregistration/"))
    events.extend(parse_icanj_calendar(session, "https://www.icanj.net/p.php?p=2122&Tournaments%20Calendar="))
    return events


def print_summary(events: list[Event], csv_path: Path, html_path: Path) -> None:
    print(f"Saved {len(events)} events")
    print(f"CSV: {csv_path}")
    print(f"HTML: {html_path}")
    for event in events[:12]:
        when = event.start.strftime("%Y-%m-%d %H:%M") if event.start else "TBD"
        drive = f"{event.estimated_drive_minutes} min" if event.estimated_drive_minutes is not None else "n/a"
        print(f"- {when} | {event.title} | {event.source} | {drive}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect nearby future chess tournaments and optionally publish the results to Google Drive."
    )
    parser.add_argument("--months-ahead", type=int, default=DEFAULT_MONTHS_AHEAD)
    parser.add_argument("--max-air-miles", type=float, default=DEFAULT_MAX_AIR_MILES)
    parser.add_argument("--max-drive-minutes", type=int, default=DEFAULT_MAX_DRIVE_MINUTES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--google-drive-folder-id", default=os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""))
    parser.add_argument(
        "--google-service-account-json",
        type=Path,
        default=Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service-account.json")),
    )
    parser.add_argument("--publish-drive", action="store_true")
    parser.add_argument("--make-public", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    session = build_session()

    try:
        events = collect_events(session, months_ahead=args.months_ahead)
    except requests.HTTPError as exc:
        print(f"HTTP error while scraping: {exc}", file=sys.stderr)
        return 2

    filtered = merge_and_enrich(
        events=events,
        months_ahead=args.months_ahead,
        max_air_miles=args.max_air_miles,
        max_drive_minutes=args.max_drive_minutes,
    )

    csv_path = args.output_dir / "nearby_chess_tournaments.csv"
    html_path = args.output_dir / "nearby_chess_tournaments.html"
    write_csv(filtered, csv_path)
    write_html_report(filtered, html_path)
    print_summary(filtered, csv_path, html_path)

    if args.publish_drive:
        if not args.google_drive_folder_id:
            print("--publish-drive requires --google-drive-folder-id", file=sys.stderr)
            return 3
        uploads = upload_to_google_drive(
            files=[csv_path, html_path],
            credentials_path=args.google_service_account_json,
            folder_id=args.google_drive_folder_id,
            make_public=args.make_public,
        )
        for item in uploads:
            print(f"Drive: {item['name']} -> {item['webViewLink']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
