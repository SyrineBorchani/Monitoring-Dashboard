const endpoints = {
  indicators: "/api/powerbi/monitoring/indicators?live=false",
  datasets: "/api/powerbi/storage/datasets",
  fabricExecutions: "/api/powerbi/storage/fabric/executions?limit=40",
  fabricItems: "/api/powerbi/storage/fabric/items",
  fabricSqlExecutions: "/api/powerbi/storage/fabric/sql-executions?limit=40",
  incidents: "/api/powerbi/storage/incidents?limit=30",
  reports: "/api/powerbi/reports",
  refreshes: "/api/powerbi/storage/refreshes?limit=",
  sync: "/api/powerbi/monitoring/sync?refresh_top=10",
  workspaces: "/api/powerbi/storage/workspaces",
};

const viewLabels = {
  indicators: "Indicateurs",
  performance: "Performance",
  fabric: "Fabric",
  incidents: "Incidents",
};

const ui = {
  heroMeta: document.getElementById("heroMeta"),
  highlightsGrid: document.getElementById("highlightsGrid"),
  navLinks: Array.from(document.querySelectorAll("[data-view-target]")),
  reloadButton: document.getElementById("reloadButton"),
  status: document.getElementById("statusMessage"),
  summaryGrid: document.getElementById("summaryGrid"),
  syncButton: document.getElementById("syncButton"),
  viewPanels: Array.from(document.querySelectorAll("[data-view-panel]")),
  workspaceCards: document.getElementById("workspaceCards"),
};

let refreshLimit = 12;
const refreshStep = 12;
let isLoadingDashboard = false;

function ensureBridge(name) {
  const bridge = window[name] || {};
  bridge.current = bridge.current ?? null;
  window[name] = bridge;
  return bridge;
}

const panelsBridge = ensureBridge("dashboardPanels");

function setStatus(message, isError = false) {
  ui.status.textContent = message;
  ui.status.classList.toggle("is-error", isError);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeFrenchText(value) {
  return String(value ?? "");
}

function formatNumber(value) {
  return new Intl.NumberFormat("fr-FR").format(Number(value ?? 0));
}

function formatRate(value) {
  return `${(Number(value ?? 0) * 100).toFixed(1).replace(".", ",")}%`;
}

function formatDuration(value) {
  if (value == null) {
    return "N/A";
  }
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) {
    return "N/A";
  }
  if (seconds >= 3600) {
    return `${(seconds / 3600).toFixed(2).replace(".", ",")} h`;
  }
  if (seconds >= 60) {
    return `${(seconds / 60).toFixed(1).replace(".", ",")} min`;
  }
  return `${seconds.toFixed(0)} s`;
}

function formatTimestamp(value) {
  if (!value) {
    return "N/A";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatShortDate(value) {
  if (!value) {
    return "N/A";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
  });
}

function clampPercent(value) {
  return Math.max(6, Math.min(100, Number(value ?? 0)));
}

function toPercent(value, maxValue) {
  const safeMax = Math.max(Number(maxValue ?? 0), 1);
  return (Number(value ?? 0) / safeMax) * 100;
}

function translateCause(cause) {
  const normalized = String(cause ?? "").toLowerCase();
  const labels = {
    credentials: "Identifiants",
    gateway: "Gateway",
    "source de donnees": "Source de donn\u00e9es",
    capacite: "Capacit\u00e9",
    "modele semantique": "Mod\u00e8le s\u00e9mantique",
    planification: "Planification",
    "power query": "Power Query",
  };
  return labels[normalized] ?? normalizeFrenchText(cause ?? "Cause inconnue");
}

function renderEmptyState(message) {
  return `<div class="empty-state">${escapeHtml(normalizeFrenchText(message))}</div>`;
}

function activateView(viewName) {
  const nextView = viewLabels[viewName] ? viewName : "indicators";
  ui.navLinks.forEach((link) => {
    link.classList.toggle("is-active", link.dataset.viewTarget === nextView);
  });
  ui.viewPanels.forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.viewPanel === nextView);
  });
}

function activateViewFromHash() {
  activateView(window.location.hash.replace("#", "") || "indicators");
}

