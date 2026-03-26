export const state = {
  symbols: new Set(),
  prices: {},
  volume: {},
  orderflow: {},
  oi: {},
  signals: {},
  tickers: new Map(),
  prevPrice: {},
  liquidity: {},
  htf: {},
  imbalance: {},
  funding: {},
  liquidations: {},
  performance: {},
  tradeHistory: []
};

export function resetState() {
  state.symbols = new Set();
  state.prices = {};
  state.volume = {};
  state.orderflow = {};
  state.oi = {};
  state.signals = {};
  state.tickers = new Map();
  state.prevPrice = {};
  state.liquidity = {};
  state.htf = {};
  state.imbalance = {};
  state.funding = {};
  state.liquidations = {};
}
