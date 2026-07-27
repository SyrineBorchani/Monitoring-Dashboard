const endpoints = {
  mode: "/api/powerbi/mode",
  indicators: "/api/powerbi/monitoring/indicators?live=false",
  sync: "/api/powerbi/monitoring/sync?refresh_top=10",
  workspaces: "/api/powerbi/storage/workspaces",
  datasets: "/api/powerbi/storage/datasets",
  refreshes: "/api/powerbi/storage/refreshes?limit=12",
  incidents: "/api/powerbi/storage/incidents?limit=10",
};

const ui = {
  capacityIncidents: document.getElementById("capacityIncidents"),
  countStrip: document.getElementById("countStrip"),
  credentialsIncidents: document.getElementById("credentialsIncidents"),
  dataSourceIncidents: document.getElementById("dataSourceIncidents"),
  datasetCards: document.getElementById("datasetCards"),
  environmentBanner: document.getElementById("environmentBanner"),
  environmentDescription: document.getElementById("environmentDescription"),
  environmentMode: document.getElementById("environmentMode"),
  environmentTitle: document.getElementById("environmentTitle"),
  failedDatasets: document.getElementById("failedDatasets"),
  gatewayIncidents: document.getElementById("gatewayIncidents"),
  highlightsGrid: document.getElementById("highlightsGrid"),
  incidentTable: document.getElementById("incidentTable"),
  refreshTable: document.getElementById("refreshTable"),
  reloadButton: document.getElementById("reloadButton"),
  slowDatasets: document.getElementById("slowDatasets"),
  status: document.getElementById("statusMessage"),
  summaryGrid: document.getElementById("summaryGrid"),
  syncButton: document.getElementById("syncButton"),
  workspaceCards: document.getElementById("workspaceCards"),
};

let appMode = "live";

function setStatus(message, isError = false) {
  ui.status.textContent = message;
  ui.status.style.color = isError ? "#b8483b" : "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("fr-FR").format(value ?? 0);
}

function formatRate(value) {
  return `${((value ?? 0) * 100).toFixed(1).replace(".", ",")}%`;
}

