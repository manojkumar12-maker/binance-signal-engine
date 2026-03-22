export function calculateConfidence(data) {
  const { score = 0, volumeSpike = 0, momentum = 0, imbalance = 1, priceChange = 0, trend = 'DOWN', orderflow = 1, oiChange = 0 } = data;

  if (!score || score < 0) return 0;

  let confidence = 0;

  confidence += score * 0.5;
  confidence += Math.min(volumeSpike, 3) * 6;
  confidence += Math.min(Math.max(momentum, 0), 0.1) * 40;
  
  if (orderflow && orderflow > 1) {
    confidence += Math.min(orderflow - 1, 1) * 15;
  }
  
  confidence += Math.min(Math.abs(oiChange), 5) * 2;
  confidence += Math.min(imbalance * 4, 12);

  if (trend === 'UP' || trend === 'BULLISH') {
    confidence += 5;
  }

  if (priceChange > 10) confidence -= 10;
  if (momentum < 0) confidence -= 5;

  return Math.max(0, Math.min(100, Math.round(confidence)));
}

export function classifyByConfidence(confidence) {
  if (confidence >= 75) return { tier: 'SNIPER', action: 'TRADE' };
  if (confidence >= 60) return { tier: 'CONFIRMED', action: 'WATCH' };
  if (confidence >= 45) return { tier: 'EARLY', action: 'WATCH' };
  return { tier: null, action: 'REJECT' };
}

export function hasConfluence(data) {
  let confluence = 0;

  if (data.volumeSpike > 3) confluence++;
  if (data.momentum > 0.1) confluence++;
  if (data.imbalance > 1.3) confluence++;
  if (data.trend === 'UP') confluence++;
  if (data.orderflow > 1.3) confluence++;

  return confluence >= 3;
}

export function isTrendingMarket(data) {
  if (!data.atr || !data.atrMA) return { trending: true, regime: 'TRENDING' };
  return { trending: data.atr > data.atrMA, regime: data.atr > data.atrMA ? 'TRENDING' : 'SIDEWAYS' };
}

export function isFakePump(data) {
  const { volumeSpike, momentum, orderflow } = data;
  return volumeSpike > 6 && momentum < 0.02 && (orderflow || 1) < 1.2;
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
    !fakePump;

  const shouldGenerateSignal = 
    classification.action !== 'REJECT' ||
    confluencePassed;

  const confluenceCount = [data.volumeSpike > 3, data.momentum > 0.1, data.imbalance > 1.3, data.trend === 'UP', data.orderflow > 1.3, data.oiChange > 1].filter(Boolean).length;

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
