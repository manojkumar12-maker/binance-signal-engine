import { state } from '../core/state.js';

export function detectLiquiditySweep(symbol, price) {
  const prev = state.prevPrice[symbol] || price;
  
  let sweep = null;
  
  if (price > prev * 1.002) {
    sweep = 'HIGH_SWEEP';
  }
  
  if (price < prev * 0.998) {
    sweep = 'LOW_SWEEP';
  }
  
  state.liquidity[symbol] = sweep;
  state.prevPrice[symbol] = price;
  
  return sweep;
}

export function detectStopHunt(symbol, volume, priceChange) {
  if (volume > 2 && Math.abs(priceChange) < 1) {
    return true;
  }
  return false;
}

export function smartEntry(symbol, sweep, flow) {
  if (sweep === 'LOW_SWEEP' && flow > 1.2) {
    return 'LONG';
  }
  
  if (sweep === 'HIGH_SWEEP' && flow < 0.8) {
    return 'SHORT';
  }
  
  return null;
}

export function updateHTF(symbol, price) {
  if (!state.htf) state.htf = {};
  
  const prev = state.htf[symbol] || price;
  
  if (price > prev) {
    state.htf[symbol] = price;
    return 'UP';
  } else {
    state.htf[symbol] = price;
    return 'DOWN';
  }
}

export function confirmMTF(symbol, entrySignal) {
  const trend = state.htf?.[symbol];
  if (!trend) return false;
  
  if (entrySignal === 'LONG' && trend === 'UP') return true;
  if (entrySignal === 'SHORT' && trend === 'DOWN') return true;
  
  return false;
}

export function getLiquidationZones(symbol, price) {
  if (!state.liquidity || !state.liquidity[symbol]) return null;
  
  const map = state.liquidity[symbol];
  if (!map.high || !map.low) return null;
  
  const range = map.high - map.low;
  
  return {
    longLiquidationZone: map.low + range * 0.1,
    shortLiquidationZone: map.high - range * 0.1
  };
}
