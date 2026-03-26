export const sniperState = {
  imbalance: {},
  volumeRatio: {},
  prevHigh: {},
  prevFast: {},
  price: {},
  oiChange: {},
  symbols: new Set()
};

export function updateSniperState(symbol, data) {
  sniperState.symbols.add(symbol);
  if (data.imbalance !== undefined) sniperState.imbalance[symbol] = data.imbalance;
  if (data.volumeRatio !== undefined) sniperState.volumeRatio[symbol] = data.volumeRatio;
  if (data.price !== undefined) sniperState.price[symbol] = data.price;
  if (data.oiChange !== undefined) sniperState.oiChange[symbol] = data.oiChange;
}

// ==============================
// STAGE 1 — PRESSURE
// ==============================
function detectPressure(symbol) {
  const imbalance = sniperState.imbalance[symbol] || 1;
  const volume = sniperState.volumeRatio[symbol] || 1;

  if (imbalance > 1.05 || volume > 1.2) {
    return true;
  }
  return false;
}

// ==============================
// STAGE 2 — BREAKOUT
// ==============================
function detectBreakout(symbol, price) {
  const prevHigh = sniperState.prevHigh[symbol] || price;

  if (price > prevHigh * 1.001) {
    sniperState.prevHigh[symbol] = price;
    return true;
  }

  sniperState.prevHigh[symbol] = price;
  return false;
}

// ==============================
// STAGE 3 — MOMENTUM
// ==============================
function detectMomentum(symbol, price) {
  const prev = sniperState.prevFast[symbol] || price;

  const velocity = prev > 0 ? (price - prev) / prev : 0;
  sniperState.prevFast[symbol] = price;

  return velocity > 0.002;
}

// ==============================
// STAGE 4 — ENTRY LOGIC
// ==============================
function getEntrySignal(symbol, data) {
  const { price, oiChange, volumeRatio } = data;

  const pressure = detectPressure(symbol);
  const breakout = detectBreakout(symbol, price);
  const momentum = detectMomentum(symbol, price);

  // 🔥 CONFIRMED ENTRY
  if (pressure && breakout && momentum && oiChange > 0.5 && volumeRatio > 2.0) {
    return {
      type: "CONFIRMED ENTRY",
      score: 3
    };
  }

  // ⚡ EARLY ENTRY
  if (pressure && breakout) {
    return {
      type: "EARLY ENTRY",
      score: 1
    };
  }

  return null;
}

// ==============================
// STAGE 5 — RANKING
// ==============================
function rankSignals(signals) {
  return signals
    .map(s => ({
      ...s,
      finalScore: s.score + (s.oiChange * 5) + (s.volumeRatio * 2)
    }))
    .sort((a, b) => b.finalScore - a.finalScore)
    .slice(0, 5); // ONLY TOP 5
}

// ==============================
// RUNNER
// ==============================
export function runSniper() {
  const signals = [];

  for (const s of sniperState.symbols) {
    const data = {
      price: sniperState.price[s],
      oiChange: sniperState.oiChange[s] || 0,
      volumeRatio: sniperState.volumeRatio[s] || 1
    };

    if (!data.price) continue;

    const signal = getEntrySignal(s, data);

    if (signal) {
      signals.push({
        symbol: s,
        ...signal,
        ...data
      });
    }
  }

  return rankSignals(signals);
}
