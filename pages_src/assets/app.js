window.__eventsForCities = [];

void init();

async function init() {
  const ui = bindUi();

  try {
    const dataset = await fetchDataset();
    const events = normalizeEvents(dataset.events || []);
    const defaults = buildDefaults(events);
    let homeCoords = null;

    window.__eventsForCities = events;

    populateMultiSelect(ui.states, uniqueValues(events, "state"), defaults.states);
    populateMultiSelect(ui.sources, uniqueSourceValues(events), uniqueSourceValues(events));
    populateMultiSelect(ui.cities, cityOptions(events, defaults.states), []);

    applyDefaultsToUi(ui, defaults);
    applyUrlToUi(ui, defaults);
    updateHeader(dataset, events.length, ui);

    ui.form.addEventListener("submit", async (event) => {
      event.preventDefault();
      homeCoords = await maybeResolveHomeZip(ui.homeZip.value.trim());
      await applyFilters();
    });

    ui.resetButton.addEventListener("click", async () => {
      applyDefaultsToUi(ui, defaults);
      homeCoords = null;
      clearFlash(ui.flash);
      await applyFilters();
    });

    ui.states.addEventListener("change", () => {
      const selectedStates = selectedValues(ui.states);
      const currentCities = new Set(selectedValues(ui.cities));
      populateMultiSelect(ui.cities, cityOptions(events, selectedStates), [...currentCities]);
    });

    ui.cardLimit.addEventListener("change", () => void applyFilters());
    ui.sortMode.addEventListener("change", () => void applyFilters());

    async function applyFilters() {
      const filters = readFiltersFromUi(ui, defaults);
      syncUrl(filters);

      if (filters.homeZip && filters.useDriveLimit && !homeCoords) {
        homeCoords = await maybeResolveHomeZip(filters.homeZip);
      }

      if (filters.homeZip && filters.useDriveLimit && !homeCoords) {
        showFlash(
          ui.flash,
          "The drive filter needs a valid 5-digit US ZIP code. Other filters still work."
        );
      } else if (dataset.stale && dataset.refresh_error) {
        showFlash(
          ui.flash,
          "This page is showing cached data because the latest live refresh failed."
        );
      } else {
        clearFlash(ui.flash);
      }

      const enrichedEvents = homeCoords ? enrichWithDrive(events, homeCoords) : events;
      const filteredEvents = sortEvents(
        filterEvents(enrichedEvents, filters),
        filters.sortMode
      );
      renderEverything(filteredEvents, filters, ui);
    }

    await applyFilters();
  } catch (error) {
    handleFatalError(ui, error);
  }
}

async function fetchDataset() {
  const response = await fetch("data/tournaments.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Could not load tournament data.");
  }
  return response.json();
}

function bindUi() {
  return {
    flash: document.getElementById("flash"),
    form: document.getElementById("filters-form"),
    search: document.getElementById("search"),
    homeZip: document.getElementById("home-zip"),
    useDriveLimit: document.getElementById("use-drive-limit"),
    maxDriveMinutes: document.getElementById("max-drive-minutes"),
    startDate: document.getElementById("start-date"),
    endDate: document.getElementById("end-date"),
    states: document.getElementById("states"),
    cities: document.getElementById("cities"),
    sources: document.getElementById("sources"),
    scholasticOnly: document.getElementById("scholastic-only"),
    beginnerFriendly: document.getElementById("beginner-friendly"),
    sortMode: document.getElementById("sort-mode"),
    cardLimit: document.getElementById("card-limit"),
    generatedAt: document.getElementById("generated-at"),
    sourceCount: document.getElementById("source-count"),
    totalCached: document.getElementById("total-cached"),
    resultsCount: document.getElementById("results-count"),
    metrics: document.getElementById("metrics"),
    sourceCoverage: document.getElementById("source-coverage"),
    summaryBody: document.getElementById("summary-body"),
    cards: document.getElementById("cards"),
    emptyState: document.getElementById("empty-state"),
    resetButton: document.getElementById("reset-filters"),
  };
}

