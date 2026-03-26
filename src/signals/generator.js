import { state } from '../core/state.js';
import { config, STAGES } from '../core/config.js';
import { calculateInstitutionalScore } from './scorer.js';
import { canTrade, setSignalTime, isDeadMarket, detectEarlyPump, detectTrap, isWeak } from './filters.js';
import { getVolumeRatio } from '../processing/volume.js';
import { getOrderflowData } from '../processing/orderflow.js';
import { detectLiquiditySweep, smartEntry, confirmMTF, updateHTF } from '../processing/structure.js';
import { calculateMomentum, updateMomentum } from '../processing/momentum.js';
import { analyzeLiquidations } from '../data/liquidations.js';
import { analyzeFunding } from '../data/funding.js';
import { getImbalance } from '../data/orderbook.js';

const symbolScores = new Map();
const symbolState = new Map();

export function generateSignal(symbol, ticker) {
  if (isWeak(symbol)) return null;
  if (!canTrade(symbol)) return null;
  
  const price = ticker?.price || state.prices[symbol] || 0;
  const priceChange = ticker?.priceChangePercent || 0;
  const volume = getVolumeRatio(symbol);
  const ofData = getOrderflowData(symbol);
  const momentum = calculateMomentum(symbol);
  
  updateMomentum(symbol, price);
  
  const data = {
    symbol,
    priceChange,
    volume,
    orderFlow: ofData.ratio,
    oiChange: state.oi[symbol] || 0,
    fakeOI: 0,
    momentum,
    price
  };
  
  if (isDeadMarket(data.volume, data.oiChange)) return null;
  if (detectTrap(data.priceChange, data.orderFlow)) return null;
  
  const score = calculateInstitutionalScore(data);
  symbolScores.set(symbol, score);
  
  const sweep = detectLiquiditySweep(symbol, price);
  const entry = smartEntry(symbol, sweep, data.orderFlow);
  
  const liqSignal = analyzeLiquidations(symbol);
  const fundingBias = analyzeFunding(symbol);
  const imbalance = getImbalance(symbol);
  
  const currentState = symbolState.get(symbol) || { stage: STAGES.IDLE };
  
  if (currentState.stage === STAGES.IDLE) {
    if (detectEarlyPump(data.volume, data.oiChange, data.priceChange)) {
      symbolState.set(symbol, { stage: STAGES.PRESSURE, score, startTime: Date.now() });
      setSignalTime(symbol);
      
      return {
        type: 'EARLY_PUMP',
        symbol,
        confidence: score,
        entry: price,
        data,
        sweep,
        entry
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
        data,
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
      data
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
