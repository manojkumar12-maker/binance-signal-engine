const d1TrendMap = new Map();
const h4Zones = new Map();
const m15Data = new Map();
const WEIGHT = { volume: 10, oiChange: 20, orderFlow: 15, momentum: 10 };

let whaleCache = new Map();
let newsCache = new Map();
let enableWhaleFilter = true;
let enableNewsFilter = false;

export function setWhaleFilter(enabled) {
  enableWhaleFilter = enabled;
}

export function setNewsFilter(enabled) {
  enableNewsFilter = enabled;
}

export function detectWhale(d) {
  const { volume, oiChange, priceChange, orderFlow } = d;
  
  if (volume >= 1.5 && oiChange >= 0.01 && Math.abs(priceChange) < 1.5) {
    if (orderFlow > 1.2) {
      return 'ACCUMULATION';
    }
    if (orderFlow < 0.8) {
      return 'DISTRIBUTION';
    }
  }
  
  if (volume >= 2 && oiChange >= 0.03 && Math.abs(priceChange) < 2) {
    if (orderFlow > 1.3) {
      return 'ACCUMULATION';
    }
    if (orderFlow < 0.7) {
      return 'DISTRIBUTION';
    }
  }
  
  return null;
}

export function detectFuturesWhale(d) {
  const { volume, oiChange, priceChange, takerBuyRatio, takerSellRatio } = d;
  
  if (
    oiChange > 0.2 &&
    takerBuyRatio > 1.2 &&
    priceChange < 0.5
  ) return 'ACCUMULATION';
  
  if (
    oiChange > 0.2 &&
    takerSellRatio > 1.2 &&
    priceChange < 0.5
  ) return 'DISTRIBUTION';
  
  return null;
}

export function getWhaleFromCache(symbol) {
  const cached = whaleCache.get(symbol);
  if (cached && Date.now() - cached.timestamp < 60000) {
    return cached.whale;
  }
  return null;
}

export function setWhaleCache(symbol, whale) {
  whaleCache.set(symbol, { whale, timestamp: Date.now() });
}

export function getDirectionFromWhale(whale) {
  if (whale === 'ACCUMULATION') return 'LONG';
  if (whale === 'DISTRIBUTION') return 'SHORT';
  return null;
}

export function getNewsImpact(news) {
  if (!news) return 0;
  
  if (news.positive) return 10;
  if (news.negative) return -10;
  if (news.impact === 'high') return 5;
  if (news.impact === 'low') return 0;
  
  return 0;
}

export function getNewsFromCache(symbol) {
  const cached = newsCache.get(symbol);
  if (cached && Date.now() - cached.timestamp < 300000) {
    return cached.news;
  }
  return null;
}

export function setNewsCache(symbol, news) {
  newsCache.set(symbol, { news, timestamp: Date.now() });
}

export function analyzeNewsSentiment(newsList) {
  if (!newsList || newsList.length === 0) return { score: 0, impact: 'none', sentiment: 'neutral' };
  
  let score = 0;
  const keywords = {
    positive: ['bullish', 'surge', 'rally', 'breakout', 'upgrade', 'ETF', 'adoption'],
    negative: ['bearish', 'crash', 'hack', 'ban', 'regulation', 'lawsuit', 'liquidate']
  };
  
  newsList.forEach(news => {
    const title = (news.title || '').toLowerCase();
    
    keywords.positive.forEach(kw => {
      if (title.includes(kw)) score += 2;
    });
    
    keywords.negative.forEach(kw => {
      if (title.includes(kw)) score -= 3;
    });
  });
  
  const impact = score > 5 ? 'high' : score > 2 ? 'medium' : 'low';
  const sentiment = score > 3 ? 'positive' : score < -3 ? 'negative' : 'neutral';
  
  return { score, impact, sentiment };
}

export function isHighImpactNewsTime() {
  const hour = new Date().getUTCHours();
  const highImpactHours = [13, 14, 15, 8, 9, 10];
  return highImpactHours.includes(hour);
}