function normalizeEvents(events) {
  return events
    .map((event) => ({
      ...event,
      title: event.title || "",
      source: event.source || "",
      allSources: normalizeStringList(event.contributing_sources, event.source),
      city: event.city || "",
      state: event.state || "",
      organizer: event.organizer || "",
      summary: event.summary || "",
      sections: event.sections || "",
      locationLabel: [
        event.venue_name,
        event.address,
        event.city,
        event.state,
        event.postal_code,
      ]
        .filter(Boolean)
        .join(", "),
      startDate: event.start ? new Date(event.start) : null,
      endDate: event.end ? new Date(event.end) : null,
      updatedAt: event.source_updated_at
        ? new Date(event.source_updated_at)
        : event.source_created_at
          ? new Date(event.source_created_at)
          : null,
      latitude: numericOrNull(event.latitude),
      longitude: numericOrNull(event.longitude),
    }))
    .filter((event) => event.startDate && !Number.isNaN(event.startDate.getTime()));
}

function normalizeStringList(values, fallback) {
  const list = Array.isArray(values) ? values : [];
  const normalized = list.map((value) => String(value || "").trim()).filter(Boolean);
  if (!normalized.length && fallback) {
    normalized.push(String(fallback).trim());
  }
  return [...new Set(normalized)];
}

function numericOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function buildDefaults(events) {
  const today = new Date();
  const todayIso = toIsoDate(today);
  const latestDefaultDate = new Date(today);
  latestDefaultDate.setDate(today.getDate() + 90);
  const latestEventDate = events.reduce((maxValue, event) => {
    const value = toIsoDate(event.startDate);
    return value > maxValue ? value : maxValue;
  }, todayIso);

  return {
    search: "",
    homeZip: "",
    useDriveLimit: false,
    maxDriveMinutes: "120",
    startDate: todayIso,
    endDate:
      latestEventDate < toIsoDate(latestDefaultDate)
        ? latestEventDate
        : toIsoDate(latestDefaultDate),
    states: ["NY", "NJ", "CT"].filter((state) =>
      uniqueValues(events, "state").includes(state)
    ),
    cities: [],
    sources: uniqueSourceValues(events),
    scholasticOnly: true,
    beginnerFriendly: false,
    sortMode: "date",
    cardLimit: "20",
  };
}

function applyDefaultsToUi(ui, defaults) {
  ui.search.value = defaults.search;
  ui.homeZip.value = defaults.homeZip;
  ui.useDriveLimit.checked = defaults.useDriveLimit;
  ui.maxDriveMinutes.value = defaults.maxDriveMinutes;
  ui.startDate.value = defaults.startDate;
  ui.endDate.value = defaults.endDate;
  selectValues(ui.states, defaults.states);
  populateMultiSelect(ui.cities, cityOptionsFromUi(ui.states), defaults.cities);
  selectValues(ui.sources, defaults.sources);
  ui.scholasticOnly.checked = defaults.scholasticOnly;
  ui.beginnerFriendly.checked = defaults.beginnerFriendly;
  ui.sortMode.value = defaults.sortMode;
  ui.cardLimit.value = defaults.cardLimit;
}

function applyUrlToUi(ui, defaults) {
  const params = new URLSearchParams(window.location.search);
  if (!params.toString()) {
    return;
  }

  ui.search.value = params.get("search") || defaults.search;
  ui.homeZip.value = params.get("homeZip") || defaults.homeZip;
  ui.useDriveLimit.checked = params.get("useDriveLimit") === "1";
  ui.maxDriveMinutes.value = params.get("maxDriveMinutes") || defaults.maxDriveMinutes;
  ui.startDate.value = params.get("startDate") || defaults.startDate;
  ui.endDate.value = params.get("endDate") || defaults.endDate;
  selectValues(
    ui.states,
    params.getAll("state").length ? params.getAll("state") : defaults.states
  );
  populateMultiSelect(ui.cities, cityOptionsFromUi(ui.states), params.getAll("city"));
  selectValues(
    ui.sources,
    params.getAll("source").length ? params.getAll("source") : defaults.sources
  );
  ui.scholasticOnly.checked = params.get("scholasticOnly") !== "0";
  ui.beginnerFriendly.checked = params.get("beginnerFriendly") === "1";
  ui.sortMode.value = params.get("sortMode") || defaults.sortMode;
  ui.cardLimit.value = params.get("cardLimit") || defaults.cardLimit;
}