function formatDuration(seconds) {
  if (seconds == null) {
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

function translateStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  const labels = {
    completed: "Termine",
    failed: "Echoue",
    unknown: "Non termine",
    cancelled: "Annule",
    disabled: "Desactive",
  };
  return labels[normalized] ?? status ?? "Inconnu";
}

function translateSeverity(severity) {
  const normalized = String(severity ?? "").toLowerCase();
  const labels = {
    high: "Haute",
    haute: "Haute",
    medium: "Moyenne",
    moyenne: "Moyenne",
    low: "Faible",
    faible: "Faible",
  };
  return labels[normalized] ?? severity ?? "Moyenne";
}

function translateIncidentType(incidentType) {
  const labels = {
    FailedRefresh: "Refresh echoue",
    DelayedRefresh: "Refresh en retard",
    DurationAnomaly: "Anomalie de duree",
    RefreshNotExecuted: "Refresh non termine",
    ConsecutiveFailures: "Echecs consecutifs",
  };
  return labels[incidentType] ?? incidentType ?? "Incident";
}

function renderEnvironment(payload) {
  appMode = payload?.mode ?? "live";
  ui.environmentBanner.hidden = false;
  ui.environmentTitle.textContent = payload?.title ?? "Environnement";
  ui.environmentDescription.textContent = payload?.description ?? "";
  ui.environmentMode.textContent = appMode === "demo" ? "DEMO" : "LIVE";
  ui.syncButton.textContent = appMode === "demo"
    ? "Regenerer le snapshot"
    : "Synchroniser le monitoring";
}

function renderCountStrip(modePayload, indicators, workspaces, datasets, refreshes, incidents) {
  const counts = modePayload?.counts ?? {};
  const items = [
    ["Workspaces", counts.workspaces ?? workspaces.length],
    ["Datasets", counts.datasets ?? datasets.length],
    ["Refreshs", counts.refreshes ?? indicators?.totals?.refreshes ?? refreshes.length],
    ["Incidents", counts.incidents ?? indicators?.totals?.incidents ?? incidents.length],
  ];

  ui.countStrip.innerHTML = items.map(([label, value]) => `
    <div class="count-chip">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(formatNumber(value))}</strong>
    </div>
  `).join("");
}

function renderSummary(indicators) {
  if (!indicators) {
    ui.summaryGrid.innerHTML = `<div class="empty-state">Les indicateurs ne sont pas disponibles.</div>`;
    return;
  }

  const totals = indicators.totals ?? {};
  const rates = indicators.rates ?? {};
  const durations = indicators.durations ?? {};
  const cards = [
    ["Nombre total de refreshs", formatNumber(totals.refreshes), `${formatNumber(totals.incidents)} incident(s) detecte(s)`],
    ["Taux de succes", formatRate(rates.successRate), `${formatNumber(totals.successfulRefreshes)} refreshs termines`],
    ["Taux d'echec", formatRate(rates.failureRate), `${formatNumber(totals.failedRefreshes)} refreshs echoues`],
    ["Duree moyenne", formatDuration(durations.averageSeconds), `Pic a ${formatDuration(durations.maximumSeconds)}`],
    ["Refreshs en retard", formatNumber(totals.delayedRefreshes), `Seuil de ${formatDuration(indicators.thresholds?.delayedRefreshSeconds)}`],
    ["Anomalies de duree", formatNumber(totals.durationAnomalies), `Executions non terminees: ${formatNumber(totals.inProgressRefreshes)}`],
  ];

  ui.summaryGrid.innerHTML = cards.map(([label, value, note]) => `
    <article class="metric-card">
      <p class="metric-label">${escapeHtml(label)}</p>
      <p class="metric-value">${escapeHtml(value)}</p>
      <p class="metric-note">${escapeHtml(note)}</p>
    </article>
  `).join("");
}

function topIncidentBySeverity(incidents) {
  const rank = { Haute: 3, Moyenne: 2, Faible: 1 };
  return [...incidents].sort((left, right) => {
    const leftRank = rank[translateSeverity(left.severity)] ?? 0;
    const rightRank = rank[translateSeverity(right.severity)] ?? 0;
    if (leftRank !== rightRank) {
      return rightRank - leftRank;
    }
    return String(right.detectedAt ?? "").localeCompare(String(left.detectedAt ?? ""));
  })[0];
}

function renderHighlights(indicators, refreshes, incidents) {
  const slowestDataset = indicators?.datasets?.slowest?.[0];
  const topFailureDataset = indicators?.datasets?.mostFailures?.[0];
  const topCause = indicators?.incidents?.byCauseType?.[0];
  const criticalIncident = topIncidentBySeverity(incidents);
  const latestRefresh = [...refreshes].sort(
    (left, right) => String(right.startTime ?? "").localeCompare(String(left.startTime ?? "")),
  )[0];

  const cards = [
    {
      title: "Point chaud principal",
      value: slowestDataset?.datasetName ?? "Aucun dataset critique",
      note: slowestDataset
        ? `Duree moyenne ${formatDuration(slowestDataset.averageDurationSeconds)}`
        : "Les donnees de duree ne sont pas disponibles.",
    },
    {
      title: "Cause dominante",
      value: topCause?.causeType ?? "Aucune cause dominante",
      note: topCause ? `${formatNumber(topCause.count)} incidents rattaches` : "Aucun incident a classifier.",
    },
    {
      title: "Dataset le plus expose",
      value: topFailureDataset?.datasetName ?? "Aucun echec remonte",
      note: topFailureDataset
        ? `${formatNumber(topFailureDataset.failureCount)} refresh(s) echoue(s)`
        : "La serie ne contient pas d'echec.",
    },
    {
      title: "Action prioritaire",
      value: criticalIncident?.datasetName ?? latestRefresh?.datasetName ?? "Verifier le mode en cours",
      note: criticalIncident
        ? criticalIncident.recommendation ?? translateIncidentType(criticalIncident.incidentType)
        : latestRefresh
          ? `Dernier refresh: ${translateStatus(latestRefresh.status)}`
          : "Aucune action n'a pu etre derivee.",
    },
  ];

  ui.highlightsGrid.innerHTML = cards.map((card) => `
    <article class="highlight-card">
      <p class="highlight-label">${escapeHtml(card.title)}</p>
      <h3>${escapeHtml(card.value)}</h3>
      <p class="highlight-note">${escapeHtml(card.note)}</p>
    </article>
  `).join("");
}

function buildTable(headers, rows, allowHtml = false) {
  if (!rows.length) {
    return `<div class="empty-state">Aucune ligne disponible pour le moment.</div>`;
  }

  const head = headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("");
  const body = rows.map((row) => `
    <tr>
      ${row.map((cell) => `<td>${allowHtml ? cell : escapeHtml(cell)}</td>`).join("")}
    </tr>
  `).join("");

  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderStatusBadge(status) {
  const normalized = String(status ?? "").toLowerCase();
  let className = "warning";
  if (normalized === "completed") className = "success";
  if (normalized === "failed") className = "failed";
  return `<span class="badge ${className}">${escapeHtml(translateStatus(status))}</span>`;
}

function renderSeverityBadge(severity) {
  const normalized = translateSeverity(severity).toLowerCase();
  let className = "warning";
  if (normalized === "haute") className = "failed";
  if (normalized === "faible") className = "success";
  return `<span class="badge ${className}">${escapeHtml(translateSeverity(severity))}</span>`;
}

function renderWorkspaceCards(workspaces, datasets, refreshes, incidents) {
  if (!workspaces.length) {
    ui.workspaceCards.innerHTML = `<div class="empty-state">Aucun workspace disponible.</div>`;
    return;
  }

  ui.workspaceCards.innerHTML = workspaces.map((workspace) => {
    const workspaceDatasets = datasets.filter((item) => item.workspaceId === workspace.workspaceId);
    const workspaceRefreshes = refreshes.filter((item) => item.workspaceId === workspace.workspaceId);
    const workspaceIncidents = incidents.filter((item) => item.workspaceId === workspace.workspaceId);
    return `
      <article class="info-card">
        <div class="info-card-header">
          <h3>${escapeHtml(workspace.workspaceName ?? workspace.workspaceId)}</h3>
          <span class="mini-pill">${escapeHtml(workspace.capacityMode ?? "Shared")}</span>
        </div>
        <p class="info-card-text">${escapeHtml(workspace.defaultDatasetStorageFormat ?? "N/A")} storage</p>
        <dl class="mini-stats">
          <div><dt>Datasets</dt><dd>${escapeHtml(formatNumber(workspaceDatasets.length))}</dd></div>
          <div><dt>Refreshs</dt><dd>${escapeHtml(formatNumber(workspaceRefreshes.length))}</dd></div>
          <div><dt>Incidents</dt><dd>${escapeHtml(formatNumber(workspaceIncidents.length))}</dd></div>
        </dl>
      </article>
    `;
  }).join("");
}

function renderDatasetCards(datasets, refreshes, incidents) {
  if (!datasets.length) {
    ui.datasetCards.innerHTML = `<div class="empty-state">Aucun dataset disponible.</div>`;
    return;
  }

  const cards = datasets.map((dataset) => {
    const datasetRefreshes = refreshes.filter((item) => item.datasetId === dataset.datasetId);
    const datasetIncidents = incidents.filter((item) => item.datasetId === dataset.datasetId);
    const latestRefresh = [...datasetRefreshes].sort(
      (left, right) => String(right.startTime ?? "").localeCompare(String(left.startTime ?? "")),
    )[0];
    const latestStatus = latestRefresh ? translateStatus(latestRefresh.status) : "N/A";
    return {
      dataset,
      incidents: datasetIncidents.length,
      latestStatus,
      sources: (dataset.dataSourceTypes ?? []).join(", ") || "N/A",
    };
  }).sort((left, right) => right.incidents - left.incidents).slice(0, 4);

  ui.datasetCards.innerHTML = cards.map((card) => `
    <article class="info-card">
      <div class="info-card-header">
        <h3>${escapeHtml(card.dataset.datasetName ?? card.dataset.datasetId)}</h3>
        <span class="mini-pill">${escapeHtml(formatNumber(card.incidents))} incident(s)</span>
      </div>
      <p class="info-card-text">${escapeHtml(card.dataset.workspaceName ?? card.dataset.workspaceId)}</p>
      <p class="info-card-text">Sources: ${escapeHtml(card.sources)}</p>
      <p class="info-card-text">Dernier statut: ${escapeHtml(card.latestStatus)}</p>
    </article>
  `).join("");
}

function renderList(container, items, renderItem) {
  if (!items?.length) {
    container.innerHTML = `<div class="empty-state">Aucune donnee disponible pour le moment.</div>`;
    return;
  }
  container.innerHTML = items.map(renderItem).join("");
}

function renderSlowDatasets(indicators) {
  renderList(
    ui.slowDatasets,
    indicators?.datasets?.slowest ?? [],
    (item) => `
      <article class="list-item">
        <strong>${escapeHtml(item.datasetName ?? item.datasetId)}</strong>
        <p class="list-note">Moyenne ${formatDuration(item.averageDurationSeconds)} | Maximum ${formatDuration(item.maxDurationSeconds)}</p>
        <div class="stat-row">
          <span class="stat-pill">${escapeHtml(formatNumber(item.refreshCount))} refresh(s)</span>
        </div>
      </article>
    `,
  );
}

function renderFailedDatasets(indicators) {
  renderList(
    ui.failedDatasets,
    indicators?.datasets?.mostFailures ?? [],
    (item) => `
      <article class="list-item">
        <strong>${escapeHtml(item.datasetName ?? item.datasetId)}</strong>
        <p class="list-note">${escapeHtml(formatNumber(item.failureCount))} refresh(s) echoue(s)</p>
      </article>
    `,
  );
}

function renderIncidentBreakdowns(indicators) {
  renderList(
    ui.gatewayIncidents,
    indicators?.incidents?.byGateway ?? [],
    (item) => `
      <article class="list-item">
        <strong>${escapeHtml(item.gatewayId ?? "Gateway inconnue")}</strong>
        <p class="list-note">${escapeHtml(formatNumber(item.count))} incident(s)</p>
      </article>
    `,
  );

  renderList(
    ui.capacityIncidents,
    indicators?.incidents?.byCapacity ?? [],
    (item) => `
      <article class="list-item">
        <strong>${escapeHtml(item.capacityId ?? "Capacite partagee")}</strong>
        <p class="list-note">${escapeHtml(formatNumber(item.count))} incident(s)</p>
      </article>
    `,
  );

  const credentialsRelated = indicators?.incidents?.credentialsRelated ?? 0;
  const totalIncidents = indicators?.totals?.incidents ?? 0;
  ui.credentialsIncidents.innerHTML = `
    <div class="metric-chip">
      <span>Incidents credentials</span>
      <strong>${escapeHtml(formatNumber(credentialsRelated))}</strong>
    </div>
    <div class="metric-chip">
      <span>Part dans les incidents</span>
      <strong>${escapeHtml(totalIncidents ? formatRate(credentialsRelated / totalIncidents) : "0,0%")}</strong>
    </div>
  `;

  renderList(
    ui.dataSourceIncidents,
    indicators?.incidents?.byDataSource ?? [],
    (item) => `
      <article class="list-item">
        <strong>${escapeHtml(item.datasourceType ?? "Source inconnue")}</strong>
        <p class="list-note">${escapeHtml(formatNumber(item.count))} incident(s)</p>
      </article>
    `,
  );
}

function renderRefreshTable(refreshes) {
  const rows = refreshes.map((item) => [
    item.datasetName ?? item.datasetId,
    item.workspaceName ?? item.workspaceId,
    renderStatusBadge(item.status),
    formatDuration(item.durationSeconds),
    formatTimestamp(item.startTime),
    item.errorCode ?? item.errorMessage ?? "Aucune erreur",
  ]);

  ui.refreshTable.innerHTML = buildTable(
    ["Dataset", "Workspace", "Statut", "Duree", "Debut", "Detail"],
    rows,
    true,
  );
}

function renderIncidentTable(incidents) {
  const rows = incidents.map((item) => [
    translateIncidentType(item.incidentType),
    item.datasetName ?? item.datasetId,
    renderSeverityBadge(item.severity),
    item.suspectedCause ?? "N/A",
    formatTimestamp(item.detectedAt),
    item.recommendation ?? "N/A",
  ]);

  ui.incidentTable.innerHTML = buildTable(
    ["Incident", "Dataset", "Severite", "Cause", "Detection", "Recommandation"],
    rows,
    true,
  );
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

function renderEmptyDashboard(message) {
  ui.countStrip.innerHTML = "";
  ui.summaryGrid.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  ui.highlightsGrid.innerHTML = `<div class="empty-state">Aucun point cle ne peut etre calcule.</div>`;
  ui.workspaceCards.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.datasetCards.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.slowDatasets.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.failedDatasets.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.gatewayIncidents.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.capacityIncidents.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.credentialsIncidents.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.dataSourceIncidents.innerHTML = `<div class="empty-state">Aucune donnee a afficher.</div>`;
  ui.refreshTable.innerHTML = `<div class="empty-state">Aucun refresh a afficher.</div>`;
  ui.incidentTable.innerHTML = `<div class="empty-state">Aucun incident a afficher.</div>`;
}

async function loadDashboard() {
  setStatus("Chargement du tableau de bord PoC...");

  try {
    const modePayload = await fetchJson(endpoints.mode);
    renderEnvironment(modePayload);

    const results = await Promise.allSettled([
      fetchJson(endpoints.indicators),
      fetchJson(endpoints.workspaces),
      fetchJson(endpoints.datasets),
      fetchJson(endpoints.refreshes),
      fetchJson(endpoints.incidents),
    ]);

    const indicators = fulfilledValue(results[0]);
    const workspaces = fulfilledValue(results[1])?.value ?? [];
    const datasets = fulfilledValue(results[2])?.value ?? [];
    const refreshes = fulfilledValue(results[3])?.value ?? [];
    const incidents = fulfilledValue(results[4])?.value ?? [];
    const errors = [
      resultError("Indicateurs", results[0]),
      resultError("Workspaces", results[1]),
      resultError("Datasets", results[2]),
      resultError("Refreshs", results[3]),
      resultError("Incidents", results[4]),
    ].filter(Boolean);

    renderCountStrip(modePayload, indicators, workspaces, datasets, refreshes, incidents);
    renderSummary(indicators);
    renderHighlights(indicators, refreshes, incidents);
    renderWorkspaceCards(workspaces, datasets, refreshes, incidents);
    renderDatasetCards(datasets, refreshes, incidents);
    renderSlowDatasets(indicators);
    renderFailedDatasets(indicators);
    renderIncidentBreakdowns(indicators);
    renderRefreshTable(refreshes);
    renderIncidentTable(incidents);

    if (errors.length) {
      setStatus(`Chargement partiel: ${errors.length} source(s) indisponible(s).`, true);
    } else {
      setStatus(
        `Chargement termine: ${formatNumber(refreshes.length)} refresh(s), ${formatNumber(incidents.length)} incident(s), ${formatNumber(datasets.length)} dataset(s).`
      );
    }
  } catch (error) {
    console.error(error);
    renderEnvironment({
      mode: "unknown",
      title: "Dashboard indisponible",
      description: "Impossible de charger le mode d'execution du service.",
    });
    renderEmptyDashboard("Le service n'a pas repondu correctement.");
    setStatus(`Echec du chargement du dashboard: ${error.message}`, true);
  }
}

async function syncMonitoring() {
  ui.syncButton.disabled = true;
  try {
    setStatus(appMode === "demo"
      ? "Regeneration du snapshot ..."
      : "Synchronisation du monitoring en cours...");
    const result = await fetchJson(endpoints.sync, { method: "POST" });
    setStatus(
      `Synchronisation terminee: ${formatNumber(result.counts?.workspaces)} workspaces, ${formatNumber(result.counts?.datasets)} datasets, ${formatNumber(result.counts?.refreshes)} refreshs.`
    );
    await loadDashboard();
  } catch (error) {
    console.error(error);
    setStatus(`La synchronisation a echoue: ${error.message}`, true);
  } finally {
    ui.syncButton.disabled = false;
  }
}

ui.syncButton.addEventListener("click", syncMonitoring);
ui.reloadButton.addEventListener("click", loadDashboard);

loadDashboard();
