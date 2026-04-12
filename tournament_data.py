from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

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
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
DEFAULT_MONTHS_AHEAD = 6
TARGET_STATES = ("NY", "NJ", "CT")
DEFAULT_CACHE_DIR = Path("data")
DEFAULT_CACHE_FILE = DEFAULT_CACHE_DIR / "tournaments_cache.json"
DEFAULT_COORD_CACHE_FILE = DEFAULT_CACHE_DIR / "coordinate_cache.json"
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_SEED_DIR = Path("seed_data")
OFFICIAL_CHESS_SOURCE_URL = "https://officialchess.org/events/list/"
OFFICIAL_CHESS_SITE_ROOT = "https://officialchess.org"
LITTLE_HOUSE_SOURCE_URL = "https://littlehouseofchess.org/calendar/"
LITTLE_HOUSE_EVENTS_SOURCE_URL = "https://littlehouseofchess.org/events/"
LITTLE_HOUSE_SITE_ROOT = "https://littlehouseofchess.org"
WESTCHESTER_SOURCE_URL = "https://www.westchesterchessclub.com/schedule"
TRI_STATE_SOURCE_URL = "https://tristatechess.com/onlineregistration/"
ICA_NJ_SOURCE_URL = "https://www.icanj.net/p.php?p=2122&Tournaments%20Calendar="
CHESS_IN_THE_SCHOOLS_SOURCE_URL = "https://chessintheschools.org/tournament/"
CHESS_FATHER_SOURCE_URL = "https://www.chessfather.com/tournaments"
EVENTS4CHESS_SOURCE_URL = "https://www.events4chess.com/events/?s=0&when=1&activity=1&rpp=100"
US_CHESS_SOURCE_URL = (
    "https://new.uschess.org/upcoming-tournaments?combine=&"
    "field_event_address_administrative_area=NY&field_online_event_value=All&"
    "field_geofield_proximity%5Bvalue%5D=&"
    "field_geofield_proximity%5Bsource_configuration%5D%5Borigin_address%5D="
)
ZIP_LOOKUP_URL_TEMPLATE = "https://api.zippopotam.us/us/{postal_code}"
LITTLE_HOUSE_SEED_FILE = DEFAULT_SEED_DIR / "little_house_events.json"

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
    "little_house_of_chess": 90,
    "us_chess": 89,
    "events4chess": 88,
    "chess_in_the_schools": 85,
    "chess_father": 80,
    "tri_state_chess": 72,
    "ica_nj": 68,
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
    contributing_sources: list[str] = field(default_factory=list)
    contributing_providers: list[str] = field(default_factory=list)
    dedupe_key: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        source_values = [
            clean_text(value)
            for value in [*self.contributing_sources, self.source]
            if clean_text(value)
        ]
        provider_values = [
            clean_text(value)
            for value in [*self.contributing_providers, self.provider]
            if clean_text(value)
        ]
        self.contributing_sources = list(dict.fromkeys(source_values))
        self.contributing_providers = list(dict.fromkeys(provider_values))

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
            "contributing_sources": self.contributing_sources,
            "contributing_providers": self.contributing_providers,
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
            contributing_sources=[str(tag) for tag in record.get("contributing_sources", []) or []],
            contributing_providers=[str(tag) for tag in record.get("contributing_providers", []) or []],
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
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
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
        sanitized = re.sub(
            r"\b(?:EDT|EST|CDT|CST|MDT|MST|PDT|PST|UTC|GMT)\b",
            "",
            str(value),
            flags=re.IGNORECASE,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return date_parser.parse(sanitized, fuzzy=True, default=default).replace(tzinfo=None)
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


def is_social_or_platform_link(url: str) -> bool:
    lower = canonicalize_url(url).lower()
    return any(
        token in lower
        for token in (
            "facebook.com",
            "twitter.com",
            "linkedin.com",
            "youtube.com",
            "instagram.com",
            "whatsapp.com",
            "maps.google.com",
            "google.com/maps",
            "calendar.google.com",
            "mailto:",
            "tel:",
            "uscfsales.com",
            "skvare.com/uscf",
            "privacy-policy",
            "search/posts?query=%23",
        )
    )


def first_external_link(urls: Iterable[str], *, excluded_domains: Iterable[str] = ()) -> str:
    excluded = tuple(domain.lower() for domain in excluded_domains)
    for url in urls:
        canonical = canonicalize_url(url)
        if not canonical or is_social_or_platform_link(canonical):
            continue
        lower = canonical.lower()
        if any(domain in lower for domain in excluded):
            continue
        return canonical
    return ""


def parse_compact_utc_datetime(value: str) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def split_google_calendar_dates(url: str) -> tuple[datetime | None, datetime | None]:
    query = parse_qs(urlparse(url).query)
    value = clean_text((query.get("dates") or [""])[0])
    if "/" not in value:
        return (None, None)
    start_text, end_text = value.split("/", 1)
    return (parse_compact_utc_datetime(start_text), parse_compact_utc_datetime(end_text))


def normalize_state_token(value: str) -> str:
    text = clean_text(value).lower()
    mapping = {
        "new york": "NY",
        "ny": "NY",
        "new jersey": "NJ",
        "nj": "NJ",
        "connecticut": "CT",
        "ct": "CT",
        "pennsylvania": "PA",
        "pa": "PA",
        "massachusetts": "MA",
        "ma": "MA",
        "illinois": "IL",
        "il": "IL",
        "rhode island": "RI",
        "ri": "RI",
    }
    return mapping.get(text, text.upper())


def parse_city_state_label(value: str) -> tuple[str, str]:
    text = clean_text(value)
    match = re.search(r"([^,]+),\s*([A-Za-z ]+)$", text)
    if not match:
        return ("", "")
    return (clean_text(match.group(1)), normalize_state_token(match.group(2)))


def to_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()).strip("-")


