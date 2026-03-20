export function calculateConfidence(data) {
  let confidence = 0;
  
  const { score, volumeSpike, momentum, imbalance, priceChange, trend, atr, atrMA } = data;

  if (!score || score < 40) return 0;

  confidence += Math.min(score * 0.35, 35);

  if (volumeSpike) {
    confidence += Math.min(volumeSpike * 12, 24);
  }

  if (momentum !== undefined && momentum !== null) {
    confidence += Math.max(Math.min(momentum * 80, 20), -10);
  }

  if (imbalance && imbalance > 1) {
    confidence += Math.min(imbalance * 8, 16);
  }

  if (trend === 'UP' || trend === 'BULLISH') {
    confidence += 10;
  } else if (trend === 'DOWN' || trend === 'BEARISH') {
    confidence -= 5;
  }

  if (atr && atrMA && atr > atrMA) {
    confidence += 8;
  }

  if (priceChange > 12) {
    confidence -= 18;
  } else if (priceChange > 8) {
    confidence -= 8;
  } else if (priceChange < 1) {
    confidence -= 5;
  }

  if (volumeSpike > 3 && momentum < 0.05) {
    confidence -= 15;
  }

  if (momentum < 0) {
    confidence -= 8;
  }

  return Math.max(0, Math.min(100, Math.round(confidence)));
}

export function classifyByConfidence(confidence) {
  if (confidence >= 80) return 'SNIPER';
  if (confidence >= 65) return 'CONFIRMED';
  if (confidence >= 50) return 'EARLY';
  return null;
}

export function hasConfluence(data) {
  let confluence = 0;
  
  const { volumeSpike, momentum, imbalance, trend, priceChange } = data;

  if (volumeSpike >= 2) confluence++;
  if (volumeSpike >= 3) confluence++;
  if (momentum >= 0.1) confluence++;
  if (momentum >= 0.2) confluence++;
  if (imbalance >= 1.3) confluence++;
  if (imbalance >= 1.5) confluence++;
  if (trend === 'UP' || trend === 'BULLISH') confluence++;
  if (priceChange >= 2 && priceChange <= 8) confluence++;

  return confluence >= 4;
}

export function isTrendingMarket(data) {
  const { atr, atrMA } = data;
  if (!atr || !atrMA) return true;
  return atr > atrMA * 0.9;
}

export function isFakePump(data) {
  const { volumeSpike, momentum } = data;
  return volumeSpike > 3 && (momentum < 0.05 || momentum < 0);
}

export function getSmartEntry(entryPrice, atr) {
  if (!atr) return entryPrice;
  return entryPrice - (0.003 * atr);
}

export function getEntryQuality(data) {
  const { priceChange } = data;
  
  if (priceChange >= 2 && priceChange <= 5) return 'EXCELLENT';
  if (priceChange >= 5 && priceChange <= 8) return 'GOOD';
  if (priceChange >= 8 && priceChange <= 12) return 'LATE';
  return 'TOO_LATE';
}

export function analyzeSignal(data) {
  const confidence = calculateConfidence(data);
  const type = classifyByConfidence(confidence);
  
  return {
    ...data,
    confidence,
    type,
    hasConfluence: hasConfluence(data),
    isTrendingMarket: isTrendingMarket(data),
    isFakePump: isFakePump(data),
    entryQuality: getEntryQuality(data),
    smartEntry: getSmartEntry(data.entryPrice, data.atr)
  };
}
