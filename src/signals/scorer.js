import { config } from '../core/config.js';

let weights = { ...config.WEIGHTS };

export function calculateInstitutionalScore(data) {
  const { oiChange, volume, orderFlow, momentum, structureBreak } = data;
  
  let score = 0;
  
  if (oiChange > 3) score += 2;
  else if (oiChange > 1.5) score += 1;
  
  if (volume > 2.5) score += 2;
  else if (volume > 2.0) score += 1;
  
  if (orderFlow > 1.3) score += 2;
  else if (orderFlow > 1.15) score += 1;
  
  if (structureBreak) score += 2;
  
  if (momentum > 0.7) score += 1;
  
  return Math.min(9, score);
}

export function dynamicScore(data) {
  const { oi, volume, flow, momentum } = data;
  
  return (
    oi * weights.oi +
    volume * weights.volume +
    flow * weights.flow +
    momentum * weights.momentum
  );
}

export function adjustWeights(win) {
  if (win) {
    weights.volume += 0.1;
    weights.flow += 0.1;
  } else {
    weights.oi = Math.max(0.5, weights.oi - 0.1);
  }
}

export function getWeights() {
  return { ...weights };
}

export function resetWeights() {
  weights = { ...config.WEIGHTS };
}
