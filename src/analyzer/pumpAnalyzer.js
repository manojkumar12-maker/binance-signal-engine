import { config } from '../../config/config.js';
import { autoTuner } from '../engine/autoTuner.js';
import { orderBookAnalyzer } from '../engine/orderBookAnalyzer.js';

const STABLECOINS = ['USDT', 'BUSD', 'USDC', 'DAI', 'USD', 'UST'];

class PumpAnalyzer {
  constructor() {
    this.priceHistory = new Map();
    this.volumeHistory = new Map();
    this.candleHistory = new Map();
    this.highPrices = new Map();
    this.lowPrices = new Map();
    this.lastSignalTime = new Map();
    this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, lastReset: Date.now() };
    this.volumeRateHistory = new Map();
    this.quoteVolumeHistory = new Map();
    this.orderbookImbalance = new Map();
    this.lastSignalEmit = 0;
  }

  isStablecoin(symbol) {
    const stablePairs = ['BUSDUSDT', 'USDCUSDT', 'TUSDUSDT', 'FDUSDUSDT', 'DAIUSDT'];
    return stablePairs.some(s => symbol === s);
  }

  calculateSpread(ticker) {
    if (!ticker.bid || !ticker.ask || ticker.bid === 0 || ticker.ask === 0) return 0;
    return (ticker.ask - ticker.bid) / ticker.ask;
  }

  calculateEMA(prices, period) {
    if (!prices || prices.length < period) return null;
    const k = 2 / (period + 1);
    let ema = prices.slice(0, period).reduce((sum, p) => sum + p.price, 0) / period;
    for (let i = period; i < prices.length; i++) {
      ema = prices[i].price * k + ema * (1 - k);
    }
    return ema;
  }

  calculateATR(symbol, period = 14) {
    const candles = this.candleHistory.get(symbol);
    if (!candles || candles.length < period + 1) return null;

    const trueRanges = [];
    for (let i = 1; i < candles.length; i++) {
      const tr = Math.max(
        candles[i].high - candles[i].low,
        Math.abs(candles[i].high - candles[i - 1].close),
        Math.abs(candles[i].low - candles[i - 1].close)
      );
      trueRanges.push(tr);
    }
    return trueRanges.slice(-period).reduce((a, b) => a + b, 0) / period;
  }

  checkBreakOfStructure(symbol) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < 20) return false;
    const recent = prices.slice(-20);
    const highs = recent.map(p => p.price);
    const maxIdx = highs.indexOf(Math.max(...highs));
    const recentHigh = prices[prices.length - 1].price;
    return maxIdx >= prices.length - 5 && recentHigh > Math.max(...highs.slice(0, -5));
  }

  checkLiquiditySweep(symbol, currentPrice) {
    const highs = this.highPrices.get(symbol);
    if (!highs || highs.length < 5) return { detected: false, reclaimed: false };
    const recentHighs = highs.slice(-5);
    const prevHigh = recentHighs[recentHighs.length - 2] || currentPrice;
    const sweepTolerance = currentPrice * 0.002;
    const swept = recentHighs.some(h => h > currentPrice && (h - currentPrice) < sweepTolerance);
    return { detected: swept, reclaimed: swept && currentPrice > prevHigh };
  }

  calculateVolumeTrend(symbol) {
    const volumes = this.volumeHistory.get(symbol);
    if (!volumes || volumes.length < 5) return false;
    const recent = volumes.slice(-5).map(v => v.volume);
    for (let i = 1; i < recent.length; i++) {
      if (recent[i] < recent[i - 1]) return false;
    }
    return true;
  }

  calculateImbalance(symbol) {
    const volumes = this.volumeHistory.get(symbol);
    if (!volumes || volumes.length < 3) return 1;
    const recent = volumes.slice(-3).map(v => v.volume);
    const avg = recent.reduce((a, b) => a + b, 0) / 3;
    const current = recent[recent.length - 1];
    return avg > 0 ? current / avg : 1;
  }

  preFilter(ticker) {
    const { symbol, quoteVolume } = ticker;
    if (quoteVolume < (config?.preFilters?.minVolume24h || 500000)) return false;
    if (this.isStablecoin(symbol)) return false;
    const spread = this.calculateSpread(ticker);
    if (spread > (config?.preFilters?.maxSpreadPercent || 0.5)) return false;
    return true;
  }

  updateHistory(symbol, ticker) {
    const { price, quoteVolume, high, low } = ticker;
    const now = Date.now();

    if (!this.priceHistory.has(symbol)) {
      this.priceHistory.set(symbol, []);
      this.volumeHistory.set(symbol, []);
      this.candleHistory.set(symbol, []);
      this.highPrices.set(symbol, []);
      this.lowPrices.set(symbol, []);
      this.volumeRateHistory.set(symbol, []);
      this.quoteVolumeHistory.set(symbol, []);
    }

    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);
    const candles = this.candleHistory.get(symbol);
    const highs = this.highPrices.get(symbol);
    const lows = this.lowPrices.get(symbol);
    const volumeRates = this.volumeRateHistory.get(symbol);
    const quoteVolHistory = this.quoteVolumeHistory.get(symbol);

    prices.push({ price, timestamp: now });
    highs.push(high || price);
    lows.push(low || price);

    const prevQuoteVol = quoteVolHistory.length > 0 ? quoteVolHistory[quoteVolHistory.length - 1].volume : quoteVolume;
    const prevTimestamp = quoteVolHistory.length > 0 ? quoteVolHistory[quoteVolHistory.length - 1].timestamp : now;
    const timeDelta = Math.max((now - prevTimestamp) / 1000, 1);
    const volumeRate = Math.abs(quoteVolume - prevQuoteVol) / timeDelta;

    quoteVolHistory.push({ volume: quoteVolume, timestamp: now });
    volumeRates.push({ rate: volumeRate, timestamp: now });

    const estimatedBaseVolume = quoteVolume / 86400;
    const volumeSpikeRatio = estimatedBaseVolume > 0 ? volumeRate / estimatedBaseVolume : 1;
    volumes.push({ volume: quoteVolume, volumeRate, volumeSpikeRatio, timestamp: now });

    if (candles.length === 0 || now - candles[candles.length - 1].timestamp > 60000) {
      candles.push({ high: high || price, low: low || price, close: price, open: price, timestamp: now });
    } else {
      const last = candles[candles.length - 1];
      last.high = Math.max(last.high, high || price);
      last.low = Math.min(last.low, low || price);
      last.close = price;
    }

    if (prices.length > 100) prices.shift();
    if (volumes.length > 100) volumes.shift();
    if (candles.length > 100) candles.shift();
    if (highs.length > 100) highs.shift();
    if (lows.length > 100) lows.shift();
    if (volumeRates.length > 100) volumeRates.shift();
    if (quoteVolHistory.length > 100) quoteVolHistory.shift();
  }

  checkCooldown(symbol) {
    const lastTime = this.lastSignalTime.get(symbol);
    if (!lastTime) return true;
    const cooldownMs = (config?.signals?.cooldownMinutes || 2) * 60 * 1000;
    return Date.now() - lastTime > cooldownMs;
  }

  analyze(ticker) {
    const { symbol, priceChangePercent } = ticker;

    if (!this.preFilter(ticker)) return null;
    this.updateHistory(symbol, ticker);
    if (!this.checkCooldown(symbol)) return null;

    const orderbookData = orderBookAnalyzer.getAnalysis(symbol);
    const analysis = this.calculateMetrics(symbol, priceChangePercent, orderbookData);
    
    const tier = this.determineTier(analysis);
    
    if (tier) {
      this.lastSignalTime.set(symbol, Date.now());
      this.lastSignalEmit = Date.now();
      this.signalCounts[tier.type]++;
      this.checkAutoRelax();
    } else {
      if (Date.now() - this.lastSignalEmit > 60000) {
        autoTuner.incrementNoSignal();
      }
    }
    
    autoTuner.tune();
    return tier;
  }

  calculateMetrics(symbol, priceChangePercent, orderbookData = null) {
    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);
    const candles = this.candleHistory.get(symbol);
    const volumeRates = this.volumeRateHistory.get(symbol);

    if (!prices || prices.length < 5) {
      return { priceChange: 0, volumeSpike: 0, momentum: 0, acceleration: 0, strength: 0 };
    }

    const currentPrice = prices[prices.length - 1].price;
    const recentPrices = prices.slice(-10);
    
    const localChange = ((currentPrice - recentPrices[0].price) / recentPrices[0].price) * 100;
    const priceChange = Math.abs(priceChangePercent || localChange || 0);
    
    const currentVolumeData = volumes.length > 0 ? volumes[volumes.length - 1] : { volumeSpikeRatio: 1 };
    const volumeSpikeRatio = currentVolumeData.volumeSpikeRatio || 1;
    
    let avgVolumeRate = 1;
    if (volumeRates && volumeRates.length >= 5) {
      const recentRates = volumeRates.slice(-10).map(v => v.rate);
      avgVolumeRate = recentRates.reduce((a, b) => a + b, 0) / recentRates.length;
    }
    const currentVolumeRate = volumeRates && volumeRates.length > 0 ? volumeRates[volumeRates.length - 1].rate : 1;
    const volumeSpike = avgVolumeRate > 0 ? currentVolumeRate / avgVolumeRate : volumeSpikeRatio;

    const momentum = this.calculateMomentum(recentPrices);
    const acceleration = this.calculateAcceleration(recentPrices);
    const ema50 = this.calculateEMA(prices, 50);
    const atrPeriod = config?.riskManagement?.atrPeriod || 14;
    const atr = this.calculateATR(symbol, atrPeriod) || currentPrice * 0.01;

    const { detected: liquiditySweep, reclaimed: sweptReclaimed } = this.checkLiquiditySweep(symbol, currentPrice);
    const breakOfStructure = this.checkBreakOfStructure(symbol);
    const volumeTrend = this.calculateVolumeTrend(symbol);
    const imbalance = this.calculateImbalance(symbol);
    const rsi = this.calculateRSI(symbol);
    const strongCandle = this.analyzeCandleStrength(candles);

    const orderbookImbalance = orderbookData?.imbalance || 1;
    const spoofingRisk = orderbookData?.spoofingRisk || 0;

    const score = this.calculateScore({
      ema50, currentPrice, liquiditySweep, sweptReclaimed, volumeSpike,
      momentum, acceleration, strongCandle, rsi, volumeTrend, priceChange,
      orderbookImbalance, spoofingRisk
    });

    return {
      priceChange,
      localChange,
      volumeSpike,
      momentum,
      acceleration,
      score,
      atr,
      entryPrice: currentPrice,
      ema50,
      breakOfStructure,
      liquiditySweep,
      sweptReclaimed,
      volumeTrend,
      imbalance,
      rsi,
      strongCandle,
      orderbookImbalance,
      spoofingRisk,
      factors: this.getFactors({
        ema50, currentPrice, breakOfStructure, liquiditySweep, sweptReclaimed,
        volumeSpike, momentum, acceleration, strongCandle, volumeTrend, priceChange,
        orderbookImbalance
      })
    };
  }

  calculateScore(metrics) {
    const weights = config?.smartScoring || {};
    const filters = config?.aiFilters || {};
    const tunedParams = autoTuner.getParams();
    let score = 0;

    if (metrics.priceChange >= 0.5) score += Math.min(metrics.priceChange * 4, 35);
    
    if (metrics.ema50 !== null && metrics.currentPrice > metrics.ema50) {
      score += weights.htfTrendWeight || 10;
    }
    if (metrics.breakOfStructure) score += weights.bosWeight || 12;
    if (metrics.liquiditySweep) {
      if (metrics.sweptReclaimed) score += (weights.liquiditySweepWeight || 12) + 5;
      else score += 5;
    }
    if (metrics.volumeSpike >= 1.2) score += Math.min((metrics.volumeSpike - 1) * 25, weights.volumeSpikeWeight || 18);
    if (metrics.momentum > 0.03) score += Math.min(metrics.momentum * 60, weights.momentumWeight || 12);
    if (metrics.acceleration > 0.005) score += Math.min(metrics.acceleration * 120, weights.accelerationWeight || 12);
    if (metrics.strongCandle) score += weights.candleStrengthWeight || 6;
    if (metrics.volumeTrend) score += 4;

    if (metrics.orderbookImbalance > 1.5) score += 15;
    if (metrics.orderbookImbalance > 1.8) score += 15;
    if (metrics.orderbookImbalance > 2.2) score += 10;
    
    if (metrics.spoofingRisk > 30) score -= 20;
    else if (metrics.spoofingRisk > 15) score -= 10;

    if (metrics.rsi > (filters.maxRSI || 85)) return Math.max(0, score - 15);
    if (metrics.rsi > 75) score -= 3;

    return Math.min(Math.max(score, 0), 100);
  }

  getFactors(metrics) {
    const factors = [];
    if (metrics.priceChange >= 1) factors.push(`+${metrics.priceChange.toFixed(2)}%`);
    if (metrics.ema50 !== null && metrics.currentPrice > metrics.ema50) factors.push('HTF Uptrend');
    if (metrics.breakOfStructure) factors.push('BOS');
    if (metrics.liquiditySweep) factors.push(metrics.sweptReclaimed ? 'Liq Sweep + Reclaim' : 'Liq Sweep');
    if (metrics.volumeSpike >= 1.2) factors.push(`Vol: ${metrics.volumeSpike.toFixed(1)}x`);
    if (metrics.momentum > 0.05) factors.push(`Mom: ${metrics.momentum.toFixed(3)}`);
    if (metrics.acceleration > 0.01) factors.push(`Acc: ${metrics.acceleration.toFixed(3)}`);
    if (metrics.strongCandle) factors.push('Strong Candle');
    if (metrics.volumeTrend) factors.push('Vol Trend Up');
    if (metrics.orderbookImbalance > 1.3) factors.push(`OB Imb: ${metrics.orderbookImbalance.toFixed(2)}`);
    if (metrics.spoofingRisk > 15) factors.push(`Spoof: ${metrics.spoofingRisk.toFixed(0)}`);
    return factors;
  }

  determineTier(analysis) {
    if (analysis.score === 0) return null;

    const tiers = config?.signalTiers || {};
    const tunedParams = autoTuner.getParams();
    const { score, priceChange, volumeSpike, momentum, imbalance, spoofingRisk } = analysis;

    if (spoofingRisk > 40) return null;

    if (score >= Math.max(tiers.SNIPER?.scoreThreshold || 75, tunedParams.scoreThreshold) &&
        priceChange >= (tiers.SNIPER?.priceChangeThreshold || 3) &&
        volumeSpike >= Math.max(tiers.SNIPER?.volumeSpikeThreshold || 3, tunedParams.volumeSpike)) {
      return {
        type: 'SNIPER',
        score,
        priority: 1,
        signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'SNIPER'),
        ...analysis
      };
    }

    if (score >= Math.max(tiers.CONFIRMED?.scoreThreshold || 65, tunedParams.scoreThreshold - 10) &&
        priceChange >= Math.max(tiers.CONFIRMED?.priceChangeThreshold || 2.5, tunedParams.priceChange) &&
        volumeSpike >= Math.max(tiers.CONFIRMED?.volumeSpikeThreshold || 2, tunedParams.volumeSpike)) {
      return {
        type: 'CONFIRMED',
        score,
        priority: 2,
        signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'CONFIRMED'),
        ...analysis
      };
    }

    if (score >= Math.max(tiers.EARLY?.scoreThreshold || 50, tunedParams.scoreThreshold - 15) &&
        priceChange >= (tiers.EARLY?.priceChangeThreshold || 1.5) &&
        volumeSpike >= (tiers.EARLY?.volumeSpikeThreshold || 1.5) &&
        momentum >= (tiers.EARLY?.momentumThreshold || 0.2)) {
      return {
        type: 'EARLY',
        score,
        priority: 3,
        signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'EARLY'),
        ...analysis
      };
    }

    return null;
  }

  generateEntryExit(entryPrice, atr, tier) {
    const multipliers = config?.riskManagement?.atrMultiplier || { tp1: 0.5, tp2: 1.0, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.2 };
    const tierMultipliers = tier === 'SNIPER' ? { tp1: 1, tp2: 2, tp3: 3, tp4: 4, tp5: 5, sl: 1.5 } :
                            tier === 'CONFIRMED' ? { tp1: 0.75, tp2: 1.5, tp3: 2.5, tp4: 3.5, tp5: 5, sl: 1.2 } :
                            { tp1: 0.5, tp2: 1, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.0 };

    return {
      entry: entryPrice,
      tp1: entryPrice + (tierMultipliers.tp1 * atr),
      tp2: entryPrice + (tierMultipliers.tp2 * atr),
      tp3: entryPrice + (tierMultipliers.tp3 * atr),
      tp4: entryPrice + (tierMultipliers.tp4 * atr),
      tp5: entryPrice + (tierMultipliers.tp5 * atr),
      sl: entryPrice - (tierMultipliers.sl * atr),
      atr
    };
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
      changes.push((recent[i].price - recent[i - 1].price) / recent[i - 1].price);
    }
    return changes[changes.length - 1] - changes[0];
  }

  calculateRSI(symbol, period = 14) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < period + 1) return 50;
    let gains = 0, losses = 0;
    for (let i = prices.length - period; i < prices.length - 1; i++) {
      const change = prices[i + 1].price - prices[i].price;
      if (change > 0) gains += change;
      else losses += Math.abs(change);
    }
    const avgGain = gains / period;
    const avgLoss = losses / period;
    if (avgLoss === 0) return 100;
    return 100 - (100 / (1 + avgGain / avgLoss));
  }

  analyzeCandleStrength(candles) {
    if (candles.length < 2) return false;
    const last = candles[candles.length - 1];
    const body = Math.abs(last.close - (last.open || last.close));
    const range = last.high - last.low;
    if (range === 0) return false;
    return (last.close - last.low) / range > 0.7;
  }

  checkAutoRelax() {
    if (!config?.autoRelax?.enabled) return;
    const now = Date.now();
    const elapsed = (now - this.signalCounts.lastReset) / 60000;
    
    if (elapsed >= (config.autoRelax.noSignalsMinutes || 10)) {
      const totalSignals = this.signalCounts.EARLY + this.signalCounts.CONFIRMED + this.signalCounts.SNIPER;
      if (totalSignals === 0) {
        console.log(`\n⚠️ Auto-relax: No signals in ${elapsed.toFixed(0)}min, reducing thresholds...`);
      }
      this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, lastReset: now };
    }
  }

  getStats() {
    return { ...this.signalCounts };
  }

  clearHistory(symbol) {
    this.priceHistory.delete(symbol);
    this.volumeHistory.delete(symbol);
    this.candleHistory.delete(symbol);
    this.highPrices.delete(symbol);
    this.lowPrices.delete(symbol);
    this.volumeRateHistory.delete(symbol);
    this.quoteVolumeHistory.delete(symbol);
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
