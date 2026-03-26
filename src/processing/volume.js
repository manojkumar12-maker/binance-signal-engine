import { state } from '../core/state.js';

const volumeWindows = new Map();
const WINDOW_SIZE = 60000;

export function updateVolume(symbol, qty) {
  if (!state.volume[symbol]) {
    state.volume[symbol] = {
      current: 0,
      historical: [],
      lastUpdate: Date.now()
    };
  }
  
  const vol = state.volume[symbol];
  const now = Date.now();
  
  vol.current += qty;
  vol.lastUpdate = now;
  
  if (!volumeWindows.has(symbol)) {
    volumeWindows.set(symbol, []);
  }
  
  const window = volumeWindows.get(symbol);
  window.push({ qty, time: now });
  
  const cutoff = now - WINDOW_SIZE;
  while (window.length > 0 && window[0].time < cutoff) {
    window.shift();
  }
  
  vol.historical = window.map(w => w.qty);
}

export function getVolumeRatio(symbol) {
  const vol = state.volume[symbol];
  if (!vol || !vol.historical || vol.historical.length < 5) return 1;
  
  const avg = vol.historical.reduce((a, b) => a + b, 0) / vol.historical.length;
  if (avg === 0) return 1;
  
  const current = vol.current / 10;
  return current / avg;
}

export function getVolumeData(symbol) {
  return state.volume[symbol] || { current: 0, historical: [] };
}

export function resetVolume(symbol) {
  if (state.volume[symbol]) {
    state.volume[symbol].current = 0;
  }
  volumeWindows.delete(symbol);
}
