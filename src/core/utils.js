export function normalizeValue(value, allValues) {
  if (!allValues || allValues.length === 0) return 0;
  const max = Math.max(...allValues.filter(v => !isNaN(v) && v > 0));
  return max > 0 ? value / max : 0;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function calculateBuyPressure(buyVolume, sellVolume) {
  const total = buyVolume + sellVolume;
  if (total === 0) return 0.5;
  return buyVolume / total;
}

export function formatNumber(num, decimals = 2) {
  if (num === undefined || num === null) return '0';
  return num.toFixed(decimals);
}

export function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

export function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}
