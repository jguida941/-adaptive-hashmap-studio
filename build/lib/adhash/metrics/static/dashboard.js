const summary = document.getElementById('summary');
const comparisonSummary = document.getElementById('comparison-summary');
const banner = document.getElementById('alert-banner');
const eventsLog = document.getElementById('events-log');

const canvases = {
  throughput: document.getElementById('chart-throughput'),
  load: document.getElementById('chart-load'),
  probeAvg: document.getElementById('chart-probe'),
  tombstone: document.getElementById('chart-tombstone'),
  latency: document.getElementById('chart-latency'),
  probeHist: document.getElementById('chart-probe-hist'),
  heatmap: document.getElementById('chart-heatmap'),
};

const tokenMeta = document.querySelector('meta[name="adhash-token"]');
const apiToken = tokenMeta ? tokenMeta.content : '';
const hasAuthToken = Boolean(apiToken);

if (hasAuthToken && window.location.search.includes('token=')) {
  const url = new URL(window.location.href);
  url.searchParams.delete('token');
  window.history.replaceState({}, document.title, url.toString());
}

function withAuthHeaders(init = {}) {
  const headers = new Headers(init.headers || {});
  if (hasAuthToken) {
    headers.set('Authorization', `Bearer ${apiToken}`);
  }
  return { ...init, headers };
}

function fetchJson(url, init = {}) {
  const opts = withAuthHeaders(init);
  const headers = new Headers(opts.headers || {});
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }
  opts.headers = headers;
  return fetch(url, opts).then((res) => {
    if (!res.ok) {
      const error = new Error(`Request failed with status ${res.status}`);
      error.response = res;
      throw error;
    }
    return res.json();
  });
}

function authorizedFetch(url, init = {}) {
  return fetch(url, withAuthHeaders(init));
}

let comparisonData = null;

const pollSelect = document.getElementById('poll-interval');
const downloadButton = document.getElementById('download-timeline');
let pollIntervalMs = 2000;
let pollTimer = null;

const scheduleNextPoll = () => {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
  }
  pollTimer = window.setTimeout(poll, pollIntervalMs);
};

if (pollSelect) {
  pollSelect.value = String(pollIntervalMs);
  pollSelect.addEventListener('change', (event) => {
    const value = Number(event.target.value);
    if (Number.isFinite(value)) {
      pollIntervalMs = Math.max(500, value);
    }
    scheduleNextPoll();
  });
}

function updateDownloadLink(limit = MAX_POINTS) {
  if (!downloadButton) {
    return;
  }
  const safeLimit = Math.max(1, Math.min(Math.floor(limit), MAX_POINTS));
  downloadButton.href = `/api/metrics/history.csv?limit=${safeLimit}`;
}