export function filterByNewsRisk(session) {
  if (!enableNewsFilter) return { filtered: false, reason: null };
  
  const isHighImpact = isHighImpactNewsTime();
  
  if (isHighImpact && session === 'ASIA') {
    return { filtered: true, reason: 'HIGH_IMPACT_NEWS_ASIA_SESSION' };
  }
  
  return { filtered: false, reason: null };
}

export function getDirection(d) {
  const { orderFlow, oiChange, momentum, priceChange } = d;
  const priceUp = priceChange > 0;
  const priceDown = priceChange < 0;
  
  if (
    orderFlow > 1.1 &&
    oiChange > 0 &&
    momentum > 0
  ) {
    return 'LONG';
  }
  
  if (
    orderFlow < 0.9 &&
    oiChange > 0 &&
    momentum < 0
  ) {
    return 'SHORT';
  }
  
  if (priceUp && orderFlow < 1.0) {
    return 'SHORT';
  }
  
  if (priceDown && orderFlow > 1.0) {
    return 'LONG';
  }
  
  return null;
}

export function getDirectionForSignalType(type, d) {
  const direction = getDirection(d);
  
  switch (type) {
    case 'HIGH_PUMP':
    case 'SNIPER':
      return direction;
      
    case 'PRESSURE':
    case 'ACCUMULATION':
      return direction;
      
    case 'EARLY_PUMP':
      return direction;
      
    case 'TRAP':
      return direction === 'LONG' ? 'SHORT' : 'LONG';
      
    default:
      return direction;
  }
}

export function getD1Bias(symbol, d1Data) {
  if (!d1Data) return 'NEUTRAL';
  
  const trend = d1Data.trend || d1Data.direction;
  if (trend === 'up' || trend === 'bullish' || trend === 'LONG') return 'BUY';
  if (trend === 'down' || trend === 'bearish' || trend === 'SHORT') return 'SELL';
  return 'NEUTRAL';
}

export function setD1Trend(symbol, trend) {
  d1TrendMap.set(symbol, { trend, timestamp: Date.now() });
}

export function getD1Trend(symbol) {
  return d1TrendMap.get(symbol) || { trend: 'NEUTRAL' };
}

export function filterByD1Trend(signal, symbol) {
  const d1 = getD1Trend(symbol);
  const d1Bias = getD1Bias(symbol, d1);
  
  if (d1Bias === 'NEUTRAL') return { filtered: false, reason: 'D1_NEUTRAL' };
  
  const signalDir = signal.direction === 'LONG' ? 'BUY' : 'SELL';
  
  if (signalDir !== d1Bias) {
    return { filtered: true, reason: `D1_TREND_MISMATCH: signal=${signalDir}, d1=${d1Bias}` };
  }
  
  return { filtered: false, reason: null };
}

export function isNearZone(price, zones, threshold = 0.005) {
  if (!zones || zones.length === 0) return true;
  return zones.some(z => Math.abs(price - z) / price < threshold);
}

export function setH4Zone(symbol, zone) {
  const existing = h4Zones.get(symbol) || [];
  existing.push({ ...zone, timestamp: Date.now() });
  h4Zones.set(symbol, existing);
}

export function getH4Zones(symbol) {
  const zones = h4Zones.get(symbol) || [];
  return zones.map(z => z.price || z);
}

export function filterByH4Zone(signal) {
  const symbol = signal.symbol;
  const zones = getH4Zones(symbol);
  const price = signal.entry || signal.price;
  
  if (!isNearZone(price, zones, 0.005)) {
    return { filtered: true, reason: 'NOT_NEAR_H4_ZONE' };
  }
  
  return { filtered: false, reason: null };
}

export function getSession() {
  const hour = new Date().getUTCHours();
  
  if (hour >= 7 && hour < 16) return 'LONDON';
  if (hour >= 13 && hour < 22) return 'NEW_YORK';
  if (hour >= 0 && hour < 7) return 'ASIA';
  if (hour >= 22 || hour < 0) return 'ASIA';
  return 'ASIA';
}

