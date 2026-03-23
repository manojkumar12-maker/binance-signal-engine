const BINANCE_API = 'https://fapi.binance.com';

const oiCache = new Map();
let prioritySymbols = new Set();
let isRunning = false;
let normalInterval = null;
let priorityInterval = null;
let updateIndex = 0;
let allSymbols = [];
const UPDATE_WINDOW_MS = 10000;
const BATCH_SIZE = 50;

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
  const now = Date.now();
  
  for (const symbol of symbols) {
    try {
      const data = await fetchOI(symbol);
      if (!data) continue;

      const newOI = parseFloat(data.openInterest);
      if (isNaN(newOI) || newOI === 0) continue;

      const existing = oiCache.get(symbol);
      const lastUpdate = existing?.lastUpdate || 0;
      
      let prevOI;
      
      if (!existing) {
        prevOI = newOI;
      } else if (now - lastUpdate >= UPDATE_WINDOW_MS) {
        prevOI = existing.oi;
      } else {
        prevOI = existing.prevOi;
      }

      oiCache.set(symbol, {
        oi: newOI,
        prevOi: prevOI,
        lastUpdate: now
      });

      if (symbol === 'BTCUSDT') {
        const d = oiCache.get(symbol);
        const change = d.prevOi > 0 ? ((d.oi - d.prevOi) / d.prevOi) * 100 : 0;
        if (Math.abs(change) > 0.05) {
          console.log(`📊 OICache BTC: oi=${d.oi} prevOi=${d.prevOi} change=${change.toFixed(3)}%`);
        }
      }
    } catch (e) {
      continue;
    }
  }
}

function getNextBatch() {
  if (!allSymbols || allSymbols.length === 0) return [];
  
  const start = updateIndex;
  const end = Math.min(start + BATCH_SIZE, allSymbols.length);
  const batch = allSymbols.slice(start, end);
  
  updateIndex = end >= allSymbols.length ? 0 : end;
  
  return batch;
}

function getOIChange(symbol) {
  const data = oiCache.get(symbol);
  if (!data || !data.prevOi || data.prevOi === 0) return null;

  const change = ((data.oi - data.prevOi) / data.prevOi) * 100;
  
  return change;
}

function getOI(symbol) {
  return oiCache.get(symbol) || null;
}

function getOIStateLabel(priceChange, oiChange) {
  const pc = priceChange || 0;
  const oi = oiChange || 0;
  if (Math.abs(oi) < 0.3) return '⚪ NO_OI';
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
  allSymbols = symbols;
  updateIndex = 0;

  priorityInterval = setInterval(async () => {
    if (prioritySymbols.size > 0) {
      await updateOICache([...prioritySymbols], true);
    }
  }, 3000);

  normalInterval = setInterval(async () => {
    const batch = getNextBatch();
    if (batch.length > 0) {
      await updateOICache(batch, false);
    }
  }, 2000);
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
    if (now - data.lastUpdate > 30000) stale++;
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
