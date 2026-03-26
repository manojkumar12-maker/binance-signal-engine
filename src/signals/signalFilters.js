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

export function isHighQuality(signal) {
  if (!signal) return false;
  
  const score = signal.finalScore || signal.score || signal.confidence || 0;
  const volume = signal.volumeRatio || signal.volume || 1;
  const orderFlow = signal.orderFlow || signal.imbalance || 1;
  
  return (
    score >= 30 &&
    volume > 1.5 &&
    orderFlow > 1.2
  );
}

export function isExecutionReady(signal) {
  if (!signal) return false;
  
  const type = signal.type || '';
  const score = signal.finalScore || signal.score || signal.confidence || 0;
  
  const executionTypes = ['CONFIRMED ENTRY', 'SNIPER ENTRY', 'EXPLOSION'];
  const highScore = score >= 40;
  
  return executionTypes.includes(type) || highScore;
}

export function formatSignalForTelegram(s) {
  const fmt = n => Number(n || 0).toFixed(4);
  const fmtPrice = n => Number(n || 0).toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  
  const type = s.type || 'SIGNAL';
  const symbol = s.symbol || 'N/A';
  const score = s.finalScore || s.score || s.confidence || 0;
  const level = s.level || 'WATCH';
  
  const oi = s.oiChange || 0;
  const vol = s.volumeRatio || s.volume || 1;
  const oflow = s.orderFlow || s.imbalance || 1;
  
  let emoji = '👀';
  if (type.includes('CONFIRMED') || score >= 70) emoji = '✅';
  else if (type.includes('SNIPER') || score >= 50) emoji = '🎯';
  else if (type.includes('EXPLOSION') || score >= 40) emoji = '💥';
  else if (type.includes('ENTRY') || score >= 30) emoji = '🚀';
  else if (type.includes('BUILDING')) emoji = '🔥';
  
  const direction = s.direction || (s.priceChange > 0 ? 'LONG' : 'SHORT');
  const side = direction === 'LONG' ? '🟢 LONG' : '🔴 SHORT';
  
  let msg = `${emoji} ${type}\n\n`;
  msg += `📊 ${symbol.replace('USDT', '/USDT')} — ${side}\n\n`;
  msg += `📈 Score: ${score.toFixed(0)} | Level: ${level}\n\n`;
  msg += `--- METRICS ---\n`;
  msg += `OI: ${fmt(oi)}%\n`;
  msg += `Vol: ${fmt(vol)}x\n`;
  msg += `OF: ${fmt(oflow)}\n\n`;
  
  if (s.entry) {
    msg += `--- ENTRY ---\n`;
    msg += `Entry: ${fmtPrice(s.entry)}\n`;
    if (s.tp1) msg += `TP1: ${fmtPrice(s.tp1)}\n`;
    if (s.tp2) msg += `TP2: ${fmtPrice(s.tp2)}\n`;
    if (s.stopLoss) msg += `SL: ${fmtPrice(s.stopLoss)}\n`;
  }
  
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
