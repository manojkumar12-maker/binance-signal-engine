export function detectMarketRegime(data) {
  let score = {
    trend: 0,
    chop: 0,
    squeeze: 0
  };

  if (Math.abs(data.priceChange) > 2) score.trend += 2;
  if (data.momentum > 0.2) score.trend += 1;
  if (data.emaTrend === true) score.trend += 1;
  if (data.vwapTrend === true) score.trend += 1;

  if (Math.abs(data.priceChange) < 1) score.chop += 2;
  if (data.volume < 1.5) score.chop += 1;
  if (Math.abs(data.orderFlow - 1) < 0.2) score.chop += 1;
  if (data.rsi > 45 && data.rsi < 55) score.chop += 1;

  const effectiveOI = getEffectiveOI(data);
  if (Math.abs(effectiveOI) > 0.5) score.squeeze += 2;
  if (data.fakeOI > 0.5) score.squeeze += 2;
  if (data.volume > 4) score.squeeze += 1;
  if (data.orderFlow > 1.8) score.squeeze += 1;

  if (score.squeeze >= 4) return 'SQUEEZE';
  if (score.trend >= 4) return 'TREND';
  if (score.chop >= 3) return 'CHOP';

  return 'NEUTRAL';
}

function getEffectiveOI(data) {
  if (Math.abs(data.oiChange) > 0.01) return data.oiChange;
  if (data.fakeOI !== undefined && Math.abs(data.fakeOI) > 0.01) return data.fakeOI;
  return data.oiChange || 0;
}

export function getRegimeEmoji(regime) {
  switch (regime) {
    case 'TREND': return '📈';
    case 'CHOP': return '🌀';
    case 'SQUEEZE': return '💥';
    default: return '⚪';
  }
}

export function getRegimeThreshold(regime) {
  switch (regime) {
    case 'SQUEEZE': return 55;
    case 'TREND': return 65;
    case 'NEUTRAL': return 70;
    case 'CHOP': return 85;
    default: return 65;
  }
}
