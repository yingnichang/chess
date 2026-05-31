(() => {
  const configScript =
    document.currentScript ||
    document.querySelector("script[data-analytics-provider]");
  const chip = document.getElementById("visitor-count-chip");
  const countTarget = document.getElementById("visitor-count");

  if (!configScript || !chip || !countTarget) {
    return;
  }

  const provider = cleanConfigValue(configScript.dataset.analyticsProvider);
  const site = cleanConfigValue(configScript.dataset.analyticsSite);

  if (!provider || provider === "none" || !site) {
    return;
  }

  if (provider !== "goatcounter") {
    return;
  }

  const baseUrl = goatCounterBaseUrl(site);
  if (!baseUrl) {
    return;
  }

  chip.classList.remove("hidden");
  countTarget.textContent = "Loading...";

  if (isLocalPreview()) {
    countTarget.textContent = "Preview mode";
    return;
  }

  loadGoatCounter(baseUrl);
  updateGoatCounterTotal(baseUrl, countTarget);
})();

function cleanConfigValue(value) {
  const text = String(value || "").trim();
  if (!text || text.startsWith("__")) {
    return "";
  }
  return text.toLowerCase();
}

function goatCounterBaseUrl(site) {
  if (/^https:\/\/[a-z0-9-]+\.goatcounter\.com$/i.test(site)) {
    return site.replace(/\/$/, "");
  }

  if (/^[a-z0-9-]+$/i.test(site)) {
    return `https://${site}.goatcounter.com`;
  }

  return "";
}

function isLocalPreview() {
  return ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
}

function loadGoatCounter(baseUrl) {
  window.goatcounter = window.goatcounter || {};

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://gc.zgo.at/count.js";
  script.dataset.goatcounter = `${baseUrl}/count`;
  document.head.appendChild(script);
}

async function updateGoatCounterTotal(baseUrl, countTarget) {
  try {
    const response = await fetch(`${baseUrl}/counter/TOTAL.json`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error("Could not load visitor count.");
    }

    const payload = await response.json();
    const count = Number(payload.count);
    countTarget.textContent = Number.isFinite(count)
      ? count.toLocaleString()
      : "Tracking";
  } catch {
    countTarget.textContent = "Tracking";
  }
}
