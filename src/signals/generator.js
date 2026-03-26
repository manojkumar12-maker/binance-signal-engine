import { state } from '../core/state.js';
import { config, STAGES } from '../core/config.js';
import { calculateInstitutionalScore } from './scorer.js';
import { canTrade, setSignalTime, isDeadMarket, detectEarlyPump, detectTrap, isWeak } from './filters.js';
import { getVolumeRatio, getVolumeData } from '../processing/volume.js';
import { getOrderflowData } from '../processing/orderflow.js';
import { detectLiquiditySweep, smartEntry, confirmMTF, updateHTF } from '../processing/structure.js';
import { calculateMomentum, updateMomentum } from '../processing/momentum.js';
import { analyzeLiquidations, getLiquidations } from '../data/liquidations.js';
import { analyzeFunding } from '../data/funding.js';
import { getImbalance } from '../data/orderbook.js';
import {
  detectAccumulation,
  detectCompression,
  calculateVelocity,
  detectBreakout,
  detectExpansion,
  detectTrapLongSqueeze,
  detectTrapShortSqueeze,
  calculatePumpScore,
  isHighPumpSignal,
  getPumpPhase,
  updateVolumeWindow,
  updateOIWindow
} from '../processing/pumpDetector.js';

const symbolScores = new Map();
const symbolState = new Map();

export function generateSignal(symbol, ticker) {
  if (isWeak(symbol)) return null;
  if (!canTrade(symbol)) return null;
  
  const price = ticker?.price || state.prices[symbol] || 0;
  const priceChange = ticker?.priceChangePercent || 0;
  const volumeRatio = getVolumeRatio(symbol);
  const volumeData = getVolumeData(symbol);
  const ofData = getOrderflowData(symbol);
  const momentum = calculateMomentum(symbol);
  const oiChange = state.oi[symbol] || 0;
  
  updateMomentum(symbol, price);
  updateVolumeWindow(symbol, volumeData.current || 0);
  updateOIWindow(symbol, oiChange);
  
  const compression = detectCompression(symbol, price);
  const velocity = calculateVelocity(symbol, price);
  const pumpPhase = getPumpPhase(symbol);
  
  const data = {
    symbol,
    priceChange,
    volume: volumeRatio,
    orderFlow: ofData.ratio,
    oiChange,
    fakeOI: 0,
    momentum,
    price,
    velocity,
    compression,
    pumpPhase
  };
  
  if (isDeadMarket(data.volume, data.oiChange)) return null;
  if (detectTrap(data.priceChange, data.orderFlow)) return null;
  
  const accumulation = detectAccumulation(symbol, volumeRatio, priceChange, oiChange);
  const breakout = detectBreakout(symbol, price, priceChange > 0 ? 'UP' : 'DOWN');
  const expansion = detectExpansion(symbol, volumeRatio, velocity);
  
  const liqSignal = analyzeLiquidations(symbol);
  const liquidations = getLiquidations(symbol);
  const fundingBias = analyzeFunding(symbol);
  const imbalance = getImbalance(symbol);
  
  const priceReclaim = priceChange > 0;
  const trapLong = detectTrapLongSqueeze(symbol, liquidations, fundingBias, priceReclaim);
  const trapShort = detectTrapShortSqueeze(symbol, liquidations, fundingBias, !priceReclaim);
  
  const pumpData = {
    accumulation,
    compression,
    breakout,
    expansion,
    volumeRatio,
    oiChange,
    imbalance,
    velocity,
    trapLong,
    trapShort,
    pumpPhase
  };
  
  const pumpScore = calculatePumpScore(pumpData);
  const isHighPump = isHighPumpSignal(pumpData);
  
  if (isHighPump) {
    symbolScores.set(symbol, pumpScore);
    symbolState.set(symbol, { stage: STAGES.SNIPER, score: pumpScore, startTime: Date.now(), type: 'HIGH_PUMP' });
    setSignalTime(symbol);
    
    const direction = trapLong ? 'LONG' : trapShort ? 'SHORT' : priceChange > 0 ? 'LONG' : 'SHORT';
    const risk = price * (config.STOP_LOSS_PERCENT / 100);
    
    console.log(`🔥 HIGH PUMP: ${symbol} | Phase: ${pumpPhase} | Score: ${pumpScore} | Vol: ${volumeRatio}x | Vel: ${velocity.toFixed(3)}`);
    
    return {
      type: 'HIGH_PUMP',
      symbol,
      direction,
      entry: price,
      stopLoss: direction === 'LONG' ? price - risk : price + risk,
      takeProfit: direction === 'LONG' ? price + risk * 3 : price - risk * 3,
      confidence: pumpScore,
      data: pumpData,
      pumpPhase,
      accumulation,
      compression: compression.compressed,
      breakout,
      expansion,
      trapLong,
      trapShort
    };
  }
  
  const score = calculateInstitutionalScore(data);
  symbolScores.set(symbol, score);
  
  const sweep = detectLiquiditySweep(symbol, price);
  const entry = smartEntry(symbol, sweep, data.orderFlow);
  
  const currentState = symbolState.get(symbol) || { stage: STAGES.IDLE };
  
  if (currentState.stage === STAGES.IDLE) {
    if (accumulation || detectEarlyPump(data.volume, data.oiChange, data.priceChange)) {
      symbolState.set(symbol, { stage: STAGES.PRESSURE, score, startTime: Date.now() });
      setSignalTime(symbol);
      
      return {
        type: 'ACCUMULATION',
        symbol,
        confidence: score,
        entry: price,
        data: pumpData,
        pumpPhase,
        accumulation
      };
    }
  }
  
  if (entry && confirmMTF(symbol, entry)) {
    let validEntry = false;
    
    if (entry === 'LONG' && (liqSignal === 'LONG_WIPED' || imbalance > 1.2 || fundingBias === 'LONG_SQUEEZE_SETUP')) {
      validEntry = true;
    }
    
    if (entry === 'SHORT' && (liqSignal === 'SHORT_WIPED' || imbalance < 0.8 || fundingBias === 'SHORT_SQUEEZE_SETUP')) {
      validEntry = true;
    }
    
    if (validEntry && score >= config.MIN_SIGNAL_SCORE) {
      symbolState.set(symbol, { stage: STAGES.SNIPER, score, startTime: Date.now() });
      setSignalTime(symbol);
      
      const risk = price * (config.STOP_LOSS_PERCENT / 100);
      
      return {
        type: 'SNIPER',
        symbol,
        direction: entry,
        entry: price,
        stopLoss: entry === 'LONG' ? price - risk : price + risk,
        takeProfit: entry === 'LONG' ? price + risk * 3 : price - risk * 3,
        confidence: score,
        data: pumpData,
        pumpPhase,
        sweep,
        liqSignal,
        fundingBias,
        imbalance
      };
    }
  }
  
  if (score >= 6 && data.volume > 3 && data.orderFlow > 1.5) {
    symbolState.set(symbol, { stage: STAGES.PRESSURE, score, startTime: Date.now() });
    
    return {
      type: 'PRESSURE',
      symbol,
      confidence: score,
      entry: price,
      data: pumpData,
      pumpPhase
    };
  }
  
  return null;
}

export function getTopSymbols(limit = 10) {
  return [...symbolScores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

export function getSymbolState(symbol) {
  return symbolState.get(symbol) || { stage: STAGES.IDLE };
}

export function resetSymbol(symbol) {
  symbolState.set(symbol, { stage: STAGES.IDLE });
}

export { getPumpPhase, calculatePumpScore, isHighPumpSignal };
