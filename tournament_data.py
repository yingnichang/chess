from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

try:
    import pgeocode
except ImportError:
    pgeocode = None

try:
    from geopy.geocoders import Nominatim
except ImportError:
    Nominatim = None


USER_AGENT = "NYChessParentFinder/1.0 (+https://example.com)"
DEFAULT_MONTHS_AHEAD = 6
TARGET_STATES = ("NY", "NJ", "CT")
DEFAULT_CACHE_DIR = Path("data")
DEFAULT_CACHE_FILE = DEFAULT_CACHE_DIR / "tournaments_cache.json"
DEFAULT_COORD_CACHE_FILE = DEFAULT_CACHE_DIR / "coordinate_cache.json"
DEFAULT_OUTPUT_DIR = Path("output")
OFFICIAL_CHESS_SOURCE_URL = "https://officialchess.org/events/list/"
WESTCHESTER_SOURCE_URL = "https://www.westchesterchessclub.com/schedule"
ZIP_LOOKUP_URL_TEMPLATE = "https://api.zippopotam.us/us/{postal_code}"

KEYWORD_SCHOLASTIC = (
    "scholastic",
    "students only",
    "youth",
    "junior",
    "elementary",
    "middle school",
    "high school",
    "grades",
    "kindergarten",
    "kids",
    "rookie",
)

KEYWORD_BEGINNER = (
    "beginner",
    "novice",
    "u300",
    "u400",
    "u500",
    "u600",
    "u700",
    "u800",
    "u900",
    "under 300",
    "under 400",
    "under 500",
    "under 600",
    "under 700",
    "under 800",
    "under 900",
)

KEYWORD_ADVANCED = (
    "championship",
    "masters",
    "expert",
    "elite",
    "u1600",
    "u1800",
    "u2000",
    "1000+",
)

SOURCE_PRIORITY = {
    "official_chess": 100,
    "westchester_chess_club": 60,
}


@dataclass(slots=True)
class Event:
    provider: str
    source: str
    title: str
    start: datetime | None = None
    end: datetime | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    event_url: str = ""
    registration_url: str = ""
    source_url: str = ""
    venue_name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    organizer: str = ""
    summary: str = ""
    description: str = ""
    entry_fee: str = ""
    sections: str = ""
    scholastic_only: str = ""
    time_control: str = ""
    rounds: str = ""
    uscf_rating_impact: str = ""
    age_fit: str = "unclear"
    beginner_fit: str = "unclear"
    latitude: float | None = None
    longitude: float | None = None
    distance_air_miles: float | None = None
    estimated_drive_minutes: int | None = None
    tags: list[str] = field(default_factory=list)
    dedupe_key: str = field(default="", repr=False)

    @property
    def primary_link(self) -> str:
        return self.registration_url or self.event_url or self.source_url

    @property
    def location_label(self) -> str:
        parts = [self.venue_name, self.address, self.city, self.state, self.postal_code]
        return ", ".join(part for part in parts if part)

    @property
    def updated_sort_value(self) -> datetime:
        return self.source_updated_at or self.source_created_at or self.start or datetime.min

    def to_record(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "source": self.source,
            "title": self.title,
            "start": self.start.isoformat() if self.start else "",
            "end": self.end.isoformat() if self.end else "",
            "source_created_at": self.source_created_at.isoformat() if self.source_created_at else "",
            "source_updated_at": self.source_updated_at.isoformat() if self.source_updated_at else "",
            "event_url": self.event_url,
            "registration_url": self.registration_url,
            "source_url": self.source_url,
            "venue_name": self.venue_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "organizer": self.organizer,
            "summary": self.summary,
            "description": self.description,
            "entry_fee": self.entry_fee,
            "sections": self.sections,
            "scholastic_only": self.scholastic_only,
            "time_control": self.time_control,
            "rounds": self.rounds,
            "uscf_rating_impact": self.uscf_rating_impact,
            "age_fit": self.age_fit,
            "beginner_fit": self.beginner_fit,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "distance_air_miles": self.distance_air_miles,
            "estimated_drive_minutes": self.estimated_drive_minutes,
            "tags": self.tags,
        }

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "Event":
        return cls(
            provider=str(record.get("provider", "")),
            source=str(record.get("source", "")),
            title=str(record.get("title", "")),
            start=parse_iso_datetime(record.get("start")),
            end=parse_iso_datetime(record.get("end")),
            source_created_at=parse_iso_datetime(record.get("source_created_at")),
            source_updated_at=parse_iso_datetime(record.get("source_updated_at")),
            event_url=str(record.get("event_url", "")),
            registration_url=str(record.get("registration_url", "")),
            source_url=str(record.get("source_url", "")),
            venue_name=str(record.get("venue_name", "")),
            address=str(record.get("address", "")),
            city=str(record.get("city", "")),
            state=str(record.get("state", "")),
            postal_code=str(record.get("postal_code", "")),
            organizer=str(record.get("organizer", "")),
            summary=str(record.get("summary", "")),
            description=str(record.get("description", "")),
            entry_fee=str(record.get("entry_fee", "")),
            sections=str(record.get("sections", "")),
            scholastic_only=str(record.get("scholastic_only", "")),
            time_control=str(record.get("time_control", "")),
            rounds=str(record.get("rounds", "")),
            uscf_rating_impact=str(record.get("uscf_rating_impact", "")),
            age_fit=str(record.get("age_fit", "unclear")),
            beginner_fit=str(record.get("beginner_fit", "unclear")),
            latitude=to_float(record.get("latitude")),
            longitude=to_float(record.get("longitude")),
            distance_air_miles=to_float(record.get("distance_air_miles")),
            estimated_drive_minutes=to_int(record.get("estimated_drive_minutes")),
            tags=[str(tag) for tag in record.get("tags", []) or []],
        )