def normalized_title_for_dedupe(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"\b(entries?|register(?: now)?|registration)\b", "", text)
    text = re.sub(r"\s+[–-]\s+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return to_slug(text)


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


def load_seed_events(path: Path) -> list[Event]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [Event.from_record(item) for item in payload.get("events", []) or []]


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


def parse_tribe_event(
    item: dict[str, object],
    *,
    provider: str,
    source: str,
    source_url: str,
) -> Event:
    description_html = str(item.get("description", "") or "")
    description_text = strip_html(description_html)
    venue = item.get("venue") or {}
    organizer_payload = (item.get("organizer") or [{}])[0]
    fields = custom_field_map(item.get("custom_fields"))

    event = Event(
        provider=provider,
        source=source,
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
        source_url=source_url,
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


def parse_official_chess_event(item: dict[str, object]) -> Event:
    return parse_tribe_event(
        item,
        provider="official_chess",
        source="Official Chess",
        source_url=OFFICIAL_CHESS_SOURCE_URL,
    )


def parse_little_house_event(item: dict[str, object]) -> Event:
    return parse_tribe_event(
        item,
        provider="little_house_of_chess",
        source="Little House of Chess",
        source_url=LITTLE_HOUSE_SOURCE_URL,
    )


def collect_tribe_events(
    session: requests.Session,
    *,
    site_root: str,
    months_ahead: int,
    parser: Callable[[dict[str, object]], Event],
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
    api_url = f"{site_root}/wp-json/tribe/events/v1/events?" + urlencode(params)

    while api_url:
        response = session.get(api_url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("events", []):
            events.append(parser(item))
        api_url = payload.get("next_rest_url") or ""

    return events


def collect_official_chess(session: requests.Session, months_ahead: int) -> list[Event]:
    return collect_tribe_events(
        session,
        site_root=OFFICIAL_CHESS_SITE_ROOT,
        months_ahead=months_ahead,
        parser=parse_official_chess_event,
    )


def parse_little_house_event_page(session: requests.Session, event_url: str) -> Event | None:
    response = session.get(event_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    title_node = soup.find("h1")
    title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
    if not title:
        return None

    description_node = soup.select_one(".mec-single-event-description")
    description = clean_text(description_node.get_text(" ", strip=True) if description_node else soup.get_text(" ", strip=True))
    summary = summarize_text(description or title)

    register_link = soup.select_one(".mec-booking-button[href]")
    organizer_website_link = soup.select_one(".mec-organizer-url a[href]")
    google_calendar_link = soup.select_one(".mec-events-gcal[href]")

    start = None
    end = None
    if google_calendar_link is not None:
        start, end = split_google_calendar_dates(clean_text(google_calendar_link.get("href")))

    venue_name = ""
    address = ""
    location_box = soup.select_one(".mec-single-event-location")
    if location_box is not None:
        venue_node = location_box.select_one(".author.fn.org")
        address_node = location_box.select_one(".mec-address")
        venue_name = clean_text(venue_node.get_text(" ", strip=True) if venue_node else "")
        address = clean_text(address_node.get_text(" ", strip=True) if address_node else "")

    if not address:
        address_match = re.search(
            r"Address:\s*(.+?)\s+([A-Za-z ]+,\s*[A-Za-z ]+\s+\d{5}(?:-\d{4})?)",
            description,
            flags=re.IGNORECASE,
        )
        if address_match:
            venue_name = clean_text(address_match.group(1))
            address = clean_text(address_match.group(2))

    city, state, postal_code = parse_city_state_postal(address)
    if not city or not state:
        city, state = parse_city_state_label(address)

    organizer_box = soup.select_one(".mec-single-event-organizer")
    organizer = ""
    if organizer_box is not None:
        organizer_node = organizer_box.select_one(".mec-organizer h6")
        organizer = clean_text(organizer_node.get_text(" ", strip=True) if organizer_node else "")

    description_links = []
    if description_node is not None:
        description_links = [
            href
            for href in (link.get("href") for link in description_node.select("a[href]"))
            if href and href.startswith("http")
        ]

    registration_url = (
        canonicalize_url(register_link.get("href", ""))
        if register_link is not None
        else canonicalize_url(organizer_website_link.get("href", ""))
        if organizer_website_link is not None
        else first_external_link(description_links, excluded_domains=("littlehouseofchess.org",))
        or canonicalize_url(event_url)
    )
    if not organizer:
        organizer = "Little House of Chess"

    updated_meta = soup.find("meta", attrs={"property": "article:modified_time"})
    created_meta = soup.find("meta", attrs={"property": "article:published_time"})
    category = clean_text(
        " | ".join(link.get_text(" ", strip=True) for link in soup.select(".mec-events-event-categories a"))
    )
    time_control = clean_text(
        " ".join(
            re.findall(
                r"(Game/\d+\s*,?\s*d\d+|G/\d+\s*,?\s*d\d+|Game/\d+|G/\d+)",
                description,
                flags=re.IGNORECASE,
            )
        )
    )

    event = Event(
        provider="little_house_of_chess",
        source="Little House of Chess",
        title=title,
        start=start,
        end=end,
        source_created_at=parse_iso_datetime(created_meta.get("content")) if created_meta else None,
        source_updated_at=parse_iso_datetime(updated_meta.get("content")) if updated_meta else None,
        event_url=canonicalize_url(event_url),
        registration_url=registration_url,
        source_url=LITTLE_HOUSE_EVENTS_SOURCE_URL,
        venue_name=venue_name,
        address=address,
        city=city,
        state=state,
        postal_code=postal_code,
        organizer=organizer,
        summary=summary,
        description=description,
        sections=category,
        entry_fee=extract_entry_fee(description),
        time_control=time_control,
    )
    return classify_event_fit(event)


def parse_little_house_calendar_article(article: BeautifulSoup) -> Event | None:
    modal = article.select_one(".mec-single-event")
    if modal is None:
        return None

    title_node = article.select_one(".mec-toggle-title")
    title = clean_text(title_node.get_text(" ", strip=True) if title_node else "")
    if not title:
        return None

    description_node = modal.select_one(".mec-single-event-description")
    description = clean_text(
        description_node.get_text(" ", strip=True) if description_node else modal.get_text(" ", strip=True)
    )
    summary = summarize_text(description or title)

    register_link = modal.select_one(".mec-booking-button[href]")
    organizer_website_link = modal.select_one(".mec-organizer-url a[href]")
    more_info_link = modal.select_one(".mec-more-info-button[href]")
    google_calendar_link = modal.select_one(".mec-events-gcal[href]")

    start = None
    end = None
    if google_calendar_link is not None:
        start, end = split_google_calendar_dates(clean_text(google_calendar_link.get("href")))

    venue_name = ""
    address = ""
    location_box = modal.select_one(".mec-single-event-location")
    if location_box is not None:
        venue_node = location_box.select_one(".author.fn.org")
        address_node = location_box.select_one(".mec-address")
        venue_name = clean_text(venue_node.get_text(" ", strip=True) if venue_node else "")
        address = clean_text(address_node.get_text(" ", strip=True) if address_node else "")

    city, state, postal_code = parse_city_state_postal(address)
    if not city or not state:
        city, state = parse_city_state_label(address)

    organizer_box = modal.select_one(".mec-single-event-organizer")
    organizer = ""
    if organizer_box is not None:
        organizer_node = organizer_box.select_one(".mec-organizer h6")
        organizer = clean_text(organizer_node.get_text(" ", strip=True) if organizer_node else "")

    description_links = []
    if description_node is not None:
        description_links = [
            href
            for href in (link.get("href") for link in description_node.select("a[href]"))
            if href and href.startswith("http")
        ]

    modal_links = [
        href
        for href in (link.get("href") for link in modal.select("a[href]"))
        if href and href.startswith("http")
    ]
    preferred_external = first_external_link(
        [canonicalize_url(more_info_link.get("href", ""))] if more_info_link is not None else [],
        excluded_domains=("littlehouseofchess.org",),
    ) or first_external_link(
        [*description_links, *modal_links],
        excluded_domains=("littlehouseofchess.org",),
    )

    registration_url = (
        canonicalize_url(register_link.get("href", ""))
        if register_link is not None
        else canonicalize_url(organizer_website_link.get("href", ""))
        if organizer_website_link is not None
        else preferred_external
        or LITTLE_HOUSE_SOURCE_URL
    )
    event_url = (
        canonicalize_url(more_info_link.get("href", ""))
        if more_info_link is not None
        else preferred_external or registration_url
    )

    if not organizer:
        organizer = "Little House of Chess"

    category = clean_text(
        " | ".join(link.get_text(" ", strip=True) for link in modal.select(".mec-events-event-categories a"))
    )
    time_control = clean_text(
        " ".join(
            re.findall(
                r"(Game/\d+\s*,?\s*d\d+|G/\d+\s*,?\s*d\d+|Game/\d+|G/\d+)",
                description,
                flags=re.IGNORECASE,
            )
        )
    )

    event = Event(
        provider="little_house_of_chess",
        source="Little House of Chess",
        title=title,
        start=start,
        end=end,
        event_url=event_url,
        registration_url=registration_url,
        source_url=LITTLE_HOUSE_SOURCE_URL,
        venue_name=venue_name,
        address=address,
        city=city,
        state=state,
        postal_code=postal_code,
        organizer=organizer,
        summary=summary,
        description=description,
        sections=category,
        entry_fee=extract_entry_fee(description),
        time_control=time_control,
    )
    return classify_event_fit(event)


def collect_little_house_calendar(session: requests.Session, months_ahead: int) -> list[Event]:
    response = session.get(LITTLE_HOUSE_SOURCE_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    start_day = date.today()
    end_day = start_day + timedelta(days=31 * months_ahead)
    events: list[Event] = []

    for article in soup.select(".mec-event-article"):
        event = parse_little_house_calendar_article(article)
        if event is None or event.start is None:
            continue
        if event.start.date() < start_day or event.start.date() > end_day:
            continue
        events.append(event)

    return events


def collect_little_house_of_chess(session: requests.Session, months_ahead: int) -> list[Event]:
    combined_events = collect_little_house_calendar(session, months_ahead=months_ahead)
    response = session.get("https://littlehouseofchess.org/mec-events-sitemap.xml", timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    start_day = date.today()
    end_day = start_day + timedelta(days=31 * months_ahead)

    for loc in root.findall(".//sm:loc", namespace):
        event_url = clean_text(loc.text)
        if not event_url or event_url.rstrip("/") == LITTLE_HOUSE_EVENTS_SOURCE_URL.rstrip("/"):
            continue
        try:
            event = parse_little_house_event_page(session, event_url)
        except Exception:
            continue
        if event is None or event.start is None:
            continue
        if event.start.date() < start_day or event.start.date() > end_day:
            continue
        combined_events.append(event)

    return dedupe_events(combined_events)


def solve_sucuri_cookie_challenge(session: requests.Session, response_text: str) -> bool:
    challenge_match = re.search(r"S='([^']+)'", response_text)
    if challenge_match is None:
        return False

    decoded = base64_decode(challenge_match.group(1))
    header_match = re.search(r"([A-Za-z])=(.*?);document\.cookie=", decoded)
    if header_match is None:
        return False

    var_name, value_expr = header_match.groups()
    cookie_value = evaluate_js_concat_expression(value_expr)
    name_match = re.search(
        r'document\.cookie=(.*?)\+\s*"="\s*\+\s*' + re.escape(var_name),
        decoded,
    )
    if name_match is None:
        return False

    cookie_name = evaluate_js_concat_expression(name_match.group(1))
    session.cookies.set(cookie_name, cookie_value, domain="www.events4chess.com", path="/")
    return True


def base64_decode(value: str) -> str:
    import base64

    return base64.b64decode(value).decode("utf-8", "replace")


def evaluate_js_concat_expression(expression: str) -> str:
    python_expression = re.sub(
        r"String\.fromCharCode\((\d+)\)",
        lambda match: repr(chr(int(match.group(1)))),
        expression,
    )
    python_expression = re.sub(r"'([^']*)'", lambda match: repr(match.group(1)), python_expression)
    python_expression = re.sub(r'"([^"]*)"', lambda match: repr(match.group(1)), python_expression)
    return str(eval(python_expression, {"__builtins__": {}}))


def fetch_events4chess_html(session: requests.Session, url: str) -> str:
    for _ in range(4):
        response = session.get(url, timeout=30)
        response.raise_for_status()
        if "sucuri_cloudproxy_js" not in response.text:
            return response.text
        if not solve_sucuri_cookie_challenge(session, response.text):
            break
    raise RuntimeError("Events4Chess anti-bot challenge could not be solved")


def parse_events4chess_card(card: BeautifulSoup) -> Event | None:
    title_link = card.select_one("a.displayEventName[href]")
    if title_link is None:
        return None

    title = clean_text(title_link.get_text(" ", strip=True))
    if not title:
        return None

    detail_url = canonicalize_url(urljoin(EVENTS4CHESS_SOURCE_URL, title_link.get("href", "")))
    register_link = card.select_one('a[href*="cat=1"]')
    registration_url = canonicalize_url(
        urljoin(EVENTS4CHESS_SOURCE_URL, (register_link or title_link).get("href", ""))
    )

    rows = card.select("#eventsTableEntry tr")
    event_date = None
    location_label = ""
    for row in rows:
        icon = clean_text(row.get_text(" ", strip=True))
        cells = row.select("td")
        if not cells:
            continue
        value = clean_text(cells[0].get_text(" ", strip=True))
        if "Sunday" in value or "Monday" in value or "Tuesday" in value or "Wednesday" in value or "Thursday" in value or "Friday" in value or "Saturday" in value:
            event_date = safe_parse_date(value)
        elif "NY" in value or "NJ" in value or "CT" in value or "PA" in value:
            location_label = value

    venue_name = ""
    city = ""
    state = ""
    if location_label:
        venue_match = re.match(r"(.+?)\s*-\s*([^,]+,\s*[A-Za-z ]+)$", location_label)
        if venue_match:
            venue_name = clean_text(venue_match.group(1))
            city, state = parse_city_state_label(venue_match.group(2))
        else:
            city, state = parse_city_state_label(location_label)

    summary_node = card.select_one(".text-muted.small")
    summary = clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")
    description = clean_text(
        " ".join(value.get_text(" ", strip=True) for value in card.select(".text-muted.small, #eventsTableEntry"))
    )

    event = Event(
        provider="events4chess",
        source="Events4Chess",
        title=title,
        start=event_date,
        event_url=detail_url,
        registration_url=registration_url,
        source_url=EVENTS4CHESS_SOURCE_URL,
        venue_name=venue_name,
        city=city,
        state=state,
        organizer="",
        summary=summarize_text(summary or description or title),
        description=description,
        sections=summary,
    )
    return classify_event_fit(event)


def collect_events4chess(session: requests.Session) -> list[Event]:
    html = fetch_events4chess_html(session, EVENTS4CHESS_SOURCE_URL)
    soup = BeautifulSoup(html, "html.parser")
    events: list[Event] = []
    for card in soup.select(".card"):
        event = parse_events4chess_card(card)
        if event is not None:
            events.append(event)
    return events


def parse_us_chess_detail(detail_url: str, session: requests.Session) -> dict[str, object]:
    response = session.get(detail_url, timeout=30)
    response.raise_for_status()
    html_text = response.text
    soup = BeautifulSoup(html_text, "html.parser")

    description_meta = soup.find("meta", attrs={"name": "description"})
    description = clean_text(description_meta.get("content")) if description_meta else ""
    updated_meta = soup.find("meta", attrs={"property": "og:updated_time"})
    created_meta = soup.find("meta", attrs={"property": "article:published_time"})

    address_match = re.search(
        r'views-label-field-event-address.*?<span class="field-content"><p class="address"[^>]*>'
        r'(.*?)</p>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    address_html = address_match.group(1) if address_match else ""
    address_text = clean_text(BeautifulSoup(address_html, "html.parser").get_text(" ", strip=True))
    city, state, postal_code = ("", "", "")
    if address_text:
        city, state, postal_code = parse_city_state_postal(address_text)
        if not city or not state:
            city, state = parse_city_state_label(address_text)

    external_links = [
        href
        for href in (link.get("href") for link in soup.select("a[href]"))
        if href and href.startswith("http")
    ]
    organizer_url = first_external_link(
        external_links,
        excluded_domains=("new.uschess.org", "uschess.org"),
    )

    return {
        "description": description,
        "address": address_text,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "registration_url": organizer_url or detail_url,
        "source_updated_at": parse_iso_datetime(updated_meta.get("content")) if updated_meta else None,
        "source_created_at": parse_iso_datetime(created_meta.get("content")) if created_meta else None,
    }


def collect_us_chess(session: requests.Session) -> list[Event]:
    events: list[Event] = []
    page = 0
    seen_urls: set[str] = set()

    while True:
        page_url = f"{US_CHESS_SOURCE_URL}&page={page}"
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select(".views-row")
        if not rows:
            break

        for row in rows:
            title_link = row.select_one(".title3 a[href]")
            if title_link is None:
                continue
            title = clean_text(title_link.get_text(" ", strip=True))
            detail_url = canonicalize_url(urljoin("https://new.uschess.org", title_link.get("href", "")))
            if not title or not detail_url or detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)
            address_node = row.select_one(".address")
            address_label = clean_text(address_node.get_text(" ", strip=True) if address_node else "")
            city, state = parse_city_state_label(address_label)
            organizer_node = row.select_one(".organizer-name")
            organizer = clean_text(organizer_node.get_text(" ", strip=True) if organizer_node else "")
            summary_node = row.select_one(".information")
            summary = clean_text(summary_node.get_text(" ", strip=True) if summary_node else "")
            time_value = row.select_one("time[datetime]")
            start = None
            if time_value is not None:
                start = parse_iso_datetime(time_value.get("datetime"))
            if start is None:
                dates_node = row.select_one(".dates")
                start = safe_parse_date(clean_text(dates_node.get_text(" ", strip=True) if dates_node else ""))

            detail = parse_us_chess_detail(detail_url, session)
            event = Event(
                provider="us_chess",
                source="US Chess",
                title=title,
                start=start,
                source_created_at=detail["source_created_at"],
                source_updated_at=detail["source_updated_at"],
                event_url=detail_url,
                registration_url=clean_text(str(detail["registration_url"])),
                source_url=US_CHESS_SOURCE_URL,
                address=clean_text(str(detail["address"])),
                city=clean_text(str(detail["city"] or city)),
                state=clean_text(str(detail["state"] or state)),
                postal_code=clean_text(str(detail["postal_code"])),
                organizer=organizer,
                summary=summarize_text(summary or clean_text(str(detail["description"]))),
                description=clean_text(str(detail["description"])),
                entry_fee=extract_entry_fee(summary + " " + clean_text(str(detail["description"]))),
                time_control=clean_text(
                    " ".join(
                        re.findall(
                            r"(G/\d+\s*d\d+|G/\d+\s*d\d*|Game/\d+\s*d\d+|Game/\d+)",
                            summary + " " + clean_text(str(detail["description"])),
                            flags=re.IGNORECASE,
                        )
                    )
                ),
            )
            events.append(classify_event_fit(event))

        if not soup.select_one('a[href*="page=' + str(page + 1) + '"]'):
            break
        page += 1

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


def find_registration_url_from_text(text: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", text or "")
    return canonicalize_url(match.group(0)) if match else ""


def parse_tristate_registration(session: requests.Session) -> list[Event]:
    response = session.get(TRI_STATE_SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    events: list[Event] = []

    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = canonicalize_url(urljoin(TRI_STATE_SOURCE_URL, link.get("href", "")))
        if not title or len(title) < 6:
            continue
        if "register" not in title.lower() and "chess" not in title.lower():
            continue

        date_match = re.search(
            r"((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?)",
            title,
            flags=re.IGNORECASE,
        )
        start = (
            safe_parse_date(date_match.group(1), default_year=date.today().year)
            if date_match
            else None
        )
        event = Event(
            provider="tri_state_chess",
            source="Tri-State Chess",
            title=title,
            start=start,
            event_url=href,
            registration_url=href,
            source_url=TRI_STATE_SOURCE_URL,
            summary="Scraped from Tri-State Chess online registration page.",
            description=title,
            organizer="Tri-State Chess",
        )
        events.append(classify_event_fit(event))

    return events


def parse_icanj_calendar(session: requests.Session) -> list[Event]:
    response = session.get(ICA_NJ_SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    current_year = date.today().year
    events: list[Event] = []

    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = canonicalize_url(urljoin(ICA_NJ_SOURCE_URL, link.get("href", "")))
        if not title:
            continue
        if (
            "tournament" not in title.lower()
            and "quad" not in title.lower()
            and "championship" not in title.lower()
        ):
            continue
        if "calendar" in title.lower():
            continue

        date_match = re.search(
            r"((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:[-/]\d{1,2})?(?:,\s*\d{4})?)",
            title,
            flags=re.IGNORECASE,
        )
        start = (
            safe_parse_date(date_match.group(1), default_year=current_year)
            if date_match
            else None
        )
        event = Event(
            provider="ica_nj",
            source="ICA NJ",
            title=title,
            start=start,
            event_url=href,
            registration_url=href,
            source_url=ICA_NJ_SOURCE_URL,
            summary="Scraped from the ICA NJ tournament calendar.",
            description=title,
            organizer="ICA NJ",
        )
        events.append(classify_event_fit(event))

    return events


def parse_chess_in_the_schools_detail(
    session: requests.Session,
    event_url: str,
    title: str,
    start: datetime | None,
    location_label: str,
) -> Event:
    response = session.get(event_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    body_text = clean_text(soup.get_text("\n", strip=True))

    register_link = ""
    for link in soup.select("a[href]"):
        href = clean_text(link.get("href"))
        label = clean_text(link.get_text(" ", strip=True))
        if "register" in label.lower():
            register_link = canonicalize_url(urljoin(event_url, href))
            break

    location_heading = soup.find(["h3", "h4"], string=re.compile(r"^\s*PS |School|MS |IS |ERHS", re.IGNORECASE))
    venue_name = clean_text(location_heading.get_text(" ", strip=True)) if location_heading else ""

    address_match = re.search(
        r"(\d{1,5}[^,\n]+,\s*(?:NY|New York),?\s*NY(?:\s+\d{5})?)",
        body_text,
        flags=re.IGNORECASE,
    )
    address = clean_text(address_match.group(1)) if address_match else clean_text(location_label)
    city = "New York" if "new york" in address.lower() or "ny, ny" in address.lower() else ""
    postal_code = normalize_postal_code(address)

    event = Event(
        provider="chess_in_the_schools",
        source="Chess In The Schools",
        title=title,
        start=start,
        event_url=canonicalize_url(event_url),
        registration_url=register_link or canonicalize_url(event_url),
        source_url=CHESS_IN_THE_SCHOOLS_SOURCE_URL,
        venue_name=venue_name,
        address=address,
        city=city,
        state="NY",
        postal_code=postal_code,
        organizer="Chess In The Schools",
        summary=summarize_text(body_text),
        description=body_text,
        sections=clean_text(
            " | ".join(re.findall(r"(K-[^\.]+|JH-HS[^\.]+|EL[^\.]+|Primary[^\.]+)", body_text))
        ),
        time_control=clean_text(
            " ".join(re.findall(r"(G/\d+\s*(?:or\s*G/\d+)?[^\.]*Delay)", body_text, flags=re.IGNORECASE))
        ),
    )
    return classify_event_fit(event)


def parse_chess_in_the_schools_tournaments(session: requests.Session) -> list[Event]:
    response = session.get(CHESS_IN_THE_SCHOOLS_SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    events: list[Event] = []

    for link in soup.select("a[href]"):
        label = clean_text(link.get_text(" ", strip=True))
        href = canonicalize_url(urljoin(CHESS_IN_THE_SCHOOLS_SOURCE_URL, link.get("href", "")))
        if label != "Tournament Details":
            continue

        card_heading = link.find_previous(["h2", "h3"])
        if card_heading is None:
            continue
        title = clean_text(card_heading.get_text(" ", strip=True))
        if not title or title.lower() == "all tournaments":
            continue

        card_text_parts: list[str] = []
        cursor = card_heading.find_next_sibling()
        while cursor is not None and cursor.name != card_heading.name:
            if hasattr(cursor, "find") and cursor.find(
                "a", string=re.compile("Tournament Details", re.IGNORECASE)
            ):
                break
            if hasattr(cursor, "get_text"):
                card_text_parts.append(clean_text(cursor.get_text(" ", strip=True)))
            else:
                card_text_parts.append(clean_text(str(cursor)))
            cursor = cursor.find_next_sibling()
        card_text = " ".join(part for part in card_text_parts if part)

        date_match = re.search(
            r"(Saturday|Sunday|Monday|Tuesday|Wednesday|Thursday|Friday),\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}",
            card_text,
        )
        start = safe_parse_date(date_match.group(0)) if date_match else None
        location_match = re.search(r"(PS|MS|IS|ERHS)\s+[^\s]+", card_text)
        location_label = location_match.group(0) if location_match else ""

        try:
            events.append(
                parse_chess_in_the_schools_detail(
                    session,
                    event_url=href,
                    title=title,
                    start=start,
                    location_label=location_label,
                )
            )
        except Exception:
            fallback = Event(
                provider="chess_in_the_schools",
                source="Chess In The Schools",
                title=title,
                start=start,
                event_url=href,
                registration_url=href,
                source_url=CHESS_IN_THE_SCHOOLS_SOURCE_URL,
                venue_name=location_label,
                state="NY",
                organizer="Chess In The Schools",
                summary=summarize_text(card_text),
                description=card_text,
            )
            events.append(classify_event_fit(fallback))

    return events


def parse_city_state_postal(address: str) -> tuple[str, str, str]:
    match = re.search(
        r"([^,]+),\s*([A-Za-z ]+)\s+(\d{5})(?:-\d{4})?(?:\s+United States)?$",
        clean_text(address),
    )
    if not match:
        return ("", "", normalize_postal_code(address))
    return (clean_text(match.group(1)), normalize_state_token(match.group(2)), match.group(3))


def extract_jsonld_events(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        if payload.get("@type") == "Event":
            return [payload]
        if "@graph" in payload and isinstance(payload["@graph"], list):
            events: list[dict[str, object]] = []
            for item in payload["@graph"]:
                events.extend(extract_jsonld_events(item))
            return events
    if isinstance(payload, list):
        events: list[dict[str, object]] = []
        for item in payload:
            events.extend(extract_jsonld_events(item))
        return events
    return []


def parse_chess_father_event(session: requests.Session, event_url: str) -> Event | None:
    response = session.get(event_url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    jsonld_events: list[dict[str, object]] = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            payload = json.loads(script.get_text(strip=True))
        except json.JSONDecodeError:
            continue
        jsonld_events.extend(extract_jsonld_events(payload))

    if not jsonld_events:
        return None

    event_data = jsonld_events[0]
    location = event_data.get("location") or {}
    address_text = clean_text(location.get("address")) if isinstance(location, dict) else ""
    city, state, postal_code = parse_city_state_postal(address_text)
    offers = event_data.get("offers") or {}
    entry_fee = ""
    if isinstance(offers, dict):
        low_price = clean_text(offers.get("lowPrice"))
        high_price = clean_text(offers.get("highPrice"))
        if low_price and high_price and low_price != high_price:
            entry_fee = f"${low_price}-${high_price}"
        elif low_price:
            entry_fee = f"${low_price}"

    event = Event(
        provider="chess_father",
        source="Chess Father",
        title=clean_text(event_data.get("name")),
        start=parse_iso_datetime(event_data.get("startDate")),
        end=parse_iso_datetime(event_data.get("endDate")),
        event_url=canonicalize_url(event_url),
        registration_url=canonicalize_url(event_url),
        source_url=CHESS_FATHER_SOURCE_URL,
        venue_name=clean_text(location.get("name")) if isinstance(location, dict) else "",
        address=address_text,
        city=city,
        state=state,
        postal_code=postal_code,
        organizer="Chess Father",
        summary=summarize_text(clean_text(event_data.get("description"))),
        description=clean_text(event_data.get("description")),
        entry_fee=entry_fee,
        time_control=clean_text(
            " ".join(
                re.findall(r"(G/\d+\s*;?\s*d/?\d+|G/\d+\s*d\d+)", clean_text(event_data.get("description")), flags=re.IGNORECASE)
            )
        ),
    )
    return classify_event_fit(event)


def parse_chess_father_tournaments(session: requests.Session) -> list[Event]:
    response = session.get(CHESS_FATHER_SOURCE_URL, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    event_urls = sorted(
        {
            canonicalize_url(urljoin(CHESS_FATHER_SOURCE_URL, link.get("href", "")))
            for link in soup.select('a[href*="/event-details/"]')
            if link.get("href")
        }
    )

    events: list[Event] = []
    for event_url in event_urls:
        try:
            event = parse_chess_father_event(session, event_url)
        except Exception:
            continue
        if event is not None:
            events.append(event)
    return events


def collect_events(session: requests.Session, months_ahead: int = DEFAULT_MONTHS_AHEAD) -> list[Event]:
    collected: list[Event] = []
    errors: list[str] = []

    for label, collector, seed_file in (
        ("Official Chess", lambda: collect_official_chess(session, months_ahead=months_ahead), None),
        (
            "Little House of Chess",
            lambda: collect_little_house_of_chess(session, months_ahead=months_ahead),
            LITTLE_HOUSE_SEED_FILE,
        ),
        ("US Chess", lambda: collect_us_chess(session), None),
        ("Events4Chess", lambda: collect_events4chess(session), None),
        ("Chess In The Schools", lambda: parse_chess_in_the_schools_tournaments(session), None),
        ("Chess Father", lambda: parse_chess_father_tournaments(session), None),
        ("Tri-State Chess", lambda: parse_tristate_registration(session), None),
        ("ICA NJ", lambda: parse_icanj_calendar(session), None),
        ("Westchester Chess Club", lambda: parse_westchester_schedule(session), None),
    ):
        try:
            source_events = collector()
            if source_events:
                collected.extend(source_events)
                continue
            raise RuntimeError("source returned no events")
        except Exception as exc:
            fallback_events = load_seed_events(seed_file) if seed_file is not None else []
            if fallback_events:
                collected.extend(fallback_events)
                errors.append(f"{label}: {exc} (using tracked seed fallback)")
            else:
                errors.append(f"{label}: {exc}")

    if not collected:
        raise RuntimeError("No sources refreshed successfully. " + " | ".join(errors))
    return collected


def build_url_dedupe_key(event: Event) -> str:
    event_day = event.start.date().isoformat() if event.start else ""
    canonical_registration = canonicalize_url(event.registration_url)
    if canonical_registration:
        return f"link|{canonical_registration}|{event_day}"
    canonical_event_url = canonicalize_url(event.event_url)
    if canonical_event_url:
        return f"event|{canonical_event_url}|{event_day}"
    return ""


def build_dedupe_key(event: Event) -> str:
    event_day = event.start.date().isoformat() if event.start else ""
    return "|".join(
        [
            "semantic",
            normalized_title_for_dedupe(event.title),
            event_day,
            normalize_postal_code(event.postal_code) or to_slug(event.city),
            to_slug(event.venue_name or event.address or event.organizer),
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
    merged.contributing_sources = list(
        dict.fromkeys([*winner.contributing_sources, *loser.contributing_sources])
    )
    merged.contributing_providers = list(
        dict.fromkeys([*winner.contributing_providers, *loser.contributing_providers])
    )
    classify_event_fit(merged)
    return merged


def dedupe_by_key(events: Iterable[Event], key_builder: Callable[[Event], str]) -> list[Event]:
    best_by_key: dict[str, Event] = {}
    for event in events:
        key = key_builder(event)
        if not key:
            key = f"fallback|{id(event)}"
        event.dedupe_key = key
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = event
            continue
        best_by_key[key] = merge_events(existing, event)
    return list(best_by_key.values())


def dedupe_events(events: Iterable[Event]) -> list[Event]:
    deduped_by_url = dedupe_by_key(events, build_url_dedupe_key)
    return dedupe_by_key(deduped_by_url, build_dedupe_key)


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
        if source_filter and not set(event.contributing_sources or [event.source]).intersection(source_filter):
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
                    " ".join(event.contributing_sources),
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
                "contributing_sources": " | ".join(event.contributing_sources),
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
        "contributing_sources",
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
