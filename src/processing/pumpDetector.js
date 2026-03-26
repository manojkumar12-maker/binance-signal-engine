import { state } from '../core/state.js';

const priceWindows = new Map();
const volumeWindows = new Map();
const oiWindows = new Map();
const COMPRESSION_WINDOW = 300000;
const VELOCITY_WINDOW = 5000;

export function detectAccumulation(symbol, volumeRatio, priceChange, oiChange) {
  return (
    volumeRatio > 1.5 &&
    Math.abs(priceChange) < 0.5 &&
    oiChange > 1
  );
}

export function detectCompression(symbol, currentPrice) {
  if (!priceWindows.has(symbol)) {
    priceWindows.set(symbol, []);
  }
  
  const window = priceWindows.get(symbol);
  const now = Date.now();
  
  window.push({ price: currentPrice, time: now });
  
  while (window.length > 0 && window[0].time < now - COMPRESSION_WINDOW) {
    window.shift();
  }
  
  if (window.length < 10) return { compressed: false, range: 0 };
  
  const prices = window.map(w => w.price);
  const high = Math.max(...prices);
  const low = Math.min(...prices);
  const range = ((high - low) / low) * 100;
  const avgVol = volumeWindows.get(symbol)?.slice(-10)?.reduce((a, b) => a + b, 0) / 10 || 0;
  const currentVol = volumeWindows.get(symbol)?.slice(-1)[0] || 0;
  
  const volIncreasing = currentVol > avgVol * 1.2;
  
  return {
    compressed: range < 1.5 && volIncreasing,
    range,
    volatility: range,
    tightening: range < 2
  };
}

export function updateVolumeWindow(symbol, volume) {
  if (!volumeWindows.has(symbol)) {
    volumeWindows.set(symbol, []);
  }
  
  const window = volumeWindows.get(symbol);
  const now = Date.now();
  
  window.push({ volume, time: now });
  
  while (window.length > 0 && window[0].time < now - COMPRESSION_WINDOW) {
    window.shift();
  }
}

export function updateOIWindow(symbol, oiChange) {
  if (!oiWindows.has(symbol)) {
    oiWindows.set(symbol, []);
  }
  
  const window = oiWindows.get(symbol);
  const now = Date.now();
  
  window.push({ oi: oiChange, time: now });
  
  while (window.length > 0 && window[0].time < now - COMPRESSION_WINDOW) {
    window.shift();
  }
}

export function calculateVelocity(symbol, currentPrice) {
  const window = priceWindows.get(symbol);
  if (!window || window.length < 2) return 0;
  
  const now = Date.now();
  const cutoff = now - VELOCITY_WINDOW;
  
  const recent = window.filter(w => w.time >= cutoff);
  if (recent.length < 2) return 0;
  
  const oldest = recent[0];
  const newest = recent[recent.length - 1];
  
  const timeDiff = (newest.time - oldest.time) / 1000;
  if (timeDiff === 0) return 0;
  
  const priceDiff = newest.price - oldest.price;
  const velocity = (priceDiff / oldest.price) * 100 / timeDiff;
  
  return velocity;
}

export function detectBreakout(symbol, currentPrice, direction) {
  const window = priceWindows.get(symbol);
  if (!window || window.length < 20) return false;
  
  const recent = window.slice(-20);
  const high = Math.max(...recent.map(w => w.price));
  const low = Math.min(...recent.map(w => w.price));
  
  if (direction === 'UP' && currentPrice > high * 1.002) {
    return true;
  }
  
  if (direction === 'DOWN' && currentPrice < low * 0.998) {
    return true;
  }
  
  return false;
}

export function detectExpansion(symbol, volumeRatio, velocity) {
  return (
    volumeRatio > 2 &&
    Math.abs(velocity) > 0.1
  );
}

export function detectTrapLongSqueeze(symbol, liquidations, fundingBias, priceReclaim) {
  const recentLiq = liquidations?.slice(-20) || [];
  
  let longWiped = 0;
  let shortWiped = 0;
  
  recentLiq.forEach(l => {
    if (l.side === 'SELL') longWiped += l.qty;
    if (l.side === 'BUY') shortWiped += l.qty;
  });
  
  const longDominant = longWiped > shortWiped * 2;
  
  return (
    longDominant &&
    (fundingBias === 'LONG_SQUEEZE_SETUP' || fundingBias < 0) &&
    priceReclaim
  );
}

export function detectTrapShortSqueeze(symbol, liquidations, fundingBias, priceReclaim) {
  const recentLiq = liquidations?.slice(-20) || [];
  
  let longWiped = 0;
  let shortWiped = 0;
  
  recentLiq.forEach(l => {
    if (l.side === 'SELL') longWiped += l.qty;
    if (l.side === 'BUY') shortWiped += l.qty;
  });
  
  const shortDominant = shortWiped > longWiped * 2;
  
  return (
    shortDominant &&
    (fundingBias === 'SHORT_SQUEEZE_SETUP' || fundingBias > 0) &&
    priceReclaim
  );
}

export function calculatePumpScore(data) {
  const {
    accumulation,
    compression,
    breakout,
    expansion,
    volumeRatio,
    oiChange,
    imbalance,
    velocity,
    trapLong,
    trapShort
  } = data;
  
  let score = 0;
  
  if (accumulation) score += 25;
  if (compression?.compressed) score += 20;
  if (breakout) score += 25;
  if (expansion) score += 20;
  if (volumeRatio > 2.5) score += 15;
  if (oiChange > 2) score += 10;
  if (imbalance > 1.3) score += 10;
  if (Math.abs(velocity) > 0.1) score += 10;
  if (trapLong || trapShort) score += 30;
  
  return Math.min(100, score);
}

export function isHighPumpSignal(data) {
  const score = calculatePumpScore(data);
  return score >= 70;
}

export function getPumpPhase(symbol) {
  const window = priceWindows.get(symbol);
  if (!window || window.length < 10) return 'UNKNOWN';
  
  const recent = window.slice(-10);
  const prices = recent.map(w => w.price);
  const high = Math.max(...prices);
  const low = Math.min(...prices);
  const range = ((high - low) / low) * 100;
  
  const volWindow = volumeWindows.get(symbol) || [];
  const volTrend = volWindow.slice(-5);
  const volIncreasing = volTrend.length > 1 && 
    volTrend[volTrend.length-1].volume > volTrend[0].volume * 1.3;
  
  const currentPrice = prices[prices.length - 1];
  const nearHigh = currentPrice >= high * 0.99;
  const nearLow = currentPrice <= low * 1.01;
  
  if (range < 1.5 && volIncreasing) return 'COMPRESSION';
  if (nearHigh && volIncreasing) return 'EXPANSION';
  if (nearLow && range > 2) return 'ACCUMULATION';
  
  return 'CONSOLIDATION';
}

export function resetPumpData(symbol) {
  priceWindows.delete(symbol);
  volumeWindows.delete(symbol);
  oiWindows.delete(symbol);
}
