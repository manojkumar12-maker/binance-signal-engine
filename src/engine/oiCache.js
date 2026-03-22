const BINANCE_API = 'https://fapi.binance.com';

const oiCache = new Map();
let prioritySymbols = new Set();
let isRunning = false;
let normalInterval = null;
let priorityInterval = null;

async function fetchOI(symbol) {
  try {
    const res = await fetch(`${BINANCE_API}/fapi/v1/openInterest?symbol=${symbol}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

async function updateOICache(symbols, isPriority = false) {
  for (const symbol of symbols) {
    try {
      const data = await fetchOI(symbol);
      if (!data) continue;

      const prev = oiCache.get(symbol);

      oiCache.set(symbol, {
        oi: parseFloat(data.openInterest),
        prevOi: prev?.oi || 0,
        timestamp: Date.now()
      });
    } catch (e) {
      continue;
    }
  }
}

function getOIChange(symbol) {
  const data = oiCache.get(symbol);
  if (!data || !data.prevOi || data.prevOi === 0) return null;

  return ((data.oi - data.prevOi) / data.prevOi) * 100;
}

function getOI(symbol) {
  return oiCache.get(symbol) || null;
}

function getOIStateLabel(priceChange, oiChange) {
  const pc = priceChange || 0;
  const oi = oiChange || 0;
  if (Math.abs(oi) < 0.1) return '⚪ NO_OI';
  if (pc > 0 && oi > 0.3) return '🚀 LONG';
  if (pc > 0 && oi < -0.3) return '⚠️ SHORT_CVR';
  if (pc < 0 && oi > 0.3) return '🔻 SHORT';
  if (pc < 0 && oi < -0.3) return '⚠️ LONG_EXT';
  return '⚪ NO_OI';
}

function setPrioritySymbols(symbols) {
  prioritySymbols = new Set(symbols);
}

function start(symbols) {
  if (isRunning) return;
  isRunning = true;

  priorityInterval = setInterval(async () => {
    if (prioritySymbols.size > 0) {
      await updateOICache([...prioritySymbols], true);
    }
  }, 3000);

  normalInterval = setInterval(async () => {
    const normalSymbols = symbols.filter(s => !prioritySymbols.has(s));
    if (normalSymbols.length > 0) {
      await updateOICache(normalSymbols, false);
    }
  }, 10000);
}

function stop() {
  isRunning = false;
  if (normalInterval) clearInterval(normalInterval);
  if (priorityInterval) clearInterval(priorityInterval);
}

function addPriority(symbol) {
  prioritySymbols.add(symbol);
}

function removePriority(symbol) {
  prioritySymbols.delete(symbol);
}

function getStats() {
  let withData = 0;
  let stale = 0;
  const now = Date.now();
  for (const [_, data] of oiCache) {
    if (data.oi > 0) withData++;
    if (now - data.timestamp > 30000) stale++;
  }
  return {
    total: oiCache.size,
    withData,
    stale,
    priorityCount: prioritySymbols.size
  };
}

export {
  oiCache,
  fetchOI,
  updateOICache,
  getOIChange,
  getOI,
  getOIStateLabel,
  setPrioritySymbols,
  start,
  stop,
  addPriority,
  removePriority,
  getStats
};