function renderSummary(indicators) {
  if (!indicators) {
    ui.summaryGrid.innerHTML = renderEmptyState("Les indicateurs ne sont pas disponibles.");
    return;
  }

  const totals = indicators.totals ?? {};
  const rates = indicators.rates ?? {};
  const durations = indicators.durations ?? {};
  const maxDuration = Math.max(
    durations.maximumSeconds ?? 0,
    indicators.thresholds?.delayedRefreshSeconds ?? 0,
    1,
  );

  const cards = [
    {
      label: "Nombre total de refreshs",
      value: formatNumber(totals.refreshes),
      note: `${formatNumber(totals.incidents)} incident(s) d\u00e9tect\u00e9(s)`,
      percent: 100,
    },
    {
      label: "Taux de succ\u00e8s",
      value: formatRate(rates.successRate),
      note: `${formatNumber(totals.successfulRefreshes)} refreshs termin\u00e9s`,
      percent: (rates.successRate ?? 0) * 100,
    },
    {
      label: "Taux d'\u00e9chec",
      value: formatRate(rates.failureRate),
      note: `${formatNumber(totals.failedRefreshes)} refreshs \u00e9chou\u00e9s`,
      percent: (rates.failureRate ?? 0) * 100,
    },
    {
      label: "Dur\u00e9e moyenne des refreshs",
      value: formatDuration(durations.averageSeconds),
      note: "Moyenne calcul\u00e9e sur l'historique",
      percent: toPercent(durations.averageSeconds, maxDuration),
    },
    {
      label: "Dur\u00e9e maximale des refreshs",
      value: formatDuration(durations.maximumSeconds),
      note: "Pic de dur\u00e9e observ\u00e9",
      percent: toPercent(durations.maximumSeconds, maxDuration),
    },
    {
      label: "Refreshs en retard",
      value: formatNumber(totals.delayedRefreshes),
      note: `Seuil ${formatDuration(indicators.thresholds?.delayedRefreshSeconds)}`,
      percent: totals.refreshes ? toPercent(totals.delayedRefreshes, totals.refreshes) : 0,
    },
  ];

  ui.summaryGrid.innerHTML = cards.map((card) => `
    <article class="metric-card">
      <span class="metric-label">${escapeHtml(card.label)}</span>
      <p class="metric-value">${escapeHtml(card.value)}</p>
      <p class="metric-note">${escapeHtml(card.note)}</p>
      <div class="metric-meter"><span style="width:${clampPercent(card.percent)}%"></span></div>
    </article>
  `).join("");
}

function renderHighlights(indicators) {
  if (!indicators) {
    ui.highlightsGrid.innerHTML = renderEmptyState("Les points essentiels ne sont pas disponibles.");
    return;
  }

  const slowestDataset = indicators.datasets?.slowest?.[0];
  const failedDataset = indicators.datasets?.mostFailures?.[0];
  const topCause = indicators.incidents?.byCauseType?.[0];
  const totals = indicators.totals ?? {};

  const cards = [
    {
      label: "Anomalies de dur\u00e9e",
      value: formatNumber(totals.durationAnomalies),
      note: `${formatNumber(totals.inProgressRefreshes)} refresh(s) non termin\u00e9(s)`,
    },
    {
      label: "Dataset le plus lent",
      value: slowestDataset?.datasetName ?? "Aucun dataset",
      note: slowestDataset
        ? `Moyenne ${formatDuration(slowestDataset.averageDurationSeconds)}`
        : "Aucune mesure disponible",
    },
    {
      label: "Dataset avec le plus d'\u00e9checs",
      value: failedDataset?.datasetName ?? "Aucun dataset",
      note: failedDataset
        ? `${formatNumber(failedDataset.failureCount)} \u00e9chec(s)`
        : "Aucune mesure disponible",
    },
    {
      label: "Cause la plus fr\u00e9quente",
      value: translateCause(topCause?.causeType ?? "Aucune cause"),
      note: topCause ? `${formatNumber(topCause.count)} incident(s)` : "Aucun incident class\u00e9",
    },
  ];

  ui.highlightsGrid.innerHTML = cards.map((card) => `
    <article class="highlight-card">
      <span class="highlight-label">${escapeHtml(card.label)}</span>
      <h4>${escapeHtml(card.value)}</h4>
      <p class="highlight-note">${escapeHtml(card.note)}</p>
    </article>
  `).join("");
}

