const patternMemory = new Map();

function bucket(value, levels) {
  for (let i = 0; i < levels.length; i++) {
    if (value < levels[i]) return i;
  }
  return levels.length;
}

export function buildPattern(data) {
  return {
    dir: data.priceChange > 0 ? 'LONG' : 'SHORT',
    vol: bucket(data.volume, [2, 3, 5]),
    of: bucket(data.orderFlow, [1.2, 1.5, 2]),
    oi: bucket(Math.abs(data.oiChange || data.fakeOI || 0), [0.3, 0.5, 1]),
    accel: bucket(data.priceAcceleration || 0, [0.2, 0.3, 0.5]),
    trap: data.trap ? 1 : 0
  };
}

export function patternKey(pattern) {
  return `${pattern.dir}|${pattern.vol}|${pattern.of}|${pattern.oi}|${pattern.accel}|${pattern.trap}`;
}

function createPatternMemory(key) {
  return {
    key,
    trades: 0,
    wins: 0,
    losses: 0,
    pnl: 0,
    score: 50,
    lastTrades: []
  };
}

export function updatePatternMemory(data, result) {
  const pattern = buildPattern(data);
  const key = patternKey(pattern);

  let mem = patternMemory.get(key);
  if (!mem) {
    mem = createPatternMemory(key);
    patternMemory.set(key, mem);
  }

  mem.trades++;
  if (result.pnl > 0) mem.wins++;
  else mem.losses++;

  mem.pnl += result.pnl;
  mem.lastTrades.push(result.pnl);
  if (mem.lastTrades.length > 20) mem.lastTrades.shift();

  mem.score = calculatePatternScore(mem);
}

function calculatePatternScore(mem) {
  if (mem.trades < 5) return 50;

  const winRate = mem.wins / mem.trades;
  const recent = mem.lastTrades.reduce((a, b) => a + b, 0);

  let score = 0;
  score += winRate * 60;
  if (recent > 0) score += 20;
  else score -= 20;

  const positives = mem.lastTrades.filter(x => x > 0).length;
  score += (positives / mem.lastTrades.length) * 20;

  return Math.max(0, Math.min(100, score));
}

export function passesPatternFilter(data) {
  const key = patternKey(buildPattern(data));
  const mem = patternMemory.get(key);

  if (!mem) return true;
  if (mem.score < 40 && mem.trades > 10) return false;

  return true;
}

export function applyPatternBoost(data, baseScore) {
  const key = patternKey(buildPattern(data));
  const mem = patternMemory.get(key);

  if (!mem) return baseScore;
  return baseScore + (mem.score - 50) * 0.3;
}

export function isDeadPattern(data) {
  const key = patternKey(buildPattern(data));
  const mem = patternMemory.get(key);

  if (!mem) return false;
  return mem.trades > 10 && mem.score < 35;
}

export function getPatternMemory() {
  return patternMemory;
}
