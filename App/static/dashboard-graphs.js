(function bootstrapDashboardReact() {
  if (!window.React || !window.ReactDOM) {
    return;
  }

  const {
    Fragment,
    createElement: h,
    useDeferredValue,
    useEffect,
    useMemo,
    useState,
  } = window.React;

  function createBridge(name) {
    const bridge = window[name] || {};
    bridge.current = bridge.current ?? null;
    bridge.listeners = bridge.listeners || new Set();
    bridge.subscribe = function subscribe(listener) {
      bridge.listeners.add(listener);
      return function unsubscribe() {
        bridge.listeners.delete(listener);
      };
    };
    bridge.update = function update(nextPayload) {
      bridge.current = nextPayload;
      bridge.listeners.forEach((listener) => listener(nextPayload));
    };
    window[name] = bridge;
    return bridge;
  }

  const graphsBridge = createBridge("dashboardGraphs");
  const panelsBridge = createBridge("dashboardPanels");
  const SQL_SLOW_FACTOR = 1.5;
  const HIGH_SQL_VARIANCE_COEFFICIENT_THRESHOLD = 1.0;

  function useBridgePayload(bridge) {
    const [payload, setPayload] = useState(bridge.current);

    useEffect(() => {
      setPayload(bridge.current);
      return bridge.subscribe(setPayload);
    }, [bridge]);

    return payload;
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("fr-FR").format(Number(value ?? 0));
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

  function formatSqlDuration(value) {
    if (value == null) {
      return "N/A";
    }
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) {
      return "N/A";
    }
    if (seconds < 1) {
      return `${Math.round(seconds * 1000)} ms`;
    }
    return formatDuration(seconds);
  }

  function formatRate(value) {
    return `${(Number(value ?? 0) * 100).toFixed(1).replace(".", ",")}%`;
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

  function formatDateKey(value) {
    if (!value) {
      return "";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "";
    }
    return parsed.toISOString().slice(0, 10);
  }

  function parseDateKey(value) {
    if (!value) {
      return null;
    }
    const parsed = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return parsed;
  }

  function shiftDateKey(value, offsetDays) {
    const parsed = parseDateKey(value);
    if (!parsed) {
      return value;
    }
    parsed.setUTCDate(parsed.getUTCDate() + offsetDays);
    return parsed.toISOString().slice(0, 10);
  }

  function enumerateDateKeys(fromDate, toDate) {
    if (!fromDate || !toDate || fromDate > toDate) {
      return [];
    }
    const keys = [];
    let cursor = fromDate;
    while (cursor <= toDate) {
      keys.push(cursor);
      cursor = shiftDateKey(cursor, 1);
    }
    return keys;
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

  function translateStatus(status) {
    const normalized = String(status ?? "").toLowerCase();
    const labels = {
      completed: "Termin\u00e9",
      failed: "\u00c9chou\u00e9",
      inprogress: "En cours",
      notstarted: "Non d\u00e9marr\u00e9",
      unknown: "En attente",
      cancelled: "Annul\u00e9",
      canceled: "Annul\u00e9",
      succeeded: "Termin\u00e9",
      deduped: "D\u00e9dupliqu\u00e9",
      disabled: "D\u00e9sactiv\u00e9",
    };
    return labels[normalized] ?? status ?? "Inconnu";
  }

  function extractEmbeddedErrorCode(rawMessage) {
    if (!rawMessage) {
      return "";
    }
    const text = String(rawMessage);
    const directMatch = text.match(/DMTS_[A-Za-z0-9_]+/);
    if (directMatch) {
      return directMatch[0];
    }
    try {
      const parsed = JSON.parse(text);
      return (
        parsed?.error?.code
        || parsed?.["pbi.error"]?.code
        || parsed?.error?.["pbi.error"]?.code
        || ""
      );
    } catch (error) {
      return "";
    }
  }

  function humanizeErrorCode(code) {
    if (!code) {
      return "Erreur de refresh";
    }
    return String(code)
      .replace(/^ModelRefresh_/, "")
      .replace(/^DMTS_/, "")
      .replace(/_/g, " ")
      .trim();
  }

  function describeRefreshError(item) {
    const rawCode = String(item?.errorCode ?? "").trim();
    const rawMessage = String(item?.errorMessage ?? "").trim();
    const embeddedCode = extractEmbeddedErrorCode(rawMessage);
    const normalizedCode = rawCode === "ModelRefresh_ShortMessage_ProcessingError" && embeddedCode
      ? embeddedCode
      : (rawCode || embeddedCode);

    const knownErrors = {
      DMTS_OAuthFailedToGetResourceIdError: {
        title: "Auth source impossible",
        message: "Impossible de r\u00e9cup\u00e9rer l'authentification de la source.",
      },
      GatewayTimeout: {
        title: "Gateway indisponible",
        message: "La gateway a mis trop de temps \u00e0 r\u00e9pondre.",
      },
      DM_GWPipeline_Gateway_MashupDataAccessError: {
        title: "Acc\u00e8s source refus\u00e9",
        message: "Power BI ne peut pas lire la source via la gateway.",
      },
      ModelRefreshFailed_CredentialsNotSpecified: {
        title: "Identifiants manquants",
        message: "Les identifiants de la source doivent \u00eatre renseign\u00e9s.",
      },
      ModelRefreshFailed_CredentialsInvalid: {
        title: "Identifiants invalides",
        message: "Les identifiants de la source ne sont plus valides.",
      },
    };

    if (!normalizedCode && !rawMessage) {
      return {
        title: "Aucune erreur",
        message: item?.refreshType || "Ex\u00e9cution standard",
      };
    }

    if (knownErrors[normalizedCode]) {
      return knownErrors[normalizedCode];
    }

    if (rawMessage && !rawMessage.startsWith("{")) {
      const compactMessage = rawMessage.length > 120
        ? `${rawMessage.slice(0, 117).trim()}...`
        : rawMessage;
      return {
        title: humanizeErrorCode(normalizedCode || rawCode),
        message: compactMessage,
      };
    }

    return {
      title: humanizeErrorCode(normalizedCode || rawCode),
      message: "Voir le d\u00e9tail technique dans Power BI si n\u00e9cessaire.",
    };
  }

  function translateIncidentType(incidentType) {
    const labels = {
      FailedRefresh: "Refresh \u00e9chou\u00e9",
      DelayedRefresh: "Refresh en retard",
      DurationAnomaly: "Anomalie de dur\u00e9e",
      RefreshNotExecuted: "Refresh non ex\u00e9cut\u00e9",
      ConsecutiveFailures: "\u00c9checs cons\u00e9cutifs",
    };
    return labels[incidentType] ?? incidentType ?? "Incident";
  }

  function translateCause(cause) {
    const normalized = String(cause ?? "").toLowerCase();
    const labels = {
      credentials: "Identifiants",
      identifiants: "Identifiants",
      gateway: "Gateway",
      "source de donnees": "Source de donn\u00e9es",
      capacite: "Capacit\u00e9",
      "modele semantique": "Mod\u00e8le s\u00e9mantique",
      planification: "Planification",
      "power query": "Power Query",
    };
    return labels[normalized] ?? cause ?? "Cause inconnue";
  }

  function normalizeCauseKey(cause) {
    return translateCause(cause)
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
  }

  function classifySeverity(severity) {
    const normalized = translateSeverity(severity).toLowerCase();
    if (normalized === "haute") {
      return "failed";
    }
    if (normalized === "faible") {
      return "success";
    }
    return "warning";
  }

  function classifyStatus(status) {
    const normalized = String(status ?? "").toLowerCase();
    if (normalized === "completed" || normalized === "succeeded") {
      return "success";
    }
    if (normalized === "failed") {
      return "failed";
    }
    return "warning";
  }

  function translateFabricItemType(itemType) {
    const labels = {
      Warehouse: "Warehouse",
      Lakehouse: "Lakehouse",
    };
    return labels[itemType] ?? itemType ?? "Item Fabric";
  }

  function filterTimedItems(items, getDateKey, fromDate, toDate) {
    return items
      .filter((item) => {
        const dateKey = getDateKey(item);
        if (!dateKey) {
          return false;
        }
        if (fromDate && dateKey < fromDate) {
          return false;
        }
        if (toDate && dateKey > toDate) {
          return false;
        }
        return true;
      })
      .sort((left, right) => {
        const leftTime = new Date(getDateKey(left) || 0).getTime();
        const rightTime = new Date(getDateKey(right) || 0).getTime();
        return rightTime - leftTime;
      });
  }

  function buildStoredProcedureLeaders(sqlExecutions) {
    const groups = new Map();

    sqlExecutions.forEach((item) => {
      if (!item.isStoredProcedure) {
        return;
      }
      const name = item.procedureName || item.command || "Proc\u00e9dure";
      if (!groups.has(name)) {
        groups.set(name, {
          procedureName: name,
          averageDurationSeconds: 0,
          executionCount: 0,
          latestItemName: item.itemName,
          maximumDurationSeconds: 0,
        });
      }
      const current = groups.get(name);
      const duration = Number(item.durationSeconds ?? 0);
      current.executionCount += 1;
      current.averageDurationSeconds += duration;
      current.maximumDurationSeconds = Math.max(current.maximumDurationSeconds, duration);
      current.latestItemName = item.itemName || current.latestItemName;
    });

    return [...groups.values()]
      .map((item) => ({
        ...item,
        averageDurationSeconds: item.executionCount
          ? item.averageDurationSeconds / item.executionCount
          : 0,
      }))
      .sort((left, right) => right.averageDurationSeconds - left.averageDurationSeconds);
  }

  function normalizeStatementType(statementType) {
    const normalized = String(statementType ?? "").trim().toUpperCase();
    return normalized || "UNKNOWN";
  }

  function computeMedian(values) {
    if (!values.length) {
      return null;
    }
    const sorted = [...values].sort((left, right) => left - right);
    const middle = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 0) {
      return (sorted[middle - 1] + sorted[middle]) / 2;
    }
    return sorted[middle];
  }

  function roundMetric(value) {
    if (value == null || Number.isNaN(Number(value))) {
      return null;
    }
    return Math.round(Number(value) * 100) / 100;
  }

  function buildFabricSqlStatementGroups(sqlExecutions) {
    const groups = new Map();

    sqlExecutions.forEach((item) => {
      const key = normalizeStatementType(item.statementType);
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key).push(item);
    });

    return [...groups.entries()]
      .map(([statementType, executions]) => {
        const durations = executions
          .map((item) => Number(item.durationSeconds))
          .filter((value) => Number.isFinite(value));
        const averageDurationSeconds = durations.length
          ? durations.reduce((total, value) => total + value, 0) / durations.length
          : null;
        const medianDurationSeconds = computeMedian(durations);
        const varianceSeconds = durations.length > 1 && averageDurationSeconds != null
          ? durations.reduce(
            (total, value) => total + ((value - averageDurationSeconds) ** 2),
            0,
          ) / durations.length
          : 0;
        const varianceCoefficient = averageDurationSeconds
          ? Math.sqrt(varianceSeconds) / averageDurationSeconds
          : 0;
        const baselineMethod = durations.length > 1 && varianceCoefficient >= HIGH_SQL_VARIANCE_COEFFICIENT_THRESHOLD
          ? "average"
          : "median";
        const baselineDurationSeconds = baselineMethod === "average"
          ? averageDurationSeconds
          : medianDurationSeconds;
        const slowThresholdSeconds = baselineDurationSeconds != null
          ? baselineDurationSeconds * SQL_SLOW_FACTOR
          : null;
        const slowExecutionCount = durations.filter(
          (value) => slowThresholdSeconds != null && value > slowThresholdSeconds,
        ).length;
        const latestExecution = [...executions].sort(
          (left, right) => String(right.startTime ?? "").localeCompare(String(left.startTime ?? "")),
        )[0];

        return {
          statementType,
          executionCount: executions.length,
          averageDurationSeconds: roundMetric(averageDurationSeconds),
          medianDurationSeconds: roundMetric(medianDurationSeconds),
          varianceSeconds: roundMetric(varianceSeconds),
          varianceCoefficient: roundMetric(varianceCoefficient),
          baselineMethod,
          baselineDurationSeconds: roundMetric(baselineDurationSeconds),
          slowThresholdSeconds: roundMetric(slowThresholdSeconds),
          slowExecutionCount,
          maximumDurationSeconds: roundMetric(
            durations.length ? Math.max(...durations) : null,
          ),
          lastSeenAt: latestExecution?.startTime || latestExecution?.endTime || "",
          programNames: [...new Set(
            executions
              .map((item) => String(item.programName ?? "").trim())
              .filter(Boolean),
          )].sort(),
        };
      })
      .sort((left, right) => (
        Number(right.slowExecutionCount ?? 0) - Number(left.slowExecutionCount ?? 0)
        || Number(right.executionCount ?? 0) - Number(left.executionCount ?? 0)
        || Number(right.maximumDurationSeconds ?? 0) - Number(left.maximumDurationSeconds ?? 0)
        || String(left.statementType ?? "").localeCompare(String(right.statementType ?? ""))
      ));
  }

  function labelBaselineMethod(method) {
    return method === "average" ? "moyenne" : "m\u00e9diane";
  }

  function describeSqlExecutionAnomaly(execution, group) {
    const duration = Number(execution?.durationSeconds);
    if (!group || !Number.isFinite(duration)) {
      return {
        isSlow: false,
        badgeVariant: "warning",
        label: "Sans base",
        note: "Dur\u00e9e ou groupe indisponible",
      };
    }

    const threshold = Number(group.slowThresholdSeconds);
    const baseline = Number(group.baselineDurationSeconds);
    const methodLabel = labelBaselineMethod(group.baselineMethod);

    if (!Number.isFinite(threshold) || !Number.isFinite(baseline) || baseline <= 0) {
      return {
        isSlow: false,
        badgeVariant: "warning",
        label: "Sans base",
        note: "Historique insuffisant pour d\u00e9tecter un ralentissement",
      };
    }

    if (duration > threshold) {
      return {
        isSlow: true,
        badgeVariant: "warning",
        label: "Lent",
        note: `Seuil ${formatSqlDuration(threshold)} via ${methodLabel}`,
      };
    }

    return {
      isSlow: false,
      badgeVariant: "success",
      label: "Nominal",
      note: `Base ${formatSqlDuration(baseline)} via ${methodLabel}`,
    };
  }

  function clampPercent(value) {
    return Math.max(6, Math.min(100, Number(value ?? 0)));
  }

  function toPercent(value, maxValue) {
    const safeMax = Math.max(Number(maxValue ?? 0), 1);
    return (Number(value ?? 0) / safeMax) * 100;
  }

  function filterItemsByDateRange(items, getDateKey, fromDate, toDate) {
    return items.filter((item) => {
      const dateKey = getDateKey(item);
      if (!dateKey) {
        return false;
      }
      if (fromDate && dateKey < fromDate) {
        return false;
      }
      if (toDate && dateKey > toDate) {
        return false;
      }
      return true;
    });
  }

  function collectGraphDateKeys(indicators) {
    if (!indicators) {
      return [];
    }
    const refreshDates = (indicators.trends?.refreshTimeline ?? [])
      .map((item) => formatDateKey(item.timestamp))
      .filter(Boolean);
    const dailyDates = (indicators.trends?.dailyRefreshPerformance ?? [])
      .map((item) => item.date)
      .filter(Boolean);
    const storedRefreshDates = (indicators.refreshes ?? [])
      .map((item) => formatDateKey(item.startTime))
      .filter(Boolean);
    return [...refreshDates, ...dailyDates, ...storedRefreshDates].sort();
  }

  function getGraphBounds(indicators) {
    const keys = collectGraphDateKeys(indicators);
    if (!keys.length) {
      return null;
    }
    return { min: keys[0], max: keys[keys.length - 1] };
  }

  function computePresetRange(preset, bounds) {
    if (!bounds) {
      return { from: "", to: "" };
    }
    if (preset === "all") {
      return { from: bounds.min, to: bounds.max };
    }
    const match = String(preset).match(/^(\d+)d$/);
    if (!match) {
      return { from: bounds.min, to: bounds.max };
    }
    const days = Number(match[1]);
    const from = shiftDateKey(bounds.max, -(days - 1));
    return {
      from: from < bounds.min ? bounds.min : from,
      to: bounds.max,
    };
  }

  function clampRange(range, bounds) {
    if (!bounds) {
      return { from: "", to: "" };
    }
    let from = range.from || bounds.min;
    let to = range.to || bounds.max;
    if (from < bounds.min) {
      from = bounds.min;
    }
    if (to > bounds.max) {
      to = bounds.max;
    }
    if (from > to) {
      from = bounds.min;
      to = bounds.max;
    }
    return { from, to };
  }

  function buildGridLines(width, height, padding, rows) {
    const chartHeight = height - padding.top - padding.bottom;
    return Array.from({ length: rows + 1 }, (_, index) => {
      const y = padding.top + (chartHeight / rows) * index;
      return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>`;
    }).join("");
  }

  function chartCoordinates(points, valueAccessor, width, height) {
    const padding = { top: 20, right: 20, bottom: 38, left: 48 };
    const values = points.map((item) => Number(valueAccessor(item) ?? 0));
    const maxValue = Math.max(...values, 1);
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const denominator = Math.max(points.length - 1, 1);
    const coords = points.map((item, index) => {
      const value = Number(valueAccessor(item) ?? 0);
      const x = padding.left + (chartWidth / denominator) * index;
      const y = padding.top + chartHeight - ((value / maxValue) * chartHeight);
      return { ...item, value, x, y };
    });
    return { coords, padding, width, height, maxValue };
  }

  function linePath(coords) {
    return coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  }

  function areaPath(coords, baselineY) {
    if (!coords.length) {
      return "";
    }
    return `${linePath(coords)} L ${coords[coords.length - 1].x} ${baselineY} L ${coords[0].x} ${baselineY} Z`;
  }

  function chartCaption(items) {
    return h(
      "div",
      { className: "chart-caption" },
      items.map((item, index) =>
        h("div", { className: "chart-stat", key: `${item.label}-${index}` }, [
          h("strong", { key: "value" }, item.value),
          h("span", { key: "label" }, item.label),
        ]),
      ),
    );
  }

  function getRefreshBounds(refreshes) {
    const keys = refreshes
      .map((item) => formatDateKey(item.startTime))
      .filter(Boolean)
      .sort();
    if (!keys.length) {
      return null;
    }
    return { min: keys[0], max: keys[keys.length - 1] };
  }

  function getFabricBounds(fabricExecutions, fabricSqlExecutions) {
    const keys = [
      ...fabricExecutions.map((item) => formatDateKey(item.startTimeUtc || item.startTime)),
      ...fabricSqlExecutions.map((item) => formatDateKey(item.startTime)),
    ]
      .filter(Boolean)
      .sort();
    if (!keys.length) {
      return null;
    }
    return { min: keys[0], max: keys[keys.length - 1] };
  }

  function classifyRefreshType(type) {
    const normalized = String(type ?? "").toLowerCase();
    if (normalized.includes("sched")) {
      return "scheduled";
    }
    if (
      normalized.includes("manual")
      || normalized.includes("ondemand")
      || normalized.includes("on-demand")
      || normalized.includes("api")
    ) {
      return "manual";
    }
    return "other";
  }

  function labelRefreshTypeBucket(bucket) {
    const labels = {
      all: "Tous",
      scheduled: "Planifi\u00e9",
      manual: "\u00c0 la demande",
      other: "Autre",
    };
    return labels[bucket] ?? bucket;
  }

  function refreshStatusRank(status) {
    const normalized = String(status ?? "").toLowerCase();
    if (normalized === "failed") {
      return 0;
    }
    if (normalized === "completed") {
      return 1;
    }
    return 2;
  }

  function applyRefreshFilters(refreshes, filters, searchTerm) {
    const filtered = [...refreshes].filter((item) => {
      const dateKey = formatDateKey(item.startTime);
      const normalizedStatus = String(item.status ?? "").toLowerCase();
      const bucket = classifyRefreshType(item.refreshType);
      const errorDetails = describeRefreshError(item);
      const haystack = [
        item.datasetName,
        item.workspaceName,
        item.refreshType,
        item.errorCode,
        item.errorMessage,
        errorDetails.title,
        errorDetails.message,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      if (filters.from && (!dateKey || dateKey < filters.from)) {
        return false;
      }
      if (filters.to && (!dateKey || dateKey > filters.to)) {
        return false;
      }
      if (filters.status !== "all" && normalizedStatus !== filters.status) {
        return false;
      }
      if (filters.type !== "all" && bucket !== filters.type) {
        return false;
      }
      if (searchTerm && !haystack.includes(searchTerm)) {
        return false;
      }
      return true;
    });

    filtered.sort((left, right) => {
      const leftTime = new Date(left.startTime ?? 0).getTime();
      const rightTime = new Date(right.startTime ?? 0).getTime();
      const leftDuration = Number(left.durationSeconds ?? 0);
      const rightDuration = Number(right.durationSeconds ?? 0);

      if (filters.sort === "oldest") {
        return leftTime - rightTime;
      }
      if (filters.sort === "failed-first") {
        const rankDiff = refreshStatusRank(left.status) - refreshStatusRank(right.status);
        if (rankDiff !== 0) {
          return rankDiff;
        }
        return rightTime - leftTime;
      }
      if (filters.sort === "success-first") {
        const successRank = { completed: 0, failed: 1 };
        const leftRank = successRank[String(left.status ?? "").toLowerCase()] ?? 2;
        const rightRank = successRank[String(right.status ?? "").toLowerCase()] ?? 2;
        if (leftRank !== rightRank) {
          return leftRank - rightRank;
        }
        return rightTime - leftTime;
      }
      if (filters.sort === "longest") {
        return rightDuration - leftDuration || rightTime - leftTime;
      }
      if (filters.sort === "shortest") {
        return leftDuration - rightDuration || rightTime - leftTime;
      }
      if (filters.sort === "delayed-first") {
        const delayedRankLeft = left.isDelayed ? 0 : 1;
        const delayedRankRight = right.isDelayed ? 0 : 1;
        if (delayedRankLeft !== delayedRankRight) {
          return delayedRankLeft - delayedRankRight;
        }
      }
      return rightTime - leftTime;
    });

    return filtered;
  }

  function applyIncidentFilters(incidents, filters, searchTerm) {
    const filtered = [...incidents].filter((item) => {
      const dateKey = formatDateKey(item.detectedAt);
      const severity = translateSeverity(item.severity).toLowerCase();
      const cause = normalizeCauseKey(item.suspectedCause);
      const type = String(item.incidentType ?? "");
      const haystack = [
        item.datasetName,
        item.workspaceName,
        item.incidentType,
        item.suspectedCause,
        item.recommendation,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      if (filters.from && (!dateKey || dateKey < filters.from)) {
        return false;
      }
      if (filters.to && (!dateKey || dateKey > filters.to)) {
        return false;
      }
      if (filters.severity !== "all" && severity !== filters.severity) {
        return false;
      }
      if (filters.type !== "all" && type !== filters.type) {
        return false;
      }
      if (filters.cause !== "all" && cause !== filters.cause) {
        return false;
      }
      if (searchTerm && !haystack.includes(searchTerm)) {
        return false;
      }
      return true;
    });

    filtered.sort((left, right) => {
      const leftTime = new Date(left.detectedAt ?? 0).getTime();
      const rightTime = new Date(right.detectedAt ?? 0).getTime();

      if (filters.sort === "oldest") {
        return leftTime - rightTime;
      }
      if (filters.sort === "severity") {
        const severityRank = { haute: 0, moyenne: 1, faible: 2 };
        const leftRank = severityRank[translateSeverity(left.severity).toLowerCase()] ?? 3;
        const rightRank = severityRank[translateSeverity(right.severity).toLowerCase()] ?? 3;
        if (leftRank !== rightRank) {
          return leftRank - rightRank;
        }
        return rightTime - leftTime;
      }
      if (filters.sort === "dataset") {
        return String(left.datasetName ?? "").localeCompare(String(right.datasetName ?? ""))
          || rightTime - leftTime;
      }
      return rightTime - leftTime;
    });

    return filtered;
  }

  function summarizeRefreshType(refreshes, bucket) {
    const scoped = refreshes.filter((item) => classifyRefreshType(item.refreshType) === bucket);
    const totalDuration = scoped.reduce((total, item) => total + Number(item.durationSeconds ?? 0), 0);
    const failures = scoped.filter((item) => String(item.status ?? "").toLowerCase() === "failed").length;
    return {
      count: scoped.length,
      averageDurationSeconds: scoped.length ? totalDuration / scoped.length : null,
      failures,
    };
  }

  function buildRefreshDiagnostic(refreshes) {
    const scheduled = summarizeRefreshType(refreshes, "scheduled");
    const manual = summarizeRefreshType(refreshes, "manual");

    if (!scheduled.count && !manual.count) {
      return "Pas assez de refreshs à comparer entre planifié et à la demande.";
    }
    if (scheduled.count && manual.count && Number(scheduled.averageDurationSeconds ?? 0) > Number(manual.averageDurationSeconds ?? 0) * 2) {
      return "Les refreshs planifi\u00e9s paraissent plus longs dans l'\u00e9chantillon charg\u00e9. Cela pointe souvent vers une file d'attente, une fen\u00eatre de charge ou un volume plus lourd trait\u00e9 la nuit.";
    }
    if (scheduled.count && manual.count && Number(manual.averageDurationSeconds ?? 0) > Number(scheduled.averageDurationSeconds ?? 0) * 2) {
      return "Les refreshs \u00e0 la demande dominent la dur\u00e9e moyenne visible. Cela peut signaler des reruns manuels sur incidents ou des ex\u00e9cutions cibl\u00e9es plus lourdes.";
    }
  }
  function EmptyState(props) {
    return h("div", { className: props.className || "empty-state" }, props.message);
  }

  function LoadingState(props) {
    return h("div", { className: `empty-state react-placeholder react-loading ${props.className || ""}`.trim() }, [
      h("div", { className: "react-loader-orbit", key: "orbit" }),
      h("div", { className: "react-loading-copy", key: "copy" }, [
        h("strong", { key: "title" }, props.title || "Chargement du dashboard"),
        h("span", { key: "body" }, props.body || "Pr\u00e9paration des cartes interactives."),
      ]),
    ]);
  }

  function GraphCard(props) {
    return h("article", { className: props.spanClass }, [
      h("div", { className: `chart-shell is-interactive ${props.className || ""}`.trim(), key: "shell" }, [
        h("div", { className: "panel-header", key: "header" }, [
          h("div", { key: "header-inner" }, [
            h("p", { className: "panel-kicker", key: "kicker" }, props.kicker),
            h("h3", { key: "title" }, props.title),
          ]),
        ]),
        props.children,
      ]),
    ]);
  }

  function DetailCard(props) {
    return h("article", { className: props.spanClass || "span-12" }, [
      h("div", { className: "chart-shell is-interactive dynamic-shell", key: "shell" }, [
        h("div", { className: "panel-header panel-header-split", key: "header" }, [
          h("div", { key: "left" }, [
            h("p", { className: "panel-kicker", key: "kicker" }, props.kicker),
            h("h3", { key: "title" }, props.title),
          ]),
          props.headerRight || null,
        ]),
        props.children,
      ]),
    ]);
  }

  function GlassPill(props) {
    return h("div", { className: "react-glass-pill" }, [
      h("span", { key: "label" }, props.label),
      h("strong", { key: "value" }, props.value),
    ]);
  }

  function Badge(props) {
    return h("span", { className: `badge ${props.variant || "warning"}`.trim() }, props.children);
  }

  function TinyMeter(props) {
    return h("div", { className: "tiny-meter" }, [
      h("span", {
        key: "fill",
        style: { width: `${clampPercent(props.percent)}%` },
      }),
    ]);
  }

  function ListItem(props) {
    return h("article", { className: "list-item" }, [
      props.header,
      props.title ? h("strong", { key: "title" }, props.title) : null,
      props.body ? h("p", { className: "list-note", key: "body" }, props.body) : null,
      props.meta ? h("div", { className: "stat-row", key: "meta" }, props.meta) : null,
      props.meterPercent != null ? h(TinyMeter, { key: "meter", percent: props.meterPercent }) : null,
    ]);
  }

  function renderSimpleList(items, emptyMessage, renderItem) {
    if (!items.length) {
      return h(EmptyState, { message: emptyMessage });
    }
    return h("div", { className: "stack-list" }, items.map(renderItem));
  }

  function RefreshDurationChart(props) {
    const timeline = props.timeline;
    if (!timeline.length) {
      return h(EmptyState, {
        className: "empty-state react-placeholder",
        message: "Aucun refresh ne correspond a la plage de dates choisie.",
      });
    }

    const chart = chartCoordinates(timeline, (item) => item.durationSeconds, 860, 240);
    const baselineY = chart.height - chart.padding.bottom;
    const longest = [...timeline].sort((left, right) => Number(right.durationSeconds ?? 0) - Number(left.durationSeconds ?? 0))[0];
    const delayedCount = timeline.filter((item) => item.isDelayed).length;
    const failedCount = timeline.filter((item) => String(item.status ?? "").toLowerCase() === "failed").length;
    const labelPoints = [chart.coords[0], chart.coords[Math.floor(chart.coords.length / 2)], chart.coords[chart.coords.length - 1]]
      .filter(Boolean);

    const svg = `
      <svg class="chart-svg" viewBox="0 0 ${chart.width} ${chart.height}" role="img" aria-label="\u00c9volution de la dur\u00e9e des refreshs">
        <g class="chart-grid">${buildGridLines(chart.width, chart.height, chart.padding, 4)}</g>
        <path class="chart-area" d="${areaPath(chart.coords, baselineY)}"></path>
        <path class="chart-line" d="${linePath(chart.coords)}"></path>
        ${chart.coords.map((point) => {
          const classNames = ["chart-point"];
          if (point.isDelayed) classNames.push("delayed");
          if (String(point.status ?? "").toLowerCase() === "failed") classNames.push("failed");
          return `<circle class="${classNames.join(" ")}" cx="${point.x}" cy="${point.y}" r="5"></circle>`;
        }).join("")}
        <text class="chart-axis-label" x="${chart.padding.left}" y="${chart.padding.top - 4}">${formatDuration(chart.maxValue)}</text>
        <text class="chart-axis-label" x="${chart.padding.left}" y="${baselineY}">${formatDuration(0)}</text>
        ${labelPoints.map((point) => `
          <text class="chart-axis-label" x="${point.x}" y="${chart.height - 10}" text-anchor="middle">${formatShortDate(point.timestamp)}</text>
        `).join("")}
      </svg>
    `;

    return h(Fragment, null, [
      h("div", {
        key: "svg",
        dangerouslySetInnerHTML: { __html: svg },
      }),
      chartCaption([
        { value: formatDuration(longest?.durationSeconds), label: `Pic sur ${formatShortDate(longest?.timestamp)}` },
        { value: formatNumber(delayedCount), label: "refresh(s) en retard visibles" },
        { value: formatNumber(failedCount), label: "refresh(s) \u00e9chou\u00e9(s) visibles" },
      ]),
    ]);
  }

  function DelayTrendChart(props) {
    const series = props.series;
    if (!series.length) {
      return h(EmptyState, {
        className: "empty-state react-placeholder",
        message: "Aucun pic journalier ne correspond \u00e0 la plage de dates choisie.",
      });
    }

    const width = 860;
    const height = 240;
    const padding = { top: 24, right: 20, bottom: 42, left: 48 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(...series.map((item) => Number(item.maximumDurationSeconds ?? 0)), 1);
    const barWidth = Math.max(14, Math.min(38, chartWidth / Math.max(series.length, 1) - 8));
    const totalDelayed = series.reduce((total, item) => total + Number(item.delayedRefreshes ?? 0), 0);
    const worstDay = [...series].sort((left, right) => Number(right.maximumDurationSeconds ?? 0) - Number(left.maximumDurationSeconds ?? 0))[0];

    const svg = `
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Pic journalier des refreshs">
        <g class="chart-grid">${buildGridLines(width, height, padding, 4)}</g>
        ${series.map((item, index) => {
          const x = padding.left + ((chartWidth / Math.max(series.length, 1)) * index) + 4;
          const value = Number(item.maximumDurationSeconds ?? 0);
          const barHeight = (value / maxValue) * chartHeight;
          const y = padding.top + chartHeight - barHeight;
          const className = Number(item.delayedRefreshes ?? 0) > 0 ? "chart-bar warning" : "chart-bar";
          return `
            <rect class="${className}" x="${x}" y="${y}" width="${barWidth}" height="${Math.max(barHeight, 4)}" rx="8"></rect>
            <text class="chart-axis-label" x="${x + (barWidth / 2)}" y="${height - 12}" text-anchor="middle">${formatShortDate(item.date)}</text>
            <text class="chart-value-label ${Number(item.delayedRefreshes ?? 0) > 0 ? "emphasis" : ""}" x="${x + (barWidth / 2)}" y="${Math.max(y - 8, 14)}" text-anchor="middle">${item.delayedRefreshes ?? 0}</text>
          `;
        }).join("")}
        <text class="chart-axis-label" x="${padding.left}" y="${padding.top - 6}">${formatDuration(maxValue)}</text>
        <text class="chart-axis-label" x="${padding.left}" y="${height - padding.bottom}">${formatDuration(0)}</text>
      </svg>
    `;

    return h(Fragment, null, [
      h("div", {
        key: "svg",
        dangerouslySetInnerHTML: { __html: svg },
      }),
      chartCaption([
        { value: formatNumber(totalDelayed), label: "retard(s) sur la p\u00e9riode" },
        { value: formatDuration(worstDay?.maximumDurationSeconds), label: `plus long le ${formatShortDate(worstDay?.date)}` },
        {
          value: formatRate(Number(worstDay?.failedRefreshes ?? 0) / Math.max(Number(worstDay?.totalRefreshes ?? 1), 1)),
          label: "taux d'\u00e9chec du jour le plus lent",
        },
      ]),
    ]);
  }

  function colorForReport(label) {
    const palette = ["#e0ac2b", "#e85252", "#6689c6", "#9a6fb0", "#a53253", "#56dfcf", "#49a8f5", "#f08c46"];
    const source = String(label ?? "rapport");
    let hash = 0;
    for (let index = 0; index < source.length; index += 1) {
      hash = source.charCodeAt(index) + ((hash << 5) - hash);
    }
    return palette[Math.abs(hash) % palette.length];
  }

  function shortenLabel(value, limit = 12) {
    const label = String(value ?? "").trim();
    if (!label) {
      return "Rapport";
    }
    if (label.length <= limit) {
      return label;
    }
    return `${label.slice(0, Math.max(limit - 1, 1)).trim()}…`;
  }

  function readNestedNumber(source, path) {
    let current = source;
    for (let index = 0; index < path.length; index += 1) {
      if (!current || typeof current !== "object") {
        return null;
      }
      current = current[path[index]];
    }
    const parsed = Number(current);
    if (!Number.isFinite(parsed) || parsed < 0) {
      return null;
    }
    return parsed;
  }

  function extractReportViewCount(report) {
    const candidates = [
      ["viewCount"],
      ["views"],
      ["viewsCount"],
      ["reportViewCount"],
      ["usageCount"],
      ["nombreVues"],
      ["nombreDeVues"],
      ["nbVues"],
      ["usageMetrics", "viewCount"],
      ["usageMetrics", "views"],
      ["metrics", "viewCount"],
      ["metrics", "views"],
      ["stats", "viewCount"],
      ["stats", "views"],
    ];

    for (let index = 0; index < candidates.length; index += 1) {
      const value = readNestedNumber(report, candidates[index]);
      if (value != null) {
        return value;
      }
    }

    return 0;
  }

  function extractReportStartDateKey(report) {
    const candidates = [
      report?.createdDateTime,
      report?.createdDate,
      report?.createdAt,
      report?.creationDate,
      report?.creationDateTime,
      report?.createdOn,
      report?.created,
    ];

    for (let index = 0; index < candidates.length; index += 1) {
      const dateKey = formatDateKey(candidates[index]);
      if (dateKey) {
        return dateKey;
      }
    }

    return "";
  }

  function buildSmoothPath(points) {
    if (!points.length) {
      return "";
    }
    if (points.length === 1) {
      return `M ${points[0].x} ${points[0].y}`;
    }

    function lineProperties(pointA, pointB) {
      const lengthX = pointB.x - pointA.x;
      const lengthY = pointB.y - pointA.y;
      return {
        angle: Math.atan2(lengthY, lengthX),
        length: Math.sqrt((lengthX ** 2) + (lengthY ** 2)),
      };
    }

    function controlPoint(current, previous, next, reverse) {
      const safePrevious = previous || current;
      const safeNext = next || current;
      const smoothing = 0.18;
      const properties = lineProperties(safePrevious, safeNext);
      const angle = properties.angle + (reverse ? Math.PI : 0);
      const length = properties.length * smoothing;
      return {
        x: current.x + (Math.cos(angle) * length),
        y: current.y + (Math.sin(angle) * length),
      };
    }

    function bezierCommand(point, index, source) {
      const start = controlPoint(source[index - 1], source[index - 2], point, false);
      const end = controlPoint(point, source[index - 1], source[index + 1], true);
      return `C ${start.x} ${start.y}, ${end.x} ${end.y}, ${point.x} ${point.y}`;
    }

    return points.reduce((path, point, index, source) => {
      if (index === 0) {
        return `M ${point.x} ${point.y}`;
      }
      return `${path} ${bezierCommand(point, index, source)}`;
    }, "");
  }

  function buildSmoothAreaPath(points, baselineY) {
    if (!points.length) {
      return "";
    }
    return `${buildSmoothPath(points)} L ${points[points.length - 1].x} ${baselineY} L ${points[0].x} ${baselineY} Z`;
  }

  function buildReportSeries(refreshes, datasets, reports, fromDate, toDate) {
    const reportMap = new Map();
    const reportIdsByDataset = new Map();
    const refreshDayKeys = new Set();

    function attachDatasetReport(datasetId, reportId) {
      if (!datasetId || !reportId) {
        return;
      }
      if (!reportIdsByDataset.has(datasetId)) {
        reportIdsByDataset.set(datasetId, []);
      }
      const existing = reportIdsByDataset.get(datasetId);
      if (!existing.includes(reportId)) {
        existing.push(reportId);
      }
    }

    function ensureReport(id, name, workspaceName, datasetId, availableFrom) {
      const key = id || name || "rapport-inconnu";
      if (!reportMap.has(key)) {
        reportMap.set(key, {
          id: key,
          datasetId: datasetId || null,
          name: name || id || "Rapport inconnu",
          workspaceName: workspaceName || "Workspace",
          availableFrom: availableFrom || "",
          averageDurationSeconds: 0,
          delayedCount: 0,
          failedCount: 0,
          maxDurationSeconds: 0,
          pointsByDay: new Map(),
          refreshCount: 0,
          viewCount: 0,
        });
      } else if (datasetId && !reportMap.get(key).datasetId) {
        reportMap.get(key).datasetId = datasetId;
      } else if (availableFrom && !reportMap.get(key).availableFrom) {
        reportMap.get(key).availableFrom = availableFrom;
      }
      return reportMap.get(key);
    }

    (reports ?? []).forEach((item) => {
      const report = ensureReport(
        item.reportId || item.id || item.datasetId,
        item.reportName || item.name,
        item.workspaceName,
        item.datasetId,
        extractReportStartDateKey(item),
      );
      report.viewCount = Math.max(
        Number(report.viewCount ?? 0),
        extractReportViewCount(item),
      );
      attachDatasetReport(item.datasetId, report.id);
    });

    refreshes.forEach((item) => {
      const dayKey = formatDateKey(item.startTime || item.timestamp);
      const linkedReportIds = reportIdsByDataset.get(item.datasetId);
      const targets = linkedReportIds?.length
        ? linkedReportIds.map((reportId) => reportMap.get(reportId)).filter(Boolean)
        : [
          ensureReport(
            item.datasetId,
            item.datasetName,
            item.workspaceName,
            item.datasetId,
          ),
        ];
      const eligibleTargets = targets.filter((report) => !report.availableFrom || !dayKey || dayKey >= report.availableFrom);
      if (dayKey) {
        refreshDayKeys.add(dayKey);
      }

      eligibleTargets.forEach((report) => {
        const duration = Number(item.durationSeconds ?? 0);
        report.refreshCount += 1;
        report.averageDurationSeconds += duration;
        report.maxDurationSeconds = Math.max(report.maxDurationSeconds, duration);
        if (dayKey) {
          const currentPoint = report.pointsByDay.get(dayKey) ?? {
            date: dayKey,
            durationSeconds: 0,
            refreshCount: 0,
          };
          currentPoint.refreshCount += 1;
          currentPoint.durationSeconds = Math.max(
            Number(currentPoint.durationSeconds ?? 0),
            duration,
          );
          report.pointsByDay.set(dayKey, currentPoint);
        }
        if (item.isDelayed) {
          report.delayedCount += 1;
        }
        if (String(item.status ?? "").toLowerCase() === "failed") {
          report.failedCount += 1;
        }
      });
    });

    datasets.forEach((item) => {
      const datasetId = item.datasetId || item.id;
      const linkedReportIds = reportIdsByDataset.get(datasetId);
      if (linkedReportIds?.length) {
        linkedReportIds.forEach((reportId) => {
          const report = reportMap.get(reportId);
          if (report && !report.workspaceName && item.workspaceName) {
            report.workspaceName = item.workspaceName;
          }
        });
        return;
      }

      ensureReport(
        datasetId,
        item.datasetName || item.name,
        item.workspaceName,
        datasetId,
      );
    });

    const dateKeys = enumerateDateKeys(fromDate, toDate).length
      ? enumerateDateKeys(fromDate, toDate)
      : [...refreshDayKeys].sort();

    return [...reportMap.values()]
      .map((item) => ({
        ...item,
        averageDurationSeconds: item.refreshCount
          ? item.averageDurationSeconds / item.refreshCount
          : 0,
        color: colorForReport(item.name),
        points: dateKeys.map((dateKey) => ({
          date: dateKey,
          durationSeconds: item.availableFrom && dateKey < item.availableFrom
            ? 0
            : Number(item.pointsByDay.get(dateKey)?.durationSeconds ?? 0),
          refreshCount: item.availableFrom && dateKey < item.availableFrom
            ? 0
            : Number(item.pointsByDay.get(dateKey)?.refreshCount ?? 0),
        })),
      }))
      .filter((item) => Boolean(item.name || item.id));
  }

  function UnifiedReportBarplot(props) {
    const {
      activeReportId,
      onSelectReport,
      reports,
    } = props;
    const [hoveredDayIndex, setHoveredDayIndex] = useState(null);

    const visibleReports = [...reports]
      .sort((left, right) => (
        Number(right.maxDurationSeconds ?? 0) - Number(left.maxDurationSeconds ?? 0)
      ) || left.name.localeCompare(right.name))
      .slice(0, 8);

    if (!visibleReports.length) {
      return h(EmptyState, {
        className: "empty-state react-placeholder",
        message: "Aucun rapport n'est encore disponible sur la plage choisie.",
      });
    }

    const strongestReport = visibleReports[0];
    const resolvedActiveReportId = activeReportId ?? null;
    const summaryReport = visibleReports.find((item) => item.id === resolvedActiveReportId) ?? strongestReport ?? visibleReports[0] ?? {
      name: "Aucun rapport",
      workspaceName: "Workspace",
      maxDurationSeconds: 0,
      delayedCount: 0,
      viewCount: 0,
    };
    if (!window.d3) {
      return h(EmptyState, {
        className: "empty-state react-placeholder",
        message: "La librairie du graphe n'est pas encore charg\u00e9e.",
      });
    }

    const d3 = window.d3;
    const streamWidth = 620;
    const barplotWidth = 320;
    const width = streamWidth + barplotWidth;
    const height = 400;
    const margin = { top: 30, right: 30, bottom: 50, left: 50 };
    const boundsWidth = streamWidth - margin.right - margin.left;
    const boundsHeight = height - margin.top - margin.bottom;
    const dayKeys = [...new Set(
      visibleReports.flatMap((item) => (item.points ?? []).map((point) => point.date)),
    )].filter(Boolean).sort();

    if (!dayKeys.length) {
      return h(EmptyState, {
        className: "empty-state react-placeholder",
        message: "Aucune journ\u00e9e de refresh n'est disponible sur la plage choisie.",
      });
    }

    const groups = visibleReports.map((item) => item.id);
    const reportById = new Map(visibleReports.map((item) => [item.id, item]));
    const streamData = dayKeys.map((dateKey, index) => {
      const row = { x: index, date: dateKey };
      visibleReports.forEach((report) => {
        row[report.id] = Number(
          report.points?.find((point) => point.date === dateKey)?.durationSeconds ?? 0,
        );
      });
      return row;
    });

    const barplotData = [...visibleReports]
      .map((item) => ({
        id: item.id,
        name: item.name,
        value: Number(item.maxDurationSeconds ?? 0),
        color: item.color,
      }))
      .sort((left, right) => right.value - left.value);
    const maxDurationValue = Math.max(...barplotData.map((item) => item.value), 10);

    const stackSeries = d3
      .stack()
      .keys(groups)
      .order(d3.stackOrderNone)
      .offset(d3.stackOffsetSilhouette);
    const series = stackSeries(streamData);
    const xScale = d3.scaleLinear()
      .domain([0, Math.max(streamData.length - 1, 0)])
      .range([0, boundsWidth]);
    const topYValues = series.flatMap((item) => item.map((entry) => entry[1]));
    const bottomYValues = series.flatMap((item) => item.map((entry) => entry[0]));
    const yScale = d3.scaleLinear()
      .domain([Math.min(...bottomYValues, 0), Math.max(...topYValues, 1)])
      .range([boundsHeight, 0]);
    const areaBuilder = d3
      .area()
      .x((item) => xScale(item.data.x))
      .y1((item) => yScale(item[1]))
      .y0((item) => yScale(item[0]))
      .curve(d3.curveCatmullRom);
    const xTickStep = Math.max(1, Math.ceil(dayKeys.length / 6));
    const durationAxisScale = d3.scaleLinear()
      .domain([0, maxDurationValue])
      .range([boundsHeight, 0]);
    const durationTicks = durationAxisScale.ticks(4);
    const hoveredDay = hoveredDayIndex != null ? streamData[hoveredDayIndex] ?? null : null;
    const hoveredDayX = hoveredDay ? xScale(hoveredDay.x) : null;
    const hoveredTooltipReport = resolvedActiveReportId
      ? visibleReports.find((report) => report.id === resolvedActiveReportId) ?? null
      : null;
    const hoveredDayValue = hoveredDay && hoveredTooltipReport
      ? Number(hoveredDay[hoveredTooltipReport.id] ?? 0)
      : null;
    const tooltipWidth = 190;
    const tooltipHeight = 74;
    const tooltipX = hoveredDayX == null
      ? 0
      : Math.min(
        Math.max(hoveredDayX + 14, 10),
        boundsWidth - tooltipWidth - 10,
      );
    const tooltipY = 12;

    const svg = h(
      "svg",
      {
        className: "hover-barplot-svg report-compare-svg",
        viewBox: `0 0 ${width} ${height}`,
        role: "img",
        "aria-label": "Tendance continue et classement des rapports par dur\u00e9e",
        onClick: () => onSelectReport(null),
      },
      [
        h(
          "g",
          {
            className: "report-stream-root",
            key: "root",
            transform: `translate(${margin.left}, ${margin.top})`,
            onMouseMove: (event) => {
              const bounds = event.currentTarget.getBoundingClientRect();
              const relativeX = event.clientX - bounds.left;
              const hoveredIndex = Math.round(
                (relativeX / Math.max(bounds.width, 1)) * Math.max(streamData.length - 1, 0),
              );
              const clampedIndex = Math.max(0, Math.min(streamData.length - 1, hoveredIndex));
              setHoveredDayIndex(Number.isFinite(clampedIndex) ? clampedIndex : null);
            },
            onMouseLeave: () => setHoveredDayIndex(null),
          },
          [
            h("rect", {
              key: "hover-surface",
              x: 0,
              y: 0,
              width: boundsWidth,
              height: boundsHeight,
              fill: "transparent",
            }),
            h(
              "g",
              { className: "report-stream-grid", key: "grid" },
              [
                ...durationTicks.map((value) =>
                  h("line", {
                    key: `h-grid-${value}`,
                    x1: 0,
                    x2: boundsWidth,
                    y1: durationAxisScale(value),
                    y2: durationAxisScale(value),
                    className: "report-stream-grid-line",
                  }),
                ),
                ...dayKeys
                  .filter((dateKey, index) => index % xTickStep === 0 || index === dayKeys.length - 1)
                  .map((dateKey) =>
                    h("line", {
                      key: `v-grid-${dateKey}`,
                      x1: xScale(dayKeys.indexOf(dateKey)),
                      x2: xScale(dayKeys.indexOf(dateKey)),
                      y1: 0,
                      y2: boundsHeight,
                      className: "report-stream-grid-line",
                    }),
                  ),
              ],
            ),
            h(
              "g",
              { className: "report-stream-axis", key: "y-axis" },
              durationTicks.map((value) =>
                h(
                  "text",
                  {
                    key: `y-tick-${value}`,
                    x: -12,
                    y: durationAxisScale(value) + 4,
                    textAnchor: "end",
                    className: "report-trend-axis-text",
                  },
                  formatDuration(value),
                ),
              ),
            ),
            h(
              "g",
              { key: "areas" },
              series.map((serie) => {
                const path = areaBuilder(serie);
                const report = reportById.get(serie.key);
                const isActive = resolvedActiveReportId === serie.key;

                return h("path", {
                  key: serie.key,
                  d: path,
                  className: "report-stream-path",
                  opacity: resolvedActiveReportId ? (isActive ? 1 : 0.38) : 1,
                  stroke: "rgba(255, 255, 255, 0.18)",
                  fill: report?.color ?? colorForReport(serie.key),
                  fillOpacity: isActive ? 0.88 : 0.74,
                  cursor: "pointer",
                  onClick: (event) => {
                    event.stopPropagation();
                    onSelectReport(serie.key);
                  },
                });
              }),
            ),
            hoveredDayX != null && hoveredTooltipReport
              ? h(
                "g",
                { className: "report-day-hover", key: "day-hover" },
                [
                  h("line", {
                    key: "line",
                    x1: hoveredDayX,
                    x2: hoveredDayX,
                    y1: 0,
                    y2: boundsHeight,
                    className: "report-day-hover-line",
                  }),
                  h("rect", {
                    key: "tooltip-bg",
                    x: tooltipX,
                    y: tooltipY,
                    width: tooltipWidth,
                    height: tooltipHeight,
                    rx: 14,
                    className: "report-day-tooltip",
                  }),
                  h(
                    "text",
                    {
                      key: "tooltip-title",
                      x: tooltipX + 14,
                      y: tooltipY + 20,
                      className: "report-day-tooltip-title",
                    },
                    formatShortDate(hoveredDay.date),
                  ),
                  h("circle", {
                    key: "dot",
                    cx: tooltipX + 14,
                    cy: tooltipY + 42,
                    r: 4,
                    fill: hoveredTooltipReport.color,
                  }),
                  h(
                    "text",
                    {
                      key: "name",
                      x: tooltipX + 24,
                      y: tooltipY + 46,
                      className: "report-day-tooltip-text",
                    },
                    shortenLabel(hoveredTooltipReport.name, 16),
                  ),
                  h(
                    "text",
                    {
                      key: "value",
                      x: tooltipX + tooltipWidth - 14,
                      y: tooltipY + 46,
                      textAnchor: "end",
                      className: `report-day-tooltip-value ${hoveredDayValue > 0 ? "has-value" : ""}`.trim(),
                    },
                    formatDuration(hoveredDayValue ?? 0),
                  ),
                ],
              )
              : null,
            h(
              "g",
              { className: "report-stream-axis", key: "x-axis" },
              dayKeys
                .filter((dateKey, index) => index % xTickStep === 0 || index === dayKeys.length - 1)
                .map((dateKey) =>
                  h(
                    "g",
                    { key: `axis-${dateKey}` },
                    [
                      h(
                        "text",
                        {
                          x: xScale(dayKeys.indexOf(dateKey)),
                          y: boundsHeight + 14,
                          textAnchor: "middle",
                          alignmentBaseline: "central",
                          className: "report-trend-axis-text",
                        },
                        formatShortDate(dateKey),
                      ),
                    ],
                  ),
                ),
            ),
          ],
        ),
        h(
          "text",
          {
            className: "chart-axis-label",
            key: "axis-title",
            x: margin.left,
            y: margin.top - 10,
          },
          "Dur\u00e9e",
        ),
        h(
          "text",
          {
            className: "chart-axis-label",
            key: "x-title",
            x: streamWidth - margin.right,
            y: height - 8,
            textAnchor: "end",
          },
          "Jour",
        ),
        h(
          "g",
          {
            className: "report-barplot-panel",
            key: "barplot",
            transform: `translate(${streamWidth}, 0)`,
          },
          barplotData.map((item, index) => {
            const isActive = item.id === resolvedActiveReportId;
            const opacity = resolvedActiveReportId ? (isActive ? 1 : 0.45) : 1;
            const itemY = 42 + (index * 44);

            return h(
              "g",
              {
                key: `legend-${item.id}`,
                className: "report-legend-group",
                opacity,
                onClick: (event) => {
                  event.stopPropagation();
                  onSelectReport(item.id);
                },
              },
              [
                h("circle", {
                  key: "swatch",
                  cx: 28,
                  cy: itemY,
                  r: isActive ? 8 : 6,
                  fill: item.color,
                  className: "report-legend-swatch",
                }),
                h(
                  "text",
                  {
                    key: "label",
                    x: 46,
                    y: itemY + 4,
                    textAnchor: "start",
                    className: `report-barplot-label ${isActive ? "is-active" : ""}`.trim(),
                  },
                  shortenLabel(item.name, 18),
                ),
                h(
                  "title",
                  { key: "title" },
                  `${item.name} | ${formatDuration(item.value)}`,
                ),
              ],
            );
          }),
        ),
      ],
    );

    return h("div", { className: "report-barplot-shell" }, [
      h("div", { className: "report-barplot-grid", key: "grid" }, [
        h("div", { className: "report-barplot-scroll", key: "chart" }, [
          svg,
        ]),
        h("div", { className: "report-barplot-summary", key: "summary" }, [
          h("span", { className: "highlight-label", key: "label" }, "Rapport suivi"),
          h("h4", { key: "title" }, summaryReport.name),
          h("p", { className: "workspace-meta", key: "workspace" }, summaryReport.workspaceName ?? "Workspace"),
          h("div", { className: "stack-list compact", key: "stats" }, [
            h(ListItem, {
              key: "duration",
              title: "Pic de dur\u00e9e",
              body: formatDuration(summaryReport.maxDurationSeconds),
              meterPercent: (summaryReport.maxDurationSeconds / Math.max(...visibleReports.map((item) => item.maxDurationSeconds), 1)) * 100,
            }),
            h(ListItem, {
              key: "delay",
              title: "Retards sur la p\u00e9riode",
              body: `${formatNumber(summaryReport.delayedCount)} retard(s)`,
              meterPercent: (summaryReport.delayedCount / Math.max(...visibleReports.map((item) => item.delayedCount), 1)) * 100,
            }),
            h(ListItem, {
              key: "views",
              title: "Nombre de vues",
              body: `${formatNumber(summaryReport.viewCount)} vue(s)`,
              meterPercent: (summaryReport.viewCount / Math.max(...visibleReports.map((item) => item.viewCount), 1)) * 100,
            }),
          ]),
        ]),
      ]),
    ]);
  }

  function GraphsApp() {
    const payload = useBridgePayload(graphsBridge);
    const [preset, setPreset] = useState("30d");
    const [range, setRange] = useState({ from: "", to: "" });
    const [selectedReport, setSelectedReport] = useState(null);
    const bounds = useMemo(() => getGraphBounds(payload), [payload]);

    useEffect(() => {
      if (!bounds) {
        setRange({ from: "", to: "" });
        return;
      }
      setRange(computePresetRange(preset, bounds));
    }, [bounds, preset]);

    const graphData = useMemo(() => {
      if (!payload) {
        return {
          from: "",
          to: "",
          datasets: [],
          reports: [],
          refreshes: [],
          refreshTimeline: [],
          dailyRefreshPerformance: [],
        };
      }
      const activeRange = bounds ? clampRange(range, bounds) : range;
      return {
        from: activeRange.from,
        to: activeRange.to,
        datasets: payload.datasets ?? [],
        reports: payload.reports ?? [],
        refreshes: filterItemsByDateRange(
          payload.refreshes ?? [],
          (item) => formatDateKey(item.startTime),
          activeRange.from,
          activeRange.to,
        ),
        refreshTimeline: filterItemsByDateRange(
          payload.trends?.refreshTimeline ?? [],
          (item) => formatDateKey(item.timestamp),
          activeRange.from,
          activeRange.to,
        ),
        dailyRefreshPerformance: filterItemsByDateRange(
          payload.trends?.dailyRefreshPerformance ?? [],
          (item) => item.date,
          activeRange.from,
          activeRange.to,
        ),
      };
    }, [payload, bounds, range]);

    const reportSeries = useMemo(
      () => buildReportSeries(
        graphData.refreshTimeline,
        graphData.datasets,
        graphData.reports,
        graphData.from,
        graphData.to,
      ),
      [graphData],
    );
    const activeReportId = selectedReport ?? null;

    useEffect(() => {
      if (!reportSeries.length) {
        setSelectedReport(null);
        return;
      }
      if (selectedReport && !reportSeries.some((item) => item.id === selectedReport)) {
        setSelectedReport(null);
      }
    }, [reportSeries, selectedReport]);

    if (!payload) {
      return h(LoadingState, {
        title: "Chargement des graphes",
        body: "Pr\u00e9paration des tendances, filtres et cartes interactives.",
      });
    }

    return h("div", { className: "react-graphs-shell" }, [
      h("div", { className: "react-filter-shell", key: "filters" }, [
        h("p", { className: "panel-kicker react-filter-kicker", key: "label" }, "P\u00e9riode"),
        h(
          "div",
          { className: "react-preset-row", key: "preset-row" },
          [
            { value: "7d", label: "7 jours" },
            { value: "30d", label: "30 jours" },
            { value: "90d", label: "90 jours" },
            { value: "all", label: "Historique" },
          ].map((option) =>
            h(
              "button",
              {
                type: "button",
                key: option.value,
                className: `preset-chip ${preset === option.value ? "is-active" : ""}`.trim(),
                onClick: () => setPreset(option.value),
              },
              option.label,
            ),
          ),
        ),
      ]),
      h("div", { className: "graph-react-grid", key: "grid" }, [
        h(GraphCard, {
          spanClass: "span-12",
          kicker: "Comparatif",
          title: "Tendance par rapport",
          key: "unified-report-barplot",
          children: h(UnifiedReportBarplot, {
            activeReportId,
            onSelectReport: setSelectedReport,
            reports: reportSeries,
          }),
        }),
      ]),
    ]);
  }

  function PerformanceApp() {
    const payload = useBridgePayload(panelsBridge);
    const [filters, setFilters] = useState({
      search: "",
      from: "",
      to: "",
      status: "all",
      type: "all",
      sort: "recent",
    });
    const datasetLimit = 10;
    const deferredSearch = useDeferredValue(filters.search.trim().toLowerCase());

    const refreshes = payload?.refreshes ?? [];
    const incidents = payload?.incidents ?? [];
    const indicators = payload?.indicators ?? null;
    const totalRefreshes = Number(payload?.totalRefreshes ?? refreshes.length);
    const refreshBounds = useMemo(() => getRefreshBounds(refreshes), [refreshes]);

    const filteredRefreshes = useMemo(
      () => applyRefreshFilters(refreshes, filters, deferredSearch),
      [refreshes, filters, deferredSearch],
    );

    const filteredScheduled = useMemo(
      () => summarizeRefreshType(filteredRefreshes, "scheduled"),
      [filteredRefreshes],
    );
    const filteredManual = useMemo(
      () => summarizeRefreshType(filteredRefreshes, "manual"),
      [filteredRefreshes],
    );

    const delayedIncidents = useMemo(
      () => incidents.filter((item) => item.incidentType === "DelayedRefresh").slice(0, datasetLimit),
      [incidents, datasetLimit],
    );
    const anomalyIncidents = useMemo(
      () => incidents.filter((item) => item.incidentType === "DurationAnomaly").slice(0, datasetLimit),
      [incidents, datasetLimit],
    );

    if (!payload) {
      return h(LoadingState, {
        title: "Chargement de la performance",
        body: "Pr\u00e9paration des d\u00e9tails, filtres et tableaux de refreshs.",
      });
    }

    const visibleDelayed = filteredRefreshes.filter((item) => item.isDelayed).length;
    const hasMoreRefreshes = refreshes.length < totalRefreshes;
    const refreshDiagnostic = buildRefreshDiagnostic(filteredRefreshes);
    const slowestDatasets = (indicators?.datasets?.slowest ?? []).slice(0, datasetLimit);
    const failedDatasets = (indicators?.datasets?.mostFailures ?? []).slice(0, datasetLimit);

    return h("div", { className: "dynamic-react-shell" }, [
      h("div", { className: "dynamic-grid", key: "grid" }, [
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "Performance",
          title: "Datasets les plus lents",
          note: "Le top reste dynamique pour presenter les plus gros pics du moment.",
          children: renderSimpleList(
            slowestDatasets,
            "Aucun dataset lent n'a encore ete calcule.",
            (item) => h(ListItem, {
              key: item.datasetId || item.datasetName,
              title: item.datasetName ?? item.datasetId,
              body: `Moyenne ${formatDuration(item.averageDurationSeconds)} | Maximum ${formatDuration(item.maxDurationSeconds)}`,
              meterPercent: toPercent(
                item.averageDurationSeconds,
                item.maxDurationSeconds || item.averageDurationSeconds || 1,
              ),
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "Fiabilite",
          title: "Datasets avec le plus d'\u00e9checs",
          note: "Tres utile pour capter rapidement les zones qui degradent la confiance.",
          children: renderSimpleList(
            failedDatasets,
            "Aucun dataset avec \u00e9checs n'a encore \u00e9t\u00e9 calcul\u00e9.",
            (item) => h(ListItem, {
              key: item.datasetId || item.datasetName,
              title: item.datasetName ?? item.datasetId,
              body: `${formatNumber(item.failureCount)} refresh(s) \u00e9chou\u00e9(s)`,
              meterPercent: indicators?.totals?.failedRefreshes
                ? (Number(item.failureCount ?? 0) / Number(indicators.totals.failedRefreshes)) * 100
                : 100,
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Retards et ecarts",
          title: "Refreshs en retard et anomalies de dur\u00e9e",
          children: h("div", { className: "dynamic-dual-grid" }, [
            h("div", { className: "dual-card", key: "delayed" }, [
              h("strong", { key: "title" }, "Refreshs en retard"),
              h("p", { className: "metric-value", key: "count" }, formatNumber(visibleDelayed)),
              h("div", { className: "stack-list compact", key: "list" }, delayedIncidents.length
                ? delayedIncidents.map((item) =>
                  h(ListItem, {
                    key: `${item.datasetId || item.datasetName}-${item.detectedAt}`,
                    header: h("div", { className: "dual-card-header", key: "header" }, [
                      h("strong", { key: "title" }, item.datasetName ?? item.datasetId ?? "Dataset"),
                      h(Badge, { key: "badge", variant: classifySeverity(item.severity), children: translateSeverity(item.severity) }),
                    ]),
                    body: `${translateCause(item.suspectedCause ?? "Cause non renseign\u00e9e")} | ${formatTimestamp(item.detectedAt)}`,
                  }),
                )
                : h(EmptyState, { message: "Aucun refresh en retard remonte." }),
              ),
            ]),
            h("div", { className: "dual-card", key: "anomalies" }, [
              h("strong", { key: "title" }, "Anomalies de dur\u00e9e"),
              h("p", { className: "metric-value", key: "count" }, formatNumber(indicators?.totals?.durationAnomalies ?? anomalyIncidents.length)),
              h("div", { className: "stack-list compact", key: "list" }, anomalyIncidents.length
                ? anomalyIncidents.map((item) =>
                  h(ListItem, {
                    key: `${item.datasetId || item.datasetName}-${item.detectedAt}`,
                    header: h("div", { className: "dual-card-header", key: "header" }, [
                      h("strong", { key: "title" }, item.datasetName ?? item.datasetId ?? "Dataset"),
                      h(Badge, { key: "badge", variant: classifySeverity(item.severity), children: translateSeverity(item.severity) }),
                    ]),
                    body: `${translateCause(item.suspectedCause ?? "Cause non renseign\u00e9e")} | ${formatTimestamp(item.detectedAt)}`,
                  }),
                )
                : h(EmptyState, { message: "Aucune anomalie de dur\u00e9e remont\u00e9e." }),
              ),
            ]),
          ]),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Historique",
          title: "Tous les refreshs",
          note: `${refreshDiagnostic} Planifi\u00e9 : ${formatDuration(filteredScheduled.averageDurationSeconds)} | \u00c0 la demande : ${formatDuration(filteredManual.averageDurationSeconds)}.`,
          headerRight: h("div", { className: "table-actions", key: "actions" }, [
            h("span", { className: "table-meta", key: "meta" }, `${formatNumber(filteredRefreshes.length)} visible(s) | ${formatNumber(refreshes.length)} charg\u00e9(s)`),
            h(
              "button",
              {
                className: "action-button tertiary",
                type: "button",
                disabled: !hasMoreRefreshes || panelsBridge.isLoadingMore,
                onClick: async () => {
                  if (typeof panelsBridge.requestMore === "function") {
                    await panelsBridge.requestMore();
                  }
                },
              },
              panelsBridge.isLoadingMore ? "Chargement..." : "Afficher plus",
            ),
          ]),
          children: h(Fragment, null, [
            h("div", { className: "filter-bar filter-bar-wide", key: "bar" }, [
              h("label", { className: "filter-field filter-field-wide", key: "search" }, [
                h("span", { key: "label" }, "Recherche"),
                h("input", {
                  className: "filter-input",
                  type: "search",
                  placeholder: "Dataset, workspace, erreur...",
                  value: filters.search,
                  onChange: (event) => setFilters((previous) => ({ ...previous, search: event.target.value })),
                }),
              ]),
              h("label", { className: "filter-field", key: "from" }, [
                h("span", { key: "label" }, "Du"),
                h("input", {
                  className: "filter-input",
                  type: "date",
                  min: refreshBounds?.min || undefined,
                  max: refreshBounds?.max || undefined,
                  value: filters.from,
                  onChange: (event) => setFilters((previous) => ({ ...previous, from: event.target.value })),
                }),
              ]),
              h("label", { className: "filter-field", key: "to" }, [
                h("span", { key: "label" }, "Au"),
                h("input", {
                  className: "filter-input",
                  type: "date",
                  min: refreshBounds?.min || undefined,
                  max: refreshBounds?.max || undefined,
                  value: filters.to,
                  onChange: (event) => setFilters((previous) => ({ ...previous, to: event.target.value })),
                }),
              ]),
              h("label", { className: "filter-field", key: "status" }, [
                h("span", { key: "label" }, "Statut"),
                h("select", {
                  className: "filter-input",
                  value: filters.status,
                  onChange: (event) => setFilters((previous) => ({ ...previous, status: event.target.value })),
                }, [
                  h("option", { key: "all", value: "all" }, "Tous"),
                  h("option", { key: "failed", value: "failed" }, "\u00c9chou\u00e9s"),
                  h("option", { key: "completed", value: "completed" }, "Termin\u00e9s"),
                  h("option", { key: "unknown", value: "unknown" }, "En attente"),
                ]),
              ]),
              h("label", { className: "filter-field", key: "type" }, [
                h("span", { key: "label" }, "Type"),
                h("select", {
                  className: "filter-input",
                  value: filters.type,
                  onChange: (event) => setFilters((previous) => ({ ...previous, type: event.target.value })),
                }, [
                  h("option", { key: "all", value: "all" }, "Tous"),
                  h("option", { key: "scheduled", value: "scheduled" }, "Planifi\u00e9s"),
                  h("option", { key: "manual", value: "manual" }, "\u00c0 la demande"),
                  h("option", { key: "other", value: "other" }, "Autres"),
                ]),
              ]),
              h("label", { className: "filter-field", key: "sort" }, [
                h("span", { key: "label" }, "Tri"),
                h("select", {
                  className: "filter-input",
                  value: filters.sort,
                  onChange: (event) => setFilters((previous) => ({ ...previous, sort: event.target.value })),
                }, [
                  h("option", { key: "recent", value: "recent" }, "Plus r\u00e9cents"),
                  h("option", { key: "oldest", value: "oldest" }, "Plus anciens"),
                  h("option", { key: "failed-first", value: "failed-first" }, "\u00c9checs d'abord"),
                  h("option", { key: "success-first", value: "success-first" }, "Succ\u00e8s d'abord"),
                  h("option", { key: "longest", value: "longest" }, "Plus longs"),
                  h("option", { key: "shortest", value: "shortest" }, "Plus courts"),
                  h("option", { key: "delayed-first", value: "delayed-first" }, "Retards d'abord"),
                ]),
              ]),
            ]),
            h("div", { className: "react-range-actions", key: "reset-row" }, [
              h(
                "button",
                {
                  className: "action-button tertiary react-reset-button",
                  type: "button",
                  onClick: () => setFilters({
                    search: "",
                    from: "",
                    to: "",
                    status: "all",
                    type: "all",
                    sort: "recent",
                  }),
                },
                "R\u00e9initialiser",
              ),
            ]),
            filteredRefreshes.length
              ? h("div", { className: "table-shell dynamic-table-shell", key: "table-shell" }, [
                h("table", { key: "table" }, [
                  h("thead", { key: "head" }, [
                    h("tr", { key: "row" }, [
                      h("th", { key: "dataset" }, "Dataset"),
                      h("th", { key: "workspace" }, "Workspace"),
                      h("th", { key: "type" }, "Type"),
                      h("th", { key: "status" }, "Statut"),
                      h("th", { key: "duration" }, "Dur\u00e9e"),
                      h("th", { key: "start" }, "D\u00e9but"),
                      h("th", { key: "detail" }, "D\u00e9tail"),
                    ]),
                  ]),
                  h("tbody", { key: "body" }, filteredRefreshes.map((item, index) =>
                    (() => {
                      const errorDetails = describeRefreshError(item);
                      return h("tr", { key: `${item.requestId || item.datasetId || "refresh"}-${item.startTime || index}` }, [
                        h("td", { key: "dataset" }, [
                          h("div", { className: "table-cell-title", key: "title" }, item.datasetName ?? item.datasetId ?? "Dataset"),
                          h("div", { className: "table-cell-note", key: "note" }, item.isDelayed ? "Retard d\u00e9tect\u00e9" : "Flux nominal"),
                        ]),
                        h("td", { key: "workspace" }, item.workspaceName ?? item.workspaceId ?? "Workspace"),
                        h("td", { key: "type" }, labelRefreshTypeBucket(classifyRefreshType(item.refreshType))),
                        h("td", { key: "status" }, h(Badge, { variant: classifyStatus(item.status), children: translateStatus(item.status) })),
                        h("td", { key: "duration" }, formatDuration(item.durationSeconds)),
                        h("td", { key: "start" }, formatTimestamp(item.startTime)),
                        h("td", { key: "detail" }, [
                          h("div", { className: "table-cell-title", key: "code" }, errorDetails.title),
                          h("div", { className: "table-cell-note", key: "message" }, errorDetails.message),
                        ]),
                      ]);
                    })(),
                  )),
                ]),
              ])
              : h(EmptyState, { key: "empty", message: "Aucun refresh ne correspond aux filtres choisis." }),
          ]),
        }),
      ]),
    ]);
  }

  function FabricApp() {
    const payload = useBridgePayload(panelsBridge);
    const [filters, setFilters] = useState({
      from: "",
      to: "",
    });
    const [selectedStatementType, setSelectedStatementType] = useState("");
    const [openCommand, setOpenCommand] = useState(null);
    const [showAllSqlExecutions, setShowAllSqlExecutions] = useState(false);
    const datasetLimit = 10;

    const fabricItems = payload?.fabricItems ?? [];
    const fabricExecutions = payload?.fabricExecutions ?? [];
    const fabricSqlExecutions = payload?.fabricSqlExecutions ?? [];
    const indicators = payload?.indicators ?? null;
    const fabricBounds = useMemo(
      () => getFabricBounds(fabricExecutions, fabricSqlExecutions),
      [fabricExecutions, fabricSqlExecutions],
    );

    const filteredFabricExecutions = useMemo(
      () => filterTimedItems(
        fabricExecutions,
        (item) => formatDateKey(item.startTimeUtc || item.startTime),
        filters.from,
        filters.to,
      ),
      [fabricExecutions, filters.from, filters.to],
    );
    const filteredFabricSqlExecutions = useMemo(
      () => filterTimedItems(
        fabricSqlExecutions,
        (item) => formatDateKey(item.startTime),
        filters.from,
        filters.to,
      ),
      [fabricSqlExecutions, filters.from, filters.to],
    );
    const procedureLeaders = useMemo(
      () => buildStoredProcedureLeaders(filteredFabricSqlExecutions).slice(0, datasetLimit),
      [filteredFabricSqlExecutions, datasetLimit],
    );
    const statementGroups = useMemo(
      () => buildFabricSqlStatementGroups(filteredFabricSqlExecutions),
      [filteredFabricSqlExecutions],
    );
    const slowestItems = (indicators?.fabric?.executions?.slowestItems ?? []).slice(0, datasetLimit);
    const failingItems = (indicators?.fabric?.executions?.mostFailures ?? []).slice(0, datasetLimit);
    const selectedGroup = statementGroups.find(
      (item) => item.statementType === selectedStatementType,
    ) || statementGroups[0] || null;
    const selectedSqlExecutions = useMemo(
      () => filteredFabricSqlExecutions.filter(
        (item) => normalizeStatementType(item.statementType) === (selectedGroup?.statementType || ""),
      ),
      [filteredFabricSqlExecutions, selectedGroup],
    );
    const rankedSqlExecutions = useMemo(
      () => [...selectedSqlExecutions].sort((left, right) => {
        const leftAnomaly = describeSqlExecutionAnomaly(left, selectedGroup);
        const rightAnomaly = describeSqlExecutionAnomaly(right, selectedGroup);
        if (leftAnomaly.isSlow !== rightAnomaly.isSlow) {
          return leftAnomaly.isSlow ? -1 : 1;
        }
        return String(right.startTime ?? "").localeCompare(String(left.startTime ?? ""));
      }),
      [selectedSqlExecutions, selectedGroup],
    );
    const slowSqlExecutions = useMemo(
      () => rankedSqlExecutions.filter((item) => describeSqlExecutionAnomaly(item, selectedGroup).isSlow),
      [rankedSqlExecutions, selectedGroup],
    );
    const visibleSqlExecutions = showAllSqlExecutions || !slowSqlExecutions.length
      ? rankedSqlExecutions
      : slowSqlExecutions;

    useEffect(() => {
      if (!statementGroups.length) {
        if (selectedStatementType) {
          setSelectedStatementType("");
        }
        return;
      }
      if (!statementGroups.some((item) => item.statementType === selectedStatementType)) {
        setSelectedStatementType(statementGroups[0].statementType);
      }
    }, [selectedStatementType, statementGroups]);

    useEffect(() => {
      setShowAllSqlExecutions(false);
    }, [selectedGroup?.statementType, filters.from, filters.to]);

    if (!payload) {
      return h(LoadingState, {
        title: "Chargement de Fabric",
        body: "Pr\u00e9paration des warehouses, lakehouses et ex\u00e9cutions SQL.",
      });
    }

    return h("div", { className: "dynamic-react-shell" }, [
      h("div", { className: "dynamic-grid", key: "grid" }, [
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Fabric",
          title: "Inventaire warehouses et lakehouses",
          headerRight: h(
            "span",
            { className: "table-meta", key: "meta" },
            `${formatNumber(fabricItems.length)} item(s) | ${formatNumber((indicators?.fabric?.inventory?.sqlEnabledItems) ?? fabricItems.filter((item) => item.isSqlEnabled).length)} SQL actif(s)`,
          ),
          children: renderSimpleList(
            fabricItems,
            "Aucun item Fabric n'est encore historis\u00e9.",
            (item) => h(ListItem, {
              key: item.itemId || item.itemName,
              title: item.itemName ?? item.itemId ?? "Item Fabric",
              body: [
                translateFabricItemType(item.itemType),
                item.workspaceName,
                item.isSqlEnabled ? "SQL activ\u00e9" : "SQL indisponible",
              ].filter(Boolean).join(" | "),
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Activit\u00e9",
          title: "Filtrer l'activit\u00e9 Fabric",
          headerRight: fabricBounds
            ? h(
              "span",
              { className: "table-meta", key: "meta" },
              `${formatShortDate(fabricBounds.min)} -> ${formatShortDate(fabricBounds.max)}`,
            )
            : null,
          children: h("div", { className: "filter-bar", key: "filters" }, [
            h("label", { className: "filter-field", key: "from" }, [
              h("span", { key: "label" }, "Du"),
              h("input", {
                className: "filter-input",
                type: "date",
                min: fabricBounds?.min || undefined,
                max: fabricBounds?.max || undefined,
                value: filters.from,
                onChange: (event) => setFilters((previous) => ({ ...previous, from: event.target.value })),
              }),
            ]),
            h("label", { className: "filter-field", key: "to" }, [
              h("span", { key: "label" }, "Au"),
              h("input", {
                className: "filter-input",
                type: "date",
                min: fabricBounds?.min || undefined,
                max: fabricBounds?.max || undefined,
                value: filters.to,
                onChange: (event) => setFilters((previous) => ({ ...previous, to: event.target.value })),
              }),
            ]),
            h("div", { className: "react-range-actions", key: "reset-wrap" }, [
              h(
                "button",
                {
                  className: "action-button tertiary react-reset-button",
                  type: "button",
                  onClick: () => setFilters({ from: "", to: "" }),
                },
                "R\u00e9initialiser",
              ),
            ]),
          ]),
        }),
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "Dur\u00e9e",
          title: "Items Fabric les plus lents",
          children: renderSimpleList(
            slowestItems,
            "Aucun item lent n'a encore \u00e9t\u00e9 calcul\u00e9.",
            (item) => h(ListItem, {
              key: item.itemId || item.itemName,
              title: item.itemName ?? item.itemId ?? "Item Fabric",
              body: `${translateFabricItemType(item.itemType)} | moyenne ${formatDuration(item.averageDurationSeconds)} | maximum ${formatDuration(item.maximumDurationSeconds)}`,
              meterPercent: toPercent(
                item.averageDurationSeconds,
                item.maximumDurationSeconds || item.averageDurationSeconds || 1,
              ),
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "Fiabilit\u00e9",
          title: "Items Fabric avec le plus d'\u00e9checs",
          children: renderSimpleList(
            failingItems,
            "Aucun \u00e9chec Fabric n'a encore \u00e9t\u00e9 historis\u00e9.",
            (item) => h(ListItem, {
              key: item.itemId || item.itemName,
              title: item.itemName ?? item.itemId ?? "Item Fabric",
              body: `${translateFabricItemType(item.itemType)} | ${formatNumber(item.failureCount)} \u00e9chec(s)`,
              meterPercent: indicators?.fabric?.executions?.failed
                ? (Number(item.failureCount ?? 0) / Number(indicators.fabric.executions.failed)) * 100
                : 100,
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "SQL",
          title: "Proc\u00e9dures stock\u00e9es les plus lentes",
          headerRight: h(
            "span",
            { className: "table-meta", key: "meta" },
            `${formatNumber(filteredFabricSqlExecutions.length)} ex\u00e9cution(s) SQL sur la p\u00e9riode`,
          ),
          children: renderSimpleList(
            procedureLeaders,
            "Aucune proc\u00e9dure stock\u00e9e n'appara\u00eet sur la p\u00e9riode choisie.",
            (item) => h(ListItem, {
              key: item.procedureName,
              title: item.procedureName,
              body: `Moyenne ${formatDuration(item.averageDurationSeconds)} | Maximum ${formatDuration(item.maximumDurationSeconds)} | ${item.latestItemName ?? "Item inconnu"}`,
              meterPercent: toPercent(
                item.averageDurationSeconds,
                item.maximumDurationSeconds || item.averageDurationSeconds || 1,
              ),
            }),
          ),
        }),
        h(DetailCard, {
          spanClass: "span-6",
          kicker: "Vue rapide",
          title: "Activit\u00e9 SQL et OneLake",
          children: h("div", { className: "breakdown-grid" }, [
            h("div", { className: "breakdown-card", key: "warehouses" }, [
              h("h4", { key: "title" }, "Warehouses"),
              h("p", { className: "metric-value", key: "value" }, formatNumber(indicators?.fabric?.inventory?.warehouseCount ?? 0)),
            ]),
            h("div", { className: "breakdown-card", key: "lakehouses" }, [
              h("h4", { key: "title" }, "Lakehouses"),
              h("p", { className: "metric-value", key: "value" }, formatNumber(indicators?.fabric?.inventory?.lakehouseCount ?? 0)),
            ]),
            h("div", { className: "breakdown-card", key: "sql" }, [
              h("h4", { key: "title" }, "Ex\u00e9cutions SQL"),
              h("p", { className: "metric-value", key: "value" }, formatNumber(indicators?.fabric?.procedures?.sqlExecutionCount ?? filteredFabricSqlExecutions.length)),
            ]),
            h("div", { className: "breakdown-card", key: "stored" }, [
              h("h4", { key: "title" }, "Proc\u00e9dures suivies"),
              h("p", { className: "metric-value", key: "value" }, formatNumber(indicators?.fabric?.procedures?.storedProcedureExecutionCount ?? procedureLeaders.length)),
            ]),
          ]),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "exec_requests_history",
          title: "Historique SQL group\u00e9 par statement type",
          headerRight: h("div", { className: "table-actions", key: "actions" }, [
            h(
              "span",
              { className: "table-meta", key: "meta" },
              `${formatNumber(statementGroups.length)} type(s) visible(s) | ${formatNumber(slowSqlExecutions.length)} lente(s) | ${formatNumber(selectedSqlExecutions.length)} ex\u00e9cution(s)`,
            ),
            selectedSqlExecutions.length > slowSqlExecutions.length && slowSqlExecutions.length
              ? h(
                "button",
                {
                  className: "action-button tertiary",
                  type: "button",
                  key: "toggle-all",
                  onClick: () => setShowAllSqlExecutions((previous) => !previous),
                },
                showAllSqlExecutions ? "Voir seulement les lentes" : "Afficher tout",
              )
              : null,
          ]),
          children: h(Fragment, null, [
            h("div", { className: "filter-bar filter-bar-sql", key: "sql-filters" }, [
              h("label", { className: "filter-field", key: "statement-type" }, [
                h("span", { key: "label" }, "Statement type"),
                h("select", {
                  className: "filter-input",
                  value: selectedGroup?.statementType || "",
                  onChange: (event) => setSelectedStatementType(event.target.value),
                }, statementGroups.map((item) => h(
                  "option",
                  { key: item.statementType, value: item.statementType },
                  `${item.statementType} (${formatNumber(item.executionCount)})`,
                ))),
              ]),
              h("div", { className: "sql-summary-grid", key: "summary" }, selectedGroup
                ? [
                  h("div", { className: "metric-chip", key: "count" }, [
                    h("span", { key: "label" }, "Ex\u00e9cutions"),
                    h("strong", { key: "value" }, formatNumber(selectedGroup.executionCount)),
                  ]),
                  h("div", { className: "metric-chip", key: "baseline" }, [
                    h("span", { key: "label" }, `Base ${labelBaselineMethod(selectedGroup.baselineMethod)}`),
                    h("strong", { key: "value" }, formatSqlDuration(selectedGroup.baselineDurationSeconds)),
                  ]),
                  h("div", { className: "metric-chip", key: "threshold" }, [
                    h("span", { key: "label" }, "Seuil lent"),
                    h("strong", { key: "value" }, formatSqlDuration(selectedGroup.slowThresholdSeconds)),
                  ]),
                  h("div", {
                    className: `metric-chip ${selectedGroup.slowExecutionCount ? "is-alert" : ""}`.trim(),
                    key: "slow",
                  }, [
                    h("span", { key: "label" }, "Ex\u00e9cutions lentes"),
                    h("strong", { key: "value" }, formatNumber(selectedGroup.slowExecutionCount)),
                  ]),
                ]
                : [
                  h(EmptyState, {
                    className: "empty-state compact-empty",
                    key: "empty",
                    message: "Aucun statement type ne correspond au filtre de dates.",
                  }),
                ]),
            ]),
            visibleSqlExecutions.length
              ? h("div", { className: "table-shell dynamic-table-shell", key: "sql-table-shell" }, [
                h("table", { key: "table" }, [
                  h("thead", { key: "head" }, [
                    h("tr", { key: "row" }, [
                      h("th", { key: "database" }, "Base"),
                      h("th", { key: "login" }, "Login"),
                      h("th", { key: "time" }, "Temps"),
                      h("th", { key: "program" }, "Program"),
                      h("th", { key: "command" }, "Commande"),
                    ]),
                  ]),
                  h("tbody", { key: "body" }, visibleSqlExecutions.map((item, index) => {
                    const anomaly = describeSqlExecutionAnomaly(item, selectedGroup);
                    return h(
                      "tr",
                      {
                        className: anomaly.isSlow ? "table-row-slow" : "",
                        key: item.queryId || `${item.itemId || "sql"}-${item.startTime || index}`,
                      },
                      [
                        h("td", { key: "database" }, [
                          h("div", { className: "table-cell-title", key: "title" }, item.databaseName ?? item.itemName ?? "Base inconnue"),
                          h("div", { className: "table-cell-note", key: "note" }, item.statementType ?? selectedGroup.statementType),
                        ]),
                        h("td", { key: "login" }, item.loginName ?? "N/A"),
                        h("td", { key: "time" }, [
                          h("div", { className: "table-cell-title", key: "duration" }, formatSqlDuration(item.durationSeconds)),
                          h("div", { className: "table-cell-note", key: "start" }, `D\u00e9but: ${formatTimestamp(item.startTime)}`),
                          h("div", { className: "table-cell-note", key: "end" }, `Fin: ${formatTimestamp(item.endTime)}`),
                          h("div", { className: "table-badge-stack", key: "stack" }, [
                            h(Badge, {
                              key: "badge",
                              variant: anomaly.badgeVariant,
                              children: anomaly.label,
                            }),
                            h("div", { className: "table-cell-note", key: "note" }, anomaly.note),
                          ]),
                        ]),
                        h("td", { key: "program" }, item.programName ?? "N/A"),
                        h("td", { key: "command" }, [
                          h(
                            "button",
                            {
                              className: "action-button tertiary command-open-button",
                              type: "button",
                              key: "open",
                              onClick: () => setOpenCommand({
                                databaseName: item.databaseName ?? item.itemName ?? "Base inconnue",
                                command: item.command ?? "Commande indisponible",
                                loginName: item.loginName ?? "N/A",
                                programName: item.programName ?? "N/A",
                                startTime: item.startTime,
                              }),
                            },
                            "Ouvrir",
                          ),
                        ]),
                      ],
                    );
                  })),
                ]),
              ])
              : h(EmptyState, {
                key: "sql-empty",
                message: "Aucune ex\u00e9cution lente n'a \u00e9t\u00e9 d\u00e9tect\u00e9e pour le statement type s\u00e9lectionn\u00e9.",
              }),
          ]),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Ex\u00e9cutions Fabric",
          title: "Ex\u00e9cutions de warehouses et lakehouses",
          headerRight: h(
            "span",
            { className: "table-meta", key: "meta" },
            `${formatNumber(filteredFabricExecutions.length)} ex\u00e9cution(s) sur la p\u00e9riode`,
          ),
          children: renderSimpleList(
            filteredFabricExecutions.slice(0, datasetLimit),
            "Aucune ex\u00e9cution Fabric n'appara\u00eet sur la plage de dates choisie.",
            (item) => h(ListItem, {
              key: item.executionId || `${item.itemId}-${item.startTimeUtc}`,
              header: h("div", { className: "dual-card-header", key: "header" }, [
                h("strong", { key: "title" }, item.itemName ?? item.itemId ?? "Item Fabric"),
                h(Badge, {
                  key: "badge",
                  variant: classifyStatus(item.status),
                  children: translateStatus(item.status),
                }),
              ]),
              body: [
                translateFabricItemType(item.itemType),
                item.invokeType ? `Type ${item.invokeType}` : null,
                `Dur\u00e9e ${formatDuration(item.durationSeconds)}`,
                formatTimestamp(item.startTimeUtc || item.startTime),
              ].filter(Boolean).join(" | "),
              meta: item.failureReasonText
                ? [h("span", { key: "failure" }, item.failureReasonText)]
                : null,
            }),
          ),
        }),
      ]),
      openCommand
        ? h("div", {
          className: "command-modal-backdrop",
          key: "command-modal",
          onClick: () => setOpenCommand(null),
        }, [
          h("div", {
            className: "command-modal",
            key: "modal",
            onClick: (event) => event.stopPropagation(),
          }, [
            h("div", { className: "panel-header panel-header-split", key: "header" }, [
              h("div", { key: "left" }, [
                h("p", { className: "panel-kicker", key: "kicker" }, "Commande"),
                h("h3", { key: "title" }, openCommand.databaseName),
                h("p", { className: "dynamic-subtitle", key: "meta" }, [
                  `${openCommand.loginName} | ${openCommand.programName} | ${formatTimestamp(openCommand.startTime)}`,
                ]),
              ]),
              h(
                "button",
                {
                  className: "action-button tertiary command-close-button",
                  type: "button",
                  key: "close",
                  onClick: () => setOpenCommand(null),
                },
                "Fermer",
              ),
            ]),
            h("pre", { className: "command-modal-code", key: "code" }, openCommand.command),
          ]),
        ])
        : null,
    ]);
  }

  function BreakdownList(props) {
    if (!props.items.length) {
      return h(EmptyState, { message: props.emptyMessage });
    }
    return h(
      "div",
      { className: "stack-list compact" },
      props.items.map((item, index) =>
        h(ListItem, {
          key: `${props.kind}-${index}`,
          title: props.titleAccessor(item),
          body: `${formatNumber(item.count ?? 0)} incident(s)`,
        }),
      ),
    );
  }

  function IncidentsApp() {
    const payload = useBridgePayload(panelsBridge);
    const [selectedCause, setSelectedCause] = useState("all");
    const [visibleCount, setVisibleCount] = useState(8);

    const incidents = payload?.incidents ?? [];
    const indicators = payload?.indicators ?? null;
    const causeCards = indicators?.incidents?.byCauseType ?? [];
    const filteredIncidents = useMemo(() => {
      if (selectedCause === "all") {
        return [...incidents].sort(
          (left, right) => new Date(right.detectedAt ?? 0).getTime() - new Date(left.detectedAt ?? 0).getTime(),
        );
      }

      return incidents
        .filter((item) => normalizeCauseKey(item.suspectedCause) === selectedCause)
        .sort(
          (left, right) => new Date(right.detectedAt ?? 0).getTime() - new Date(left.detectedAt ?? 0).getTime(),
        );
    }, [incidents, selectedCause]);

    useEffect(() => {
      setVisibleCount(8);
    }, [selectedCause]);

    if (!payload) {
      return h(LoadingState, {
        title: "Chargement des incidents",
        body: "Pr\u00e9paration des causes, s\u00e9v\u00e9rit\u00e9s et recommandations.",
      });
    }

    const visibleHigh = filteredIncidents.filter(
      (item) => translateSeverity(item.severity).toLowerCase() === "haute",
    ).length;
    const uniqueDatasets = new Set(filteredIncidents.map((item) => item.datasetId || item.datasetName).filter(Boolean)).size;

    return h("div", { className: "dynamic-react-shell" }, [
      h("div", { className: "dynamic-grid", key: "grid" }, [
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Causes",
          title: "Incidents par type de cause",
          note: "Un clic sur une cause filtre directement la liste des incidents.",
          headerRight: h("div", { className: "table-actions", key: "actions" }, [
            h("span", { className: "table-meta", key: "meta" }, [
              `${formatNumber(filteredIncidents.length)} incident(s) visible(s)`,
              " | ",
              `${formatNumber(visibleHigh)} s\u00e9v\u00e9rit\u00e9 haute`,
              " | ",
              `${formatNumber(uniqueDatasets)} dataset(s) touch\u00e9(s)`,
            ].join("")),
            selectedCause !== "all"
              ? h(
                "button",
                {
                  className: "action-button tertiary",
                  type: "button",
                  onClick: () => setSelectedCause("all"),
                },
                "Tout voir",
              )
              : null,
          ]),
          children: causeCards.length
            ? h("div", { className: "cause-grid" }, causeCards.map((item) => {
              const label = translateCause(item.causeType);
              const causeKey = normalizeCauseKey(label);
              const isActive = selectedCause === causeKey;
              return h(
                "button",
                {
                  key: label,
                  type: "button",
                  className: `cause-card ${isActive ? "is-active" : ""}`.trim(),
                  onClick: () => setSelectedCause(isActive ? "all" : causeKey),
                },
                [
                  h("span", { className: "highlight-label", key: "label" }, "Cause"),
                  h("strong", { key: "title" }, label),
                  h("p", { className: "highlight-note", key: "count" }, `${formatNumber(item.count)} incident(s)`),
                ],
              );
            }))
            : h(EmptyState, { message: "Aucune cause d'incident n'est encore disponible." }),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "Suivi",
          title: "Incidents r\u00e9cents et actions",
          note: selectedCause === "all"
            ? "La liste montre tous les incidents r\u00e9cents."
            : `Filtre actif: ${translateCause(selectedCause)}.`,
          headerRight: h("div", { className: "table-actions", key: "actions" }, [
            h("span", { className: "table-meta", key: "meta" }, `${formatNumber(filteredIncidents.length)} incident(s) filtr(e)s`),
            filteredIncidents.length > visibleCount
              ? h(
                "button",
                {
                  className: "action-button tertiary",
                  type: "button",
                  onClick: () => setVisibleCount((previous) => previous + 8),
                },
                "Afficher plus",
              )
              : null,
          ]),
          children: filteredIncidents.length
            ? h(
              "div",
              { className: "stack-list" },
              filteredIncidents.slice(0, visibleCount).map((item, index) =>
                h(ListItem, {
                  key: item.incidentId || `${item.datasetId || item.datasetName}-${item.incidentType || "incident"}-${item.detectedAt || index}`,
                  header: h("div", { className: "incident-card-header", key: "header" }, [
                    h("div", { className: "incident-card-headline", key: "left" }, [
                      h("strong", { key: "title" }, item.datasetName ?? item.datasetId ?? "Dataset"),
                      h("span", { className: "list-note", key: "workspace" }, item.workspaceName ?? item.workspaceId ?? "Workspace"),
                    ]),
                    h("div", { className: "chip-row", key: "badges" }, [
                      h(Badge, { key: "severity", variant: classifySeverity(item.severity), children: translateSeverity(item.severity) }),
                      h(Badge, { key: "type", variant: "warning", children: translateIncidentType(item.incidentType) }),
                    ]),
                  ]),
                  body: `${translateCause(item.suspectedCause ?? "Cause non renseign\u00e9e")} | ${item.recommendation ?? "Aucune recommandation."}`,
                  meta: [
                    h("span", { className: "stat-pill", key: "time" }, formatTimestamp(item.detectedAt)),
                  ],
                }),
              ),
            )
            : h(EmptyState, { message: "Aucun incident ne correspond aux filtres choisis." }),
        }),
        h(DetailCard, {
          spanClass: "span-12",
          kicker: "R\u00e9partition",
          title: "Incidents techniques",
          note: "Gateway, capacit\u00e9, identifiants et sources de donn\u00e9es sont maintenant lisibles dans une seule zone interactive.",
          children: h("div", { className: "breakdown-grid" }, [
            h("div", { className: "breakdown-card", key: "gateway" }, [
              h("h4", { key: "title" }, "Incidents li\u00e9s \u00e0 la gateway"),
              h(BreakdownList, {
                key: "list",
                kind: "gateway",
                items: indicators?.incidents?.byGateway ?? [],
                emptyMessage: "Aucun incident li\u00e9 \u00e0 la gateway.",
                titleAccessor: (item) => item.gatewayId ?? "Gateway inconnue",
              }),
            ]),
            h("div", { className: "breakdown-card", key: "capacity" }, [
              h("h4", { key: "title" }, "Incidents li\u00e9s \u00e0 la capacit\u00e9"),
              h(BreakdownList, {
                key: "list",
                kind: "capacity",
                items: indicators?.incidents?.byCapacity ?? [],
                emptyMessage: "Aucun incident de capacit\u00e9.",
                titleAccessor: (item) => item.capacityId ?? "Capacit\u00e9 partag\u00e9e",
              }),
            ]),
            h("div", { className: "breakdown-card", key: "credentials" }, [
              h("h4", { key: "title" }, "Incidents li\u00e9s aux identifiants"),
              h("div", { className: "metric-strip", key: "metrics" }, [
                h("div", { className: "metric-chip", key: "count" }, [
                  h("span", { key: "label" }, "Incidents li\u00e9s aux identifiants"),
                  h("strong", { key: "value" }, formatNumber(indicators?.incidents?.credentialsRelated ?? 0)),
                ]),
                h("div", { className: "metric-chip", key: "share" }, [
                  h("span", { key: "label" }, "Part des incidents"),
                  h("strong", { key: "value" }, indicators?.totals?.incidents
                    ? formatRate((Number(indicators.incidents.credentialsRelated ?? 0) / Number(indicators.totals.incidents)))
                    : "0,0%"),
                ]),
              ]),
            ]),
            h("div", { className: "breakdown-card", key: "source" }, [
              h("h4", { key: "title" }, "Incidents li\u00e9s aux sources de donn\u00e9es"),
              h(BreakdownList, {
                key: "list",
                kind: "source",
                items: indicators?.incidents?.byDataSource ?? [],
                emptyMessage: "Aucun incident de source de donn\u00e9es.",
                titleAccessor: (item) => item.datasourceType ?? "Source inconnue",
              }),
            ]),
          ]),
        }),
      ]),
    ]);
  }

  const graphRootElement = document.getElementById("reactGraphsRoot");
  if (graphRootElement) {
    if (typeof window.ReactDOM.createRoot === "function") {
      window.ReactDOM.createRoot(graphRootElement).render(h(GraphsApp));
    } else if (typeof window.ReactDOM.render === "function") {
      window.ReactDOM.render(h(GraphsApp), graphRootElement);
    }
  }

  const performanceRootElement = document.getElementById("reactPerformanceRoot");
  if (performanceRootElement) {
    if (typeof window.ReactDOM.createRoot === "function") {
      window.ReactDOM.createRoot(performanceRootElement).render(h(PerformanceApp));
    } else if (typeof window.ReactDOM.render === "function") {
      window.ReactDOM.render(h(PerformanceApp), performanceRootElement);
    }
  }

  const fabricRootElement = document.getElementById("reactFabricRoot");
  if (fabricRootElement) {
    if (typeof window.ReactDOM.createRoot === "function") {
      window.ReactDOM.createRoot(fabricRootElement).render(h(FabricApp));
    } else if (typeof window.ReactDOM.render === "function") {
      window.ReactDOM.render(h(FabricApp), fabricRootElement);
    }
  }

  const incidentsRootElement = document.getElementById("reactIncidentsRoot");
  if (incidentsRootElement) {
    if (typeof window.ReactDOM.createRoot === "function") {
      window.ReactDOM.createRoot(incidentsRootElement).render(h(IncidentsApp));
    } else if (typeof window.ReactDOM.render === "function") {
      window.ReactDOM.render(h(IncidentsApp), incidentsRootElement);
    }
  }
})();
