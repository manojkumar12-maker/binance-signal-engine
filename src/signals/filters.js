import { state } from '../core/state.js';
import { config } from '../core/config.js';

const performance = {};
const lastSignalTime = {};

export function updatePerformance(symbol, win) {
  if (!performance[symbol]) {
    performance[symbol] = { wins: 0, losses: 0, totalPnl: 0 };
  }
  
  if (win) {
    performance[symbol].wins++;
    performance[symbol].totalPnl += 1;
  } else {
    performance[symbol].losses++;
    performance[symbol].totalPnl -= 1;
  }
}

export function isWeak(symbol) {
  const p = performance[symbol];
  if (!p || (p.wins + p.losses) < 5) return false;
  
  const winRate = p.wins / (p.wins + p.losses);
  return winRate < 0.4;
}

export function getWinRate(symbol) {
  const p = performance[symbol];
  if (!p) return 1;
  
  const total = p.wins + p.losses;
  if (total === 0) return 1;
  
  return p.wins / total;
}

export function canTrade(symbol) {
  const last = lastSignalTime[symbol] || 0;
  return Date.now() - last > config.SIGNAL_COOLDOWN;
}

export function setSignalTime(symbol) {
  lastSignalTime[symbol] = Date.now();
}

export function isDeadMarket(volume, oiChange) {
  return volume < config.DEAD_MARKET_VOLUME_RATIO && Math.abs(oiChange) < config.DEAD_MARKET_OI_CHANGE;
}

export function detectEarlyPump(volume, oiChange, priceChange) {
  return volume > 2 && oiChange > 1.5 && priceChange < 1.0;
}

export function detectTrap(priceChange, orderFlow) {
  return (
    (priceChange > 5 && orderFlow < 1.1) ||
    (priceChange < -5 && orderFlow < 1.1)
  );
}

export function isNoise(oiChange, fakeOI, volume) {
  return (
    Math.abs(oiChange) < 0.03 &&
    Math.abs(fakeOI) < 0.15 &&
    volume < 1.8
  );
}

export function getPerformance(symbol) {
  return performance[symbol] || { wins: 0, losses: 0, totalPnl: 0 };
}

export function getAllPerformance() {
  return { ...performance };
}