function readFiltersFromUi(ui, defaults) {
  return {
    search: ui.search.value.trim(),
    homeZip: ui.homeZip.value.trim(),
    useDriveLimit: ui.useDriveLimit.checked,
    maxDriveMinutes: readPositiveNumber(ui.maxDriveMinutes.value, defaults.maxDriveMinutes, 30),
    startDate: ui.startDate.value || defaults.startDate,
    endDate: ui.endDate.value || defaults.endDate,
    states: selectedValues(ui.states),
    cities: selectedValues(ui.cities),
    sources: selectedValues(ui.sources),
    scholasticOnly: ui.scholasticOnly.checked,
    beginnerFriendly: ui.beginnerFriendly.checked,
    sortMode: ui.sortMode.value || defaults.sortMode,
    cardLimit: readPositiveNumber(ui.cardLimit.value, defaults.cardLimit, 1),
  };
}

function readPositiveNumber(value, fallback, minimum) {
  const number = Number(value);
  if (Number.isFinite(number) && number >= minimum) {
    return number;
  }
  return Number(fallback);
}

function syncUrl(filters) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.homeZip) params.set("homeZip", filters.homeZip);
  if (filters.useDriveLimit) params.set("useDriveLimit", "1");
  if (filters.maxDriveMinutes) params.set("maxDriveMinutes", String(filters.maxDriveMinutes));
  params.set("startDate", filters.startDate);
  params.set("endDate", filters.endDate);
  filters.states.forEach((value) => params.append("state", value));
  filters.cities.forEach((value) => params.append("city", value));
  filters.sources.forEach((value) => params.append("source", value));
  if (!filters.scholasticOnly) params.set("scholasticOnly", "0");
  if (filters.beginnerFriendly) params.set("beginnerFriendly", "1");
  params.set("sortMode", filters.sortMode);
  params.set("cardLimit", String(filters.cardLimit));

  const query = params.toString();
  history.replaceState(
    null,
    "",
    query ? `${window.location.pathname}?${query}` : window.location.pathname
  );
}

async function maybeResolveHomeZip(homeZip) {
  if (!/^\d{5}$/.test(homeZip)) {
    return null;
  }

  try {
    const response = await fetch(`https://api.zippopotam.us/us/${homeZip}`);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    const firstPlace = (payload.places || [])[0];
    if (!firstPlace) {
      return null;
    }
    return {
      lat: Number(firstPlace.latitude),
      lon: Number(firstPlace.longitude),
    };
  } catch {
    return null;
  }
}

function enrichWithDrive(events, homeCoords) {
  return events.map((event) => {
    if (!Number.isFinite(event.latitude) || !Number.isFinite(event.longitude)) {
      return {
        ...event,
        distanceAirMiles: null,
        estimatedDriveMinutes: null,
      };
    }

    const airMiles = haversineMiles(
      homeCoords.lat,
      homeCoords.lon,
      event.latitude,
      event.longitude
    );

    return {
      ...event,
      distanceAirMiles: Math.round(airMiles * 10) / 10,
      estimatedDriveMinutes: estimateDriveMinutes(airMiles),
    };
  });
}

function filterEvents(events, filters) {
  const search = filters.search.toLowerCase();

  return events.filter((event) => {
    const eventDate = toIsoDate(event.startDate);
    if (eventDate < filters.startDate || eventDate > filters.endDate) {
      return false;
    }
    if (filters.states.length && !filters.states.includes(event.state)) {
      return false;
    }
    if (filters.cities.length && !filters.cities.includes(event.city)) {
      return false;
    }
    if (
      filters.sources.length &&
      !event.allSources.some((source) => filters.sources.includes(source))
    ) {
      return false;
    }
    if (
      filters.scholasticOnly &&
      !(event.age_fit === "good" || startsWithYes(event.scholastic_only))
    ) {
      return false;
    }
    if (filters.beginnerFriendly && event.beginner_fit !== "good") {
      return false;
    }
    if (filters.useDriveLimit && filters.homeZip) {
      if (
        !Number.isFinite(event.estimatedDriveMinutes) ||
        event.estimatedDriveMinutes > filters.maxDriveMinutes
      ) {
        return false;
      }
    }
    if (search) {
      const haystack = [
        event.title,
        event.organizer,
        event.venue_name,
        event.city,
        event.state,
        event.summary,
        event.sections,
        event.allSources.join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(search)) {
        return false;
      }
    }
    return true;
  });
}

