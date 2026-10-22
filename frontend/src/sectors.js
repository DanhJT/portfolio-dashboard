// GICS sector for every ticker in the strategy universe (all S&P 500
// constituents). Generated from backend/data/sp500_constituents.csv by
// backend/scripts/update_sp500.py — regenerate with that script rather than
// editing by hand. Unmapped tickers fall into "Other".
import sp500Sectors from "./sp500Sectors.json";

export const SECTOR_BY_TICKER = sp500Sectors.sectors;
export const UNIVERSE_AS_OF = sp500Sectors.as_of;
export const UNIVERSE_SIZE = Object.keys(sp500Sectors.sectors).length;

// Approximate S&P 500 sector weights. Hand-maintained — refresh periodically
// from the S&P sector breakdown and bump the as-of label.
export const SP500_WEIGHTS_AS_OF = "mid-2025, approx.";
export const SP500_SECTOR_WEIGHTS = {
  "Info Tech": 0.335,
  Financials: 0.138,
  "Cons Disc": 0.104,
  "Comm Services": 0.1,
  "Health Care": 0.091,
  Industrials: 0.085,
  "Cons Staples": 0.053,
  Energy: 0.03,
  Utilities: 0.024,
  "Real Estate": 0.02,
  Materials: 0.019,
};
