export function calculateConfidence(data) {
  let confidence = 0;
  
  const { score, volumeSpike, momentum, imbalance, priceChange, trend, atr, atrMA, marketRegime } = data;

  if (!score || score < 40) return 0;

  confidence += Math.min(score * 0.6, 50);

  if (volumeSpike) {
    confidence += Math.min(volumeSpike * 10, 25);
  }

  if (momentum !== undefined && momentum !== null) {
    confidence += Math.max(Math.min(momentum * 40, 20), -15);
  }

  if (imbalance && imbalance > 1) {
    confidence += Math.min(imbalance * 12, 20);
  }

  if (trend === 'UP' || trend === 'BULLISH') {
    confidence += 12;
  } else if (trend === 'DOWN' || trend === 'BEARISH') {
    confidence -= 10;
  }

  if (atr && atrMA && atr > atrMA) {
    confidence += 10;
  }

  if (priceChange > 10) {
    confidence -= 25;
  } else if (priceChange > 8) {
    confidence -= 12;
  } else if (priceChange < 1) {
    confidence -= 8;
  }

  if (volumeSpike > 3 && momentum < 0.05) {
    confidence -= 30;
  }

  if (momentum < 0) {
    confidence -= 12;
  }

  if (marketRegime === 'SIDEWAYS') {
    confidence -= 20;
  }

  return Math.max(0, Math.min(100, Math.round(confidence)));
}

export function classifyByConfidence(confidence) {
  if (confidence >= 80) return { tier: 'SNIPER', action: 'TRADE' };
  if (confidence >= 65) return { tier: 'CONFIRMED', action: 'WATCH' };
  if (confidence >= 50) return { tier: 'EARLY', action: 'IGNORE' };
  return { tier: null, action: 'REJECT' };
}

export function getConfluenceScore(data) {
  let confluence = 0;
  const reasons = [];
  
  const { volumeSpike, momentum, imbalance, trend, priceChange, orderbookImbalance } = data;

  if (volumeSpike > 2) { confluence++; reasons.push('Vol Spike'); }
  if (volumeSpike > 3) { confluence++; reasons.push('Strong Vol'); }
  if (momentum > 0.1) { confluence++; reasons.push('Momentum'); }
  if (momentum > 0.2) { confluence++; reasons.push('Strong Mom'); }
  if ((imbalance || orderbookImbalance) > 1.3) { confluence++; reasons.push('OB Imbalance'); }
  if ((imbalance || orderbookImbalance) > 1.5) { confluence++; reasons.push('Strong OB'); }
  if (trend === 'UP' || trend === 'BULLISH') { confluence++; reasons.push('Uptrend'); }
  if (priceChange >= 2 && priceChange <= 8) { confluence++; reasons.push('Sweet Spot'); }

  confluence = Math.min(confluence, 5);

  return { score: confluence, reasons, passed: confluence >= 3 };
}

export function isTrendingMarket(data) {
  const { atr, atrMA } = data;
  if (!atr || !atrMA) return { trending: true, regime: 'TRENDING' };
  
  const trending = atr > atrMA * 0.9;
  return { 
    trending, 
    regime: trending ? 'TRENDING' : 'SIDEWAYS' 
  };
}

export function isFakePump(data) {
  const { volumeSpike, momentum } = data;
  const isFake = volumeSpike > 3 && (momentum < 0.05 || momentum < 0);
  return { isFake, reason: isFake ? 'High vol + low momentum' : null };
}

export function getLateEntryStatus(priceChange) {
  if (priceChange > 12) return { late: true, quality: 'TOO_LATE', warning: 'Exhausted pump' };
  if (priceChange > 10) return { late: true, quality: 'LATE', warning: 'Getting late' };
  if (priceChange >= 5 && priceChange <= 10) return { late: false, quality: 'GOOD', warning: null };
  if (priceChange >= 2 && priceChange < 5) return { late: false, quality: 'EXCELLENT', warning: null };
  return { late: true, quality: 'TOO_EARLY', warning: 'Too early' };
}

export function getSmartEntry(entryPrice, atr) {
  if (!atr || !entryPrice) return entryPrice;
  return entryPrice - (0.003 * atr);
}

export function analyzeSignal(data) {
  const confidence = calculateConfidence(data);
  const classification = classifyByConfidence(confidence);
  const confluence = getConfluenceScore(data);
  const marketStatus = isTrendingMarket(data);
  const fakePump = isFakePump(data);
  const entryStatus = getLateEntryStatus(data.priceChange);
  
  const shouldTrade = 
    classification.action === 'TRADE' &&
    confluence.passed &&
    marketStatus.trending &&
    !fakePump.isFake &&
    !entryStatus.late;

  return {
    ...data,
    confidence,
    tier: classification.tier,
    action: classification.action,
    confluence: confluence.score,
    confluenceReasons: confluence.reasons,
    hasConfluence: confluence.passed,
    regime: marketStatus.regime,
    isTrending: marketStatus.trending,
    isFakePump: fakePump.isFake,
    fakePumpReason: fakePump.reason,
    entryQuality: entryStatus.quality,
    entryWarning: entryStatus.warning,
    smartEntry: getSmartEntry(data.entryPrice, data.atr),
    shouldTrade
  };
}

export function rankSignals(signals) {
  return signals
    .map(signal => {
      const rankScore = calculateRankScore(signal);
      return { ...signal, rankScore };
    })
    .sort((a, b) => b.rankScore - a.rankScore)
    .map((signal, index) => ({ ...signal, rank: index + 1 }));
}

export function calculateRankScore(signal) {
  let score = 0;
  
  score += (signal.confidence || 0) * 0.6;
  
  score += Math.min((signal.volumeSpike || 0) * 10, 25);
  
  score += Math.max((signal.momentum || 0) * 40, -15);
  
  if (signal.hasConfluence) score += 15;
  
  if (signal.isTrending) score += 12;
  
  if (signal.entryQuality === 'EXCELLENT') score += 20;
  else if (signal.entryQuality === 'GOOD') score += 12;
  else if (signal.entryQuality === 'LATE') score += 5;
  else score -= 20;
  
  if (signal.tier === 'SNIPER') score += 25;
  else if (signal.tier === 'CONFIRMED') score += 15;
  
  if (!signal.isFakePump) score += 12;
  else score -= 30;
  
  return Math.round(score * 100) / 100;
}

export function getTopSignals(signals, limit = 3) {
  return rankSignals(signals).slice(0, limit);
}

export function filterTradeableSignals(signals) {
  return rankSignals(signals).filter(s => 
    s.shouldTrade && 
    s.tier !== null &&
    s.rank <= 5
  );
}