@dataclass(slots=True)
class TournamentDataset:
    generated_at: datetime
    events: list[Event]
    stale: bool = False
    refresh_error: str = ""

    @property
    def source_count(self) -> int:
        return len({event.source for event in self.events})

    def to_record(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "stale": self.stale,
            "refresh_error": self.refresh_error,
            "events": [event.to_record() for event in self.events],
        }

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "TournamentDataset":
        return cls(
            generated_at=parse_iso_datetime(record.get("generated_at")) or datetime.now(),
            stale=bool(record.get("stale", False)),
            refresh_error=str(record.get("refresh_error", "")),
            events=[Event.from_record(item) for item in record.get("events", []) or []],
        )


class CoordinateResolver:
    def __init__(self, cache_path: Path = DEFAULT_COORD_CACHE_FILE):
        self.cache_path = cache_path
        self.cache = load_json_file(cache_path)
        self.zip_resolver = pgeocode.Nominatim("us") if pgeocode is not None else None
        self.geolocator = (
            Nominatim(user_agent=USER_AGENT, timeout=15) if Nominatim is not None else None
        )

    def resolve_home_query(self, query: str) -> tuple[float, float] | None:
        return self.resolve_query(query)

    def resolve_event(self, event: Event) -> tuple[float, float] | None:
        candidates = []
        if event.postal_code:
            candidates.append(event.postal_code)
        full_address = compose_full_address(event)
        if full_address:
            candidates.append(full_address)
        city_state = ", ".join(part for part in [event.city, event.state] if part)
        if city_state:
            candidates.append(city_state)

        seen: set[str] = set()
        for candidate in candidates:
            normalized = clean_text(candidate)
            if not normalized or normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            coords = self.resolve_query(normalized)
            if coords is not None:
                return coords
        return None

    def resolve_query(self, query: str) -> tuple[float, float] | None:
        query = clean_text(query)
        if not query:
            return None

        if postal_code := normalize_postal_code(query):
            coords = self._resolve_zip(postal_code)
            if coords is not None:
                return coords

        cache_key = self._cache_key(query)
        cached = self.cache.get(cache_key)
        if cached:
            return (float(cached["lat"]), float(cached["lon"]))

        if self.geolocator is None:
            return None

        try:
            result = self.geolocator.geocode(query)
        except Exception:
            result = None

        if result is None:
            return None

        coords = (float(result.latitude), float(result.longitude))
        self.cache[cache_key] = {"lat": coords[0], "lon": coords[1], "query": query}
        save_json_file(self.cache_path, self.cache)
        return coords

    def _resolve_zip(self, postal_code: str) -> tuple[float, float] | None:
        cache_key = self._cache_key(f"zip:{postal_code}")
        cached = self.cache.get(cache_key)
        if cached:
            return (float(cached["lat"]), float(cached["lon"]))

        coords = self._resolve_zip_from_api(postal_code)
        if coords is None and self.zip_resolver is not None:
            record = self.zip_resolver.query_postal_code(postal_code)
            latitude = getattr(record, "latitude", None)
            longitude = getattr(record, "longitude", None)
            if latitude is not None and longitude is not None and not is_nan(latitude) and not is_nan(longitude):
                coords = (float(latitude), float(longitude))

        if coords is None:
            return None

        self.cache[cache_key] = {"lat": coords[0], "lon": coords[1], "query": postal_code}
        save_json_file(self.cache_path, self.cache)
        return coords

    @staticmethod
    def _cache_key(query: str) -> str:
        return hashlib.sha1(query.lower().encode("utf-8")).hexdigest()

    def _resolve_zip_from_api(self, postal_code: str) -> tuple[float, float] | None:
        try:
            response = requests.get(
                ZIP_LOOKUP_URL_TEMPLATE.format(postal_code=postal_code),
                headers={"User-Agent": USER_AGENT},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        places = payload.get("places") or []
        if not places:
            return None

        first_place = places[0]
        latitude = to_float(first_place.get("latitude"))
        longitude = to_float(first_place.get("longitude"))
        if latitude is None or longitude is None:
            return None
        return (latitude, longitude)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    return re.sub(r"\s+", " ", text).strip()


def strip_html(value: str) -> str:
    return clean_text(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True))


