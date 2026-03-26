import { state } from '../core/state.js';

const priceHistory = new Map();
const HISTORY_SIZE = 20;

export function updateMomentum(symbol, price) {
  if (!priceHistory.has(symbol)) {
    priceHistory.set(symbol, []);
  }
  
  const history = priceHistory.get(symbol);
  history.push(price);
  
  if (history.length > HISTORY_SIZE) {
    history.shift();
  }
}

export function calculateMomentum(symbol) {
  const history = priceHistory.get(symbol);
  if (!history || history.length < 5) return 0;
  
  const recent = history.slice(-5);
  const older = history.slice(0, -5);
  
  if (older.length === 0) return 0;
  
  const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
  const olderAvg = older.reduce((a, b) => a + b, 0) / older.length;
  
  const momentum = (recentAvg - olderAvg) / olderAvg * 100;
  
  return momentum;
}

export function calculateAcceleration(symbol) {
  const history = priceHistory.get(symbol);
  if (!history || history.length < 3) return 0;
  
  const recent = history.slice(-3);
  const diffs = [];
  
  for (let i = 1; i < recent.length; i++) {
    diffs.push(recent[i] - recent[i-1]);
  }
  
  if (diffs.length < 2) return 0;
  
  return diffs[1] - diffs[0];
}

export function getMomentumData(symbol) {
  return {
    momentum: calculateMomentum(symbol),
    acceleration: calculateAcceleration(symbol),
    price: priceHistory.get(symbol)?.[-1] || 0
  };
}

export function resetMomentum(symbol) {
  priceHistory.delete(symbol);
}