export function getSessionInfo() {
  const hour = new Date().getUTCHours();
  const session = getSession();
  
  return {
    session,
    hour,
    isHighLiquidity: session === 'LONDON' || session === 'NEW_YORK'
  };
}

export function filterBySession(allowAsia = false) {
  const { session, isHighLiquidity } = getSessionInfo();
  
  if (!allowAsia && !isHighLiquidity) {
    return { filtered: true, reason: `ASIA_SESSION_LOW_VOLUME: ${session}` };
  }
  
  return { filtered: false, reason: null, session };
}

export function setM15Data(symbol, data) {
  m15Data.set(symbol, { ...data, timestamp: Date.now() });
}

export function getM15Data(symbol) {
  return m15Data.get(symbol) || null;
}

export function confirmM15Entry(symbol, direction) {
  const m15 = getM15Data(symbol);
  
  if (!m15) return { confirmed: true, reason: 'NO_M15_DATA_PASSTHROUGH' }; // ✅ FIX 2: Pass through when no data
  
  const bosUp = m15.breakStructureUp || m15.bosUp || false;
  const bosDown = m15.breakStructureDown || m15.bosDown || false;
  const mom = m15.momentum || m15.mom || 0;
  
  if (direction === 'LONG' && !bosUp) {
    return { confirmed: false, reason: 'M15_NO_BOS_UP' };
  }
  
  if (direction === 'SHORT' && !bosDown) {
    return { confirmed: false, reason: 'M15_NO_BOS_DOWN' };
  }
  
  if (direction === 'LONG' && mom < 0) {
    return { confirmed: false, reason: 'M15_NEGATIVE_MOMENTUM' };
  }
  
  if (direction === 'SHORT' && mom > 0) {
    return { confirmed: false, reason: 'M15_POSITIVE_MOMENTUM' };
  }
  
  return { confirmed: true, reason: null, data: m15 };
}

export function calculateWeightedScore(data) {
  const { volume, oiChange, orderFlow, momentum } = data;
  
  let score = 0;
  score += (volume || 1) * WEIGHT.volume;
  score += Math.abs(oiChange || 0) * WEIGHT.oiChange;
  score += (orderFlow || 1) * WEIGHT.orderFlow;
  score += Math.max(0, momentum || 0) * WEIGHT.momentum;
  
  return Math.min(100, score);
}

export function formatEnhancedSignal(signal, config = {}) {
  const {
    slPercent = 0.015,
    tpPercent = 0.03
  } = config;
  
  const currentPrice = signal.entry || signal.price;
  const direction = signal.direction === 'LONG' ? 'BUY' : 'SELL';
  
  const stopLoss = direction === 'BUY' 
    ? currentPrice * (1 - slPercent) 
    : currentPrice * (1 + slPercent);
    
  const takeProfit = direction === 'BUY'
    ? currentPrice * (1 + tpPercent)
    : currentPrice * (1 - tpPercent);
  
  return {
    pair: signal.symbol,
    type: direction,
    stage: signal.level || signal.type || 'ENTRY',
    entry: currentPrice,
    stopLoss,
    takeProfit,
    confidence: signal.confidence || signal.score || 0,
    direction: signal.direction,
    metrics: {
      volume: signal.data?.volume,
      oiChange: signal.data?.oiChange,
      orderFlow: signal.data?.orderFlow,
      momentum: signal.data?.momentum
    }
  };
}