if (downloadButton && hasAuthToken) {
  downloadButton.addEventListener('click', (event) => {
    event.preventDefault();
    const href = downloadButton.getAttribute('href');
    if (!href) {
      return;
    }
    authorizedFetch(href, { headers: { Accept: 'text/csv' } })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Timeline download failed (${res.status})`);
        }
        return res.blob();
      })
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        const tempLink = document.createElement('a');
        tempLink.href = objectUrl;
        tempLink.download = downloadButton.getAttribute('download') || 'timeline.csv';
        document.body.appendChild(tempLink);
        tempLink.click();
        tempLink.remove();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      })
      .catch((err) => {
        console.error('timeline download failed', err);
      });
  });
}

const MAX_POINTS = 1200;
const WINDOW_SECONDS = 120;

const state = {
  baseTime: 0,
  throughput: [],
  throughputMarkers: [],
  load: [],
  probeAvg: [],
  tombstone: [],
  latencyLabels: [],
  latencyValues: [],
  probeLabels: [],
  probeValues: [],
  heatmapMatrix: [],
  heatmapMax: 0,
  heatmapTotal: 0,
  latestTick: {},
  backendName: '',
  windowSeconds: WINDOW_SECONDS,
  idle: false,
  runCompleted: false,
  runCompleted: false,
  seriesStats: {
    throughput: { windowPeak: undefined, windowMin: undefined, sessionPeak: undefined },
    load: { min: 0, max: 0 },
    probeAvg: { min: 0, max: 0 },
    tombstone: { min: 0, max: 0 },
  },
  heldMax: { throughput: 0, load: 0, probeAvg: 0, tombstone: 0 },
  displayUnits: {}, // reserved if you later want to lock units per series
};

let lastHistoryStamp = 0;
let lastLatencyStamp = 0;
let lastProbeStamp = 0;
let lastHeatmapStamp = 0;
let hasRendered = false;
let renderPending = false;
const resizeObservers = [];

function safeNumber(value, fallback = NaN) {
  if (value === undefined || value === null) {
    return fallback;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function eventSignature(event) {
  const type = typeof event?.type === 'string' ? event.type : '';
  const backend = typeof event?.backend === 'string' ? event.backend : '';
  const message = typeof event?.message === 'string' ? event.message : '';
  const time = safeNumber(event?.t, NaN);
  return `${type}|${backend}|${message}|${Number.isFinite(time) ? time.toFixed(6) : 'nan'}`;
}

function dedupeEvents(events) {
  const seen = new Set();
  const filtered = [];
  for (const event of events) {
    const key = eventSignature(event);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    filtered.push(event);
    if (filtered.length >= 20) {
      break;
    }
  }
  return filtered;
}

function formatLatencyLabel(label) {
  if (label === '+Inf') {
    return '≤∞';
  }
  const value = Number(label);
  if (!Number.isFinite(value)) {
    return `≤${label}`;
  }
  if (value >= 1) {
    return `≤${value.toFixed(1)} s`;
  }
  if (value >= 0.001) {
    return `≤${(value * 1000).toFixed(0)} ms`;
  }
  if (value >= 0.000001) {
    return `≤${(value * 1_000_000).toFixed(0)} µs`;
  }
  return `≤${(value * 1_000_000_000).toFixed(0)} ns`;
}

function formatCompactNumber(value, decimals = 2) {
  if (!Number.isFinite(value)) {
    return 'n/a';
  }
  const abs = Math.abs(value);
  let scaled = value;
  let suffix = '';
  if (abs >= 1_000_000_000) {
    scaled = value / 1_000_000_000;
    suffix = 'B';
  } else if (abs >= 1_000_000) {
    scaled = value / 1_000_000;
    suffix = 'M';
  } else if (abs >= 1_000) {
    scaled = value / 1_000;
    suffix = 'K';
  }
  let precision;
  if (suffix === 'K' && abs < 100_000) {
    precision = abs < 10_000 ? 2 : 1;
  } else {
    precision = abs >= 100 ? 0 : abs >= 10 ? 1 : decimals;
  }
  return `${scaled.toFixed(precision)}${suffix}`;
}

function formatValue(value, options = {}) {
  const { decimals = 2, compact = true } = options;
  if (!Number.isFinite(value)) {
    return 'n/a';
  }
  if (!compact) {
    return value.toFixed(decimals);
  }
  return formatCompactNumber(value, decimals);
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return 'n/a';
  }
  if (seconds >= 3600) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs.toFixed(1)}s`;
  }
  if (seconds >= 1) {
    return `${seconds.toFixed(1)}s`;
  }
  return `${(seconds * 1000).toFixed(0)}ms`;
}

function mmssFromSeconds(value) {
  const seconds = Math.max(0, Math.round(Number(value) || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function mmssFloorSeconds(value) {
  const seconds = Math.max(0, Math.floor(Number(value) || 0));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, '0')}`;
}

function trimmedExtents(values, options = {}) {
  const finite = values.filter((value) => Number.isFinite(value));
  if (!finite.length) {
    return { min: NaN, max: NaN };
  }
  const sorted = finite.slice().sort((a, b) => a - b);
  const trim = Math.max(0, Math.min(0.49, Number(options.trim) || 0));
  const lower = Math.floor(sorted.length * trim);
  const upper = Math.ceil(sorted.length * (1 - trim)) - 1;
  return {
    min: sorted[Math.max(0, Math.min(sorted.length - 1, lower))],
    max: sorted[Math.max(0, Math.min(sorted.length - 1, upper))],
  };
}

function calculateAutoY(ys, baseMin, baseMax, options = {}) {
  let minY = baseMin;
  let maxY = baseMax;
  if (!options.auto) {
    return { min: minY, max: maxY };
  }

  const { min: trimmedMin, max: trimmedMax } = trimmedExtents(ys, { trim: options.trim ?? 0.02 });
  if (Number.isFinite(trimmedMin) && !Number.isFinite(options.lockMin)) {
    minY = trimmedMin;
  }
  if (Number.isFinite(trimmedMax) && !Number.isFinite(options.lockMax)) {
    maxY = trimmedMax;
  }

  let span = maxY - minY;
  if (!Number.isFinite(span) || span <= 0) {
    span = Math.max(Math.abs(maxY), 1) * 0.25;
  }

  const padTop = Number.isFinite(options.padTop) ? options.padTop : 0.1;
  const padBottom = Number.isFinite(options.padBottom) ? options.padBottom : 0.04;
  minY -= span * padBottom;
  maxY += span * padTop;

  if (Number.isFinite(options.floor)) {
    minY = Math.max(minY, options.floor);
  }
  if (Number.isFinite(options.ceiling)) {
    maxY = Math.min(maxY, options.ceiling);
  }

  if (Number.isFinite(options.lockMin)) {
    minY = options.lockMin;
  }
  if (Number.isFinite(options.lockMax)) {
    maxY = options.lockMax;
  }

  if (minY === maxY) {
    const epsilon = Math.max(1e-6, Math.abs(maxY) * 0.05 || 0.05);
    minY -= epsilon;
    maxY += epsilon;
  }
  return { min: minY, max: maxY };
}

function niceTicks(min, max, count = 5) {
  const span = max - min;
  if (!Number.isFinite(span) || span <= 0) {
    return [min];
  }
  const stepBase = Math.pow(10, Math.floor(Math.log10(span / count)));
  const error = (span / count) / stepBase;
  const factor = error >= 7.5 ? 10 : error >= 3 ? 5 : error >= 1.5 ? 2 : 1;
  const step = factor * stepBase;
  const firstTick = Math.ceil(min / step) * step;
  const ticks = [];
  for (let tick = firstTick; tick <= max + step * 0.5; tick += step) {
    ticks.push(Number(tick.toFixed(12)));
  }
  if (!ticks.length) {
    ticks.push(min);
  }
  return ticks;
}

function effectiveWindowSeconds(span) {
  if (!Number.isFinite(span) || span <= 0) {
    return WINDOW_SECONDS;
  }
  if (span < 10) {
    return 15;
  }
  if (span < 30) {
    return 30;
  }
  if (span < 60) {
    return 60;
  }
  return WINDOW_SECONDS;
}

function normaliseHistory(items) {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((tick) => (tick && Number.isFinite(Number(tick.t)) ? tick : null))
    .filter((tick) => tick !== null)
    .sort((a, b) => Number(a.t) - Number(b.t));
}

function buildThroughputSeries(sorted, base) {
  const points = [];
  for (let i = 0; i < sorted.length; i += 1) {
    const tick = sorted[i];
    const t = safeNumber(tick.t, NaN);
    if (!Number.isFinite(t) || t < base) {
      continue;
    }
    let value = safeNumber(tick.ops_per_second_ema, NaN);
    if (!Number.isFinite(value)) {
      value = safeNumber(tick.ops_per_second_instant, NaN);
    }
    if (!Number.isFinite(value) && i > 0) {
      const prev = sorted[i - 1];
      const dt = safeNumber(tick.t, NaN) - safeNumber(prev.t, NaN);
      const dOps = safeNumber(tick.ops, NaN) - safeNumber(prev.ops, NaN);
      if (Number.isFinite(dt) && dt > 1e-4 && Number.isFinite(dOps)) {
        value = Math.max(0, dOps / dt);
      }
    }
    if (Number.isFinite(value)) {
      points.push({ x: t - base, y: value });
    }
  }
  return points;
}

function buildMetricSeries(sorted, base, extractor) {
  const points = [];
  for (const tick of sorted) {
    const t = safeNumber(tick.t, NaN);
    if (!Number.isFinite(t) || t < base) {
      continue;
    }
    const value = safeNumber(extractor(tick), NaN);
    if (Number.isFinite(value)) {
      points.push({ x: t - base, y: value });
    }
  }
  return points;
}

function deriveThroughput(sorted, index) {
  const tick = sorted[index];
  let value = safeNumber(tick.ops_per_second_ema, NaN);
  if (!Number.isFinite(value)) {
    value = safeNumber(tick.ops_per_second_instant, NaN);
  }
  if (!Number.isFinite(value) && index > 0) {
    const prev = sorted[index - 1];
    const dt = safeNumber(tick.t, NaN) - safeNumber(prev.t, NaN);
    const dOps = safeNumber(tick.ops, NaN) - safeNumber(prev.ops, NaN);
    if (Number.isFinite(dt) && dt > 1e-4 && Number.isFinite(dOps)) {
      value = Math.max(0, dOps / dt);
    }
  }
  return Number.isFinite(value) ? value : NaN;
}

function computeThroughputStats(sorted, base = -Infinity) {
  let peak = -Infinity;
  let floor = Infinity;
  for (let i = 0; i < sorted.length; i += 1) {
    const tick = sorted[i];
    const t = safeNumber(tick.t, NaN);
    if (!Number.isFinite(t) || t < base) {
      continue;
    }
    const value = deriveThroughput(sorted, i);
    if (Number.isFinite(value)) {
      peak = Math.max(peak, value);
      floor = Math.min(floor, value);
    }
  }
  return {
    max: peak > -Infinity ? peak : NaN,
    min: floor < Infinity ? floor : NaN,
  };
}

function computeMetricExtents(sorted, base, extractor) {
  let min = Infinity;
  let max = -Infinity;
  sorted.forEach((tick) => {
    const t = safeNumber(tick.t, NaN);
    if (!Number.isFinite(t) || t < base) {
      return;
    }
    const value = safeNumber(extractor(tick), NaN);
    if (Number.isFinite(value)) {
      if (value < min) {
        min = value;
      }
      if (value > max) {
        max = value;
      }
    }
  });
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return { min: NaN, max: NaN };
  }
  return { min, max };
}

// helper to stabilize "max" readout with ~1% hysteresis
function heldMaxFor(seriesName, nextMax) {
  if (!Number.isFinite(nextMax)) {
    return undefined;
  }
  const prev = state.heldMax?.[seriesName] ?? 0;
  const upThresh = 1.01;
  const downThresh = 0.99;

  let held = prev;
  if (!Number.isFinite(prev) || prev <= 0 || nextMax > prev) {
    held = nextMax;
  }
  state.heldMax[seriesName] = held;
  return held;
}

function formatComparisonPacket(packet, options = {}) {
  if (!packet || typeof packet !== 'object') {
    return 'n/a';
  }
  const decimals = Number.isFinite(options.decimals) ? options.decimals : 2;
  const unit = typeof options.unit === 'string' ? options.unit : '';
  const baseline = safeNumber(packet.baseline, NaN);
  const candidate = safeNumber(packet.candidate, NaN);
  const delta = safeNumber(packet.delta, NaN);
  const percent = safeNumber(packet.percent, NaN);

  const formatValueDisplay = (value) => (Number.isFinite(value) ? value.toFixed(decimals) : 'n/a');
  const suffix = unit ? ` ${unit}` : '';

  const baselineText = formatValueDisplay(baseline);
  const candidateText = formatValueDisplay(candidate);
  let deltaText = 'n/a';
  if (Number.isFinite(delta)) {
    const sign = delta > 0 ? '+' : '';
    deltaText = `${sign}${delta.toFixed(decimals)}`;
    if (Number.isFinite(percent)) {
      const pctSign = percent > 0 ? '+' : '';
      deltaText += ` (${pctSign}${percent.toFixed(2)}%)`;
    }
  }
  return `${candidateText}${suffix} vs ${baselineText}${suffix} (${deltaText})`;
}

function renderComparison() {
  if (!comparisonSummary) {
    return;
  }
  if (!comparisonData || comparisonData.schema !== 'adhash.compare.v1') {
    comparisonSummary.classList.add('hidden');
    comparisonSummary.innerHTML = '';
    return;
  }
  const diff = typeof comparisonData.diff === 'object' ? comparisonData.diff : {};
  const baselineLabel = comparisonData?.baseline?.label || 'baseline';
  const candidateLabel = comparisonData?.candidate?.label || 'candidate';
  const overallLatency = diff?.latency_ms?.overall || {};
  const cards = [
    ['Comparison', `${candidateLabel} vs ${baselineLabel}`],
    ['Ops/s', formatComparisonPacket(diff.ops_per_second || {})],
    ['Latency p99', formatComparisonPacket(overallLatency.p99 || {}, { decimals: 3, unit: 'ms' })],
  ];
  comparisonSummary.innerHTML = cards
    .map(([title, value]) => `<div class="card"><strong>${title}</strong><span>${value}</span></div>`)
    .join('');
  comparisonSummary.classList.remove('hidden');
}

function renderSummary(tick) {
  const opsByType = typeof tick.ops_by_type === 'object' && tick.ops_by_type !== null ? tick.ops_by_type : {};
  const cards = [
    ['Backend', tick.backend || 'unknown'],
    ['Total ops', Number(tick.ops || 0).toLocaleString()],
    [
      'Puts / Gets / Dels',
      `${Number(opsByType.put || 0).toLocaleString()} / ${Number(opsByType.get || 0).toLocaleString()} / ${Number(opsByType.del || 0).toLocaleString()}`,
    ],
    ['Load factor', safeNumber(tick.load_factor, 0).toFixed(3)],
    ['Avg probe', safeNumber(tick.avg_probe_estimate, 0).toFixed(3)],
    ['Tombstone ratio', safeNumber(tick.tombstone_ratio, 0).toFixed(3)],
    ['Migrations', Number(tick.migrations || 0).toLocaleString()],
    ['Compactions', Number(tick.compactions || 0).toLocaleString()],
  ];
  summary.innerHTML = cards
    .map(([title, value]) => `<div class="card"><strong>${title}</strong><span>${value}</span></div>`)
    .join('');
}

function updateAlerts(alerts) {
  if (!Array.isArray(alerts) || !alerts.length) {
    banner.classList.add('hidden');
    banner.textContent = '';
    return;
  }
  banner.classList.remove('hidden');
  banner.innerHTML = alerts
    .map((alert) => {
      const metric = alert.metric || 'metric';
      const message = alert.message || 'Threshold crossed';
      const value = typeof alert.value === 'number' ? alert.value.toFixed(3) : 'n/a';
      return `<div><strong>${metric}</strong>: ${message} (value=${value})</div>`;
    })
    .join('');
}

function updateEvents(events) {
  if (!eventsLog) {
    return;
  }
  if (!Array.isArray(events) || !events.length) {
    eventsLog.textContent = 'No migrations, compactions, or resizes yet.';
    return;
  }
  const recent = events.slice(-12).reverse();
  eventsLog.innerHTML = recent
    .map((evt) => {
      const label = evt.type || 'event';
      const backend = evt.backend || 'unknown';
      let timestamp = 'n/a';
      if (typeof evt.t === 'number') {
        const relative = Number.isFinite(state.baseTime) ? Math.max(0, evt.t - state.baseTime) : Math.max(0, evt.t);
        timestamp = mmssFromSeconds(relative);
      }
      const message = evt.message ? ` — ${evt.message}` : '';
      return `<div class="event-row"><strong>${label}</strong> @ ${timestamp} (backend=${backend})${message}</div>`;
    })
    .join('');
}

function getContext(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

function drawBackground(ctx, width, height) {
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, width - 1, height - 1);
}

function drawMessage(ctx, width, height, message) {
  ctx.fillStyle = '#94a3b8';
  ctx.font = '12px system-ui, -apple-system, BlinkMacSystemFont';
  const metrics = ctx.measureText(message);
  ctx.fillText(message, Math.max(12, (width - metrics.width) / 2), height / 2);
}

function drawNotApplicable(canvas, message) {
  const { ctx, width, height } = getContext(canvas);
  drawBackground(ctx, width, height);
  drawMessage(ctx, width, height, message);
}

function drawLineChart(canvas, points, color, options = {}) {
  const title = options.title || '';
  const unitLabel = options.unit || '';
  const yLabel = options.yLabel || unitLabel;
  const decimals = Number.isFinite(options.decimals) ? options.decimals : 2;
  const compact = options.compact !== false;
  const formatY = typeof options.formatY === 'function'
    ? options.formatY
    : (value) => {
        if (unitLabel === 'ratio') {
          return value.toFixed(Math.max(0, decimals));
        }
        return formatValue(value, { decimals, compact });
      };
  const formatStat = typeof options.formatStat === 'function'
    ? options.formatStat
    : (value) => formatValue(value, { decimals, compact });
  const { ctx, width, height } = getContext(canvas);
  drawBackground(ctx, width, height);

  canvas.__lineChartState = null;

  if (!Array.isArray(points) || points.length === 0) {
    drawMessage(ctx, width, height, 'Waiting for data…');
    return;
  }

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const dataMinY = Math.min(...ys);
  const dataMaxY = Math.max(...ys);

  const userMin = Number.isFinite(options.minY) ? options.minY : null;
  const userMax = Number.isFinite(options.maxY) ? options.maxY : null;

  let minY = Number.isFinite(userMin) ? userMin : dataMinY;
  let maxY = Number.isFinite(userMax) ? userMax : dataMaxY;

  const percentMode = options.percent === true;
  if (percentMode) {
    if (dataMaxY >= 0.9 || dataMinY <= 0.05) {
      minY = 0;
      maxY = 1;
    } else {
      const { min: autoMin, max: autoMax } = calculateAutoY(ys, dataMinY, dataMaxY, {
        auto: true,
        floor: 0,
        ceiling: 1,
        padTop: 0.08,
        padBottom: 0.04,
      });
      minY = autoMin;
      maxY = autoMax;
    }
  } else if (options.autoY) {
    const { min: autoMin, max: autoMax } = calculateAutoY(ys, minY, maxY, {
      auto: true,
      trim: options.autoYTrim,
      padTop: options.autoYPadTop,
      padBottom: options.autoYPadBottom,
      floor: options.autoYFloor,
      ceiling: options.autoYCeiling,
      lockMin: userMin,
      lockMax: userMax,
    });
    minY = autoMin;
    maxY = autoMax;
  }

  if (!Number.isFinite(minY) || !Number.isFinite(maxY)) {
    drawMessage(ctx, width, height, 'Not enough data');
    return;
  }
  if (minY === maxY) {
    const pad = Math.max(1e-6, Math.abs(maxY) * 0.05 || 0.05);
    minY -= pad;
    maxY += pad;
  }

  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const left = Math.max(72, Math.min(120, width * 0.18));
  const right = width - Math.max(20, Math.min(80, width * 0.08));
  const topPadding = Math.max(24, Math.min(36, height * 0.06));
  const headerTitleHeight = Math.max(20, Math.min(26, height * 0.06));
  const headerStatsHeight = Math.max(20, Math.min(28, height * 0.065));
  const headerGap = Math.max(32, Math.min(48, height * 0.13));
  const titleBaseline = topPadding + headerTitleHeight;
  const statsBaseline = titleBaseline + headerStatsHeight;
  const top = statsBaseline + headerGap;
  const bottomPadding = Math.max(58, Math.min(92, height * 0.24));
  const minPlotSpan = Math.max(120, height * 0.32);
  let bottom = height - bottomPadding;
  if (bottom - top < minPlotSpan) {
    bottom = Math.min(height - Math.max(20, height * 0.04), top + minPlotSpan);
  }
  const unitSuffix = unitLabel ? (unitLabel === '%' ? unitLabel : ` ${unitLabel}`) : '';

  const plotLeft = left;
  const plotRight = right;
  const plotTop = top;
  const plotBottom = bottom;
  const plotSpanX = plotRight - plotLeft;
  const plotSpanY = plotBottom - plotTop;

  const avg = ys.reduce((total, value) => total + value, 0) / ys.length;
  const peakStat = Number.isFinite(options.peakValue) ? options.peakValue : dataMaxY;
  const floorStat = Number.isFinite(options.statMinValue) ? options.statMinValue : dataMinY;
  const sessionPeakStat = Number.isFinite(options.sessionPeak) ? options.sessionPeak : NaN;

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.32)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(plotLeft, plotTop);
  ctx.lineTo(plotLeft, plotBottom);
  ctx.lineTo(plotRight, plotBottom);
  ctx.stroke();

  const yTickCount = Math.max(2, Math.min(6, Math.round(plotSpanY / 60)));
  const yTicks = niceTicks(minY, maxY, yTickCount);
  const yLabels = yTicks.map((tick) => formatY(tick));
  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px system-ui';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'alphabetic';
  const maxLabelWidth = yLabels.reduce((acc, label) => Math.max(acc, ctx.measureText(label).width), 0);
  const yLabelX = Math.max(16, plotLeft - maxLabelWidth - 14);

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.28)';
  yTicks.forEach((tick, idx) => {
    const ratio = (tick - minY) / spanY;
    const y = plotBottom - ratio * plotSpanY;
    ctx.beginPath();
    ctx.moveTo(plotLeft, y);
    ctx.lineTo(plotRight, y);
    ctx.stroke();
    const label = yLabels[idx];
    ctx.fillText(label, plotLeft - 8, y + 4);
  });

  const zeroRatio = (0 - minY) / spanY;
  const zeroY = plotBottom - zeroRatio * plotSpanY;
  if (!Number.isFinite(options.minY) && !Number.isFinite(options.maxY) && zeroY >= plotTop && zeroY <= plotBottom) {
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.42)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(plotLeft, zeroY);
    ctx.lineTo(plotRight, zeroY);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const minLabelSpacing = Math.max(80, Math.min(120, plotSpanX / 6));
  const xTickCount = Math.max(2, Math.min(8, Math.round(plotSpanX / minLabelSpacing)));
  const xTicks = niceTicks(minX, maxX, xTickCount);
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.32)';
  let lastXLabelRight = -Infinity;
  const seenLabels = new Set();
  ctx.save();
  ctx.font = '11px system-ui';
  ctx.textBaseline = 'top';
  xTicks.forEach((tick) => {
    if (!Number.isFinite(tick) || tick < minX - 1e-6 || tick > maxX + 1e-6) {
      return;
    }
    const ratio = spanX <= 1e-9 ? 0 : (tick - minX) / spanX;
    const x = plotLeft + ratio * plotSpanX;
    ctx.beginPath();
    ctx.moveTo(x, plotBottom);
    ctx.lineTo(x, plotBottom + 4);
    ctx.stroke();
    const relativeSeconds = Math.max(0, tick - minX);
    const label = mmssFloorSeconds(relativeSeconds);
    if (seenLabels.has(label)) {
      return;
    }
    const labelWidth = ctx.measureText(label).width;
    let drawLeft = x - labelWidth / 2;
    let drawRight = drawLeft + labelWidth;
    let drawAlign = 'center';
    let drawX = x;
    if (drawLeft < plotLeft + 4) {
      drawLeft = plotLeft + 4;
      drawRight = drawLeft + labelWidth;
      drawAlign = 'left';
      drawX = drawLeft;
    } else if (drawRight > plotRight - 4) {
      drawRight = plotRight - 4;
      drawLeft = drawRight - labelWidth;
      drawAlign = 'right';
      drawX = drawRight;
    }
    if (drawLeft <= lastXLabelRight + 6) {
      return;
    }
    ctx.textAlign = drawAlign;
    ctx.fillText(label, drawX, plotBottom + 18);
    lastXLabelRight = drawRight;
    seenLabels.add(label);
  });
  ctx.restore();
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';

  ctx.save();
  ctx.beginPath();
  ctx.rect(plotLeft, plotTop, plotSpanX, plotSpanY);
  ctx.clip();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  const pixelPoints = [];
  points.forEach((point, index) => {
    const xRatio = spanX <= 1e-9 ? 0 : (point.x - minX) / spanX;
    const yRatio = spanY <= 1e-12 ? 0 : (point.y - minY) / spanY;
    const x = plotLeft + xRatio * plotSpanX;
    const y = plotBottom - yRatio * plotSpanY;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
    pixelPoints.push({ x, y, value: point.y, time: point.x });
  });
  ctx.stroke();
  ctx.restore();

  const tooltipFormatter = typeof options.tooltipFormatter === 'function'
    ? options.tooltipFormatter
    : (pointInfo) => `${formatStat(pointInfo.value)}${unitSuffix}`;

  canvas.__lineChartState = {
    points: pixelPoints,
    plot: { left: plotLeft, right: plotRight, top: plotTop, bottom: plotBottom },
    formatter: tooltipFormatter,
    timeFormatter: mmssFromSeconds,
    unit: unitSuffix.trim(),
    minX,
    maxX,
    stats: {
      maxValue: peakStat,
      avgValue: avg,
      minValue: floorStat,
      sessionMaxValue: sessionPeakStat,
      unit: unitSuffix.trim(),
      format: (value) => formatStat(value),
    },
  };
  bindLineChartTooltip(canvas);

  const markers = Array.isArray(options.markers) ? options.markers : [];
  if (markers.length) {
    markers.forEach((marker, index) => {
      const markerValue = Number(marker && marker.x);
      if (!Number.isFinite(markerValue)) {
        return;
      }
      const ratio = spanX <= 1e-9 ? 0 : (markerValue - minX) / spanX;
      if (ratio < 0 || ratio > 1) {
        return;
      }
      const markerX = plotLeft + ratio * plotSpanX;
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
      ctx.beginPath();
      ctx.moveTo(markerX, plotTop);
      ctx.lineTo(markerX, plotBottom);
      ctx.stroke();
      ctx.restore();

      const label = typeof marker.label === 'string' ? marker.label : '';
      if (label) {
        ctx.save();
        ctx.font = '10px system-ui';
        const textWidth = ctx.measureText(label).width;
        const clampedX = Math.min(Math.max(markerX, plotLeft + textWidth / 2 + 8), plotRight - textWidth / 2 - 8);
        const baseY = plotTop + 6 + (index % 2) * 18;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.78)';
        ctx.fillRect(clampedX - textWidth / 2 - 6, baseY - 4, textWidth + 12, 18);
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.32)';
        ctx.strokeRect(clampedX - textWidth / 2 - 6, baseY - 4, textWidth + 12, 18);
        ctx.fillStyle = '#e2e8f0';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(label, clampedX, baseY);
        ctx.restore();
      }
    });
  }

  ctx.fillStyle = '#cbd5f5';
  ctx.font = '12px system-ui';
  if (title) {
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(title, plotLeft + plotSpanX / 2, titleBaseline);
    ctx.restore();
  }

  if (Number.isFinite(peakStat) || Number.isFinite(avg) || Number.isFinite(floorStat)) {
    const statParts = [];
    if (Number.isFinite(peakStat)) {
      statParts.push(`max ${formatStat(peakStat)}${unitSuffix}`);
    }
    if (Number.isFinite(avg)) {
      statParts.push(`avg ${formatStat(avg)}${unitSuffix}`);
    }
    if (Number.isFinite(floorStat)) {
      statParts.push(`min ${formatStat(floorStat)}${unitSuffix}`);
    }
    if (Number.isFinite(sessionPeakStat) && (!Number.isFinite(peakStat) || sessionPeakStat > peakStat * 1.01)) {
      statParts.push(`session ${formatStat(sessionPeakStat)}${unitSuffix}`);
    }
    if (statParts.length) {
      ctx.save();
      ctx.font = '11px system-ui';
      ctx.fillStyle = '#94a3b8';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(statParts.join(' · '), plotLeft + plotSpanX / 2, statsBaseline);
      ctx.restore();
    }
  }

  if (options.idle) {
    const badgeText = 'IDLE';
    ctx.save();
    ctx.font = '10px system-ui';
    const badgeWidth = ctx.measureText(badgeText).width + 12;
    const badgeHeight = 18;
    const badgeX = plotRight - badgeWidth - 6;
    const badgeY = Math.max(topPadding + 6, statsBaseline - badgeHeight - 6);
    ctx.fillStyle = 'rgba(251, 191, 36, 0.18)';
    ctx.fillRect(badgeX, badgeY, badgeWidth, badgeHeight);
    ctx.strokeStyle = 'rgba(250, 204, 21, 0.8)';
    ctx.strokeRect(badgeX + 0.5, badgeY + 0.5, badgeWidth - 1, badgeHeight - 1);
    ctx.fillStyle = '#facc15';
    ctx.fillText(badgeText, badgeX + 6, badgeY + 12);
    ctx.restore();
  }

  if (yLabel) {
    ctx.save();
    ctx.translate(Math.max(12, yLabelX - 20), plotTop + plotSpanY / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();
  }


}

const lineChartTooltip = (() => {
  let element = null;
  const create = () => {
    const node = document.createElement('div');
    node.className = 'chart-tooltip';
    node.style.position = 'fixed';
    node.style.padding = '6px 8px';
    node.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont';
    node.style.fontSize = '11px';
    node.style.background = 'rgba(15, 23, 42, 0.92)';
    node.style.color = '#f8fafc';
    node.style.pointerEvents = 'none';
    node.style.borderRadius = '6px';
    node.style.boxShadow = '0 2px 6px rgba(15, 23, 42, 0.45)';
    node.style.opacity = '0';
    node.style.transition = 'opacity 0.08s ease';
    node.style.zIndex = '9999';
    document.body.appendChild(node);
    return node;
  };
  return {
    show(x, y, text) {
      if (!element) {
        element = create();
      }
      element.textContent = text;
      element.style.left = `${x + 12}px`;
      element.style.top = `${y + 12}px`;
      element.style.opacity = '1';
    },
    hide() {
      if (element) {
        element.style.opacity = '0';
      }
    },
  };
})();

function bindLineChartTooltip(canvas) {
  if (canvas.__lineChartTooltipBound) {
    return;
  }
  canvas.__lineChartTooltipBound = true;
  canvas.addEventListener('mouseleave', () => {
    lineChartTooltip.hide();
  });
  canvas.addEventListener('mousemove', (event) => {
    const state = canvas.__lineChartState;
    if (!state || !state.points || !state.points.length) {
      lineChartTooltip.hide();
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const tolerance = Math.max(12, Math.min(36, rect.width * 0.05));
    let best = null;
    let bestDistance = Infinity;
    for (const point of state.points) {
      const distance = Math.abs(point.x - x);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = point;
      }
    }
    if (!best || bestDistance > tolerance) {
      lineChartTooltip.hide();
      return;
    }
    const label = state.timeFormatter(Math.max(0, best.time));
    const valueText = state.formatter(best);
    const text = `${label} · ${valueText}`;
    lineChartTooltip.show(event.clientX, event.clientY, text);
  });
}

function drawBarChart(canvas, labels, values, color, options = {}) {
  const title = options.title || '';
  const unitLabel = options.unit || '';
  const yLabel = options.yLabel || unitLabel;
  const xLabel = options.xLabel || '';
  const { ctx, width, height } = getContext(canvas);
  drawBackground(ctx, width, height);
  if (!Array.isArray(values) || values.length === 0) {
    drawMessage(ctx, width, height, 'Waiting for data…');
    return;
  }
  const left = Math.max(72, Math.min(120, width * 0.18));
  const right = width - Math.max(28, Math.min(80, width * 0.12));
  const top = 48;
  const bottomPadding = height <= 200 ? 108 : 92;
  const bottom = height - bottomPadding;
  const finiteValues = values.filter((value) => Number.isFinite(value) && value > 0);
  const minValue = finiteValues.length ? Math.min(...finiteValues) : 1;
  const maxValue = Math.max(...values, 1);
  const logScale = options.logY && maxValue / Math.max(1, minValue) > 25;
  const barWidth = (right - left) / values.length;

  ctx.fillStyle = '#cbd5f5';
  ctx.font = '12px system-ui';
  if (title) {
    ctx.save();
    ctx.textAlign = 'center';
    ctx.fillText(title, left + (right - left) / 2, top - 28);
    ctx.restore();
  }

  ctx.fillStyle = color;
  values.forEach((value, idx) => {
    let heightRatio;
    if (logScale) {
      const safeValue = Math.max(value, 1e-6);
      const logMax = Math.log10(Math.max(maxValue, 1));
      const logMin = Math.log10(Math.max(minValue, 1e-6));
      heightRatio = (Math.log10(safeValue) - logMin) / Math.max(1e-6, logMax - logMin);
    } else {
      heightRatio = value / maxValue;
    }
    const barHeight = Math.max(1, heightRatio * (bottom - top));
    const x = left + idx * barWidth;
    const y = bottom - barHeight;
    ctx.fillRect(x, y, Math.max(2, barWidth * 0.7), barHeight);
  });

  const total = values.reduce((sum, val) => sum + (Number.isFinite(val) ? val : 0), 0);
  const minTextValue = logScale ? formatValue(minValue, { decimals: 2 }) : '0';
  const maxTextValue = formatValue(maxValue, { decimals: 2 });

  const statParts = [];
  statParts.push(`max ${maxTextValue}`);
  statParts.push(`min ${minTextValue}`);
  statParts.push(`total ${formatValue(total, { decimals: 1 })}${unitLabel ? ` ${unitLabel}` : ''}`);
  const statLine = statParts.join(' · ');

  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px system-ui';
  ctx.save();
  ctx.textAlign = 'center';
  ctx.fillText(statLine, left + (right - left) / 2, top - 6);
  ctx.restore();

  const usableWidth = right - left;
  const maxLabels = Math.max(1, Math.floor(usableWidth / 44));
  const step = Math.max(1, Math.ceil(labels.length / maxLabels));
  let lastLabelRight = -Infinity;
  let renderedLabels = 0;
  labels.forEach((label, idx) => {
    if (idx % step !== 0) {
      return;
    }
    const text = String(label);
    const x = left + (idx + 0.5) * barWidth;
    const rawWidth = ctx.measureText(text).width;
    const projectedWidth = rawWidth * Math.SQRT1_2;
    if (x - projectedWidth < lastLabelRight + 6) {
      return;
    }
    ctx.save();
    ctx.translate(x, bottom + 24);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(text, -rawWidth / 2, 0);
    ctx.restore();
    lastLabelRight = x + projectedWidth;
    renderedLabels += 1;
  });
  if (step > 1 && renderedLabels) {
    ctx.fillText('⋯', right - 12, bottom + 20);
  }

  if (yLabel) {
    ctx.save();
    ctx.translate(left - 52, top + (bottom - top) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();
  }

  if (xLabel) {
    const labelWidth = ctx.measureText(xLabel).width;
    ctx.fillText(xLabel, width / 2 - labelWidth / 2, bottom + 54);
  }
}

function turbo(t) {
  const clamped = Math.max(0, Math.min(1, Number(t) || 0));
  const r = Math.round(255 * (0.135 + 4.615 * clamped - 42.66 * clamped ** 2 + 132.13 * clamped ** 3 - 152.94 * clamped ** 4 + 59.29 * clamped ** 5));
  const g = Math.round(255 * (0.091 + 2.178 * clamped + 10.02 * clamped ** 2 - 57.62 * clamped ** 3 + 116.63 * clamped ** 4 - 81.49 * clamped ** 5));
  const b = Math.round(255 * (0.107 + 3.011 * clamped - 25.46 * clamped ** 2 + 84.31 * clamped ** 3 - 101.2 * clamped ** 4 + 41.49 * clamped ** 5));
  const safe = (value) => Math.max(0, Math.min(255, value));
  return `rgb(${safe(r)}, ${safe(g)}, ${safe(b)})`;
}

function drawHeatmap(canvas, matrix, maxValue, total, options = {}) {
  const { ctx, width, height } = getContext(canvas);
  drawBackground(ctx, width, height);
  if (!Array.isArray(matrix) || !matrix.length || !matrix[0].length) {
    drawMessage(ctx, width, height, 'Waiting for data…');
    return;
  }

  const rows = matrix.length;
  const cols = matrix[0].length;
  const left = 36;
  const right = width - 36;
  const top = 54;
  const bottom = height - 96;
  const cellWidth = (right - left) / Math.max(1, cols);
  const cellHeight = (bottom - top) / Math.max(1, rows);

  ctx.fillStyle = '#cbd5f5';
  ctx.font = '12px system-ui';
  const header = 'Key density heatmap';
  ctx.fillText(header, left, top - 26);
  const totalLabel = `total keys ${formatValue(total, { decimals: 0, compact: false })}`;
  ctx.fillText(totalLabel, right - ctx.measureText(totalLabel).width, top - 26);

  const flatValues = matrix.flat();
  const finiteValues = flatValues.filter((value) => Number.isFinite(value));
  const clipPercent = Number.isFinite(options.clipPercent) ? options.clipPercent : 0.98;
  const baselineMax = Number.isFinite(maxValue) ? maxValue : 0;
  const floor = finiteValues.length ? Math.min(...finiteValues) : 0;
  const rawMax = finiteValues.length ? Math.max(...finiteValues, baselineMax) : baselineMax;
  let scaleMax = rawMax;
  let clipNote = '';
  if (finiteValues.length && clipPercent > 0 && clipPercent < 1) {
    const sorted = finiteValues.slice().sort((a, b) => a - b);
    const clipIndex = Math.max(0, Math.min(sorted.length - 1, Math.floor(sorted.length * clipPercent)));
    const candidate = sorted[clipIndex];
    if (candidate < rawMax) {
      scaleMax = candidate;
      clipNote = `clip @ P${Math.round(clipPercent * 100)}`;
    }
  }
  if (!Number.isFinite(scaleMax) || scaleMax <= floor) {
    scaleMax = floor + 1;
  }

  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const current = matrix[r][c] || 0;
      const ratio = scaleMax === floor ? 0 : (Math.min(current, scaleMax) - floor) / (scaleMax - floor);
      ctx.fillStyle = turbo(ratio);
      const x = left + c * cellWidth;
      const y = top + r * cellHeight;
      ctx.fillRect(x, y, Math.max(1, cellWidth - 1), Math.max(1, cellHeight - 1));
    }
  }

  const legendWidth = Math.min(220, right - left);
  const legendHeight = 12;
  const legendLeft = left;
  const legendTop = bottom + 24;
  const gradient = ctx.createLinearGradient(legendLeft, legendTop, legendLeft + legendWidth, legendTop);
  for (let i = 0; i <= 10; i += 1) {
    const stop = i / 10;
    gradient.addColorStop(stop, turbo(stop));
  }
  ctx.fillStyle = gradient;
  ctx.fillRect(legendLeft, legendTop, legendWidth, legendHeight);

  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px system-ui';
  const minText = `min ${formatValue(floor, { decimals: 0, compact: false })}`;
  ctx.fillText(minText, legendLeft, legendTop + legendHeight + 14);
  const maxText = `max ${formatValue(rawMax, { decimals: 0, compact: false })}`;
  const maxTextWidth = ctx.measureText(maxText).width;
  ctx.fillText(maxText, legendLeft + legendWidth - maxTextWidth, legendTop + legendHeight + 14);
  if (clipNote) {
    const clipWidth = ctx.measureText(clipNote).width;
    ctx.fillText(clipNote, legendLeft + legendWidth - Math.max(maxTextWidth, clipWidth), legendTop + legendHeight + 28);
  }
}

function renderCharts() {
  const windowLabel = mmssFromSeconds(state.windowSeconds || WINDOW_SECONDS);
  const timeLabel = `time (window ${windowLabel})`;
  const idle = Boolean(state.idle);
  const stats = state.seriesStats || {};
  const throughputWindowPeak = stats.throughput && Number.isFinite(stats.throughput.windowPeak)
    ? stats.throughput.windowPeak
    : undefined;
  const throughputWindowMin = stats.throughput && Number.isFinite(stats.throughput.windowMin)
    ? stats.throughput.windowMin
    : undefined;
  const throughputSessionPeak = stats.throughput && Number.isFinite(stats.throughput.sessionPeak)
    ? stats.throughput.sessionPeak
    : undefined;
  const throughputPeakStable = Number.isFinite(throughputWindowPeak)
    ? heldMaxFor('throughput', throughputWindowPeak)
    : undefined;
  const loadStats = stats.load || {};
  const probeStats = stats.probeAvg || {};
  const tombstoneStats = stats.tombstone || {};
  drawLineChart(canvases.throughput, state.throughput, '#12a7d6', {
    title: 'Throughput (EMA)',
    unit: 'ops/s',
    yLabel: 'Throughput (ops/s)',
    decimals: 1,
    compact: true,
    autoY: true,
    autoYTrim: 0,
    autoYPadTop: 0.24,
    autoYPadBottom: 0.08,
    autoYFloor: 0,
    idle,
    peakValue: throughputPeakStable,
    floorValue: 0,
    statMinValue: throughputWindowMin,
    sessionPeak: throughputSessionPeak,
    tooltipFormatter: (point) => `${formatValue(point.value, { decimals: 1 })} ops/s`,
    markers: state.throughputMarkers,
    xLabel: timeLabel,
    maxY: state.runCompleted ? throughputSessionPeak : undefined,
  });
  drawLineChart(canvases.load, state.load, '#0ea5e9', {
    title: 'Load factor',
    unit: '%',
    yLabel: 'Load factor (%)',
    decimals: 2,
    compact: false,
    percent: true,
    autoY: true,
    autoYPadTop: 0.08,
    autoYPadBottom: 0.05,
    autoYFloor: 0,
    autoYCeiling: 1,
    idle,
    peakValue: loadStats && Number.isFinite(loadStats.max) ? loadStats.max : undefined,
    floorValue: loadStats && Number.isFinite(loadStats.min) ? loadStats.min : undefined,
    formatY: (value) => `${(value * 100).toFixed(0)}%`,
    formatStat: (value) => (value * 100).toFixed(0),
    xLabel: timeLabel,
  });

  const backend = (state.backendName || '').toLowerCase();
  const chainingLike = backend.includes('chain');

  if (chainingLike) {
    drawNotApplicable(canvases.probeAvg, 'N/A for chaining backend');
    drawNotApplicable(canvases.tombstone, 'N/A for chaining backend');
    drawNotApplicable(canvases.probeHist, 'N/A for chaining backend');
  } else {
    drawLineChart(canvases.probeAvg, state.probeAvg, '#a855f7', {
      title: 'Average probe distance',
      unit: 'distance',
      yLabel: 'Probe distance',
      decimals: 2,
      compact: false,
      autoY: true,
    autoYPadTop: 0.12,
    autoYPadBottom: 0.06,
    autoYFloor: 0,
    idle,
    peakValue: probeStats && Number.isFinite(probeStats.max) ? probeStats.max : undefined,
    floorValue: probeStats && Number.isFinite(probeStats.min) ? probeStats.min : undefined,
    xLabel: timeLabel,
  });
  drawLineChart(canvases.tombstone, state.tombstone, '#22c55e', {
    title: 'Tombstone ratio',
      unit: '%',
      yLabel: 'Tombstone ratio (%)',
      decimals: 2,
      compact: false,
      percent: true,
      autoY: true,
    autoYPadTop: 0.08,
    autoYPadBottom: 0.05,
    autoYFloor: 0,
    autoYCeiling: 1,
    idle,
    peakValue: tombstoneStats && Number.isFinite(tombstoneStats.max) ? tombstoneStats.max : undefined,
    floorValue: tombstoneStats && Number.isFinite(tombstoneStats.min) ? tombstoneStats.min : undefined,
    formatY: (value) => `${(value * 100).toFixed(0)}%`,
    formatStat: (value) => (value * 100).toFixed(0),
    xLabel: timeLabel,
  });
    const skewed = state.probeValues.length && Math.max(...state.probeValues) > 100 * Math.max(1, Math.min(...state.probeValues.filter((v) => v > 0)));
    drawBarChart(canvases.probeHist, state.probeLabels, state.probeValues, '#0ea5e9', {
      title: 'Probe histogram',
      unit: 'count',
      yLabel: 'Count',
      xLabel: 'Probe distance',
      logY: skewed,
    });
  }

  drawBarChart(canvases.latency, state.latencyLabels, state.latencyValues, '#f97316', {
    title: 'Latency histogram',
    unit: 'samples',
    yLabel: 'Samples',
    xLabel: 'Latency bucket',
  });
  drawHeatmap(canvases.heatmap, state.heatmapMatrix, state.heatmapMax, state.heatmapTotal, { clipPercent: 0.98 });
}

function requestRender() {
  if (renderPending) {
    return;
  }
  renderPending = true;
  window.requestAnimationFrame(() => {
    renderPending = false;
    renderCharts();
    hasRendered = true;
  });
}

function observeCanvasResize(canvas) {
  if (!canvas || typeof ResizeObserver === 'undefined') {
    return;
  }
  let pending = 0;
  const observer = new ResizeObserver(() => {
    if (pending) {
      window.cancelAnimationFrame(pending);
    }
    pending = window.requestAnimationFrame(() => {
      pending = 0;
      requestRender();
    });
  });
  observer.observe(canvas);
  resizeObservers.push(observer);
}

Object.values(canvases).forEach((canvas) => observeCanvasResize(canvas));
window.addEventListener('beforeunload', () => {
  resizeObservers.forEach((observer) => observer.disconnect());
  resizeObservers.length = 0;
});

function updateLatencyHistogram(payload) {
  const operations = payload && typeof payload.operations === 'object' ? payload.operations : {};
  const overall = Array.isArray(operations.overall) ? operations.overall : [];
  state.latencyLabels = overall.map((bucket) => formatLatencyLabel(bucket.le || '+Inf'));
  state.latencyValues = overall.map((bucket, idx) => {
    const count = safeNumber(bucket.count, 0);
    if (idx === 0) {
      return Math.max(count, 0);
    }
    const prev = safeNumber(overall[idx - 1]?.count, 0);
    return Math.max(count - prev, 0);
  });
}

function updateProbeHistogramPayload(payload) {
  const buckets = Array.isArray(payload && payload.buckets) ? payload.buckets : [];
  state.probeLabels = buckets.map((item) => String(item.distance ?? 0));
  state.probeValues = buckets.map((item) => safeNumber(item.count, 0));
}

function updateHeatmap(payload) {
  const matrix = Array.isArray(payload && payload.matrix) ? payload.matrix : [];
  state.heatmapMatrix = matrix.map((row) => (Array.isArray(row) ? row.map((value) => safeNumber(value, 0)) : []));
  state.heatmapMax = safeNumber(payload && payload.max, 0);
  state.heatmapTotal = safeNumber(payload && payload.total, 0);
}

function updateFromHistory(payload) {
  const sorted = normaliseHistory(payload.items || []);
  if (!sorted.length) {
    state.throughput = [];
    state.throughputMarkers = [];
  state.load = [];
  state.probeAvg = [];
  state.tombstone = [];
  state.latestTick = {};
  state.backendName = '';
  state.idle = false;
  state.runCompleted = false;
  state.recentEvents = [];
  state.seriesStats = {
      throughput: { peak: 0 },
      load: { min: 0, max: 0 },
      probeAvg: { min: 0, max: 0 },
      tombstone: { min: 0, max: 0 },
    };
    renderSummary({});
  updateAlerts([]);
  state.recentEvents = [];
  updateEvents([]);
    return;
  }
  const latest = sorted[sorted.length - 1];
  const latestEvents = Array.isArray(latest.events) ? latest.events : [];
  if (latestEvents.some((evt) => evt.type === 'complete')) {
    state.runCompleted = true;
  }
  const latestT = safeNumber(latest.t, 0);
  const earliestT = safeNumber(sorted[0].t, 0);
  const observedSpan = latestT - earliestT;
  const windowSeconds = effectiveWindowSeconds(observedSpan);
  const base = Math.max(earliestT, latestT - windowSeconds);
  state.baseTime = base;
  state.windowSeconds = windowSeconds;
  state.throughput = buildThroughputSeries(sorted, base);
  const markerLabelMap = {
    migrate: 'Migration',
    migration: 'Migration',
    compact: 'Compaction',
    compaction: 'Compaction',
    resize: 'Resize',
  };

  const markers = [];
  const appendMarker = (eventType, backend, timeValue) => {
    if (!Number.isFinite(timeValue)) {
      return;
    }
    const label = markerLabelMap[eventType];
    if (!label) {
      return;
    }
    const backendSuffix = backend ? ` (${backend})` : '';
    markers.push({ x: timeValue - base, label: `${label}${backendSuffix}` });
  };

  sorted.forEach((tick) => {
    const tickTime = safeNumber(tick.t, NaN);
    if (!Number.isFinite(tickTime) || tickTime < base) {
      return;
    }
    const events = Array.isArray(tick.events) ? tick.events : [];
    events.forEach((event) => {
      const rawType = String(event && event.type ? event.type : '').toLowerCase();
      appendMarker(rawType, event && event.backend, tickTime);
    });
  });

  state.load = buildMetricSeries(sorted, base, (tick) => tick.load_factor);
  state.probeAvg = buildMetricSeries(sorted, base, (tick) => tick.avg_probe_estimate);
  state.tombstone = buildMetricSeries(sorted, base, (tick) => tick.tombstone_ratio);
  state.latestTick = latest;
  state.idle = Boolean(latest && (latest.state === 'idle' || latest.idle));
  state.backendName = (latest.backend || '').toString();

  const throughputWindowStats = computeThroughputStats(sorted, base);
  const throughputSessionStats = computeThroughputStats(sorted, -Infinity);

  const loadExtents = computeMetricExtents(sorted, base, (tick) => tick.load_factor);
  const probeExtents = computeMetricExtents(sorted, base, (tick) => tick.avg_probe_estimate);
  const tombstoneExtents = computeMetricExtents(sorted, base, (tick) => tick.tombstone_ratio);

  const normaliseRange = (extents) => {
    if (Number.isFinite(extents.min) && Number.isFinite(extents.max)) {
      return { min: extents.min, max: extents.max };
    }
    return { min: 0, max: 0 };
  };

  state.seriesStats = {
    throughput: {
      windowPeak: Number.isFinite(throughputWindowStats.max) ? throughputWindowStats.max : undefined,
      windowMin: Number.isFinite(throughputWindowStats.min) ? throughputWindowStats.min : undefined,
      sessionPeak: Number.isFinite(throughputSessionStats.max) ? throughputSessionStats.max : undefined,
    },
    load: normaliseRange(loadExtents),
    probeAvg: normaliseRange(probeExtents),
    tombstone: normaliseRange(tombstoneExtents),
  };
  renderSummary(latest);
  updateAlerts(latest.alerts || []);
  const previous = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const syntheticEvents = Array.isArray(latest.events) ? latest.events.slice() : [];
  if (previous) {
    const prevLoad = safeNumber(previous.load_factor, NaN);
    const currentLoad = safeNumber(latest.load_factor, NaN);
    if (
      Number.isFinite(prevLoad)
      && Number.isFinite(currentLoad)
      && currentLoad < prevLoad - 0.05
    ) {
      syntheticEvents.push({
        type: 'resize',
        backend: latest.backend || state.backendName || 'unknown',
        t: latestT,
        message: `load ${formatValue(prevLoad, { decimals: 3, compact: false })} → ${formatValue(currentLoad, { decimals: 3, compact: false })}`,
      });
      appendMarker('resize', latest.backend || state.backendName || 'unknown', latestT);
    }
  }
  state.throughputMarkers = markers.slice(-12);
  const collapsedEvents = syntheticEvents.concat(Array.isArray(state.recentEvents) ? state.recentEvents : []);
  collapsedEvents.sort((a, b) => safeNumber(b.t, 0) - safeNumber(a.t, 0));
  state.recentEvents = dedupeEvents(collapsedEvents);
  updateEvents(state.recentEvents);
}

function fetchComparison() {
  if (!comparisonSummary) {
    return;
  }
  authorizedFetch('/api/compare', { headers: { Accept: 'application/json' } })
    .then((res) => {
      if (!res.ok) {
        comparisonData = null;
        renderComparison();
        return null;
      }
      return res.json();
    })
    .then((data) => {
      if (!data) {
        return;
      }
      comparisonData = data;
      renderComparison();
    })
    .catch(() => {
      comparisonData = null;
      renderComparison();
    });
}

function poll() {
  Promise.all([
    fetchJson(`/api/metrics/history?limit=${MAX_POINTS}`),
    fetchJson('/api/metrics/histogram/latency'),
    fetchJson('/api/metrics/histogram/probe'),
    fetchJson('/api/metrics/heatmap'),
  ])
    .then(([historyPayload, latencyPayload, probePayload, heatmapPayload]) => {
      const historyStamp = safeNumber(historyPayload && historyPayload.generated_at, NaN);
      const latencyStamp = safeNumber(latencyPayload && latencyPayload.generated_at, NaN);
      const probeStamp = safeNumber(probePayload && probePayload.generated_at, NaN);
      const heatmapStamp = safeNumber(heatmapPayload && heatmapPayload.generated_at, NaN);

      updateFromHistory(historyPayload);
      updateLatencyHistogram(latencyPayload);
      updateProbeHistogramPayload(probePayload);
      updateHeatmap(heatmapPayload);

      const historyChanged = Number.isFinite(historyStamp) ? historyStamp !== lastHistoryStamp : true;
      const latencyChanged = Number.isFinite(latencyStamp) ? latencyStamp !== lastLatencyStamp : false;
      const probeChanged = Number.isFinite(probeStamp) ? probeStamp !== lastProbeStamp : false;
      const heatmapChanged = Number.isFinite(heatmapStamp) ? heatmapStamp !== lastHeatmapStamp : false;

      if (Number.isFinite(historyStamp)) {
        lastHistoryStamp = historyStamp;
      }
      if (Number.isFinite(latencyStamp)) {
        lastLatencyStamp = latencyStamp;
      }
      if (Number.isFinite(probeStamp)) {
        lastProbeStamp = probeStamp;
      }
      if (Number.isFinite(heatmapStamp)) {
        lastHeatmapStamp = heatmapStamp;
      }

      if (!hasRendered || historyChanged || latencyChanged || probeChanged || heatmapChanged) {
        requestRender();
      }
      const events = Array.isArray(historyPayload && historyPayload.events) ? historyPayload.events : [];
      if (events.length) {
        const collapsed = events.concat(Array.isArray(state.recentEvents) ? state.recentEvents : []);
        collapsed.sort((a, b) => safeNumber(b.t, 0) - safeNumber(a.t, 0));
        state.recentEvents = dedupeEvents(collapsed);
        updateEvents(state.recentEvents);
      }
    })
    .catch((err) => {
      console.error('metrics poll error', err);
    })
    .finally(() => {
      scheduleNextPoll();
    });
}

updateDownloadLink(MAX_POINTS);
requestRender();
fetchComparison();
poll();