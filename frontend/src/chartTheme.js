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