def safe_parse_date(value: str | None, default_year: int | None = None) -> datetime | None:
    if not value:
        return None
    try:
        default = datetime(default_year or date.today().year, 1, 1)
        return date_parser.parse(str(value), fuzzy=True, default=default).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_iso_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return safe_parse_date(str(value))


def to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_nan(value: object) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def normalize_postal_code(value: str | None) -> str:
    text = clean_text(value)
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    return match.group(1) if match else ""


def canonicalize_url(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme:
        return text
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def to_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()).strip("-")


def compose_full_address(event: Event) -> str:
    return ", ".join(
        part
        for part in [event.venue_name, event.address, event.city, event.state, event.postal_code]
        if part
    )


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
    road_miles = air_miles * 1.23
    average_speed_mph = 39.0
    return int(round((road_miles / average_speed_mph) * 60))


def load_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def extract_urls_from_html(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    urls: list[str] = []
    for link in soup.select("a[href]"):
        href = clean_text(link.get("href"))
        if href:
            urls.append(href)
    return urls


def choose_registration_url(event_url: str, website: str, description_html: str) -> str:
    if website:
        return website
    for url in extract_urls_from_html(description_html):
        lower = url.lower()
        if "google.com/maps" in lower:
            continue
        if lower.endswith(".pdf"):
            continue
        if "officialchess.org" in lower and url != event_url:
            continue
        return url
    return event_url


def extract_entry_fee(description_text: str) -> str:
    patterns = (
        r"Entry Fee[:\s]+\$?\s*(\d+(?:\.\d{2})?)",
        r"EF[:\s]+\$?\s*(\d+(?:\.\d{2})?)",
        r"from \$\s*(\d+(?:\.\d{2})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, description_text, flags=re.IGNORECASE)
        if match:
            return f"${match.group(1)}"
    return ""


def summarize_text(text: str, max_length: int = 280) -> str:
    text = clean_text(text)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def custom_field_map(custom_fields: dict[str, dict[str, str]] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for payload in (custom_fields or {}).values():
        label = clean_text(payload.get("label"))
        value = clean_text(str(payload.get("value", "")).replace("|", ", "))
        if label and value:
            result[label] = value
    return result


def classify_event_fit(event: Event) -> Event:
    scholastic_text = clean_text(event.scholastic_only).lower()
    haystack = " ".join(
        [
            event.title,
            event.summary,
            event.description,
            event.sections,
            event.organizer,
            event.venue_name,
            event.time_control,
        ]
    ).lower()

    if scholastic_text.startswith("yes") or any(keyword in haystack for keyword in KEYWORD_SCHOLASTIC):
        event.age_fit = "good"
    else:
        event.age_fit = "unclear"

    if any(keyword in haystack for keyword in KEYWORD_ADVANCED):
        event.beginner_fit = "mixed" if event.age_fit == "good" else "maybe-hard"
    elif scholastic_text.startswith("yes") or any(keyword in haystack for keyword in KEYWORD_BEGINNER):
        event.beginner_fit = "good"
    else:
        event.beginner_fit = "unclear"

    tags: list[str] = []
    if event.age_fit == "good":
        tags.append("scholastic")
    if event.beginner_fit == "good":
        tags.append("beginner-friendly")
    if event.entry_fee:
        tags.append(f"entry {event.entry_fee}")
    event.tags = tags
    return event


def parse_official_chess_event(item: dict[str, object]) -> Event:
    description_html = str(item.get("description", "") or "")
    description_text = strip_html(description_html)
    venue = item.get("venue") or {}
    organizer_payload = (item.get("organizer") or [{}])[0]
    fields = custom_field_map(item.get("custom_fields"))

    event = Event(
        provider="official_chess",
        source="Official Chess",
        title=clean_text(item.get("title")),
        start=parse_iso_datetime(item.get("start_date")),
        end=parse_iso_datetime(item.get("end_date")),
        source_created_at=parse_iso_datetime(item.get("date")),
        source_updated_at=parse_iso_datetime(item.get("modified")),
        event_url=canonicalize_url(item.get("url")),
        registration_url=canonicalize_url(
            choose_registration_url(
                event_url=canonicalize_url(item.get("url")),
                website=canonicalize_url(item.get("website")),
                description_html=description_html,
            )
        ),
        source_url=OFFICIAL_CHESS_SOURCE_URL,
        venue_name=clean_text(venue.get("venue")),
        address=clean_text(venue.get("address")),
        city=clean_text(venue.get("city")),
        state=clean_text(venue.get("state") or venue.get("stateprovince")),
        postal_code=normalize_postal_code(venue.get("zip")),
        organizer=clean_text(organizer_payload.get("organizer")),
        summary=summarize_text(description_text),
        description=description_text,
        entry_fee=extract_entry_fee(description_text),
        sections=fields.get("Playing Sections") or fields.get("Sections") or "",
        scholastic_only=fields.get("Scholastic Only?") or "",
        time_control=fields.get("Time Controls - Specific") or "",
        rounds=fields.get("Number of Rounds") or "",
        uscf_rating_impact=fields.get("USCF Ratings Impact") or "",
    )
    return classify_event_fit(event)


def collect_official_chess(session: requests.Session, months_ahead: int) -> list[Event]:
    events: list[Event] = []
    start_day = date.today()
    end_day = start_day + timedelta(days=31 * months_ahead)
    params = {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "per_page": "100",
        "page": "1",
    }
    api_url = (
        "https://officialchess.org/wp-json/tribe/events/v1/events?"
        + urlencode(params)
    )

    while api_url:
        response = session.get(api_url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("events", []):
            events.append(parse_official_chess_event(item))
        api_url = payload.get("next_rest_url") or ""

    return events


def parse_westchester_schedule(session: requests.Session) -> list[Event]:
    response = session.get(WESTCHESTER_SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    lines = [clean_text(line) for line in soup.get_text("\n", strip=True).splitlines() if clean_text(line)]

    current_year = date.today().year
    pattern = re.compile(
        r"^(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:,\s*(?P<year>\d{4}))?\s*[:\-]?\s*(?P<title>.+)$"
    )
    events: list[Event] = []
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
        tournament_date = safe_parse_date(
            f"{match.group('month')} {match.group('day')} {match.group('year') or current_year}"
        )
        if tournament_date is None:
            continue
        event = Event(
            provider="westchester_chess_club",
            source="Westchester Chess Club",
            title=clean_text(match.group("title")),
            start=tournament_date.replace(hour=19, minute=30),
            source_url=WESTCHESTER_SOURCE_URL,
            event_url=WESTCHESTER_SOURCE_URL,
            registration_url=WESTCHESTER_SOURCE_URL,
            venue_name="Trinity Lutheran Church",
            address="25 Crane Rd",
            city="Scarsdale",
            state="NY",
            postal_code="10583",
            organizer="Westchester Chess Club",
            summary="Club schedule listing. Confirm the exact format and registration rules on the source page.",
            description=line,
        )
        events.append(classify_event_fit(event))
    return events


def collect_events(session: requests.Session, months_ahead: int = DEFAULT_MONTHS_AHEAD) -> list[Event]:
    collected: list[Event] = []
    errors: list[str] = []

    for label, collector in (
        ("Official Chess", lambda: collect_official_chess(session, months_ahead=months_ahead)),
        ("Westchester Chess Club", lambda: parse_westchester_schedule(session)),
    ):
        try:
            collected.extend(collector())
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if not collected:
        raise RuntimeError("No sources refreshed successfully. " + " | ".join(errors))
    return collected


def build_dedupe_key(event: Event) -> str:
    event_day = event.start.date().isoformat() if event.start else ""
    canonical_registration = canonicalize_url(event.registration_url)
    if canonical_registration:
        return f"link|{canonical_registration}|{event_day}"
    canonical_event_url = canonicalize_url(event.event_url)
    if canonical_event_url:
        return f"event|{canonical_event_url}|{event_day}"
    return "|".join(
        [
            to_slug(event.title),
            event_day,
            normalize_postal_code(event.postal_code) or to_slug(event.city),
            to_slug(event.venue_name or event.address),
        ]
    )


def event_quality_score(event: Event) -> int:
    completeness_fields = (
        event.title,
        event.start,
        event.source_updated_at,
        event.registration_url,
        event.event_url,
        event.venue_name,
        event.address,
        event.city,
        event.state,
        event.postal_code,
        event.organizer,
        event.summary,
        event.entry_fee,
        event.sections,
        event.time_control,
    )
    filled = sum(1 for value in completeness_fields if value not in ("", None))
    return SOURCE_PRIORITY.get(event.provider, 0) + filled


def merge_events(primary: Event, secondary: Event) -> Event:
    winner = primary if event_quality_score(primary) >= event_quality_score(secondary) else secondary
    loser = secondary if winner is primary else primary
    merged = replace(winner)

    for field_name in (
        "event_url",
        "registration_url",
        "source_url",
        "venue_name",
        "address",
        "city",
        "state",
        "postal_code",
        "organizer",
        "summary",
        "description",
        "entry_fee",
        "sections",
        "scholastic_only",
        "time_control",
        "rounds",
        "uscf_rating_impact",
    ):
        if not getattr(merged, field_name):
            setattr(merged, field_name, getattr(loser, field_name))

    if merged.start is None and loser.start is not None:
        merged.start = loser.start
    if merged.end is None and loser.end is not None:
        merged.end = loser.end

    if loser.source_created_at and (
        merged.source_created_at is None or loser.source_created_at < merged.source_created_at
    ):
        merged.source_created_at = loser.source_created_at
    if loser.source_updated_at and (
        merged.source_updated_at is None or loser.source_updated_at > merged.source_updated_at
    ):
        merged.source_updated_at = loser.source_updated_at

    if merged.latitude is None and loser.latitude is not None:
        merged.latitude = loser.latitude
    if merged.longitude is None and loser.longitude is not None:
        merged.longitude = loser.longitude

    merged.tags = sorted({*merged.tags, *loser.tags})
    classify_event_fit(merged)
    return merged


def dedupe_events(events: Iterable[Event]) -> list[Event]:
    best_by_key: dict[str, Event] = {}
    for event in events:
        event.dedupe_key = build_dedupe_key(event)
        existing = best_by_key.get(event.dedupe_key)
        if existing is None:
            best_by_key[event.dedupe_key] = event
            continue
        best_by_key[event.dedupe_key] = merge_events(existing, event)
    return list(best_by_key.values())


def annotate_event_coordinates(events: Iterable[Event], resolver: CoordinateResolver) -> list[Event]:
    annotated: list[Event] = []
    for event in events:
        event_copy = replace(event)
        if event_copy.latitude is None or event_copy.longitude is None:
            coords = resolver.resolve_event(event_copy)
            if coords is not None:
                event_copy.latitude, event_copy.longitude = coords
        annotated.append(event_copy)
    return annotated


def with_home_distances(
    events: Iterable[Event],
    home_query: str,
    resolver: CoordinateResolver,
) -> tuple[list[Event], tuple[float, float] | None]:
    home_coords = resolver.resolve_home_query(home_query)
    if home_coords is None:
        return [replace(event, distance_air_miles=None, estimated_drive_minutes=None) for event in events], None

    annotated: list[Event] = []
    for event in events:
        event_copy = replace(event)
        if event_copy.latitude is None or event_copy.longitude is None:
            coords = resolver.resolve_event(event_copy)
            if coords is not None:
                event_copy.latitude, event_copy.longitude = coords
        if event_copy.latitude is not None and event_copy.longitude is not None:
            air_miles = haversine_miles(
                home_coords[0], home_coords[1], event_copy.latitude, event_copy.longitude
            )
            event_copy.distance_air_miles = round(air_miles, 1)
            event_copy.estimated_drive_minutes = estimate_drive_minutes(air_miles)
        else:
            event_copy.distance_air_miles = None
            event_copy.estimated_drive_minutes = None
        annotated.append(event_copy)
    return annotated, home_coords


def filter_events(
    events: Iterable[Event],
    *,
    search_text: str = "",
    start_on: date | None = None,
    end_on: date | None = None,
    states: Iterable[str] | None = None,
    cities: Iterable[str] | None = None,
    sources: Iterable[str] | None = None,
    scholastic_only: bool = False,
    beginner_friendly: bool = False,
    max_drive_minutes: int | None = None,
) -> list[Event]:
    normalized_search = clean_text(search_text).lower()
    state_filter = {clean_text(value) for value in (states or []) if clean_text(value)}
    city_filter = {clean_text(value) for value in (cities or []) if clean_text(value)}
    source_filter = {clean_text(value) for value in (sources or []) if clean_text(value)}

    filtered: list[Event] = []
    for event in events:
        if event.start is None:
            continue
        event_date = event.start.date()
        if start_on and event_date < start_on:
            continue
        if end_on and event_date > end_on:
            continue
        if state_filter and event.state not in state_filter:
            continue
        if city_filter and event.city not in city_filter:
            continue
        if source_filter and event.source not in source_filter:
            continue
        if scholastic_only and not (
            event.age_fit == "good" or clean_text(event.scholastic_only).lower().startswith("yes")
        ):
            continue
        if beginner_friendly and event.beginner_fit != "good":
            continue
        if max_drive_minutes is not None:
            if event.estimated_drive_minutes is None or event.estimated_drive_minutes > max_drive_minutes:
                continue
        if normalized_search:
            haystack = " ".join(
                [
                    event.title,
                    event.organizer,
                    event.venue_name,
                    event.city,
                    event.state,
                    event.summary,
                    event.sections,
                ]
            ).lower()
            if normalized_search not in haystack:
                continue
        filtered.append(event)
    return filtered


def sort_events(events: Iterable[Event], mode: str = "recently_updated") -> list[Event]:
    items = list(events)
    if mode == "closest":
        items.sort(
            key=lambda event: (
                event.estimated_drive_minutes if event.estimated_drive_minutes is not None else 999999,
                event.start or datetime.max,
                event.title.lower(),
            )
        )
        return items

    if mode == "date":
        items.sort(
            key=lambda event: (
                event.start or datetime.max,
                -event.updated_sort_value.timestamp() if event.updated_sort_value != datetime.min else 0,
                event.title.lower(),
            )
        )
        return items

    items.sort(
        key=lambda event: (
            -(event.updated_sort_value.timestamp() if event.updated_sort_value != datetime.min else 0),
            event.start or datetime.max,
            event.title.lower(),
        )
    )
    return items


def refresh_dataset(
    *,
    months_ahead: int = DEFAULT_MONTHS_AHEAD,
    cache_file: Path = DEFAULT_CACHE_FILE,
    coord_cache_file: Path = DEFAULT_COORD_CACHE_FILE,
) -> TournamentDataset:
    session = build_session()
    collected = collect_events(session, months_ahead=months_ahead)
    deduped = dedupe_events(collected)
    resolver = CoordinateResolver(cache_path=coord_cache_file)
    geocoded = annotate_event_coordinates(deduped, resolver)
    dataset = TournamentDataset(
        generated_at=datetime.now(),
        events=sort_events(geocoded, mode="recently_updated"),
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(dataset.to_record(), indent=2), encoding="utf-8")
    return dataset


def load_cached_dataset(cache_file: Path = DEFAULT_CACHE_FILE) -> TournamentDataset | None:
    if not cache_file.exists():
        return None
    try:
        return TournamentDataset.from_record(json.loads(cache_file.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return None


def load_or_refresh_dataset(
    *,
    force_refresh: bool = False,
    max_age_hours: int = 24,
    months_ahead: int = DEFAULT_MONTHS_AHEAD,
    cache_file: Path = DEFAULT_CACHE_FILE,
    coord_cache_file: Path = DEFAULT_COORD_CACHE_FILE,
) -> tuple[TournamentDataset, bool]:
    cached = load_cached_dataset(cache_file)
    if not force_refresh and cached is not None:
        cache_age = datetime.now() - cached.generated_at
        if cache_age <= timedelta(hours=max_age_hours):
            return cached, False

    try:
        return (
            refresh_dataset(
                months_ahead=months_ahead,
                cache_file=cache_file,
                coord_cache_file=coord_cache_file,
            ),
            True,
        )
    except Exception as exc:
        if cached is not None:
            cached.stale = True
            cached.refresh_error = str(exc)
            return cached, False
        raise


def event_table_rows(events: Iterable[Event]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in events:
        rows.append(
            {
                "source": event.source,
                "title": event.title,
                "updated_at": format_datetime(event.source_updated_at),
                "start": format_datetime(event.start),
                "end": format_datetime(event.end),
                "organizer": event.organizer,
                "venue": event.venue_name,
                "address": event.address,
                "city": event.city,
                "state": event.state,
                "postal_code": event.postal_code,
                "entry_fee": event.entry_fee,
                "sections": event.sections,
                "scholastic_only": event.scholastic_only,
                "time_control": event.time_control,
                "rounds": event.rounds,
                "uscf_rating_impact": event.uscf_rating_impact,
                "age_fit": event.age_fit,
                "beginner_fit": event.beginner_fit,
                "distance_air_miles": str(event.distance_air_miles or ""),
                "estimated_drive_minutes": str(event.estimated_drive_minutes or ""),
                "registration_url": event.registration_url,
                "event_url": event.event_url,
                "source_url": event.source_url,
                "summary": event.summary,
            }
        )
    return rows


def write_csv(events: Iterable[Event], path: Path) -> None:
    rows = event_table_rows(events)
    fieldnames = list(rows[0].keys()) if rows else [
        "source",
        "title",
        "updated_at",
        "start",
        "end",
        "organizer",
        "venue",
        "address",
        "city",
        "state",
        "postal_code",
        "entry_fee",
        "sections",
        "scholastic_only",
        "time_control",
        "rounds",
        "uscf_rating_impact",
        "age_fit",
        "beginner_fit",
        "distance_air_miles",
        "estimated_drive_minutes",
        "registration_url",
        "event_url",
        "source_url",
        "summary",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_html_report(
    events: Iterable[Event],
    path: Path,
    *,
    title: str = "New York Area Chess Tournament Finder",
    generated_at: datetime | None = None,
    home_label: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_text = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    cards: list[str] = []
    for event in events:
        drive_text = "Distance unavailable"
        if event.estimated_drive_minutes is not None and event.distance_air_miles is not None:
            drive_text = (
                f"{event.estimated_drive_minutes} min drive estimate "
                f"({event.distance_air_miles:.1f} air miles)"
            )
        cards.append(
            f"""
            <article class="card">
              <div class="card-top">
                <span class="pill">{html.escape(event.source)}</span>
                <span class="updated">Updated {html.escape(relative_date_label(event.source_updated_at))}</span>
              </div>
              <h2>{html.escape(event.title)}</h2>
              <p><strong>When:</strong> {html.escape(format_datetime(event.start, human=True) or "TBD")}</p>
              <p><strong>Where:</strong> {html.escape(event.location_label or "TBD")}</p>
              <p><strong>Parent fit:</strong> scholastic={html.escape(event.age_fit)}, beginner={html.escape(event.beginner_fit)}</p>
              <p><strong>Details:</strong> {html.escape(event.summary or "See source for details.")}</p>
              <p><strong>Drive:</strong> {html.escape(drive_text)}</p>
              <p class="links">
                <a href="{html.escape(event.registration_url or event.event_url or event.source_url)}">Registration</a>
                <a href="{html.escape(event.event_url or event.source_url)}">Source</a>
              </p>
            </article>
            """
        )

    html_report = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --ink: #16181f;
      --muted: #5f6878;
      --bg: #f4f7fb;
      --card: #ffffff;
      --line: #dbe3ef;
      --accent: #0c4a6e;
      --accent-soft: #dff3ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(12, 74, 110, 0.16), transparent 30%),
        linear-gradient(180deg, #f9fbfe 0%, var(--bg) 100%);
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      padding: 28px;
      border-radius: 24px;
      background: linear-gradient(135deg, #0f172a 0%, #0c4a6e 100%);
      color: #ffffff;
      box-shadow: 0 22px 50px rgba(12, 24, 42, 0.16);
    }}
    .hero p {{ color: rgba(255,255,255,0.84); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
      margin-top: 24px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .pill {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .updated {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .links {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    a {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>{html.escape(title)}</h1>
      <p>Generated: {html.escape(generated_text)}</p>
      <p>Home filter: {html.escape(home_label or "Not applied")}</p>
      <p>This export is generated from live chess tournament sources and keeps direct registration links for parents.</p>
    </section>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""
    path.write_text(html_report, encoding="utf-8")


def format_datetime(value: datetime | None, *, human: bool = False) -> str:
    if value is None:
        return ""
    if human:
        return value.strftime("%a %b %d, %Y %I:%M %p")
    return value.strftime("%Y-%m-%d %H:%M")


def relative_date_label(value: datetime | None) -> str:
    if value is None:
        return "time unavailable"
    today = date.today()
    delta_days = (today - value.date()).days
    if delta_days == 0:
        return "today"
    if delta_days == 1:
        return "1 day ago"
    if delta_days > 1:
        return f"{delta_days} days ago"
    return value.strftime("%Y-%m-%d")
