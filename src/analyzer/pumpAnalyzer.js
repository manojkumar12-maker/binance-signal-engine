import { config } from '../../config/config.js';

class PumpAnalyzer {
  constructor() {
    this.priceHistory = new Map();
    this.volumeHistory = new Map();
    this.pumpCandidates = new Map();
  }

  analyze(ticker) {
    const { symbol, price, priceChangePercent, volume, quoteVolume } = ticker;

    this.updateHistory(symbol, ticker);

    const signals = this.checkPumpConditions(symbol);
    if (signals.strength > 0) {
      return { ...signals, ticker };
    }

    return null;
  }

  updateHistory(symbol, ticker) {
    if (!this.priceHistory.has(symbol)) {
      this.priceHistory.set(symbol, []);
      this.volumeHistory.set(symbol, []);
    }

    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);

    prices.push({ price: ticker.price, timestamp: ticker.timestamp });
    volumes.push({ volume: ticker.volume, quoteVolume: ticker.quoteVolume, timestamp: ticker.timestamp });

    if (prices.length > 60) prices.shift();
    if (volumes.length > 60) volumes.shift();
  }

  checkPumpConditions(symbol) {
    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);

    if (prices.length < 10) return { strength: 0 };

    const currentPrice = prices[prices.length - 1].price;
    const recentPrices = prices.slice(-10);
    
    const priceChange = ((currentPrice - recentPrices[0].price) / recentPrices[0].price) * 100;
    
    const avgVolume = volumes.slice(-10).reduce((sum, v) => sum + v.quoteVolume, 0) / 10;
    const currentVolume = volumes[volumes.length - 1].quoteVolume;
    const volumeSpike = currentVolume / avgVolume;

    const momentum = this.calculateMomentum(recentPrices);
    const acceleration = this.calculateAcceleration(recentPrices);

    let strength = 0;
    const factors = [];

    if (priceChange >= config.signals.pumpThreshold) {
      strength += 40;
      factors.push(`Price surge: ${priceChange.toFixed(2)}%`);
    } else if (priceChange >= config.signals.minPriceChange) {
      strength += 20;
      factors.push(`Price change: ${priceChange.toFixed(2)}%`);
    }

    if (volumeSpike >= config.signals.volumeSpikeMultiplier) {
      strength += 30;
      factors.push(`Volume spike: ${volumeSpike.toFixed(1)}x`);
    }

    if (momentum > config.signals.priceAccelerationThreshold) {
      strength += 20;
      factors.push(`Strong momentum: ${momentum.toFixed(3)}`);
    }

    if (acceleration > 0.1) {
      strength += 10;
      factors.push(`Price acceleration: ${acceleration.toFixed(3)}`);
    }

    if (strength >= 60 && priceChange >= config.signals.pumpThreshold) {
      return {
        strength,
        type: 'PUMP',
        factors,
        priceChange,
        volumeSpike,
        momentum,
        acceleration,
        entryPrice: currentPrice,
        signals: this.generateEntryExit(currentPrice)
      };
    }

    return { strength: 0 };
  }

  calculateMomentum(prices) {
    if (prices.length < 3) return 0;
    
    const recent = prices.slice(-3);
    const rate1 = (recent[2].price - recent[1].price) / recent[1].price;
    const rate2 = (recent[1].price - recent[0].price) / recent[0].price;
    
    return rate1 + rate2;
  }

  calculateAcceleration(prices) {
    if (prices.length < 5) return 0;
    
    const recent = prices.slice(-5);
    const changes = [];
    
    for (let i = 1; i < recent.length; i++) {
      changes.push((recent[i].price - recent[i-1].price) / recent[i-1].price);
    }
    
    const velocity = changes[changes.length - 1] - changes[0];
    return velocity;
  }

  generateEntryExit(entryPrice) {
    const { tp1Percent, tp2Percent, tp3Percent, tp4Percent, tp5Percent, slPercent } = config.riskManagement;

    return {
      entry: entryPrice,
      tp1: entryPrice * (1 + tp1Percent / 100),
      tp2: entryPrice * (1 + tp2Percent / 100),
      tp3: entryPrice * (1 + tp3Percent / 100),
      tp4: entryPrice * (1 + tp4Percent / 100),
      tp5: entryPrice * (1 + tp5Percent / 100),
      sl: entryPrice * (1 - slPercent / 100),
      tp1Risk: tp1Percent,
      tp2Risk: tp2Percent,
      tp3Risk: tp3Percent,
      tp4Risk: tp4Percent,
      tp5Risk: tp5Percent,
      slRisk: slPercent
    };
  }

  clearHistory(symbol) {
    this.priceHistory.delete(symbol);
    this.volumeHistory.delete(symbol);
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
