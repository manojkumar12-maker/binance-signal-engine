export const state = {
  signals: [],
  lastSignalTime: {},
  stats: {
    total: 0,
    early: 0,
    confirmed: 0,
    sniper: 0,
    active: 0
  }
};

export function canTrigger(symbol, cooldownMs = 5 * 60 * 1000) {
  const now = Date.now();
  const lastTime = state.lastSignalTime[symbol] || 0;
  
  if (now - lastTime < cooldownMs) {
    return false;
  }
  
  state.lastSignalTime[symbol] = now;
  return true;
}

export function addSignal(signal) {
  state.signals.unshift(signal);
  if (state.signals.length > 500) {
    state.signals.pop();
  }
  
  state.stats.total++;
  if (signal.tier === 'EARLY') state.stats.early++;
  if (signal.tier === 'CONFIRMED') state.stats.confirmed++;
  if (signal.tier === 'SNIPER') state.stats.sniper++;
  
  return signal;
}

export function updateSignalStatus(symbol, status, closedPrice = null) {
  const signal = state.signals.find(s => s.symbol === symbol && 
    (s.status === 'ACTIVE' || s.status === 'HOT' || s.status === 'WATCHLIST'));
  
  if (signal) {
    signal.status = status;
    if (closedPrice) {
      signal.closedPrice = closedPrice;
      signal.closedAt = Date.now();
    }
  }
  
  return signal;
}

export function getActiveSignals() {
  return state.signals.filter(s => 
    s.status === 'ACTIVE' || s.status === 'HOT' || s.status === 'WATCHLIST'
  );
}

export function getRecentSignals(limit = 100) {
  return state.signals.slice(0, limit);
}
