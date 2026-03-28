const lastSignalTime = {};

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
  const fmtPrice = n => Number(n || 0).toFixed(2);
  
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
