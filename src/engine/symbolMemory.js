const symbolMemory = new Map();

export function createMemory(symbol) {
  return {
    symbol,
    trades: 0,
    wins: 0,
    losses: 0,
    pnl: 0,
    score: 50,
    lastTrades: [],
    lastUpdated: Date.now()
  };
}

export function updateSymbolMemory(symbol, result) {
  let mem = symbolMemory.get(symbol);
  if (!mem) {
    mem = createMemory(symbol);
    symbolMemory.set(symbol, mem);
  }

  mem.trades++;
  if (result.pnl > 0) mem.wins++;
  else mem.losses++;

  mem.pnl += result.pnl;
  mem.lastTrades.push(result.pnl);
  if (mem.lastTrades.length > 20) mem.lastTrades.shift();

  mem.score = calculateMemoryScore(mem);
  mem.lastUpdated = Date.now();
}

function calculateMemoryScore(mem) {
  if (mem.trades < 5) return 50;

  const winRate = mem.wins / mem.trades;
  const recentPnL = mem.lastTrades.reduce((a, b) => a + b, 0);

  let score = 0;
  score += winRate * 50;

  if (recentPnL > 0) score += 25;
  else score -= 25;

  const positiveTrades = mem.lastTrades.filter(x => x > 0).length;
  score += (positiveTrades / mem.lastTrades.length) * 25;

  return Math.max(0, Math.min(100, score));
}

export function passesMemoryFilter(symbol) {
  const mem = symbolMemory.get(symbol);
  if (!mem) return true;
  if (mem.score < 35) return false;
  return true;
}

export function applyMemoryBoost(symbol, baseScore) {
  const mem = symbolMemory.get(symbol);
  if (!mem) return baseScore;
  return baseScore + (mem.score - 50) * 0.3;
}

export function isOnCooldown(symbol) {
  const mem = symbolMemory.get(symbol);
  if (!mem) return false;

  const last5 = mem.lastTrades.slice(-5);
  if (last5.length < 5) return false;

  const losses = last5.filter(x => x < 0).length;
  return losses >= 3;
}

export function decayMemory() {
  for (const mem of symbolMemory.values()) {
    mem.score = mem.score * 0.95 + 50 * 0.05;
  }
}

export function getSymbolMemory() {
  return symbolMemory;
}

export function getSymbolScore(symbol) {
  const mem = symbolMemory.get(symbol);
  return mem?.score || 50;
}
