import { config } from '../../config/config.js';

const STABLECOINS = ['USDT', 'BUSD', 'USDC', 'DAI', 'USD', 'UST'];

class PumpAnalyzer {
  constructor() {
    this.priceHistory = new Map();
    this.volumeHistory = new Map();
    this.candleHistory = new Map();
    this.pumpCandidates = new Map();
    this.highPrices = new Map();
    this.lowPrices = new Map();
    this.htfPrices = new Map();
    this.lastSignalTime = new Map();
    this.marketRegime = new Map();
    this.conditionStats = {
      bos: { wins: 0, losses: 0 },
      sweep: { wins: 0, losses: 0 },
      volume: { wins: 0, losses: 0 },
      mtf: { wins: 0, losses: 0 }
    };
  }

  isStablecoin(symbol) {
    return STABLECOINS.some(s => symbol.endsWith(s));
  }

  calculateSpread(ticker) {
    if (!ticker.bid || !ticker.ask) return 0;
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
      const high = candles[i].high;
      const low = candles[i].low;
      const prevClose = candles[i - 1].close;
      const tr = Math.max(
        high - low,
        Math.abs(high - prevClose),
        Math.abs(low - prevClose)
      );
      trueRanges.push(tr);
    }

    if (trueRanges.length < period) return null;
    return trueRanges.slice(-period).reduce((a, b) => a + b, 0) / period;
  }

  calculateATRMA(symbol, period = 14, maPeriod = 20) {
    const candles = this.candleHistory.get(symbol);
    if (!candles || candles.length < period + maPeriod) return null;

    const atrs = [];
    for (let i = period; i < candles.length; i++) {
      const tr = Math.max(
        candles[i].high - candles[i].low,
        Math.abs(candles[i].high - candles[i - 1].close),
        Math.abs(candles[i].low - candles[i - 1].close)
      );
      atrs.push(tr);
    }

    if (atrs.length < maPeriod) return null;
    return atrs.slice(-maPeriod).reduce((a, b) => a + b, 0) / maPeriod;
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
    const sweepTolerance = currentPrice * 0.002;
    const prevHigh = recentHighs[recentHighs.length - 2] || currentPrice;
    
    const swept = recentHighs.some(h => h > currentPrice && (h - currentPrice) < sweepTolerance);
    const reclaimed = swept && currentPrice > prevHigh;
    
    return { detected: swept, reclaimed };
  }

  checkChopZone(symbol) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < 10) return false;
    
    const recent = prices.slice(-10);
    const high10 = Math.max(...recent.map(p => p.price));
    const low10 = Math.min(...recent.map(p => p.price));
    const currentPrice = prices[prices.length - 1].price;
    const range = high10 - low10;
    
    return (range / currentPrice) < 0.01;
  }

  checkVolatilityExpansion(symbol) {
    const atr = this.calculateATR(symbol);
    const atrMA = this.calculateATRMA(symbol);
    
    if (!atr || !atrMA) return true;
    return atr > atrMA;
  }

  checkMultiTimeframe(symbol) {
    const prices = this.priceHistory.get(symbol);
    const ltfEMA = this.calculateEMA(prices, 50);
    const htfEMA = this.calculateEMA(prices, 200);
    const currentPrice = prices ? prices[prices.length - 1].price : 0;
    
    if (!htfEMA || !ltfEMA) return { aligned: true, strength: 0 };
    
    const trendStrength = (currentPrice - htfEMA) / htfEMA;
    const aligned = currentPrice > htfEMA && currentPrice > ltfEMA;
    
    return { aligned, strength: trendStrength };
  }

  getMicroPullbackEntry(symbol, atr) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < 2) return null;
    
    const high = Math.max(...prices.slice(-3).map(p => p.price));
    const currentPrice = prices[prices.length - 1].price;
    const pullback = (high - currentPrice) / high;
    
    const entryPrice = high - (0.3 * atr);
    
    return {
      entryPrice,
      pullback,
      needsPullback: pullback < 0.002
    };
  }

  detectWeakness(symbol, currentPrice) {
    const volumes = this.volumeHistory.get(symbol);
    const candles = this.candleHistory.get(symbol);
    const prices = this.priceHistory.get(symbol);
    
    if (!volumes || volumes.length < 5 || !candles || !prices) return false;
    
    const recentVolumes = volumes.slice(-5);
    const avgVolume = recentVolumes.reduce((a, b) => a + b.volume, 0) / 5;
    const currentVolume = recentVolumes[recentVolumes.length - 1].volume;
    const volumeDropping = currentVolume < avgVolume * 0.7;
    
    const momentum = this.calculateMomentum(prices);
    const momentumSlowing = momentum < 0;
    
    const lastCandle = candles[candles.length - 1];
    const body = Math.abs(lastCandle.close - (lastCandle.open || lastCandle.close));
    const upperWick = lastCandle.high - Math.max(lastCandle.close, lastCandle.open || lastCandle.close);
    const bearishCandle = lastCandle.close < (lastCandle.open || lastCandle.close) * 0.99;
    
    return volumeDropping && momentumSlowing && bearishCandle;
  }

  detectMarketRegime(symbol) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < 50) return 'RANGE';
    
    const recent = prices.slice(-50);
    const highs = recent.map(p => p.price);
    const highsTrend = highs.filter((h, i) => i > highs.indexOf(Math.max(...highs.slice(0, i + 1))));
    
    let trendDirection = 0;
    for (let i = 1; i < recent.length; i++) {
      trendDirection += (recent[i].price - recent[i - 1].price) > 0 ? 1 : -1;
    }
    
    const trendStrength = Math.abs(trendDirection) / recent.length;
    
    return trendStrength > 0.3 ? 'TREND' : 'RANGE';
  }

  checkCooldown(symbol) {
    const lastTime = this.lastSignalTime.get(symbol);
    if (!lastTime) return true;
    
    const cooldownMs = config.signals.cooldownMinutes * 60 * 1000;
    return Date.now() - lastTime > cooldownMs;
  }

  analyze(ticker) {
    const { symbol, priceChangePercent } = ticker;

    if (!this.preFilter(ticker)) return null;
    this.updateHistory(symbol, ticker);

    if (!this.checkCooldown(symbol)) return null;

    const mtfCheck = this.checkMultiTimeframe(symbol);
    const mtfAligned = mtfCheck.aligned;

    const signals = this.checkPumpConditions(symbol, mtfAligned, priceChangePercent);
    
    const minScoreForEntry = config?.signals?.minScoreForEntry || 40;
    const earlyPumpThreshold = config?.signals?.earlyPumpThreshold || 0.5;
    const volumeSpikeThreshold = config?.signals?.volumeSpikeThreshold || 1.5;
    
    if (signals.strength >= minScoreForEntry && 
        signals.priceChange >= earlyPumpThreshold && 
        signals.volumeSpike >= volumeSpikeThreshold) {
      console.log(`[SIGNAL CANDIDATE] ${symbol}: score=${signals.strength}, change=${signals.priceChange?.toFixed(2)}%, vol=${signals.volumeSpike?.toFixed(1)}x, factors=${signals.factors?.length}`);
      
      const pullbackEntry = this.getMicroPullbackEntry(symbol, signals.atr);
      pumpAnalyzer.setLastSignalTime(symbol);
      
      return {
        ...signals,
        ticker,
        mtfAligned,
        mtfStrength: mtfCheck.strength,
        pullbackEntry,
        regime: this.detectMarketRegime(symbol)
      };
    }

    return null;
  }

  preFilter(ticker) {
    const { symbol, quoteVolume } = ticker;

    if (quoteVolume < (config?.preFilters?.minVolume24h || 1000000)) {
      return false;
    }
    if (this.isStablecoin(symbol)) return false;
    if (this.calculateSpread(ticker) > (config?.preFilters?.maxSpreadPercent || 0.2)) return false;
    
    return true;
  }

  updateHistory(symbol, ticker) {
    const { price, quoteVolume, high, low } = ticker;

    if (!this.priceHistory.has(symbol)) {
      this.priceHistory.set(symbol, []);
      this.volumeHistory.set(symbol, []);
      this.candleHistory.set(symbol, []);
      this.highPrices.set(symbol, []);
      this.lowPrices.set(symbol, []);
    }

    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);
    const candles = this.candleHistory.get(symbol);
    const highs = this.highPrices.get(symbol);
    const lows = this.lowPrices.get(symbol);

    prices.push({ price, timestamp: Date.now() });
    volumes.push({ volume: quoteVolume, timestamp: Date.now() });
    highs.push(high || price);
    lows.push(low || price);

    if (candles.length === 0 || Date.now() - candles[candles.length - 1].timestamp > 60000) {
      candles.push({ high: high || price, low: low || price, close: price, open: price, timestamp: Date.now() });
    } else {
      const last = candles[candles.length - 1];
      last.high = Math.max(last.high, high || price);
      last.low = Math.min(last.low, low || price);
      last.close = price;
    }

    if (prices.length > 200) prices.shift();
    if (volumes.length > 200) volumes.shift();
    if (candles.length > 200) candles.shift();
    if (highs.length > 200) highs.shift();
    if (lows.length > 200) lows.shift();
  }

  checkPumpConditions(symbol, mtfAligned, tickerPriceChangePercent) {
    const prices = this.priceHistory.get(symbol);
    const volumes = this.volumeHistory.get(symbol);
    const candles = this.candleHistory.get(symbol);

    if (prices.length < 5) {
      return { strength: 0, priceChange: 0, volumeSpike: 0 };
    }

    const currentPrice = prices[prices.length - 1].price;
    const recentPrices = prices.slice(-10);
    
    // Use local change for momentum calculations
    const localChange = ((currentPrice - recentPrices[0].price) / recentPrices[0].price) * 100;
    
    // Use ticker's 24h change as the primary price change metric
    const priceChange = Math.abs(tickerPriceChangePercent || localChange || 0);
    
    const avgVolume = volumes.slice(-10).reduce((sum, v) => sum + v.volume, 0) / 10;
    const currentVolume = volumes[volumes.length - 1].volume;
    const volumeSpike = avgVolume > 0 ? currentVolume / avgVolume : 0;

    // Always log for debugging
    console.log(`[CHECK] ${symbol}: tickerPct=${tickerPriceChangePercent?.toFixed(2)}%, local=${localChange?.toFixed(2)}%, volSpike=${volumeSpike.toFixed(2)}x`);

    const momentum = this.calculateMomentum(recentPrices);
    const acceleration = this.calculateAcceleration(recentPrices);
    const ema50 = this.calculateEMA(prices, 50);
    const atrPeriod = config?.riskManagement?.atrPeriod || 14;
    const atr = this.calculateATR(symbol, atrPeriod) || currentPrice * 0.01;

    const { detected: liquiditySweep, reclaimed: sweptReclaimed } = this.checkLiquiditySweep(symbol, currentPrice);
    const breakOfStructure = this.checkBreakOfStructure(symbol);
    const strongCandle = this.analyzeCandleStrength(candles);
    const rsi = this.calculateRSI(symbol);
    const { upperWick, body } = this.analyzeCandlePattern(candles);
    const isInsideRange = this.checkInsideRange(candles);

    if (this.aiQualityFilter(upperWick, body, isInsideRange, volumeSpike, rsi)) {
      return { strength: 0 };
    }

    let score = 0;
    const factors = [];
    const validation = {};

    const htfTrendWeight = config?.smartScoring?.htfTrendWeight || 15;
    const bosWeight = config?.smartScoring?.bosWeight || 20;
    const liquiditySweepWeight = config?.smartScoring?.liquiditySweepWeight || 20;
    const volumeSpikeWeight = config?.smartScoring?.volumeSpikeWeight || 15;
    const momentumWeight = config?.smartScoring?.momentumWeight || 10;
    const accelerationWeight = config?.smartScoring?.accelerationWeight || 10;
    const candleStrengthWeight = config?.smartScoring?.candleStrengthWeight || 10;
    const minScoreForEntry = config?.signals?.minScoreForEntry || 40;
    const earlyPumpThreshold = config?.signals?.earlyPumpThreshold || 0.5;
    const volumeSpikeThreshold = config?.signals?.volumeSpikeThreshold || 1.5;
    const priceAccelerationThreshold = config?.signals?.priceAccelerationThreshold || 0.3;

    if (ema50 !== null && currentPrice > ema50) {
      score += htfTrendWeight;
      factors.push(`HTF Uptrend: Price > EMA50`);
    }

    if (mtfAligned) {
      score += 10;
      factors.push(`Multi-Timeframe Aligned`);
    }

    if (breakOfStructure) {
      score += bosWeight;
      factors.push(`Break of Structure`);
      validation.bos = true;
    }

    if (liquiditySweep) {
      if (sweptReclaimed && volumeSpike >= 2) {
        score += liquiditySweepWeight + 10;
        factors.push(`Liquidity Sweep + Reclaim`);
        validation.sweep = true;
      } else {
        score -= 5;
      }
    }

    if (volumeSpike >= 2) {
      score += volumeSpikeWeight;
      factors.push(`Volume: ${volumeSpike.toFixed(1)}x`);
      validation.volume = true;
    }

    if (momentum > priceAccelerationThreshold) {
      score += momentumWeight;
      factors.push(`Momentum: ${momentum.toFixed(3)}`);
    }

    if (acceleration > 0.05) {
      score += accelerationWeight;
      factors.push(`Acceleration: ${acceleration.toFixed(3)}`);
    }

    if (strongCandle) {
      score += candleStrengthWeight;
      factors.push(`Strong Candle`);
    }

    if (score >= minScoreForEntry && priceChange >= earlyPumpThreshold && acceleration > 0) {
      return {
        strength: Math.min(score, 100),
        type: 'PUMP',
        factors,
        validation,
        priceChange,
        volumeSpike,
        momentum,
        acceleration,
        entryPrice: currentPrice,
        atr,
        signals: this.generateEntryExit(currentPrice, atr),
        metadata: {
          ema50,
          breakOfStructure,
          liquiditySweep,
          sweptReclaimed,
          strongCandle,
          rsi
        }
      };
    }

    return { strength: 0 };
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
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  analyzeCandleStrength(candles) {
    if (candles.length < 2) return false;
    const last = candles[candles.length - 1];
    const body = Math.abs(last.close - (last.open || last.close));
    const range = last.high - last.low;
    if (range === 0) return false;
    return (last.close - last.low) / range > 0.7;
  }

  analyzeCandlePattern(candles) {
    if (candles.length < 2) return { upperWick: 0, body: 0 };
    const last = candles[candles.length - 1];
    const body = Math.abs(last.close - (last.open || last.close));
    const upperWick = last.high - Math.max(last.close, last.open || last.close);
    
    return { upperWick, body };
  }

  checkInsideRange(candles) {
    if (candles.length < 2) return false;
    const last = candles[candles.length - 1];
    const prev = candles[candles.length - 2];
    return last.high < prev.high && last.low > prev.low;
  }

  aiQualityFilter(upperWick, body, isInsideRange, volumeSpike, rsi) {
    const maxUpperWickRatio = config?.aiFilters?.maxUpperWickRatio || 1.5;
    const minVolumeSpikeForQuality = config?.aiFilters?.minVolumeSpikeForQuality || 2;
    const maxRSI = config?.aiFilters?.maxRSI || 80;
    const filterInsideRange = config?.aiFilters?.filterInsideRange || false;
    
    if (body > 0 && upperWick > body * maxUpperWickRatio) return true;
    if (filterInsideRange && isInsideRange) return true;
    if (volumeSpike < minVolumeSpikeForQuality) return true;
    if (rsi > maxRSI) return true;
    return false;
  }

  generateEntryExit(entryPrice, atr) {
    const atrMultiplier = config?.riskManagement?.atrMultiplier || { tp1: 0.5, tp2: 1.0, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.2 };

    return {
      entry: entryPrice,
      tp1: entryPrice + (atrMultiplier.tp1 * atr),
      tp2: entryPrice + (atrMultiplier.tp2 * atr),
      tp3: entryPrice + (atrMultiplier.tp3 * atr),
      tp4: entryPrice + (atrMultiplier.tp4 * atr),
      tp5: entryPrice + (atrMultiplier.tp5 * atr),
      sl: entryPrice - (atrMultiplier.sl * atr),
      atr
    };
  }

  recordConditionResult(condition, won) {
    if (this.conditionStats[condition]) {
      if (won) this.conditionStats[condition].wins++;
      else this.conditionStats[condition].losses++;
    }
  }

  getConditionWinRates() {
    const rates = {};
    for (const [condition, stats] of Object.entries(this.conditionStats)) {
      const total = stats.wins + stats.losses;
      rates[condition] = total > 0 ? (stats.wins / total * 100).toFixed(1) + '%' : 'N/A';
    }
    return rates;
  }

  adjustWeights() {
    const { bos, sweep, volume, mtf } = this.conditionStats;
    
    const bosTotal = bos.wins + bos.losses;
    const sweepTotal = sweep.wins + sweep.losses;
    
    if (bosTotal >= 10 && (bos.wins / bosTotal) < 0.5) {
      config.smartScoring.bosWeight = Math.max(10, config.smartScoring.bosWeight - 5);
    }
    
    if (sweepTotal >= 10 && (sweep.wins / sweepTotal) < 0.5) {
      config.smartScoring.liquiditySweepWeight = Math.max(10, config.smartScoring.liquiditySweepWeight - 5);
    }
  }

  setLastSignalTime(symbol) {
    this.lastSignalTime.set(symbol, Date.now());
  }

  clearHistory(symbol) {
    this.priceHistory.delete(symbol);
    this.volumeHistory.delete(symbol);
    this.candleHistory.delete(symbol);
    this.highPrices.delete(symbol);
    this.lowPrices.delete(symbol);
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
