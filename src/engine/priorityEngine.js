export function calculatePriorityScore(data) {
  let score = 0;

  if (Math.abs(data.oiChange) > 0.5) score += 25;
  else if (Math.abs(data.oiChange) > 0.3) score += 15;
  else if (Math.abs(data.oiChange) > 0.1) score += 5;

  if (Math.abs(data.fakeOI) > 0.5) score += 20;
  else if (Math.abs(data.fakeOI) > 0.3) score += 12;
  else if (Math.abs(data.fakeOI) > 0.15) score += 5;

  if (data.orderFlow > 2) score += 15;
  else if (data.orderFlow > 1.5) score += 10;
  else if (data.orderFlow > 1.2) score += 5;

  if (data.volume > 5) score += 15;
  else if (data.volume > 3) score += 10;
  else if (data.volume > 2) score += 5;

  if (data.priceAcceleration > 0.3) score += 10;
  else if (data.priceAcceleration > 0.2) score += 7;
  else if (data.priceAcceleration > 0.1) score += 3;

  if (data.momentum > 0) score += 5;
  if (data.momentumAcceleration > 0) score += 3;

  return score;
}

export function getEffectiveOI(data) {
  if (Math.abs(data.oiChange) > 0.01) return data.oiChange;
  if (data.fakeOI !== undefined && Math.abs(data.fakeOI) > 0.01) return data.fakeOI;
  return data.oiChange || 0;
}

export function isPerfectSniper(data) {
  const oi = getEffectiveOI(data);
  
  return (
    data.priceAcceleration > 0.3 &&
    data.volume > 4 &&
    data.orderFlow > 1.8 &&
    Math.abs(oi) > 0.5 &&
    !isTrapAdvanced(data)
  );
}

export function isTrapAdvanced(data) {
  if (data.priceChange > 5 && data.orderFlow < 1.2) return { isTrap: true, reason: 'PUMP_NO_PARTICIPATION' };
  
  if (
    Math.abs(data.oiChange) < 0.1 &&
    Math.abs(data.fakeOI || 0) < 0.2 &&
    data.priceChange > 3
  ) return { isTrap: true, reason: 'NO_OI_FAKE_MOVE' };

  if (data.upperWickRatio > 0.5 && data.orderFlow < 1.5) return { isTrap: true, reason: 'WICK_TRAP' };

  if (data.volume > 5 && data.orderFlow < 1.0 && data.priceChange > 2) {
    return { isTrap: true, reason: 'HIGH_VOL_LOW_FLOW' };
  }

  return { isTrap: false, reason: null };
}

export function predictBreakout(data) {
  let score = 0;

  if (data.fakeOI > 0.4) score += 2;
  if (data.orderFlow > 1.5) score += 2;
  if (data.volume > 2.5) score += 2;
  if (data.priceAcceleration > 0.2) score += 2;
  if (data.liquiditySweep) score += 2;
  if (data.momentumAcceleration > 0) score += 1;
  if (data.accumulationScore > 3) score += 2;

  if (score >= 7) return { eta: '5-10s', urgency: 'IMMINENT' };
  if (score >= 5) return { eta: '10-30s', urgency: 'SOON' };
  if (score >= 3) return { eta: '30-60s', urgency: 'BUILDING' };

  return null;
}

export function applySniperFilter(data) {
  const oi = getEffectiveOI(data);
  const trap = isTrapAdvanced(data);

  if (trap.isTrap) return { pass: false, reason: trap.reason };

  if (Math.abs(oi) < 0.5) return { pass: false, reason: 'WEAK_OI' };
  if (data.volume < 4) return { pass: false, reason: 'LOW_VOLUME' };
  if (data.orderFlow < 1.8) return { pass: false, reason: 'LOW_FLOW' };
  if (data.priceAcceleration < 0.3) return { pass: false, reason: 'WEAK_ACCEL' };
  if (Math.abs(data.priceChange) > 15) return { pass: false, reason: 'LATE_ENTRY' };

  return { pass: true, reason: null };
}

export function calculateSniperConfidence(data) {
  let confidence = 70;
  const oi = getEffectiveOI(data);

  if (Math.abs(oi) > 0.7) confidence += 15;
  else if (Math.abs(oi) > 0.5) confidence += 10;

  if (data.volume > 6) confidence += 8;
  else if (data.volume > 4) confidence += 5;

  if (data.orderFlow > 2.5) confidence += 10;
  else if (data.orderFlow > 1.8) confidence += 5;

  if (data.priceAcceleration > 0.5) confidence += 10;
  else if (data.priceAcceleration > 0.3) confidence += 5;

  const trap = isTrapAdvanced(data);
  if (trap.isTrap) confidence -= 20;

  return Math.min(Math.max(confidence, 0), 95);
}
