// Chart colors live here so they stay in step with the surface tokens in
// index.css. Grid and axis values are tuned for the true-black well the charts
// sit in — anything brighter reads as a cage drawn around the data.

export const GRID = "rgba(255,255,255,0.06)";
export const AXIS = "rgba(255,255,255,0.14)";
export const TICK = "#a3a3a3";
export const LEGEND = "#e5e5e5";

// Tooltips float above everything, so they rise: --chassis-high + --edge.
export const TOOLTIP_BG = "#14171a";
export const TOOLTIP_BORDER = "rgba(255,255,255,0.09)";

// Semantic series colors — these carry meaning, not decoration. Unchanged by
// the surface pass.
export const SERIES = {
  portfolio: "#5eead4",
  benchmark: "#a3a3a3",
  positive: "#34d399",
  negative: "#fb7185",
  warning: "#facc15",
  neutral: "#e5e5e5",
  zero: "#737373",
};

// Identity colors for holdings (e.g. the weights donut). Fixed order, assigned
// by ticker position — never reuse SERIES here, green/red already mean gain/loss.
// Neon steps to match the dashboard's teal accent; order validated for CVD
// separation and contrast on the black well (intentionally brighter than the
// usual lightness band).
export const CATEGORICAL = ["#5eead4", "#e879f9", "#facc15", "#818cf8", "#fb923c", "#38bdf8", "#f472b6"];

// Deeper end of each slot's gradient (same hue family, so identity holds).
export const CATEGORICAL_DEEP = ["#0891b2", "#9333ea", "#d97706", "#4f46e5", "#ea580c", "#0369a1", "#be185d"];
