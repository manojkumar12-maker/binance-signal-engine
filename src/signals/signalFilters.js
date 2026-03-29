const lastSignalTime = {};

// ========== MARKET STATE (for adaptive scoring) ==========
export const marketState = {
  trend: 'UNKNOWN', // UP, DOWN, UNKNOWN
  volatility: 'NORMAL', // LOW, NORMAL, HIGH
  atrValue: 0,
  avgVolume: 0,
  lastUpdate: 0,
  consecutiveLosses: 0,
  riskMultiplier: 1,
  marketBias: 'NEUTRAL', // BULLISH, BEARISH, NEUTRAL, CHOP
  totalPositiveOI: 0,
  totalNegativeOI: 0
};

// ========== Z-SCORE OI DETECTION (Adaptive) ==========
const oiHistory = new Map();

export function calculateZScore(symbol, currentOI) {
  if (!oiHistory.has(symbol)) {
    oiHistory.set(symbol, []);
  }
  
  const history = oiHistory.get(symbol);
  history.push(currentOI);
  
  // Keep last 50 data points
  if (history.length > 50) history.shift();
  
  // Need at least 10 points for meaningful z-score
  if (history.length < 10) return 0;
  
  // Calculate mean
  const mean = history.reduce((a, b) => a + b, 0) / history.length;
  
  // Calculate std dev
  const variance = history.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / history.length;
  const stdDev = Math.sqrt(variance);
  
  if (stdDev === 0) return 0;
  
  // Z-score: how many std deviations from mean
  return (currentOI - mean) / stdDev;
}

export function isOISignificant(symbol, oiChange) {
  const zScore = calculateZScore(symbol, oiChange);
  
  // Z-score > 2 means unusual activity (2 std deviations)
  return {
    significant: zScore > 2,
    zScore: zScore,
    tier: zScore > 3 ? 'STRONG' : zScore > 2 ? 'MODERATE' : 'NOISE'
  };
}

// ========== CLUSTER DETECTION (Consecutive OI builds) ==========
const oiConsecutiveCount = new Map();
const OI_CLUSTER_THRESHOLD = 3; // 3 consecutive increases = cluster

export function detectOICluster(symbol, oiChange) {
  if (!oiConsecutiveCount.has(symbol)) {
    oiConsecutiveCount.set(symbol, { count: 0, direction: 0 });
  }
  
  const cluster = oiConsecutiveCount.get(symbol);
  
  if (Math.abs(oiChange) < 0.01) {
    // Reset on noise
    cluster.count = 0;
    cluster.direction = 0;
    return { isCluster: false, count: 0 };
  }
  
  const direction = oiChange > 0 ? 1 : -1;
  
  if (cluster.direction === direction) {
    cluster.count++;
  } else {
    cluster.count = 1;
    cluster.direction = direction;
  }
  
  return {
    isCluster: cluster.count >= OI_CLUSTER_THRESHOLD,
    count: cluster.count,
    direction: direction > 0 ? 'BUILDING_UP' : 'BUILDING_DOWN'
  };
}

// ========== MARKET BIAS FILTER (Skip chop) ==========
const marketBiasHistory = new Map();

export function updateMarketBias(symbol, oiChange, priceChange) {
  if (!marketBiasHistory.has(symbol)) {
    marketBiasHistory.set(symbol, { positive: 0, negative: 0, neutral: 0 });
  }
  
  const bias = marketBiasHistory.get(symbol);
  
  // Lowered threshold: was 0.02, now 0.005
  if (oiChange > 0.005) bias.positive++;
  else if (oiChange < -0.005) bias.negative++;
  else bias.neutral++;
  
  // Keep rolling window of 20
  const total = bias.positive + bias.negative + bias.neutral;
  if (total > 20) {
    const remove = total - 20;
    if (bias.positive > bias.negative) bias.positive -= remove;
    else bias.negative -= remove;
  }
  
  // Determine market bias - require larger diff to classify as CHOP
  const diff = Math.abs(bias.positive - bias.negative);
  
  if (diff < 5) {  // Was 3, now 5
    marketState.marketBias = 'NEUTRAL';
    return 'NEUTRAL';
  }
  
  if (bias.positive > bias.negative) {
    marketState.marketBias = 'BULLISH';
    return 'BULLISH';
  }
  
  if (bias.negative > bias.positive) {
    marketState.marketBias = 'BEARISH';
    return 'BEARISH';
  }
  
  marketState.marketBias = 'NEUTRAL';
  return 'NEUTRAL';
}