function sortEvents(events, mode) {
  const copy = [...events];

  if (mode === "closest") {
    return copy.sort((a, b) => {
      const aValue = Number.isFinite(a.estimatedDriveMinutes)
        ? a.estimatedDriveMinutes
        : Number.MAX_SAFE_INTEGER;
      const bValue = Number.isFinite(b.estimatedDriveMinutes)
        ? b.estimatedDriveMinutes
        : Number.MAX_SAFE_INTEGER;
      if (aValue !== bValue) return aValue - bValue;
      return a.startDate - b.startDate;
    });
  }

  if (mode === "date") {
    return copy.sort(
      (a, b) => a.startDate - b.startDate || (b.updatedAt || 0) - (a.updatedAt || 0)
    );
  }

  return copy.sort((a, b) => {
    const aUpdated = a.updatedAt ? a.updatedAt.getTime() : 0;
    const bUpdated = b.updatedAt ? b.updatedAt.getTime() : 0;
    if (aUpdated !== bUpdated) return bUpdated - aUpdated;
    return a.startDate - b.startDate;
  });
}

function renderEverything(events, filters, ui) {
  renderMetrics(events, filters, ui.metrics);
  renderSourceCoverage(events, ui.sourceCoverage);
  ui.resultsCount.textContent = String(events.length);
  renderSummary(events.slice(0, 15), ui.summaryBody);
  renderCards(events.slice(0, filters.cardLimit), ui.cards);
  ui.emptyState.classList.toggle("hidden", events.length > 0);
}

function renderMetrics(events, filters, container) {
  const metrics = [
    { label: "Results", value: events.length },
    {
      label: "Scholastic fit",
      value: events.filter((event) => event.age_fit === "good").length,
    },
    {
      label: "Beginner-friendly",
      value: events.filter((event) => event.beginner_fit === "good").length,
    },
    {
      label: filters.useDriveLimit && filters.homeZip ? "Drive estimates" : "Registration links",
      value:
        filters.useDriveLimit && filters.homeZip
          ? events.filter((event) => Number.isFinite(event.estimatedDriveMinutes)).length
          : events.filter((event) => !!event.registration_url).length,
    },
  ];

  container.innerHTML = metrics
    .map(
      (metric) => `
        <article class="metric">
          <div class="metric-label">${escapeHtml(metric.label)}</div>
          <div class="metric-value">${escapeHtml(String(metric.value))}</div>
        </article>
      `
    )
    .join("");
}

function renderSourceCoverage(events, container) {
  const counts = new Map();
  events.forEach((event) => {
    event.allSources.forEach((source) => {
      counts.set(source, (counts.get(source) || 0) + 1);
    });
  });

  const entries = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!entries.length) {
    container.innerHTML = '<p class="muted">No source coverage to show for the current filters.</p>';
    return;
  }

  container.innerHTML = entries
    .map(
      ([source, count]) => `
        <article class="coverage-chip">
          <span class="coverage-source">${escapeHtml(source)}</span>
          <strong class="coverage-count">${escapeHtml(String(count))}</strong>
        </article>
      `
    )
    .join("");
}

