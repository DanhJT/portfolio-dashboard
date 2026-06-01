// Data access layer.
//
// Two modes, selected by VITE_DATA_SOURCE:
//   "static" (default) — read everything from a precomputed snapshot.json on
//                        the CDN. No backend, instant, never fails from Yahoo.
//   "live"             — hit the FastAPI backend (local dev). Set
//                        VITE_DATA_SOURCE=live (and optionally VITE_API_BASE).
const DATA_SOURCE = import.meta.env.VITE_DATA_SOURCE ?? "static";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export const IS_STATIC = DATA_SOURCE === "static";

const DEFAULT_AUM = 1_000_000;

// ---------------------------------------------------------------------------
// Live-mode helpers
// ---------------------------------------------------------------------------

function buildQuery({ tickers, weights, period }) {
  const params = new URLSearchParams();
  tickers.forEach((t) => params.append("tickers", t));
  weights.forEach((w) => params.append("weights", String(w)));
  if (period) params.set("period", period);
  return params.toString();
}

async function fetchJSON(path, init) {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Static-mode snapshot loader (fetched once, cached)
// ---------------------------------------------------------------------------

let _snapshotPromise = null;

function loadSnapshot() {
  if (!_snapshotPromise) {
    const url = `${import.meta.env.BASE_URL}snapshot.json`;
    _snapshotPromise = fetch(url).then((res) => {
      if (!res.ok) {
        _snapshotPromise = null; // allow a retry on next call
        throw new Error(`Failed to load snapshot.json (${res.status})`);
      }
      return res.json();
    });
  }
  return _snapshotPromise;
}

const PERIOD_ALIASES = {
  "3m": "3mo",
  "3mo": "3mo",
  "6m": "6mo",
  "6mo": "6mo",
  "1y": "1y",
  "2y": "2y",
};

function periodKey(period) {
  return PERIOD_ALIASES[(period ?? "1y").toLowerCase()] ?? "1y";
}

// Liquidity sizing scales linearly with AUM; everything else (ADV, Kelly,
// liquidity score) is AUM-independent, so we recompute the few AUM-dependent
// fields client-side rather than needing a live backend.
function scaleLiquidity(base, aum) {
  const positions = base.positions.map((p) => {
    const position_usd = aum * p.current_weight;
    const pct_of_adv = p.adv_usd > 0 ? position_usd / p.adv_usd : p.pct_of_adv;
    return {
      ...p,
      position_usd,
      pct_of_adv,
      days_to_liquidate_10: pct_of_adv / 0.1,
      days_to_liquidate_20: pct_of_adv / 0.2,
      days_to_liquidate_33: pct_of_adv / 0.33,
    };
  });
  return { aum, positions };
}

export async function getSnapshotMeta() {
  if (!IS_STATIC) return null;
  const s = await loadSnapshot();
  return { generated_at: s.generated_at ?? null };
}

// ---------------------------------------------------------------------------
// Public API (each branches on data source)
// ---------------------------------------------------------------------------

export async function getCurrentPortfolio() {
  if (IS_STATIC) return (await loadSnapshot()).portfolio;
  return fetchJSON(`/api/portfolio/current`);
}

export async function getMetrics(portfolio) {
  if (IS_STATIC) {
    const s = await loadSnapshot();
    return s.periods[periodKey(portfolio.period)].metrics;
  }
  return fetchJSON(`/api/portfolio/metrics?${buildQuery(portfolio)}`);
}

export async function getPrices(portfolio) {
  if (IS_STATIC) {
    const s = await loadSnapshot();
    return s.periods[periodKey(portfolio.period)].prices;
  }
  return fetchJSON(`/api/portfolio/prices?${buildQuery(portfolio)}`);
}

export async function getNews(portfolio) {
  if (IS_STATIC) return (await loadSnapshot()).news;
  return fetchJSON(`/api/portfolio/news?${buildQuery(portfolio)}`);
}

export async function generateCommentary(metrics, module = "overview") {
  if (IS_STATIC) {
    const s = await loadSnapshot();
    const c = s.commentary?.[module];
    if (c) return c;
    return {
      commentary: "Commentary is not available in the current snapshot.",
      generated_at: s.generated_at,
      model: "snapshot",
    };
  }
  return fetchJSON(`/api/commentary/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metrics, module }),
  });
}

// --- analytical modules ---

export async function getMonteCarlo() {
  if (IS_STATIC) return (await loadSnapshot()).monte_carlo;
  return fetchJSON(`/api/risk/monte-carlo`);
}

export async function getStressTests() {
  if (IS_STATIC) return (await loadSnapshot()).stress_tests;
  return fetchJSON(`/api/risk/stress-tests`);
}

export async function postCustomStress(payload) {
  if (IS_STATIC) {
    throw new Error("Custom stress windows require the live backend.");
  }
  return fetchJSON(`/api/risk/stress-custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getGarch() {
  if (IS_STATIC) return (await loadSnapshot()).garch;
  return fetchJSON(`/api/risk/garch`);
}

export async function getLiquidity(aum) {
  if (IS_STATIC) {
    const base = (await loadSnapshot()).liquidity;
    if (!base) return base;
    if (!aum || Number(aum) === base.aum) return base;
    return scaleLiquidity(base, Number(aum));
  }
  const q = aum ? `?aum=${encodeURIComponent(aum)}` : "";
  return fetchJSON(`/api/liquidity/analysis${q}`);
}