function renderWorkspaceCards(workspaces, refreshes, incidents) {
  if (!workspaces.length) {
    ui.workspaceCards.innerHTML = renderEmptyState("Aucun workspace disponible pour le moment.");
    return;
  }

  ui.workspaceCards.innerHTML = workspaces.map((workspace) => {
    const workspaceRefreshes = refreshes.filter(
      (item) => item.workspaceId === workspace.id || item.workspaceId === workspace.workspaceId,
    );
    const workspaceIncidents = incidents.filter(
      (item) => item.workspaceId === workspace.id || item.workspaceId === workspace.workspaceId,
    );
    const failedCount = workspaceRefreshes.filter(
      (item) => String(item.status ?? "").toLowerCase() === "failed",
    ).length;
    const workspaceName = workspace.name ?? workspace.workspaceName ?? workspace.id ?? workspace.workspaceId ?? "Workspace";
    const capacityMode = workspace.capacityMode ?? (workspace.is_on_dedicated_capacity ? "Dedicated" : "Shared");
    const workspaceType = workspace.workspaceType ?? workspace.type ?? "Workspace";

    return `
      <article class="workspace-card">
        <span class="highlight-label">${escapeHtml(workspaceType)}</span>
        <h4>${escapeHtml(workspaceName)}</h4>
        <p class="workspace-meta">${escapeHtml(capacityMode)}</p>
        <div class="workspace-stats">
          <span class="stat-pill">${escapeHtml(formatNumber(workspaceRefreshes.length))} refresh(s)</span>
          <span class="stat-pill">${escapeHtml(formatNumber(failedCount))} \u00e9chec(s)</span>
          <span class="stat-pill">${escapeHtml(formatNumber(workspaceIncidents.length))} incident(s)</span>
        </div>
      </article>
    `;
  }).join("");
}

function renderHeroMeta(indicators, workspaces, refreshes) {
  if (!indicators) {
    ui.heroMeta.innerHTML = "";
    return;
  }

  const totals = indicators.totals ?? {};
  const latestRefresh = [...refreshes]
    .sort((left, right) => String(right.startTime ?? "").localeCompare(String(left.startTime ?? "")))[0];

  const pills = [
    {
      value: formatNumber(totals.refreshes),
      label: "refreshs historis\u00e9s",
    },
    {
      value: formatNumber(workspaces.length),
      label: "workspaces suivis",
    },
    {
      value: formatNumber(totals.incidents),
      label: "incidents monitor\u00e9s",
    },
  ];

  if (latestRefresh?.startTime) {
    pills.push({
      value: formatShortDate(latestRefresh.startTime),
      label: "dernier refresh visible",
    });
  }

  ui.heroMeta.innerHTML = pills.map((item) => `
    <div class="hero-pill">
      <strong>${escapeHtml(item.value)}</strong>
      <span>${escapeHtml(item.label)}</span>
    </div>
  `).join("");
}

function normalizeCollection(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }
  return payload?.value ?? [];
}

function updateReactIslands(payload) {
  if (window.dashboardGraphs?.update) {
    window.dashboardGraphs.update(payload
      ? {
        ...(payload.indicators ?? {}),
        datasets: payload.datasets ?? [],
        fabricExecutions: payload.fabricExecutions ?? [],
        fabricItems: payload.fabricItems ?? [],
        fabricSqlExecutions: payload.fabricSqlExecutions ?? [],
        incidents: payload.incidents ?? [],
        reports: payload.reports ?? [],
        refreshes: payload.refreshes ?? [],
      }
      : null);
  }
  panelsBridge.current = payload;
  if (typeof panelsBridge.update === "function") {
    panelsBridge.update(payload);
  }
}