function renderSummary(events, container) {
  if (!events.length) {
    container.innerHTML = `
      <tr>
        <td colspan="6" class="muted">No tournaments match the current filters.</td>
      </tr>
    `;
    return;
  }

  container.innerHTML = events
    .map(
      (event) => `
        <tr>
          <td>${escapeHtml(relativeDateLabel(event.updatedAt))}</td>
          <td>${escapeHtml(formatDateTime(event.startDate))}</td>
          <td>${escapeHtml(event.title)}</td>
          <td>${escapeHtml(event.locationLabel || "TBD")}</td>
          <td>${escapeHtml(driveLabel(event))}</td>
          <td>${escapeHtml(sourceSummaryLabel(event))}</td>
        </tr>
      `
    )
    .join("");
}

function renderCards(events, container) {
  container.innerHTML = events
    .map(
      (event) => `
        <article class="event-card">
          <div class="event-top">
            <span class="source-pill">${escapeHtml(event.source)}</span>
            <span class="updated-pill">Updated ${escapeHtml(
              relativeDateLabel(event.updatedAt)
            )}</span>
          </div>
          <h3>${escapeHtml(event.title)}</h3>
          <p class="card-line"><strong>When:</strong> ${escapeHtml(
            formatDateTime(event.startDate, true)
          )}</p>
          <p class="card-line"><strong>Where:</strong> ${escapeHtml(
            event.locationLabel || "TBD"
          )}</p>
          <p class="card-line"><strong>Organizer:</strong> ${escapeHtml(
            event.organizer || "Not listed"
          )}</p>
          ${otherSourcesLine(event)}
          <div class="badge-row">${eventBadges(event).join("")}</div>
          <p class="card-line">${escapeHtml(
            event.summary || "See the source listing for full event details."
          )}</p>
          <div class="card-actions">${buildActionLinks(event)}</div>
        </article>
      `
    )
    .join("");
}

function buildActionLinks(event) {
  const links = [];
  const registrationUrl = event.registration_url || event.event_url || event.source_url;
  const listingUrl = event.event_url;
  const sourceUrl = event.source_url;

  if (registrationUrl) {
    links.push(renderActionLink(registrationUrl, "Registration"));
  }
  if (listingUrl && listingUrl !== registrationUrl) {
    links.push(renderActionLink(listingUrl, "Source listing"));
  }
  if (sourceUrl && sourceUrl !== listingUrl && sourceUrl !== registrationUrl) {
    links.push(renderActionLink(sourceUrl, "Source site"));
  }

  if (!links.length) {
    return '<span class="muted">No external links listed for this event.</span>';
  }

  return links.join("");
}

function renderActionLink(url, label) {
  return `<a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">${escapeHtml(
    label
  )}</a>`;
}

function eventBadges(event) {
  const badges = [];

  if (event.age_fit === "good") {
    badges.push('<span class="badge badge-green">Scholastic</span>');
  }
  if (event.beginner_fit === "good") {
    badges.push('<span class="badge badge-blue">Beginner-friendly</span>');
  }
  if (event.beginner_fit === "mixed") {
    badges.push('<span class="badge badge-amber">Mixed difficulty</span>');
  }
  if (event.beginner_fit === "maybe-hard") {
    badges.push('<span class="badge badge-amber">Likely competitive</span>');
  }
  if (event.entry_fee) {
    badges.push(
      `<span class="badge badge-slate">${escapeHtml(event.entry_fee)} entry</span>`
    );
  }
  if (event.time_control) {
    badges.push(
      `<span class="badge badge-slate">${escapeHtml(event.time_control)}</span>`
    );
  }
  if (Number.isFinite(event.estimatedDriveMinutes)) {
    badges.push(
      `<span class="badge badge-slate">${escapeHtml(
        String(event.estimatedDriveMinutes)
      )} min drive</span>`
    );
  }

  return badges;
}

function updateHeader(dataset, totalEvents, ui) {
  ui.generatedAt.textContent = dataset.generated_at
    ? formatDateTime(new Date(dataset.generated_at))
    : "Unknown";
  ui.sourceCount.textContent = String(
    new Set(
      (dataset.events || [])
        .flatMap((event) => normalizeStringList(event.contributing_sources, event.source))
    ).size
  );
  ui.totalCached.textContent = String(totalEvents);

  if (dataset.stale && dataset.refresh_error) {
    showFlash(
      ui.flash,
      "Live refresh failed, so this site is showing cached data instead."
    );
  }
}

