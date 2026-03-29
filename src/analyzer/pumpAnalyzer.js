class PumpAnalyzer {
  constructor() {
    this.symbols = [];
    this.priceHistory = new Map();
    this.lastSignalTime = new Map();
  }

  initialize(symbols) {
    this.symbols = symbols;
    console.log('PumpAnalyzer initialized with', symbols.length, 'symbols');
  }

  analyze(ticker) {
    const { symbol, priceChangePercent, price, lastPrice, volume } = ticker;
    
    if (!symbol || !symbol.includes('USDT')) return null;
    if (symbol === 'BTCUSDT') return null;

    const priceChange = priceChangePercent || 0;
    
    return {
      symbol,
      price,
      priceChange,
      volume: volume || 0,
      lastPrice: lastPrice || price,
      fakeOI: 0,
      orderFlow: 0,
      volumeRatio: 1
    };
  }

  classifyOI(priceChange, oiChange, fakeOI = null) {
    const pc = priceChange || 0;
    const oi = oiChange || 0;
    
    if (Math.abs(oi) < 0.3) return 'NEUTRAL';
    if (pc > 0 && oi > 0.5) return 'LONG_BUILDUP';
    if (pc > 0 && oi < -0.3) return 'SHORT_SQUEEZE';
    if (pc < 0 && oi > 0.5) return 'SHORT_BUILDUP';
    if (pc < 0 && oi < -0.3) return 'LONG_EXIT';
    
    return 'NEUTRAL';
  }

  getOIStateLabel(priceChange, oiChange, fakeOI = null) {
    const pc = priceChange || 0;
    const oi = oiChange || 0;
    
    if (Math.abs(oi) < 0.3) return { label: '🟡 FLAT', tag: 'FLAT' };
    if (pc > 0 && oi > 0.5) return { label: '🟢 LONG_BUILDUP', tag: 'LONG_BUILDUP' };
    if (pc > 0 && oi < -0.3) return { label: '💥 SHORT_SQUEEZE', tag: 'SHORT_SQUEEZE' };
    if (pc < 0 && oi > 0.5) return { label: '🔴 SHORT_BUILDUP', tag: 'SHORT_BUILDUP' };
    if (pc < 0 && oi < -0.3) return { label: '🪤 LONG_EXIT', tag: 'LONG_EXIT' };
    
    return { label: '🟡 FLAT', tag: 'FLAT' };
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