function renderEmptyDashboard(message) {
  ui.heroMeta.innerHTML = "";
  ui.summaryGrid.innerHTML = renderEmptyState(message);
  ui.highlightsGrid.innerHTML = renderEmptyState("Aucune synth\u00e8se disponible.");
  ui.workspaceCards.innerHTML = renderEmptyState("Aucun workspace disponible.");
  updateReactIslands({
    datasets: [],
    fabricExecutions: [],
    fabricItems: [],
    fabricSqlExecutions: [],
    indicators: null,
    incidents: [],
    reports: [],
    refreshes: [],
    totalRefreshes: 0,
    workspaces: [],
  });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function fulfilledValue(result) {
  return result.status === "fulfilled" ? result.value : null;
}

function resultError(label, result) {
  if (result.status !== "rejected") {
    return null;
  }
  return `${label}: ${result.reason?.message ?? "erreur inconnue"}`;
}

async function loadDashboard() {
  if (isLoadingDashboard) {
    return;
  }

  isLoadingDashboard = true;
  panelsBridge.isLoadingMore = false;
  ui.reloadButton.disabled = true;
  setStatus("Chargement des indicateurs de monitoring...");

  try {
    const results = await Promise.allSettled([
      fetchJson(endpoints.indicators),
      fetchJson(endpoints.incidents),
      fetchJson(`${endpoints.refreshes}${refreshLimit}`),
      fetchJson(endpoints.workspaces),
      fetchJson(endpoints.datasets),
      fetchJson(endpoints.reports),
      fetchJson(endpoints.fabricItems),
      fetchJson(endpoints.fabricExecutions),
      fetchJson(endpoints.fabricSqlExecutions),
    ]);

    const indicators = fulfilledValue(results[0]);
    const incidents = normalizeCollection(fulfilledValue(results[1]));
    const refreshes = normalizeCollection(fulfilledValue(results[2]));
    const workspaces = normalizeCollection(fulfilledValue(results[3]));
    const datasets = normalizeCollection(fulfilledValue(results[4]));
    const reports = normalizeCollection(fulfilledValue(results[5]));
    const fabricItems = normalizeCollection(fulfilledValue(results[6]));
    const fabricExecutions = normalizeCollection(fulfilledValue(results[7]));
    const fabricSqlExecutions = normalizeCollection(fulfilledValue(results[8]));
    const totalRefreshes = Number(indicators?.totals?.refreshes ?? refreshes.length);
    const errors = [
      resultError("Indicateurs", results[0]),
      resultError("Incidents", results[1]),
      resultError("Refreshs", results[2]),
      resultError("Workspaces", results[3]),
      resultError("Datasets", results[4]),
      resultError("Rapports", results[5]),
      resultError("Items Fabric", results[6]),
      resultError("Ex\u00e9cutions Fabric", results[7]),
      resultError("SQL Fabric", results[8]),
    ].filter(Boolean);

    renderSummary(indicators);
    renderHighlights(indicators);
    renderHeroMeta(indicators, workspaces, refreshes);
    renderWorkspaceCards(workspaces, refreshes, incidents);
    updateReactIslands({
      datasets,
      fabricExecutions,
      fabricItems,
      fabricSqlExecutions,
      indicators,
      incidents,
      reports,
      refreshes,
      totalRefreshes,
      workspaces,
    });

    if (errors.length) {
      setStatus(`Chargement partiel : ${errors.length} source(s) indisponible(s).`, true);
    } else {
      setStatus("Chargement termin\u00e9.");
    }
  } catch (error) {
    console.error(error);
    renderEmptyDashboard("Le service n'a pas r\u00e9pondu correctement.");
    setStatus(`\u00c9chec du chargement du dashboard : ${error.message}`, true);
  } finally {
    isLoadingDashboard = false;
    panelsBridge.isLoadingMore = false;
    ui.reloadButton.disabled = false;
  }
}

async function syncMonitoring() {
  ui.syncButton.disabled = true;
  try {
    setStatus("Synchronisation du monitoring en cours...");
    await fetchJson(endpoints.sync, { method: "POST" });
    await loadDashboard();
  } catch (error) {
    console.error(error);
    setStatus(`La synchronisation a \u00e9chou\u00e9 : ${error.message}`, true);
  } finally {
    ui.syncButton.disabled = false;
  }
}

panelsBridge.requestMore = async function requestMoreRefreshes() {
  if (isLoadingDashboard) {
    return;
  }
  panelsBridge.isLoadingMore = true;
  refreshLimit += refreshStep;
  await loadDashboard();
};

ui.navLinks.forEach((link) => {
  link.addEventListener("click", () => {
    const target = link.dataset.viewTarget ?? "indicators";
    if (window.location.hash.replace("#", "") !== target) {
      window.location.hash = target;
      return;
    }
    activateView(target);
  });
});

window.addEventListener("hashchange", activateViewFromHash);
ui.syncButton.addEventListener("click", syncMonitoring);
ui.reloadButton.addEventListener("click", loadDashboard);

activateViewFromHash();
loadDashboard();