function handleFatalError(ui, error) {
  console.error(error);
  showFlash(
    ui.flash,
    "Tournament data could not be loaded. Try refreshing later after the site finishes rebuilding."
  );
  ui.resultsCount.textContent = "0";
  ui.metrics.innerHTML = "";
  ui.summaryBody.innerHTML = "";
  ui.cards.innerHTML = "";
  ui.emptyState.classList.add("hidden");
}

function showFlash(element, message) {
  element.textContent = message;
  element.classList.remove("hidden");
}

function clearFlash(element) {
  element.textContent = "";
  element.classList.add("hidden");
}

function populateMultiSelect(select, options, selected) {
  const selectedSet = new Set(selected);
  select.innerHTML = options
    .map(
      (option) =>
        `<option value="${escapeAttribute(option)}" ${
          selectedSet.has(option) ? "selected" : ""
        }>${escapeHtml(option)}</option>`
    )
    .join("");
}

function selectedValues(select) {
  return Array.from(select.selectedOptions).map((option) => option.value);
}

function selectValues(select, values) {
  const wanted = new Set(values);
  Array.from(select.options).forEach((option) => {
    option.selected = wanted.has(option.value);
  });
}

function uniqueValues(events, key) {
  return [...new Set(events.map((event) => event[key]).filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b))
  );
}

function uniqueSourceValues(events) {
  return [...new Set(events.flatMap((event) => event.allSources).filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b))
  );
}

function cityOptions(events, states) {
  return [
    ...new Set(
      events
        .filter((event) => !states.length || states.includes(event.state))
        .map((event) => event.city)
        .filter(Boolean)
    ),
  ].sort((a, b) => String(a).localeCompare(String(b)));
}

function cityOptionsFromUi(statesSelect) {
  const stateValues = selectedValues(statesSelect);
  return cityOptions(window.__eventsForCities || [], stateValues);
}

function toIsoDate(value) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

function formatDateTime(value, verbose) {
  if (!value) {
    return "TBD";
  }

  const options = verbose
    ? {
        weekday: "short",
        month: "short",
        day: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }
    : {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      };

  return new Intl.DateTimeFormat("en-US", options).format(value);
}

function relativeDateLabel(value) {
  if (!value) {
    return "time unavailable";
  }

  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfValue = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const deltaDays = Math.round((startOfToday - startOfValue) / 86400000);

  if (deltaDays === 0) return "today";
  if (deltaDays === 1) return "1 day ago";
  if (deltaDays > 1) return `${deltaDays} days ago`;
  return value.toISOString().slice(0, 10);
}

function driveLabel(event) {
  return Number.isFinite(event.estimatedDriveMinutes)
    ? `${event.estimatedDriveMinutes} min`
    : "";
}

function sourceSummaryLabel(event) {
  if (!event.allSources.length) {
    return event.source || "";
  }
  if (event.allSources.length === 1) {
    return event.allSources[0];
  }
  return `${event.source} + ${event.allSources.length - 1} more`;
}

function otherSourcesLine(event) {
  const others = event.allSources.filter((source) => source !== event.source);
  if (!others.length) {
    return "";
  }
  return `<p class="card-line muted"><strong>Also listed on:</strong> ${escapeHtml(
    others.join(", ")
  )}</p>`;
}

function startsWithYes(value) {
  return String(value || "").toLowerCase().startsWith("yes");
}

function haversineMiles(lat1, lon1, lat2, lon2) {
  const radiusMiles = 3958.8;
  const toRadians = (value) => (value * Math.PI) / 180;
  const phi1 = toRadians(lat1);
  const phi2 = toRadians(lat2);
  const dPhi = toRadians(lat2 - lat1);
  const dLambda = toRadians(lon2 - lon1);
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * radiusMiles * Math.asin(Math.sqrt(a));
}

function estimateDriveMinutes(airMiles) {
  const roadMiles = airMiles * 1.23;
  const averageSpeed = 39;
  return Math.round((roadMiles / averageSpeed) * 60);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}
