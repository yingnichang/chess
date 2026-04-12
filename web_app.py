from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, timedelta
from urllib.parse import urlencode

from flask import Flask, Response, jsonify, render_template_string, request

from tournament_data import (
    CoordinateResolver,
    DEFAULT_CACHE_FILE,
    DEFAULT_COORD_CACHE_FILE,
    DEFAULT_MONTHS_AHEAD,
    TARGET_STATES,
    event_table_rows,
    filter_events,
    load_or_refresh_dataset,
    relative_date_label,
    sort_events,
    with_home_distances,
)


app = Flask(__name__)

MONTHS_AHEAD = int(os.getenv("MONTHS_AHEAD", str(DEFAULT_MONTHS_AHEAD)))
CACHE_MAX_AGE_HOURS = int(os.getenv("CACHE_MAX_AGE_HOURS", "24"))
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "").strip()


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NY Chess Tournament Finder</title>
  <style>
    :root {
      --ink: #101828;
      --muted: #667085;
      --bg: #eef4fb;
      --card: rgba(255,255,255,0.94);
      --line: rgba(15, 23, 42, 0.10);
      --accent: #0c4a6e;
      --accent-2: #0369a1;
      --soft: #dff3ff;
      --good: #dcfce7;
      --good-ink: #166534;
      --warn: #fef3c7;
      --warn-ink: #92400e;
      --slate: #e2e8f0;
      --slate-ink: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.14), transparent 28%),
        radial-gradient(circle at top right, rgba(15, 23, 42, 0.08), transparent 22%),
        linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
      font-family: "Segoe UI", Arial, sans-serif;
    }
    a { color: var(--accent); text-decoration: none; }
    .shell {
      max-width: 1380px;
      margin: 0 auto;
      padding: 22px 18px 36px;
    }
    .hero {
      border: 1px solid rgba(15, 23, 42, 0.08);
      border-radius: 28px;
      padding: 28px 30px;
      background: linear-gradient(135deg, #0f172a 0%, #0c4a6e 70%, #0369a1 100%);
      color: white;
      box-shadow: 0 26px 60px rgba(15, 23, 42, 0.16);
    }
    .hero h1 {
      margin: 0 0 0.35rem 0;
      font-size: 2.2rem;
      line-height: 1.08;
    }
    .hero p {
      margin: 0.25rem 0;
      color: rgba(255,255,255,0.86);
    }
    .meta-strip {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 0.9rem;
    }
    .meta-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0.45rem 0.75rem;
      border-radius: 999px;
      background: rgba(255,255,255,0.14);
      border: 1px solid rgba(255,255,255,0.16);
      font-size: 0.92rem;
    }
    .flash {
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 18px;
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fed7aa;
    }
    .layout {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 18px;
      margin-top: 18px;
    }
    .panel {
      border: 1px solid var(--line);
      border-radius: 22px;
      background: var(--card);
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.06);
    }
    .sidebar {
      padding: 18px;
      position: sticky;
      top: 16px;
      align-self: start;
    }
    .content {
      padding: 18px;
    }
    .label {
      display: block;
      margin-top: 12px;
      margin-bottom: 6px;
      font-size: 0.86rem;
      font-weight: 700;
      color: #0f172a;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    input, select, button {
      width: 100%;
      border-radius: 12px;
      border: 1px solid #cbd5e1;
      padding: 10px 12px;
      font: inherit;
      background: white;
    }
    select[multiple] {
      min-height: 100px;
    }
    .checkbox-row {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-top: 10px;
    }
    .checkbox-row input {
      width: auto;
      margin: 0;
    }
    .button-row {
      display: flex;
      gap: 10px;
      margin-top: 16px;
    }
    .button-row a, .button-row button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
    }
    .primary {
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
      color: white;
      border: none;
    }
    .secondary {
      background: white;
      color: var(--accent);
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: white;
    }
    .metric-label {
      color: var(--muted);
      font-size: 0.86rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .metric-value {
      margin-top: 6px;
      font-size: 1.65rem;
      font-weight: 800;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .toolbar-links {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .toolbar-links a {
      padding: 0.65rem 0.9rem;
      border-radius: 999px;
      border: 1px solid #cbd5e1;
      background: white;
      font-weight: 700;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background: white;
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid var(--line);
      margin-bottom: 18px;
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid #e2e8f0;
      text-align: left;
      vertical-align: top;
      font-size: 0.95rem;
    }
    th {
      background: #f8fafc;
      color: #334155;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .event-card {
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 18px 18px 16px 18px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 18px 42px rgba(15, 23, 42, 0.06);
      margin-bottom: 0.9rem;
    }
    .event-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .source-pill {
      display: inline-block;
      padding: 0.38rem 0.7rem;
      border-radius: 999px;
      background: #e0f2fe;
      color: #075985;
      font-weight: 700;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .updated-pill {
      color: var(--muted);
      font-size: 0.92rem;
    }
    .event-card h3 {
      margin: 0.45rem 0 0.55rem 0;
      font-size: 1.22rem;
      line-height: 1.25;
    }
    .card-line {
      margin: 0.28rem 0;
      color: #344054;
    }
    .badge-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 0.8rem;
      margin-bottom: 0.65rem;
    }
    .badge {
      display: inline-block;
      padding: 0.28rem 0.62rem;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
    }
    .badge-blue { background: #dbeafe; color: #1d4ed8; }
    .badge-green { background: var(--good); color: var(--good-ink); }
    .badge-amber { background: var(--warn); color: var(--warn-ink); }
    .badge-slate { background: var(--slate); color: var(--slate-ink); }
    .card-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }
    .card-actions a {
      padding: 0.65rem 0.9rem;
      border-radius: 999px;
      border: 1px solid #cbd5e1;
      background: white;
      font-weight: 700;
    }
    .muted { color: var(--muted); }
    @media (max-width: 1040px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { position: static; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .metrics { grid-template-columns: 1fr; }
      .toolbar { align-items: flex-start; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>New York Area Chess Tournament Finder</h1>
      <p>Parent-focused local tournament search with direct registration links, freshness tracking, and optional home-drive filtering.</p>
      <div class="meta-strip">
        <span class="meta-chip">Last refresh: {{ dataset.generated_at.strftime('%Y-%m-%d %H:%M') }}</span>
        <span class="meta-chip">Sources in feed: {{ dataset.source_count }}</span>
        <span class="meta-chip">Upcoming tournaments cached: {{ total_upcoming }}</span>
      </div>
    </section>
    {% if dataset.stale and dataset.refresh_error %}
    <div class="flash">
      Live refresh failed, so the app is showing the latest cached dataset instead. Refresh error: {{ dataset.refresh_error }}
    </div>
    {% endif %}
    {% if home_query and not home_resolved %}
    <div class="flash">
      The home ZIP/address could not be resolved, so drive filtering was skipped for this request.
    </div>
    {% endif %}
    <div class="layout">
      <aside class="panel sidebar">
        <form method="get">
          <div class="label">Search</div>
          <input type="text" name="search" value="{{ search_text }}" placeholder="School, organizer, venue, city">

          <div class="label">Home ZIP or address</div>
          <input type="text" name="home" value="{{ home_query }}" placeholder="10583 or Scarsdale, NY">

          <label class="checkbox-row">
            <input type="checkbox" name="use_drive_limit" value="1" {% if use_drive_limit %}checked{% endif %}>
            <span>Limit to driving range</span>
          </label>

          <div class="label">Max drive minutes</div>
          <input type="number" min="30" max="240" step="15" name="max_drive_minutes" value="{{ max_drive_minutes }}">

          <div class="label">Start date</div>
          <input type="date" name="start" value="{{ start_date }}">

          <div class="label">End date</div>
          <input type="date" name="end" value="{{ end_date }}">

          <div class="label">States</div>
          <select name="state" multiple>
            {% for option in state_options %}
            <option value="{{ option }}" {% if option in selected_states %}selected{% endif %}>{{ option }}</option>
            {% endfor %}
          </select>

          <div class="label">Cities</div>
          <select name="city" multiple>
            {% for option in city_options %}
            <option value="{{ option }}" {% if option in selected_cities %}selected{% endif %}>{{ option }}</option>
            {% endfor %}
          </select>

          <div class="label">Sources</div>
          <select name="source" multiple>
            {% for option in source_options %}
            <option value="{{ option }}" {% if option in selected_sources %}selected{% endif %}>{{ option }}</option>
            {% endfor %}
          </select>

          <label class="checkbox-row">
            <input type="checkbox" name="scholastic_only" value="1" {% if scholastic_only %}checked{% endif %}>
            <span>Scholastic / youth oriented</span>
          </label>

          <label class="checkbox-row">
            <input type="checkbox" name="beginner_friendly" value="1" {% if beginner_friendly %}checked{% endif %}>
            <span>Beginner-friendly only</span>
          </label>

          <div class="label">Sort by</div>
          <select name="sort">
            {% for option in sort_options %}
            <option value="{{ option }}" {% if option == selected_sort %}selected{% endif %}>{{ option }}</option>
            {% endfor %}
          </select>

          <div class="label">Cards to show</div>
          <select name="limit">
            {% for option in limit_options %}
            <option value="{{ option }}" {% if option == card_limit %}selected{% endif %}>{{ option }}</option>
            {% endfor %}
          </select>

          <div class="button-row">
            <button class="primary" type="submit">Apply filters</button>
          </div>
        </form>
      </aside>

      <main class="panel content">
        <div class="metrics">
          <div class="metric">
            <div class="metric-label">Results</div>
            <div class="metric-value">{{ metrics.total }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Scholastic fit</div>
            <div class="metric-value">{{ metrics.scholastic }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Beginner-friendly</div>
            <div class="metric-value">{{ metrics.beginner }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">{{ metrics.fourth_label }}</div>
            <div class="metric-value">{{ metrics.fourth_value }}</div>
          </div>
        </div>

        <div class="toolbar">
          <div>
            <strong>{{ metrics.total }}</strong> tournaments match the current filters.
            <div class="muted">Default order is source update freshness so the latest edited tournament listings surface first.</div>
          </div>
          <div class="toolbar-links">
            <a href="{{ download_csv_href }}">Download CSV</a>
            <a href="{{ download_json_href }}">Download JSON</a>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th>Updated</th>
              <th>Date</th>
              <th>Tournament</th>
              <th>Location</th>
              <th>Drive</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {% for row in summary_rows %}
            <tr>
              <td>{{ row.updated }}</td>
              <td>{{ row.date }}</td>
              <td>{{ row.title }}</td>
              <td>{{ row.location }}</td>
              <td>{{ row.drive }}</td>
              <td>{{ row.source }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>

        {% if not events %}
          <p>No tournaments matched the current filters.</p>
        {% endif %}

        {% for event in events %}
        <article class="event-card">
          <div class="event-top">
            <span class="source-pill">{{ event.source }}</span>
            <span class="updated-pill">Updated {{ event.updated_label }}</span>
          </div>
          <h3>{{ event.title }}</h3>
          <p class="card-line"><strong>When:</strong> {{ event.when_label }}</p>
          <p class="card-line"><strong>Where:</strong> {{ event.location_label }}</p>
          <p class="card-line"><strong>Organizer:</strong> {{ event.organizer }}</p>
          <div class="badge-row">
            {% for badge in event.badges %}
            <span class="badge {{ badge.class_name }}">{{ badge.label }}</span>
            {% endfor %}
          </div>
          <p class="card-line">{{ event.summary }}</p>
          <div class="card-actions">
            <a href="{{ event.registration_href }}">Registration</a>
            <a href="{{ event.source_listing_href }}">Source listing</a>
            <a href="{{ event.source_site_href }}">Source site</a>
          </div>
        </article>
        {% endfor %}
      </main>
    </div>
  </div>
</body>
</html>
"""


@app.get("/")
def index() -> str:
    context = build_page_context(force_refresh=False)
    return render_template_string(TEMPLATE, **context)


@app.get("/healthz")
def healthz() -> Response:
    return jsonify({"ok": True})


@app.route("/admin/refresh", methods=["GET", "POST"])
def admin_refresh() -> Response:
    if REFRESH_TOKEN and request.args.get("token", "").strip() != REFRESH_TOKEN:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    dataset, refreshed = load_or_refresh_dataset(
        force_refresh=True,
        max_age_hours=CACHE_MAX_AGE_HOURS,
        months_ahead=MONTHS_AHEAD,
        cache_file=DEFAULT_CACHE_FILE,
        coord_cache_file=DEFAULT_COORD_CACHE_FILE,
    )
    return jsonify(
        {
            "ok": True,
            "refreshed": refreshed,
            "generated_at": dataset.generated_at.isoformat(),
            "event_count": len(dataset.events),
            "stale": dataset.stale,
            "refresh_error": dataset.refresh_error,
        }
    )


@app.get("/download.csv")
def download_csv() -> Response:
    filtered_events, _ = filtered_events_from_request(force_refresh=False)
    rows = event_table_rows(filtered_events)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else [])
    if rows:
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ny-area-chess-tournaments.csv"},
    )


@app.get("/download.json")
def download_json() -> Response:
    filtered_events, _ = filtered_events_from_request(force_refresh=False)
    rows = event_table_rows(filtered_events)
    return Response(
        json.dumps(rows, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=ny-area-chess-tournaments.json"},
    )


def build_page_context(*, force_refresh: bool) -> dict[str, object]:
    filtered_events, extra = filtered_events_from_request(force_refresh=force_refresh)
    limit_options = sorted({20, 40, 80, max(20, min(len(filtered_events), 120))})
    card_limit = extra["card_limit"]
    if card_limit not in limit_options:
        limit_options.append(card_limit)
        limit_options = sorted(set(limit_options))

    return {
        **extra,
        "events": [serialize_event_card(event) for event in filtered_events[:card_limit]],
        "summary_rows": [serialize_summary_row(event) for event in filtered_events[:15]],
        "limit_options": limit_options,
    }


def filtered_events_from_request(*, force_refresh: bool) -> tuple[list, dict[str, object]]:
    dataset, _ = load_or_refresh_dataset(
        force_refresh=force_refresh,
        max_age_hours=CACHE_MAX_AGE_HOURS,
        months_ahead=MONTHS_AHEAD,
        cache_file=DEFAULT_CACHE_FILE,
        coord_cache_file=DEFAULT_COORD_CACHE_FILE,
    )
    resolver = CoordinateResolver(cache_path=DEFAULT_COORD_CACHE_FILE)

    upcoming_events = [event for event in dataset.events if event.start and event.start.date() >= date.today()]
    min_event_date = min((event.start.date() for event in upcoming_events), default=date.today())
    max_event_date = max(
        (event.start.date() for event in upcoming_events),
        default=date.today() + timedelta(days=90),
    )
    default_end = min(date.today() + timedelta(days=90), max_event_date)

    search_text = request.args.get("search", "").strip()
    home_query = request.args.get("home", "").strip()
    use_drive_limit = request.args.get("use_drive_limit") == "1"
    max_drive_minutes = parse_int(request.args.get("max_drive_minutes"), default=120)
    start_date = request.args.get("start") or date.today().isoformat()
    end_date = request.args.get("end") or default_end.isoformat()
    selected_states = request.args.getlist("state") or [
        state for state in TARGET_STATES if state in {event.state for event in upcoming_events if event.state}
    ]
    selected_cities = request.args.getlist("city")
    source_options = sorted({event.source for event in upcoming_events})
    selected_sources = request.args.getlist("source") or source_options
    scholastic_only = request.args.get("scholastic_only") == "1"
    beginner_friendly = request.args.get("beginner_friendly") == "1"
    selected_sort = request.args.get("sort", "Recently updated")
    card_limit = parse_int(request.args.get("limit"), default=20)

    display_events = upcoming_events
    home_resolved = True
    if home_query:
        display_events, home_coords = with_home_distances(display_events, home_query, resolver)
        home_resolved = home_coords is not None

    if selected_sort == "Closest to home" and not home_query:
        selected_sort = "Tournament date"

    state_options = sorted({event.state for event in upcoming_events if event.state})
    city_options = sorted(
        {
            event.city
            for event in upcoming_events
            if event.city and (not selected_states or event.state in selected_states)
        }
    )

    filtered_events = filter_events(
        display_events,
        search_text=search_text,
        start_on=parse_date_only(start_date, date.today()),
        end_on=parse_date_only(end_date, default_end),
        states=selected_states,
        cities=selected_cities,
        sources=selected_sources,
        scholastic_only=scholastic_only,
        beginner_friendly=beginner_friendly,
        max_drive_minutes=max_drive_minutes if home_query and use_drive_limit else None,
    )
    filtered_events = sort_events(filtered_events, mode=sort_mode_map(selected_sort))

    metrics = {
        "total": len(filtered_events),
        "scholastic": sum(1 for event in filtered_events if event.age_fit == "good"),
        "beginner": sum(1 for event in filtered_events if event.beginner_fit == "good"),
        "fourth_label": (
            "Drive estimates" if home_query and use_drive_limit else "Registration links"
        ),
        "fourth_value": (
            sum(1 for event in filtered_events if event.estimated_drive_minutes is not None)
            if home_query and use_drive_limit
            else sum(1 for event in filtered_events if event.registration_url)
        ),
    }

    return filtered_events, {
        "dataset": dataset,
        "total_upcoming": len(upcoming_events),
        "search_text": search_text,
        "home_query": home_query,
        "home_resolved": home_resolved,
        "use_drive_limit": use_drive_limit,
        "max_drive_minutes": max_drive_minutes,
        "start_date": start_date,
        "end_date": end_date,
        "state_options": state_options,
        "city_options": city_options,
        "source_options": source_options,
        "selected_states": selected_states,
        "selected_cities": selected_cities,
        "selected_sources": selected_sources,
        "scholastic_only": scholastic_only,
        "beginner_friendly": beginner_friendly,
        "sort_options": ["Recently updated", "Tournament date", "Closest to home"],
        "selected_sort": selected_sort,
        "card_limit": card_limit,
        "metrics": metrics,
        "download_csv_href": "/download.csv?" + build_query_string(exclude={"refresh"}),
        "download_json_href": "/download.json?" + build_query_string(exclude={"refresh"}),
    }


def build_query_string(
    *,
    overrides: dict[str, str] | None = None,
    exclude: set[str] | None = None,
) -> str:
    params: dict[str, list[str]] = {}
    exclude = exclude or set()
    for key in request.args.keys():
        if key in exclude:
            continue
        params[key] = request.args.getlist(key)
    for key, value in (overrides or {}).items():
        params[key] = [value]
    return urlencode(params, doseq=True)


def serialize_summary_row(event) -> dict[str, str]:
    return {
        "updated": relative_date_label(event.source_updated_at),
        "date": event.start.strftime("%Y-%m-%d %H:%M") if event.start else "TBD",
        "title": event.title,
        "location": event.location_label or "TBD",
        "drive": (
            f"{event.estimated_drive_minutes} min"
            if event.estimated_drive_minutes is not None
            else ""
        ),
        "source": event.source,
    }


def serialize_event_card(event) -> dict[str, object]:
    return {
        "source": event.source,
        "updated_label": relative_date_label(event.source_updated_at),
        "title": event.title,
        "when_label": event.start.strftime("%a %b %d, %Y %I:%M %p") if event.start else "TBD",
        "location_label": event.location_label or "TBD",
        "organizer": event.organizer or "Not listed",
        "summary": event.summary or "See the source listing for full event details.",
        "badges": event_badges(event),
        "registration_href": event.registration_url or event.event_url or event.source_url or "#",
        "source_listing_href": event.event_url or event.source_url or "#",
        "source_site_href": event.source_url or event.event_url or "#",
    }


def event_badges(event) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    if event.age_fit == "good":
        badges.append({"label": "Scholastic", "class_name": "badge-green"})
    if event.beginner_fit == "good":
        badges.append({"label": "Beginner-friendly", "class_name": "badge-blue"})
    elif event.beginner_fit == "mixed":
        badges.append({"label": "Mixed difficulty", "class_name": "badge-amber"})
    elif event.beginner_fit == "maybe-hard":
        badges.append({"label": "Likely competitive", "class_name": "badge-amber"})
    if event.entry_fee:
        badges.append({"label": f"{event.entry_fee} entry", "class_name": "badge-slate"})
    if event.time_control:
        badges.append({"label": event.time_control, "class_name": "badge-slate"})
    if event.estimated_drive_minutes is not None:
        badges.append(
            {"label": f"{event.estimated_drive_minutes} min drive", "class_name": "badge-slate"}
        )
    return badges


def sort_mode_map(label: str) -> str:
    if label == "Tournament date":
        return "date"
    if label == "Closest to home":
        return "closest"
    return "recently_updated"


def parse_date_only(value: str, default: date) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


def parse_int(value: str | None, *, default: int) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").strip() == "1",
    )
