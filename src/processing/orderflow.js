import { state } from '../core/state.js';
import { calculateBuyPressure } from '../core/utils.js';

export function updateOrderflow(symbol, price, qty, isBuyerMaker) {
  if (!state.orderflow[symbol]) {
    state.orderflow[symbol] = {
      buy: 0,
      sell: 0,
      trades: [],
      lastUpdate: Date.now()
    };
  }
  
  const of = state.orderflow[symbol];
  
  if (isBuyerMaker) {
    of.sell += qty;
  } else {
    of.buy += qty;
  }
  
  of.trades.push({
    qty,
    price,
    isBuyerMaker,
    time: Date.now()
  });
  
  if (of.trades.length > 500) {
    of.trades = of.trades.slice(-500);
  }
  
  of.lastUpdate = Date.now();
}

export function getOrderflowRatio(symbol) {
  const of = state.orderflow[symbol];
  if (!of || of.buy === 0 && of.sell === 0) return 1;
  
  return of.buy / (of.sell || 1);
}

export function getOrderflowData(symbol) {
  const of = state.orderflow[symbol];
  if (!of) {
    return {
      ratio: 1,
      buyVolume: 0,
      sellVolume: 0,
      pressure: 'NEUTRAL',
      tradeCount: 0,
      buyPressure: 0.5
    };
  }
  
  const ratio = of.buy / (of.sell || 1);
  const buyPressure = calculateBuyPressure(of.buy, of.sell);
  
  let pressure = 'NEUTRAL';
  if (ratio > 1.6 || buyPressure > 0.65) pressure = 'EXTREME_BUY';
  else if (ratio > 1.3) pressure = 'STRONG_BUY';
  else if (ratio > 1.1) pressure = 'BUY';
  else if (ratio < 0.7 || buyPressure < 0.35) pressure = 'EXTREME_SELL';
  else if (ratio < 0.8) pressure = 'SELL';
  
  return {
    ratio: Math.max(0.5, Math.min(ratio, 3)),
    buyVolume: of.buy,
    sellVolume: of.sell,
    pressure,
    tradeCount: of.trades.length,
    buyPressure
  };
}

export function resetOrderflow(symbol) {
  if (state.orderflow[symbol]) {
    state.orderflow[symbol] = {
      buy: 0,
      sell: 0,
      trades: [],
      lastUpdate: Date.now()
    };
  }
}
