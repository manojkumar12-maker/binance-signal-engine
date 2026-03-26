export class OrderflowTracker {
  constructor() {
    this.data = new Map();
    this.lastReset = Date.now();
  }

  handleTrade(trade) {
    const symbol = trade.symbol;
    if (!symbol) {
      this._missingSymbolCount = (this._missingSymbolCount || 0) + 1;
      if (this._missingSymbolCount % 50000 === 0) {
        console.log('❌ Orderflow received trade without symbol:', JSON.stringify(trade).slice(0, 200));
      }
      return;
    }
    
    const qty = parseFloat(trade.quantity) || parseFloat(trade.q) || 0;
    if (!qty) {
      this._zeroQtyCount = (this._zeroQtyCount || 0) + 1;
      return;
    }

    if (!this.data.has(symbol)) {
      this.data.set(symbol, {
        buy: 0,
        sell: 0,
        trades: [],
        lastUpdate: Date.now()
      });
    }

    const d = this.data.get(symbol);

    if (trade.isBuyerMaker || trade.m) {
      d.sell += qty;
    } else {
      d.buy += qty;
    }

    d.trades.push({ qty, isBuyerMaker: trade.isBuyerMaker || trade.m, time: Date.now() });
    d.lastUpdate = Date.now();
    this.setLastSymbol(symbol);

    if (d.trades.length > 500) {
      d.trades = d.trades.slice(-500);
    }
  }

  getOrderflow(symbol) {
    const d = this.data.get(symbol);
    if (!d) return 1;

    const buy = d.buy;
    const sell = d.sell;

    if (buy === 0 && sell === 0) return 1;

    const ratio = buy / (sell || 1);

    return Math.max(0.5, Math.min(ratio, 3));
  }

  getOrderflowData(symbol) {
    const d = this.data.get(symbol);
    if (!d) {
      return {
        ratio: 1,
        buyVolume: 0,
        sellVolume: 0,
        pressure: 'NEUTRAL',
        tradeCount: 0
      };
    }

    const buy = d.buy;
    const sell = d.sell;
    const ratio = buy / (sell || 1);

    let pressure = 'NEUTRAL';
    if (ratio > 1.6) pressure = 'EXTREME_BUY';
    else if (ratio > 1.3) pressure = 'STRONG_BUY';
    else if (ratio > 1.1) pressure = 'BUY';
    else if (ratio < 0.7) pressure = 'EXTREME_SELL';
    else if (ratio < 0.8) pressure = 'SELL';

    return {
      ratio: Math.max(0.5, Math.min(ratio, 3)),
      buyVolume: buy,
      sellVolume: sell,
      pressure,
      tradeCount: d.trades.length
    };
  }

  reset() {
    for (const d of this.data.values()) {
      d.buy = 0;
      d.sell = 0;
    }
    this.lastReset = Date.now();
  }

  resetSymbol(symbol) {
    const d = this.data.get(symbol);
    if (d) {
      d.buy = 0;
      d.sell = 0;
      d.trades = [];
    }
  }

  getStats() {
    let totalBuy = 0;
    let totalSell = 0;
    let activeSymbols = 0;

    for (const d of this.data.values()) {
      if (d.buy > 0 || d.sell > 0) {
        activeSymbols++;
        totalBuy += d.buy;
        totalSell += d.sell;
      }
    }

    return {
      trackedSymbols: this.data.size,
      activeSymbols,
      totalBuyVolume: totalBuy,
      totalSellVolume: totalSell,
      lastReset: this.lastReset,
      lastProcessedSymbol: this._lastSymbol
    };
  }
  
  setLastSymbol(symbol) {
    this._lastSymbol = symbol;
  }
}

export const orderflowTracker = new OrderflowTracker();
