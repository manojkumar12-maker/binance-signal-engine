export function calculateConfidence(data) {
  let confidence = 0;
  
  const { score, volumeSpike, momentum, imbalance, priceChange, trend, atr, atrMA } = data;

  if (!score || score < 30) return 0;

  confidence += data.score * 0.6;
  confidence += Math.min(data.volumeSpike * 10, 25);
  confidence += Math.max((data.momentum * 100) * 0.2, 0);
  
  if (data.imbalance) {
    confidence += Math.min(data.imbalance * 10, 20);
  }

  if (data.trend === 'UP' || data.trend === 'BULLISH') {
    confidence += 10;
  }

  if (data.priceChange > 10) confidence -= 15;
  if (data.momentum < 0) confidence -= 10;

  return Math.max(0, Math.min(100, Math.round(confidence)));
}

export function classifyByConfidence(confidence) {
  if (confidence >= 80) return { tier: 'SNIPER', action: 'TRADE' };
  if (confidence >= 70) return { tier: 'CONFIRMED', action: 'WATCH' };
  if (confidence >= 40) return { tier: 'EARLY', action: 'WATCH' };
  return { tier: null, action: 'REJECT' };
}

export function hasConfluence(data) {
  let confluence = 0;

  if (data.volumeSpike > 2) confluence++;
  if (data.momentum > 0.1) confluence++;
  if (data.imbalance > 1.3) confluence++;
  if (data.trend === 'UP') confluence++;

  return confluence >= 3;
}

export function isTrendingMarket(data) {
  if (!data.atr || !data.atrMA) return { trending: true, regime: 'TRENDING' };
  return { trending: data.atr > data.atrMA, regime: data.atr > data.atrMA ? 'TRENDING' : 'SIDEWAYS' };
}

export function isFakePump(data) {
  const { volumeSpike, momentum } = data;
  return volumeSpike > 3 && momentum < 0.05;
}

export function getSmartEntry(entryPrice, atr) {
  if (!atr || !entryPrice) return entryPrice;
  return entryPrice - (0.3 * atr);
}

export function analyzeSignal(data) {
  const confidence = calculateConfidence(data);
  const classification = classifyByConfidence(confidence);
  const confluencePassed = hasConfluence(data);
  const marketStatus = isTrendingMarket(data);
  const fakePump = isFakePump(data);
  const smartEntry = getSmartEntry(data.entryPrice, data.atr);
  
  let entryQuality = 'N/A';
  if (data.priceChange >= 2 && data.priceChange <= 5) entryQuality = 'EXCELLENT';
  else if (data.priceChange >= 5 && data.priceChange <= 8) entryQuality = 'GOOD';
  else if (data.priceChange > 8) entryQuality = 'LATE';

  const shouldTrade = 
    classification.action !== 'REJECT' &&
    confluencePassed &&
    marketStatus.trending &&
    !fakePump;

  const shouldGenerateSignal = 
    classification.action !== 'REJECT' &&
    marketStatus.trending &&
    !fakePump;

  const confluenceCount = [data.volumeSpike > 2, data.momentum > 0.1, data.imbalance > 1.3, data.trend === 'UP'].filter(Boolean).length;

  return {
    ...data,
    confidence,
    confluence: Math.min(confluenceCount, 5),
    tier: classification.tier,
    action: classification.action,
    hasConfluence: confluencePassed,
    confluenceCount: Math.min(confluenceCount, 5),
    isTrending: marketStatus.trending,
    regime: marketStatus.regime,
    isFakePump: fakePump,
    entryQuality,
    smartEntry,
    shouldTrade,
    shouldGenerateSignal
  };
}

export function rankSignals(signals) {
  return signals
    .map(s => ({
      ...s,
      rankScore: (s.confidence || 0) * 0.6 + (s.volumeSpike || 0) * 10 + (s.momentum || 0) * 50
    }))
    .sort((a, b) => b.rankScore - a.rankScore)
    .map((s, i) => ({ ...s, rank: i + 1 }));
}

export function getTopSignals(signals, limit = 5) {
  return rankSignals(signals).slice(0, limit);
}

export function filterTradeableSignals(signals) {
  return rankSignals(signals).filter(s => s.shouldTrade && s.tier !== null).slice(0, 3);
}
