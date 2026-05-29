const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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

export function getCurrentPortfolio() {
  return fetchJSON(`/api/portfolio/current`);
}

export function getMetrics(portfolio) {
  return fetchJSON(`/api/portfolio/metrics?${buildQuery(portfolio)}`);
}

export function getPrices(portfolio) {
  return fetchJSON(`/api/portfolio/prices?${buildQuery(portfolio)}`);
}

export function getCorrelation(portfolio) {
  return fetchJSON(`/api/portfolio/correlation?${buildQuery(portfolio)}`);
}

export function getNews(portfolio) {
  return fetchJSON(`/api/portfolio/news?${buildQuery(portfolio)}`);
}

export function generateCommentary(metrics, module = "overview") {
  return fetchJSON(`/api/commentary/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metrics, module }),
  });
}

// --- new analytical modules ---

export function getMonteCarlo() {
  return fetchJSON(`/api/risk/monte-carlo`);
}

export function getStressTests() {
  return fetchJSON(`/api/risk/stress-tests`);
}

export function postCustomStress(payload) {
  return fetchJSON(`/api/risk/stress-custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getGarch() {
  return fetchJSON(`/api/risk/garch`);
}

export function getLiquidity(aum) {
  const q = aum ? `?aum=${encodeURIComponent(aum)}` : "";
  return fetchJSON(`/api/liquidity/analysis${q}`);
}
