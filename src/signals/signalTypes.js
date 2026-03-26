function pctChange(curr, prev) {
  if (!prev) return 0;
  return ((curr - prev) / prev) * 100;
}

export function isNoise({ volumeRatio, oiChange, orderFlow }) {
  return (
    volumeRatio < 1.1 &&
    Math.abs(oiChange) < 0.05 &&
    orderFlow < 1.05
  );
}

export function detectTrap({ priceChange, orderFlow }) {
  return (
    Math.abs(priceChange) > 5 &&
    orderFlow < 1.1
  );
}

export function detectEarlyPump({ volumeRatio, oiChange, priceChange }) {
  return (
    volumeRatio > 1.5 &&
    oiChange < 0.5 &&
    Math.abs(priceChange) < 1.5
  );
}

export function detectAccumulation({ volumeRatio, orderFlow, priceChange, fakeOI }) {
  return (
    volumeRatio > 1.8 &&
    orderFlow > 1.2 &&
    Math.abs(priceChange) < 1 &&
    fakeOI > 0.1
  );
}

export function detectPressure({ volumeRatio, orderFlow, oiChange, momentum }) {
  return (
    volumeRatio > 1.5 &&
    orderFlow > 1.2 &&
    oiChange > 0.1 &&
    momentum > 0
  );
}

export function detectExplosion({ volumeRatio, orderFlow, oiChange, momentum, velocity }) {
  return (
    volumeRatio > 2 &&
    orderFlow > 1.4 &&
    oiChange > 0.3 &&
    momentum > 0 &&
    velocity > 0.002
  );
}

export function detectHighPump({ volumeRatio, orderFlow, oiChange, priceChange, score }) {
  return (
    volumeRatio > 2.5 &&
    orderFlow > 1.5 &&
    oiChange > 0.5 &&
    Math.abs(priceChange) > 1 &&
    score >= 40
  );
}

export function calculateAdaptiveScore(data) {
  let score = 0;
  const { volumeRatio, oiChange, orderFlow, fakeOI, momentum, velocity } = data;

  if (volumeRatio > 1.5) score += 15;
  if (volumeRatio > 2) score += 10;
  if (volumeRatio > 3) score += 10;

  if (oiChange > 0.2) score += 20;
  if (oiChange > 0.5) score += 15;
  if (oiChange > 1) score += 10;

  if (orderFlow > 1.2) score += 15;
  if (orderFlow > 1.4) score += 10;
  if (orderFlow > 1.6) score += 10;

  if (fakeOI > 0.1) score += 10;
  if (fakeOI > 0.3) score += 10;
  if (fakeOI > 0.5) score += 10;

  if (momentum > 0) score += 10;
  if (velocity > 0.001) score += 10;

  return Math.min(100, score);
}

export function getSignalLevel(score) {
  if (score >= 50) return "EXPLOSION";
  if (score >= 40) return "ENTRY";
  if (score >= 30) return "BUILDING";
  if (score >= 20) return "WATCH";
  return null;
}

export function generateSignal(data) {
  const {
    symbol,
    volumeRatio,
    orderFlow,
    oiChange,
    priceChange,
    fakeOI,
    momentum,
    velocity
  } = data;

  if (isNoise(data)) return null;

  if (detectTrap(data)) {
    return { symbol, type: "TRAP", confidence: 0 };
  }

  const score = calculateAdaptiveScore(data);
  data.score = score;

  if (detectHighPump(data)) {
    return { symbol, type: "HIGH_PUMP", confidence: score, level: "EXPLOSION" };
  }

  if (detectExplosion(data)) {
    return { symbol, type: "SNIPER", confidence: score, level: "EXPLOSION" };
  }

  if (detectPressure(data)) {
    return { symbol, type: "PRESSURE", confidence: score, level: "BUILDING" };
  }

  if (detectAccumulation(data)) {
    return { symbol, type: "ACCUMULATION", confidence: score, level: "BUILDING" };
  }

  if (detectEarlyPump(data)) {
    return { symbol, type: "EARLY_PUMP", confidence: score, level: "WATCH" };
  }

  if (score >= 30) {
    return { symbol, type: "EARLY ENTRY", confidence: score, level: "BUILDING" };
  }

  return null;
}

export const SIGNAL_PRIORITY = {
  HIGH_PUMP: 5,
  SNIPER: 4,
  PRESSURE: 3,
  ACCUMULATION: 2,
  EARLY_PUMP: 1,
  EARLY_ENTRY: 1,
  TRAP: 0
};