export function applyAllFilters(signal, options = {}) {
  const {
    allowAsia = false,
    requireM15 = true,
    requireD1 = true,
    requireH4 = true,
    requireDirection = true,
    requireWhale = true
  } = options;
  
  if (!signal) return { filtered: null, reason: 'NO_SIGNAL' };
  
  if (requireWhale && enableWhaleFilter && !signal.whale) {
    return { filtered: true, reason: 'NO_WHALE_ACTIVITY' };
  }
  
  if (requireDirection && !signal.direction) {
    return { filtered: true, reason: 'NO_DIRECTION' };
  }
  
  if (requireD1) {
    const d1Result = filterByD1Trend(signal, signal.symbol);
    if (d1Result.filtered) return d1Result;
  }
  
  if (requireH4) {
    const h4Result = filterByH4Zone(signal);
    if (h4Result.filtered) return h4Result;
  }
  
  const sessionResult = filterBySession(allowAsia);
  if (sessionResult.filtered) return sessionResult;
  
  const newsRiskResult = filterByNewsRisk(sessionResult?.session || getSession());
  if (newsRiskResult.filtered) return newsRiskResult;
  
  if (requireM15) {
    const m15Result = confirmM15Entry(signal.symbol, signal.direction);
    if (!m15Result.confirmed) return { filtered: true, reason: m15Result.reason };
  }
  
  return { filtered: false, reason: null };
}

export function getTradeSignal(d) {
  if (!d) return null;
  
  const whale = detectWhale(d);
  if (!whale) {
    return { filtered: true, reason: 'NO_WHALE_ACTIVITY' };
  }
  
  const score = calculateWeightedScore(d);
  const direction = getDirection(d);
  
  if (!direction) {
    return { filtered: true, reason: 'NO_CLEAR_DIRECTION' };
  }
  
  if (score < 30) {
    return { filtered: true, reason: 'SCORE_BELOW_30' };
  }
  
  let type = 'WATCH';
  if (score >= 50) type = 'HIGH_PUMP';
  else if (score >= 40) type = 'SNIPER';
  else if (score >= 30) type = 'PRESSURE';
  
  const isTrap = (d.priceChange > 5 && d.orderFlow < 1.1) ||
                 (d.priceChange < -5 && d.orderFlow < 1.1);
  if (isTrap) {
    type = 'TRAP';
    return {
      type,
      direction: direction === 'LONG' ? 'SHORT' : 'LONG',
      level: 'TRAP',
      confidence: score,
      filtered: false,
      reason: 'TRAP_DETECTED_FADE'
    };
  }
  
  const level = score >= 40 ? 'EXPLOSION' : score >= 30 ? 'ENTRY' : 'WATCH';
  
  if (level === 'WATCH') {
    return { filtered: true, reason: 'WATCH_LEVEL_BLOCKED' };
  }
  
  return {
    type,
    direction,
    level,
    confidence: score,
    data: d,
    whale,
    filtered: false
  };
}

export function fetchD1Data(symbol) {
  return null;
}

export function fetchH4Zones(symbol) {
  return [];
}

export function fetchM15Data(symbol) {
  return null;
}

export function updateMarketTimeframes(symbol, timeframes) {
  if (timeframes.d1) setD1Trend(symbol, timeframes.d1);
  if (timeframes.h4) setH4Zone(symbol, timeframes.h4);
  if (timeframes.m15) setM15Data(symbol, timeframes.m15);
}

export const advancedFilters = {
  getD1Bias,
  setD1Trend,
  getD1Trend,
  filterByD1Trend,
  isNearZone,
  setH4Zone,
  getH4Zones,
  filterByH4Zone,
  getSession,
  getSessionInfo,
  filterBySession,
  setM15Data,
  getM15Data,
  confirmM15Entry,
  calculateWeightedScore,
  formatEnhancedSignal,
  applyAllFilters,
  updateMarketTimeframes,
  getDirection,
  getDirectionForSignalType,
  getTradeSignal,
  detectWhale,
  detectFuturesWhale,
  getWhaleFromCache,
  setWhaleCache,
  getDirectionFromWhale,
  getNewsImpact,
  analyzeNewsSentiment,
  isHighImpactNewsTime,
  filterByNewsRisk,
  setWhaleFilter,
  setNewsFilter,
  WEIGHT
};