export function isMarketChop() {
  return marketState.marketBias === 'CHOP';
}

// ========== NOISE FILTERING ==========
const OI_NOISE_THRESHOLD = 0.005; // Lowered: was 0.01
const VOL_NOISE_THRESHOLD = 0.5;  // Lowered: was 0.1

export function isNoise(oiChange, volumeRatio, priceChangePercent) {
  // Skip noise check on startup if OI data not available yet
  if (oiChange === undefined || oiChange === null) {
    return { noise: false, reason: null };
  }
  
  // OI noise
  if (Math.abs(oiChange) < OI_NOISE_THRESHOLD) {
    return { noise: true, reason: 'OI_NOISE' };
  }
  
  // Volume noise - only check if we have volume data
  if (volumeRatio !== undefined && volumeRatio < VOL_NOISE_THRESHOLD) {
    return { noise: true, reason: 'VOLUME_LOW' };
  }
  
  // Price noise - skip check when undefined (not yet available)
  if (priceChangePercent !== undefined && Math.abs(priceChangePercent) < 0.01) {
    return { noise: true, reason: 'PRICE_NOISE' };
  }
  
  return { noise: false, reason: null };
}

// ========== OI + PRICE + VOLUME COMBINATION ==========
export function analyzeOIContext(oiChange, priceChangePercent, volumeRatio) {
  // Lowered thresholds - was 0.1, now 0.02
  const oiDir = oiChange > 0.02 ? 'UP' : oiChange < -0.02 ? 'DOWN' : 'FLAT';
  const priceDir = (priceChangePercent || 0) > 0.02 ? 'UP' : (priceChangePercent || 0) < -0.02 ? 'DOWN' : 'FLAT';
  const volDir = volumeRatio > 1.3 ? 'HIGH' : volumeRatio > 0.8 ? 'NORMAL' : 'LOW';
  
  let signal = 'NEUTRAL';
  let confidence = 0;
  
  // Strongest: OI UP + Price UP + High Volume = Bullish continuation
  if (oiDir === 'UP' && priceDir === 'UP' && volDir === 'HIGH') {
    signal = 'BULLISH';
    confidence = 80;
  }
  // OI UP + Price DOWN = Shorts entering (liquidation) = Bearish
  else if (oiDir === 'UP' && priceDir === 'DOWN') {
    signal = 'BEARISH';
    confidence = 70;
  }
  // OI UP + Price FLAT + High Volume = Absorption (trap)
  else if (oiDir === 'UP' && priceDir === 'FLAT' && volDir === 'HIGH') {
    signal = 'ABSORPTION';
    confidence = 60;
  }
  // OI DOWN + Price DOWN = Shorts covering = Bullish
  else if (oiDir === 'DOWN' && priceDir === 'DOWN') {
    signal = 'BULLISH';
    confidence = 50;
  }
  // OI DOWN + Price UP = Longs covering = Bearish
  else if (oiDir === 'DOWN' && priceDir === 'UP') {
    signal = 'BEARISH';
    confidence = 50;
  }
  
  return { signal, confidence, oiDir, priceDir, volDir };
}

// ========== TREND FILTER (EMA 200) ==========
const ema200Cache = new Map();
const EMA_PERIOD = 200;

export function calculateEMA(prices, period = EMA_PERIOD) {
  if (!prices || prices.length < period) return null;
  
  const k = 2 / (period + 1);
  let ema = prices[0];
  
  for (let i = 1; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  
  return ema;
}

export function updateTrend(symbol, currentPrice, priceHistory) {
  if (!priceHistory || priceHistory.length < EMA_PERIOD) {
    return 'UNKNOWN';
  }
  
  const ema = calculateEMA(priceHistory);
  if (!ema) return 'UNKNOWN';
  
  ema200Cache.set(symbol, ema);
  
  if (currentPrice > ema * 1.001) return 'UP';   // Price above EMA = bullish trend
  if (currentPrice < ema * 0.999) return 'DOWN'; // Price below EMA = bearish trend
  return 'UNKNOWN';
}

export function getTrendDirection(symbol, currentPrice) {
  const ema = ema200Cache.get(symbol);
  if (!ema) return null;
  
  if (currentPrice > ema * 1.001) return 'LONG';   // Only allow LONG in uptrend
  if (currentPrice < ema * 0.999) return 'SHORT';  // Only allow SHORT in downtrend
  return null;
}

// ========== NO TRADE ZONE (ATR/Volume) ==========
const volumeHistory = new Map();

export function updateVolatility(symbol, currentPrice, high, low) {
  const trueRange = high - low;
  marketState.atrValue = (marketState.atrValue * 14 + trueRange) / 15; // Smoothed ATR
  marketState.lastUpdate = Date.now();
}

export function updateAvgVolume(symbol, volume) {
  if (!volumeHistory.has(symbol)) {
    volumeHistory.set(symbol, []);
  }
  const history = volumeHistory.get(symbol);
  history.push(volume);
  if (history.length > 20) history.shift();
  
  const sum = history.reduce((a, b) => a + b, 0);
  marketState.avgVolume = sum / history.length;
}

export function isNoTradeZone(symbol, volume) {
  // Only apply ATR check after it's been measured (not on startup when atrValue = 0)
  if (marketState.atrValue > 0 && marketState.atrValue < 0.0001) {
    return { blocked: true, reason: 'LOW_VOLATILITY' };
  }
  
  // Low volume filter - only if we have avgVolume data
  if (marketState.avgVolume > 0 && volume < marketState.avgVolume * 0.3) {
    return { blocked: true, reason: 'LOW_VOLUME' };
  }
  
  return { blocked: false, reason: null };
}

// ========== OI + PRICE DIRECTION (Institutional Logic) ==========
export function getOIDirection(oiChange, priceChange) {
  const oiUp = oiChange > 0.1;
  const oiDown = oiChange < -0.1;
  const priceUp = priceChange > 0;
  const priceDown = priceChange < 0;
  
  if (oiUp && priceUp) return 'BULLISH';      // Longs entering ✅
  if (oiUp && priceDown) return 'BEARISH';     // Shorts entering (liquidation) ❌
  if (oiUp && !priceUp && !priceDown) return 'ABSORPTION'; // Absorption (trap)
  if (oiDown && priceDown) return 'BEARISH';   // Shorts covering
  if (oiDown && priceUp) return 'BULLISH';      // Longs covering
  
  return 'NEUTRAL';
}

// ========== ADAPTIVE SCORING ==========
export function getAdaptiveWeights() {
  const trend = marketState.trend;
  const volatility = marketState.volatility;
  
  if (trend === 'UNKNOWN' || volatility === 'LOW') {
    return { oi: 30, volume: 30, imbalance: 40 };
  }
  
  if (volatility === 'HIGH') {
    return { oi: 50, volume: 20, imbalance: 30 }; // OI more reliable in volatile
  }
  
  if (trend === 'UP' || trend === 'DOWN') {
    return { oi: 30, volume: 40, imbalance: 30 }; // Volume matters more in trend
  }
  
  return { oi: 40, volume: 30, imbalance: 30 };
}

// ========== LOSS PROTECTION ==========
export function recordTradeResult(won) {
  if (!won) {
    marketState.consecutiveLosses++;
  } else {
    marketState.consecutiveLosses = 0;
  }
  
  // Reduce risk after 3 consecutive losses
  if (marketState.consecutiveLosses >= 3) {
    marketState.riskMultiplier = 0.5;
  } else if (marketState.consecutiveLosses === 0) {
    marketState.riskMultiplier = 1;
  }
  
  return marketState.riskMultiplier;
}

export function getRiskMultiplier() {
  return marketState.riskMultiplier;
}

export function shouldEmit(symbol, type, cooldownMs = 120000) {
  const key = `${symbol}_${type}`;
  const now = Date.now();

  if (!lastSignalTime[key]) {
    lastSignalTime[key] = now;
    return { allowed: true, cooldown: 0 };
  }

  const diff = now - lastSignalTime[key];
  const remaining = cooldownMs - diff;

  if (remaining <= 0) {
    lastSignalTime[key] = now;
    return { allowed: true, cooldown: 0 };
  }

  return { allowed: false, cooldown: Math.ceil(remaining / 1000) };
}

export function selectTopSignals(signals, limit = 5) {
  if (!signals || signals.length === 0) return [];
  
  return signals
    .sort((a, b) => (b.finalScore || b.score || 0) - (a.finalScore || a.score || 0))
    .slice(0, limit);
}

export function getDirection(orderFlow) {
  if (!orderFlow) return null;
  if (orderFlow > 1.1) return "LONG";
  if (orderFlow < 0.9) return "SHORT";
  return null;
}

export function isInNoTradeZone(orderFlow) {
  return orderFlow >= 0.95 && orderFlow <= 1.05;
}

export function validateDirection(signal) {
  const orderFlow = signal.orderFlow || signal.imbalance || 1;
  
  if (isInNoTradeZone(orderFlow)) {
    return { valid: false, reason: 'NO_TRADE_ZONE', direction: null };
  }
  
  const direction = getDirection(orderFlow);
  
  if (!direction) {
    return { valid: false, reason: 'NO_DIRECTION', direction: null };
  }
  
  return { valid: true, direction };
}

export function isHighQuality(signal) {
  if (!signal) return false;
  
  const score = signal.finalScore || signal.score || signal.confidence || 0;
  const volume = signal.volumeRatio || signal.volume || 1;
  const orderFlow = signal.orderFlow || signal.imbalance || 1;
  
  const direction = getDirection(orderFlow);
  const hasImbalance = orderFlow > 1.2 || orderFlow < 0.8;
  const validDirection = direction !== null && !isInNoTradeZone(orderFlow);
  
  return (
    score >= 30 &&
    volume > 1.5 &&
    validDirection &&
    hasImbalance
  );
}

export function isExecutionReady(signal) {
  if (!signal) return false;
  
  const type = signal.type || '';
  const score = signal.finalScore || signal.score || signal.confidence || 0;
  const orderFlow = signal.orderFlow || signal.imbalance || 1;
  
  if (isInNoTradeZone(orderFlow)) return false;
  
  const direction = getDirection(orderFlow);
  if (!direction) return false;
  
  const executionTypes = ['CONFIRMED ENTRY', 'SNIPER ENTRY', 'EXPLOSION'];
  const highScore = score >= 40;
  const strongDirection = orderFlow > 1.3 || orderFlow < 0.7;
  
  return (executionTypes.includes(type) || highScore) && strongDirection;
}

export function formatSignalForTelegram(s) {
  const fmt = n => Number(n || 0).toFixed(4);
  const fmtPrice = n => {
    if (!n || isNaN(n)) return '0';
    const val = Number(n);
    if (val >= 100) return val.toFixed(2);
    if (val >= 10) return val.toFixed(3);
    if (val >= 1) return val.toFixed(4);
    return val.toFixed(5);
  };
  
  const type = s.type || 'SIGNAL';
  const symbol = s.symbol || 'N/A';
  const score = s.finalScore || s.score || s.confidence || 0;
  const level = s.level || 'WATCH';
  
  const oi = s.oiChange || s.data?.oiChange || 0;
  const vol = s.volumeRatio || s.volume || s.data?.volume || 1;
  const oflow = s.orderFlow || s.imbalance || s.data?.orderFlow || 1;
  const whale = s.whale || s.data?.whale || null;
  const newsScore = s.newsImpact || s.newsScore || 0;
  const session = s.session || 'N/A';
  
  let emoji = '👀';
  if (type.includes('CONFIRMED') || score >= 70) emoji = '✅';
  else if (type.includes('SNIPER') || score >= 50) emoji = '🎯';
  else if (type.includes('EXPLOSION') || score >= 40) emoji = '💥';
  else if (type.includes('ENTRY') || score >= 30) emoji = '🚀';
  else if (type.includes('BUILDING')) emoji = '🔥';
  else if (type.includes('TRAP')) emoji = '⚠️';
  
  const direction = s.rawDirection || s.direction || (s.priceChange > 0 ? 'LONG' : 'SHORT');
  const side = direction === '🟢 LONG' || direction === 'LONG' ? '🟢 LONG' : '🔴 SHORT';
  const dirEmoji = direction === '🟢 LONG' || direction === 'LONG' ? '📈' : '📉';
  
  const whaleEmoji = whale === 'ACCUMULATION' ? '🐋🟢' : whale === 'DISTRIBUTION' ? '🐋🔴' : '—';
  const newsEmoji = newsScore > 0 ? '📰🟢' : newsScore < 0 ? '📰🔴' : '📰—';
  
  const strength = score >= 70 ? 'VERY HIGH' : score >= 50 ? 'HIGH' : score >= 30 ? 'MEDIUM' : 'LOW';
  
  let msg = `🚨 ${symbol} PERPETUAL SIGNAL\n\n`;
  msg += `📊 Type: ${type} (${level})\n`;
  msg += `${dirEmoji} Direction: ${side}\n`;
  if (whale) msg += `🐋 Whale: ${whale} ${whaleEmoji}\n`;
  if (newsScore !== 0) msg += `${newsEmoji} News Impact: ${newsScore > 0 ? '+' : ''}${newsScore} (${newsScore > 0 ? 'Bullish' : 'Bearish'})\n`;
  msg += `\n━━━━━━━━━━━━━━━\n`;
  
  if (s.entry) {
    msg += `💰 Entry: ${fmtPrice(s.entry)}\n`;
    msg += `🛑 Stop Loss: ${fmtPrice(s.stopLoss)}\n`;
    msg += `🎯 Take Profit:\n`;
    if (s.tp1) msg += `• TP1: ${fmtPrice(s.tp1)}\n`;
    if (s.tp2) msg += `• TP2: ${fmtPrice(s.tp2)}\n`;
    if (s.tp3) msg += `• TP3: ${fmtPrice(s.tp3)}\n`;
    msg += `\n━━━━━━━━━━━━━━━\n`;
  }
  
  msg += `📊 Confidence Score: ${score.toFixed(0)}\n`;
  msg += `⚙️ Signal Strength: ${strength}\n`;
  msg += `📍 Session: ${session}\n`;
  
  const now = new Date();
  const istTime = now.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });
  msg += `🕒 Time: ${istTime} IST\n`;
  msg += `\n━━━━━━━━━━━━━━━\n`;
  
  if (whale) {
    msg += `🧠 Logic:\n`;
    if (whale === 'ACCUMULATION') msg += `• Whale accumulation detected\n`;
    if (whale === 'DISTRIBUTION') msg += `• Whale distribution detected\n`;
    msg += `• OI increasing + strong orderflow\n`;
    msg += `• ${level} signal confirmed\n`;
  }
  
  msg += `\n⚠️ Trade with proper risk management`;
  
  return msg;
}

export function formatTopWatch(symbols) {
  if (!symbols || symbols.length === 0) {
    return '📊 No active signals';
  }
  
  const top5 = symbols.slice(0, 5);
  let msg = '📊 TOP WATCHING\n\n';
  
  top5.forEach((s, i) => {
    const emoji = s.level === 'EXPLOSION' ? '💥' :
                 s.level === 'ENTRY' ? '🚀' :
                 s.level === 'BUILDING' ? '🔥' : '👀';
    msg += `${i + 1}. ${emoji} ${s.symbol} — ${s.score?.toFixed(0) || '0'}\n`;
  });
  
  return msg;
}

export const SIGNAL_COOLDOWN = {
  WATCH: 60000,
  BUILDING: 90000,
  ENTRY: 60000,
  EXPLOSION: 45000,
  EARLY_ENTRY: 120000,
  SNIPER_ENTRY: 90000,
  CONFIRMED_ENTRY: 60000
};

export function getCooldownForType(type) {
  if (!type) return 120000;
  
  for (const [key, value] of Object.entries(SIGNAL_COOLDOWN)) {
    if (type.includes(key)) return value;
  }
  
  return 120000;
}
