import { config } from '../../config/config.js';
import { orderBookAnalyzer } from '../engine/orderBookAnalyzer.js';
import { marketDataTracker } from '../engine/marketDataTracker.js';
import { tradeLogger } from '../engine/tradeLogger.js';
import { analyzeSignal } from '../engine/confidenceEngine.js';
import { incrementSignalCount } from '../engine/adaptiveFilter.js';
import { PrePumpDetector } from '../engine/prePumpDetector.js';
import { LiquidationService } from '../engine/liquidationService.js';
import { orderflowTracker } from '../engine/orderflowTracker.js';
import { signalRankingEngine } from '../engine/signalRankingEngine.js';
import { oiTracker } from '../engine/oiTracker.js';
import { fundingService } from '../engine/fundingService.js';
import { liquidationEngine } from '../engine/liquidationEngine.js';

const prePumpDetector = new PrePumpDetector();
const liquidationService = new LiquidationService();

const STABLECOINS = ['USDT', 'BUSD', 'USDC', 'DAI', 'USD', 'UST'];

class PumpAnalyzer {
  constructor() {
    this.priceHistory = new Map();
    this.volumeHistory = new Map();
    this.candleHistory = new Map();
    this.highPrices = new Map();
    this.lowPrices = new Map();
    this.intraDayHigh = new Map();
    this.intraDayLow = new Map();
    this.lastSignalTime = new Map();
    this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, PRE_PUMP: 0, lastReset: Date.now() };
    this.volumeRateHistory = new Map();
    this.quoteVolumeHistory = new Map();
    this.orderbookImbalance = new Map();
    this.lastSignalEmit = 0;
    this.signalQueue = [];
    this.vwapHistory = new Map();
    this.symbols = [];
    this.cycleSignals = [];
    this.lastCycleProcess = Date.now();
    this.pendingOIQueue = new Map();
    this.pendingOIInterval = null;
    this.maxPendingSeconds = 120;
  }

  startPendingOIChecker() {
    if (this.pendingOIInterval) return;
    this.pendingOIInterval = setInterval(() => {
      this.checkPendingOI();
    }, 12000);
  }

  checkPendingOI() {
    if (this.pendingOIQueue.size === 0) return;

    for (const [symbol, pending] of this.pendingOIQueue) {
      const oiData = oiTracker.getOIData(symbol);
      const oiChange = oiData?.avgChange || oiData?.change || 0;
      const priceNow = this.priceHistory.get(symbol);
      const currentPrice = priceNow ? priceNow[priceNow.length - 1]?.price : null;

      if (!oiChange || Math.abs(oiChange) < 0.1) {
        if (Date.now() - pending.addedAt > this.maxPendingSeconds * 1000) {
          console.log(`⏱️ ${symbol} OI timeout (${this.maxPendingSeconds}s), discarding`);
          this.pendingOIQueue.delete(symbol);
        }
        continue;
      }

      const oiStateLabel = this.getOIStateLabel(currentPrice || pending.priceChange, oiChange);

      if (oiStateLabel === '⚠️ SHORT_CVR' || oiStateLabel === '⚠️ LONG_EXT' || oiStateLabel === '⚪ NO_OI') {
        console.log(`❌ ${symbol} OI arrived but state=${oiStateLabel}, discarding`);
        this.pendingOIQueue.delete(symbol);
        continue;
      }

      pending.oiChange = oiChange;
      pending.oiState = oiStateLabel;

      const score = this.calculatePendingRankScore(pending);
      if (score < 60) {
        console.log(`❌ ${symbol} OI valid but rankScore=${score.toFixed(0)} < 60, discarding`);
        this.pendingOIQueue.delete(symbol);
        continue;
      }

      pending.rankScore = score;
      pending.oiState = oiStateLabel;

      this.signalQueue.push(pending);
      console.log(`✅ ${symbol} OI arrived: ${oiChange.toFixed(1)}% [${oiStateLabel}] rank=${score.toFixed(0)}, queued for emission`);
      this.pendingOIQueue.delete(symbol);
    }
  }

  getOIStateLabel(priceChange, oiChange) {
    const pc = priceChange || 0;
    const oi = oiChange || 0;
    if (pc > 0 && oi > 0.3) return '🚀 LONG';
    if (pc > 0 && oi < -0.3) return '⚠️ SHORT_CVR';
    if (pc < 0 && oi > 0.3) return '🔻 SHORT';
    if (pc < 0 && oi < -0.3) return '⚠️ LONG_EXT';
    return '⚪ NO_OI';
  }

  calculatePendingRankScore(d) {
    const conf = d.confidence || 0;
    const volumeScore = Math.min((d.volumeSpike || 0) * 20, 100);
    const priceScore = Math.min(Math.abs(d.priceChange || 0) * 10, 100);
    const ofScore = Math.min((d.orderflow || 1) * 30, 100);
    const momentumScore = Math.min(Math.abs(d.momentum || 0) * 1000, 100);
    const confluenceScore = ((d.confluence || 0) / 5) * 100;

    let oiScore = 0;
    const oi = d.oiChange || 0;
    const pc = d.priceChange || 0;
    if (pc > 0 && oi > 0.3) oiScore = 100;
    else if (pc < 0 && oi > 0.3) oiScore = 100;
    else if (pc > 0 && oi < -0.3) oiScore = 30;
    else if (pc < 0 && oi < -0.3) oiScore = 30;

    return Math.min(100, Math.max(0,
      conf * 0.25 + volumeScore * 0.20 + priceScore * 0.15 +
      ofScore * 0.15 + momentumScore * 0.05 + confluenceScore * 0.05 + oiScore * 0.15
    ));
  }

  addToPendingQueue(signal) {
    this.pendingOIQueue.set(signal.symbol, { ...signal, addedAt: Date.now() });
    console.log(`⏳ ${signal.symbol} queued for OI check (pending: ${this.pendingOIQueue.size})`);
  }

  initialize(symbols) {
    this.symbols = symbols;
    this.startPendingOIChecker();
    if (config.advancedFeatures?.orderflow?.enabled) {
      marketDataTracker.initialize(symbols);
    }
    console.log('📊 Pump Analyzer initialized with advanced features');
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

  calculateVWAP(symbol, ticker) {
    const candles = this.candleHistory.get(symbol);
    if (!candles || candles.length < 5) return ticker.price;
    
    const recent = candles.slice(-20);
    let cumVP = 0;
    let cumV = 0;
    
    for (const c of recent) {
      const typicalPrice = (c.high + c.low + c.close) / 3;
      cumVP += typicalPrice * (c.close > c.open ? c.close - c.open : 1);
      cumV += (c.close > c.open ? c.close - c.open : 1);
    }
    
    return cumV > 0 ? cumVP / cumV : ticker.price;
  }

  calculateATR(symbol, period = 14) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < period + 1) return null;

    const trueRanges = [];
    for (let i = Math.max(1, prices.length - 50); i < prices.length; i++) {
      const curr = prices[i].price;
      const prev = prices[i - 1].price;
      const tr = Math.abs(curr - prev);
      trueRanges.push(tr);
    }

    if (trueRanges.length < period) return null;

    const atr = trueRanges.slice(-period).reduce((a, b) => a + b, 0) / period;
    return atr;
  }

  calculateATRPercent(symbol, period = 14) {
    const atr = this.calculateATR(symbol, period);
    const prices = this.priceHistory.get(symbol);
    if (!atr || !prices || prices.length < 2) return 0;
    const currentPrice = prices[prices.length - 1].price;
    return currentPrice > 0 ? (atr / currentPrice) * 100 : 0;
  }

  calculateATRMA(symbol, period = 14) {
    const prices = this.priceHistory.get(symbol);
    if (!prices || prices.length < period * 3) return null;

    const atrHistory = [];
    for (let i = period; i < prices.length; i++) {
      const trs = [];
      for (let j = i - period + 1; j <= i; j++) {
        trs.push(Math.abs(prices[j].price - prices[j - 1].price));
      }
      atrHistory.push(trs.reduce((a, b) => a + b, 0) / period);
    }

    if (atrHistory.length < 3) return null;
    return atrHistory.slice(-5).reduce((a, b) => a + b, 0) / Math.min(atrHistory.length, 5);
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
    if (!symbol || !ticker) return;
    const { price, quoteVolume, high, low } = ticker;
    if (!price || price <= 0) return;
    const now = Date.now();

    if (!this.priceHistory.has(symbol)) {
      this.priceHistory.set(symbol, []);
      this.volumeHistory.set(symbol, []);
      this.candleHistory.set(symbol, []);
      this.highPrices.set(symbol, []);
      this.lowPrices.set(symbol, []);
      this.volumeRateHistory.set(symbol, []);
      this.quoteVolumeHistory.set(symbol, []);
      this.intraDayHigh.set(symbol, price);
      this.intraDayLow.set(symbol, price);
    }

    const prices = this.priceHistory.get(symbol) || [];
    const volumes = this.volumeHistory.get(symbol) || [];
    const candles = this.candleHistory.get(symbol) || [];
    const highs = this.highPrices.get(symbol) || [];
    const lows = this.lowPrices.get(symbol) || [];
    const volumeRates = this.volumeRateHistory.get(symbol) || [];
    const quoteVolHistory = this.quoteVolumeHistory.get(symbol) || [];
    const intraHigh = this.intraDayHigh.get(symbol) || 0;
    const intraLow = this.intraDayLow.get(symbol) || 0;

    prices.push({ price, timestamp: now });
    highs.push(high || price);
    lows.push(low || price);
    const currentIntraHigh = Math.max(intraHigh, price);
    const currentIntraLow = Math.min(intraLow, price);
    this.intraDayHigh.set(symbol, currentIntraHigh);
    this.intraDayLow.set(symbol, currentIntraLow);

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
      candles.push({ high: price, low: price, close: price, open: price, timestamp: now });
    } else {
      const last = candles[candles.length - 1];
      last.high = Math.max(last.high, price);
      last.low = Math.min(last.low, price);
      last.close = price;
    }

    if (prices.length > 100) prices.shift();
    if (volumes.length > 100) volumes.shift();
    if (candles.length > 100) candles.shift();
    if (highs && highs.length > 100) highs.shift();
    if (lows && lows.length > 100) lows.shift();
    if (volumeRates && volumeRates.length > 100) volumeRates.shift();
    if (quoteVolHistory && quoteVolHistory.length > 100) quoteVolHistory.shift();
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
    
    const volCheck = this.checkVolatilityExpansion(analysis);
    if (volCheck.penalty) {
      analysis.score -= volCheck.penalty;
    }
    
    const entryCheck = this.checkEntryPrecision(analysis, ticker);
    if (entryCheck.penalty) {
      analysis.score -= entryCheck.penalty;
    }
    
    const tier = this.determineTier(symbol, analysis);
    
    if (tier) {
      tier.confidence = this.applyLatePumpPenalty(tier.confidence, analysis.priceChange);
      tier.confidence = this.applySignalDecay(tier);
      tier.confidence = this.applySmartMoneyBonus(tier, analysis);
      
      if (entryCheck.penalty) {
        tier.confidence -= entryCheck.penalty;
      }
      
      const tierThreshold = config.signalTiers[tier.type]?.confidenceThreshold || 20;
      if (tier.confidence < tierThreshold) {
        if (Math.random() < 0.01) {
          console.log(`⚠️ ${symbol} ${tier.type}: Conf=${tier.confidence.toFixed(0)} < ${tierThreshold} (post-adjustment)`);
        }
        return null;
      }
      
      this.signalQueue.push(tier);
      this.lastSignalTime.set(symbol, Date.now());
      this.lastSignalEmit = Date.now();
      this.signalCounts[tier.type]++;
      this.checkAutoRelax();
    }
    
    return this.selectTopSignals();
  }

  checkVolatilityExpansion(analysis) {
    const atr = analysis.atr;
    const atrMA = analysis.atrMA;
    
    if (atr && atrMA && atr > atrMA) {
      analysis.score += config.filters.volatilityExpansionBonus;
      return { passed: true, bonus: config.filters.volatilityExpansionBonus };
    }
    
    if (!atrMA) return { passed: true, bonus: 0 };
    
    return { passed: true, penalty: config.filters.volatilityExpansionPenalty };
  }

  checkEntryPrecision(analysis, ticker) {
    const highs = this.highPrices.get(analysis.symbol);
    if (!highs || highs.length < 2) return { passed: true, penalty: 0 };
    
    const recentHigh = highs[highs.length - 1];
    const currentPrice = ticker.price;
    
    const pullback = (recentHigh - currentPrice) / recentHigh;
    
    if (pullback > config.filters.entryPrecisionMaxPullback) {
      const penalty = Math.min(pullback * 100, config.filters.entryPrecisionPenalty);
      return { passed: true, penalty, pullback: pullback.toFixed(4) };
    }
    
    return { passed: true, penalty: 0 };
  }

  applyLatePumpPenalty(confidence, priceChange) {
    if (priceChange > 10) {
      confidence -= config.filters.latePumpPenalty;
    }
    return Math.max(confidence, 0);
  }

  applySignalDecay(signal) {
    const age = (Date.now() - signal.signalTime) / 60000;
    const maxAge = config.signals.signalDecayMinutes;
    
    if (age > maxAge) {
      signal.confidence -= config.filters.signalDecayPenalty;
    }
    
    return Math.max(signal.confidence, 0);
  }

  applySmartMoneyBonus(signal, analysis) {
    if (
      analysis.volumeSpike > 2 &&
      analysis.orderbookImbalance > 1.2 &&
      analysis.priceAboveVWAP
    ) {
      signal.confidence += config.filters.smartMoneyBonus;
    }
    
    return signal.confidence;
  }

  selectTopSignals() {
    if (this.signalQueue.length === 0) return null;
    
    this.cycleSignals.push(...this.signalQueue);
    this.signalQueue = [];
    
    return null;
  }

  getCycleSignals() {
    const now = Date.now();
    
    if (this.cycleSignals.length === 0) return [];
    
    if (now - this.lastCycleProcess < 10000 && this.cycleSignals.length < 5) {
      return [];
    }

    const filtered = this.cycleSignals.filter(s => !signalRankingEngine.isDuplicate(s.symbol));

    if (filtered.length === 0) {
      this.cycleSignals = [];
      this.lastCycleProcess = now;
      return [];
    }
    
    const ranked = signalRankingEngine.processSignals(filtered);
    
    this.cycleSignals = [];
    this.lastCycleProcess = now;
    
    if (ranked.length > 0) {
      console.log(`🏆 SRE: ${ranked.length} ranked: ${ranked.map(s => `${s.type}:${s.symbol}(${s.rankScore?.toFixed(0)})[${s.oiState || '?'}]`).join(' | ')}`);
    }
    
    return ranked;
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
    
    const localChange = ((currentPrice - recentPrices[recentPrices.length - 3].price) / recentPrices[recentPrices.length - 3].price) * 100;
    const priceChange = Math.abs(priceChangePercent || localChange || 0);
    
    const currentVolumeData = volumes.length > 1 ? volumes[volumes.length - 2] : { volumeSpikeRatio: 1 };
    const volumeSpikeRatio = currentVolumeData.volumeSpikeRatio || 1;
    
    let avgVolumeRate = 1;
    if (volumeRates && volumeRates.length >= 5) {
      const recentRates = volumeRates.slice(-10, -1).map(v => v.rate);
      if (recentRates.length > 0) {
        avgVolumeRate = recentRates.reduce((a, b) => a + b, 0) / recentRates.length;
      }
    }
    const currentVolumeRate = volumeRates && volumeRates.length > 1 ? volumeRates[volumeRates.length - 2].rate : 1;
    const volumeSpike = avgVolumeRate > 0 ? currentVolumeRate / avgVolumeRate : volumeSpikeRatio;

    const momentum = this.calculateMomentum(recentPrices, priceChangePercent);
    const acceleration = this.calculateAcceleration(recentPrices);
    const ema50 = this.calculateEMA(prices, 50);
    const atrPeriod = config?.riskManagement?.atrPeriod || 14;
    const atr = this.calculateATR(symbol, atrPeriod);
    const atrMA = this.calculateATRMA(symbol, atrPeriod);
    const vwap = this.calculateVWAP(symbol, { price: currentPrice });
    const priceAboveVWAP = currentPrice > vwap;

    const { detected: liquiditySweep, reclaimed: sweptReclaimed } = this.checkLiquiditySweep(symbol, currentPrice);
    const breakOfStructure = this.checkBreakOfStructure(symbol);
    const volumeTrend = this.calculateVolumeTrend(symbol);
    const imbalance = this.calculateImbalance(symbol);
    const rsi = this.calculateRSI(symbol);
    const strongCandle = this.analyzeCandleStrength(candles);
    const atrPercent = this.calculateATRPercent(symbol, atrPeriod);

    const orderbookImbalance = orderbookData?.imbalance || 1;
    const spoofingRisk = orderbookData?.spoofingRisk || 0;

    const score = this.calculateScore({
      ema50, currentPrice, liquiditySweep, sweptReclaimed, volumeSpike,
      momentum, acceleration, strongCandle, rsi, volumeTrend, priceChange,
      orderbookImbalance, spoofingRisk, breakOfStructure
    });

    return {
      symbol,
      priceChange,
      localChange,
      volumeSpike,
      momentum,
      acceleration,
      score,
      atr,
      atrMA,
      atrPercent,
      entryPrice: currentPrice,
      ema50,
      vwap,
      priceAboveVWAP,
      breakOfStructure,
      liquiditySweep,
      sweptReclaimed,
      volumeTrend,
      imbalance,
      rsi,
      strongCandle,
      orderbookImbalance,
      spoofingRisk,
      signalTime: Date.now(),
      factors: this.getFactors({
        ema50, currentPrice, breakOfStructure, liquiditySweep, sweptReclaimed,
        volumeSpike, momentum, acceleration, strongCandle, volumeTrend, priceChange,
        orderbookImbalance, atr, atrMA
      })
    };
  }

  calculateScore(metrics) {
    const s = config.scoring || {};
    let score = 0;

    if (metrics.priceChange >= 0.5) score += Math.min(metrics.priceChange * 4, 35);
    
    if (metrics.breakOfStructure) score += (s.priceActionWeight || 30) * 0.4;
    
    if (metrics.ema50 !== null && metrics.currentPrice > metrics.ema50) {
      score += s.trendWeight || 10;
    }
    
    if (metrics.liquiditySweep) {
      if (metrics.sweptReclaimed) score += (s.liquiditySweepWeight || 10) + 5;
      else score += 5;
    }
    
    if (metrics.volumeSpike >= 1.2) score += Math.min((metrics.volumeSpike - 1) * 25, s.volumeWeight || 25);
    if (metrics.volumeTrend) score += 4;
    
    if (metrics.momentum > 0.1) score += Math.min(metrics.momentum * 3, s.momentumWeight || 15);
    else if (metrics.momentum > 0) score += 2;
    if (metrics.acceleration > 0.01) score += Math.min(metrics.acceleration * 30, 8);
    if (metrics.strongCandle) score += 4;
    
    if (metrics.orderbookImbalance > 1.5) score += Math.min((metrics.orderbookImbalance - 1) * 25, s.orderbookWeight || 10);
    if (metrics.orderbookImbalance > 2.0) score += 5;
    
    if (metrics.spoofingRisk > 30) score -= 20;
    else if (metrics.spoofingRisk > 15) score -= 10;

    if (metrics.rsi > 95) score -= 5;
    if (metrics.rsi > 92) score -= 2;

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
    if (metrics.atr && metrics.atrMA && metrics.atr > metrics.atrMA) factors.push('Vol Expansion');
    if (metrics.spoofingRisk > 15) factors.push(`Spoof: ${metrics.spoofingRisk.toFixed(0)}`);
    return factors;
  }

  determineTier(symbol, analysis) {
    if (!analysis) return null;
    let { score, priceChange, volumeSpike, momentum, orderbookImbalance } = analysis;

    const NO_PUMP_SYMBOLS = ['BTCUSDT', 'ETHUSDT'];
    const isFilteredSymbol = NO_PUMP_SYMBOLS.includes(symbol);

    if (score === undefined || score === null || isNaN(score)) score = 0;
    if (priceChange === undefined || priceChange === null) priceChange = 0;
    if (volumeSpike === undefined || volumeSpike === null) volumeSpike = 0;
    if (momentum === undefined || momentum === null) momentum = 0;
    if (orderbookImbalance === undefined || orderbookImbalance === null) orderbookImbalance = 1;

    const orderflowData = orderflowTracker.getOrderflowData(symbol);
    const oiData = oiTracker.getOIData(symbol);
    const fundingData = fundingService.getFundingData(symbol);
    const liqData = liquidationEngine.analyze(symbol, analysis.entryPrice || 0);
    const ofRatio = orderflowData?.ratio || 1;
    const oiChange = oiData?.change || oiData?.avgChange || 0;
    const fundingRate = fundingData?.rate || 0;

    const prePumpData = {
      priceChange,
      volumeSpike,
      orderflow: ofRatio,
      oiChange,
      fundingRate,
      imbalance: orderbookImbalance,
      momentum
    };
    const prePumpResult = prePumpDetector.analyze(symbol, prePumpData);

    const HARD_PUMP_FILTERS = priceChange >= 3 && volumeSpike >= 5 && ofRatio >= 1.5 && Math.abs(oiChange) >= 0.3;
    if (!HARD_PUMP_FILTERS && Math.random() < 0.01) {
      console.log(`❌ ${symbol} → HardFilter: PC=${priceChange.toFixed(1)}% Vol=${volumeSpike.toFixed(1)}x OF=${ofRatio.toFixed(2)} OI=${oiChange.toFixed(1)}%`);
    }

    let confluence = 0;
    if (volumeSpike > 3) confluence++;
    if (ofRatio > 1.3) confluence++;
    if (oiChange > 1) confluence++;
    if (momentum > 0.1) confluence++;
    if (priceChange > 3) confluence++;
    confluence = Math.min(confluence, 5);

    const confidenceData = {
      score,
      volumeSpike,
      momentum,
      imbalance: orderbookImbalance,
      orderbookImbalance,
      priceChange,
      orderflow: ofRatio,
      oiChange: oiChange,
      fundingRate,
      trend: analysis.currentPrice > analysis.ema50 ? 'UP' : 'DOWN',
      atr: analysis.atr,
      atrMA: analysis.atrMA,
      marketRegime: this.detectMarketRegime(symbol),
      liquidationSignal: liqData.signal,
      liquidationDirection: liqData.direction
    };

    const result = analyzeSignal(confidenceData);
    let enhancedResult = { ...result, confluence, prePump: prePumpResult };
    
    if (liqData.signal && liqData.direction === 'UP') {
      enhancedResult.confidence += 10;
      enhancedResult.confidence = Math.min(enhancedResult.confidence, 100);
    }
    
    if (fundingData.signal === 'SHORT_SQUEEZE' && priceChange > 0) {
      enhancedResult.confidence += 12;
      enhancedResult.confidence = Math.min(enhancedResult.confidence, 100);
    }
    
    if (fundingData.signal === 'RISKY_LONG') {
      enhancedResult.confidence -= 8;
    }

    if (enhancedResult.isFakePump) return null;

    if (!enhancedResult.shouldGenerateSignal && confluence < 2 && prePumpResult.prePumpScore < 4) {
      if (Math.random() < 0.01) {
        console.log(`❌ ${symbol} → NoSignal: conf=${enhancedResult.confidence} tier=${enhancedResult.tier} confluence=${confluence}`);
      }
      return null;
    }

    if (priceChange > 15) {
      if (Math.random() < 0.01) console.log(`❌ ${symbol} → LATE: priceChange=${priceChange.toFixed(1)}% > 15%`);
      return null;
    }

    const checkRR = (entry, atr, atrPct, tier) => {
      const ex = this.generateEntryExit(entry, atr, atrPct, tier);
      return this.validateRiskReward(ex.entry, ex.sl, ex.tp1) && this.validateMinimumMove(ex.entry, ex.tp3);
    };

    const hasOI = Math.abs(oiChange) >= 0.3;
    const oiStateLabel = this.getOIStateLabel(priceChange, oiChange);
    const isBadOIState = oiStateLabel === '⚠️ SHORT_CVR' || oiStateLabel === '⚠️ LONG_EXT' || oiStateLabel === '⚪ NO_OI';
    const isGoodOIState = oiStateLabel === '🚀 LONG' || oiStateLabel === '🔻 SHORT';

    const buildSignal = (type, ex) => {
      return { symbol, type, score, ...enhancedResult, oiChange, priority: type === 'SNIPER' ? 1 : type === 'CONFIRMED' ? 2 : type === 'EARLY' ? 3 : 0, signalTime: Date.now(), signals: ex };
    };

    const tryEmit = (type, ex, minScore = 55) => {
      if (!hasOI || isBadOIState) {
        const rawScore = this.calculatePendingRankScore({ ...enhancedResult, priceChange, volumeSpike, orderflow: ofRatio, momentum: enhancedResult.momentum, oiChange, confidence: enhancedResult.confidence, confluence });
        if (rawScore >= minScore) {
          const signal = buildSignal(type, ex);
          this.addToPendingQueue(signal);
          return null;
        } else {
          if (Math.random() < 0.01) console.log(`❌ ${symbol} ${type}: low score ${rawScore.toFixed(0)} + no OI, skipping`);
          return null;
        }
      }
      console.log(`${type === 'SNIPER' ? '🔴' : type === 'CONFIRMED' ? '🟢' : type === 'EARLY' ? '🟡' : '🟣'} ${type} ⭐🔥: ${symbol} | PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OF=${ofRatio.toFixed(2)} | OI=${oiChange.toFixed(1)}% [${oiStateLabel}] | Conf=${enhancedResult.confidence} | R:R=${ex.rr1.toFixed(1)}`);
      const signal = buildSignal(type, ex);
      this.signalCounts[type]++;
      incrementSignalCount();
      return signal;
    };

    if (priceChange >= 8 && volumeSpike >= 5 && ofRatio >= 2.0 && priceChange <= 15) {
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'CONFIRMED')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'CONFIRMED');
      return tryEmit('CONFIRMED', ex, 55);
    }

    if (priceChange >= 5 && volumeSpike >= 3 && ofRatio >= 1.5 && priceChange <= 15) {
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'SNIPER')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'SNIPER');
      return tryEmit('SNIPER', ex, 55);
    }

    if (priceChange >= 2 && volumeSpike >= 2 && priceChange <= 15) {
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'EARLY')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'EARLY');
      return tryEmit('EARLY', ex, 55);
    }

    if (prePumpResult.isPrePump && prePumpResult.prePumpScore >= 4 && volumeSpike >= 2.5 && ofRatio >= 1.3 && !isFilteredSymbol) {
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PRE_PUMP')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PRE_PUMP');
      const signal = buildSignal('PRE_PUMP', ex);
      if (!hasOI || isBadOIState) {
        this.addToPendingQueue(signal);
        return null;
      }
      console.log(`🟣 PRE-PUMP 🚀: ${symbol} | PrePump:${prePumpResult.prePumpScore} | Vol:${volumeSpike.toFixed(1)}x | OF:${ofRatio.toFixed(2)} | OI=${oiChange.toFixed(1)}% [${oiStateLabel}]`);
      console.log(`   → ${prePumpResult.reasons.join(' | ')}`);
      this.signalCounts.PRE_PUMP++;
      incrementSignalCount();
      return signal;
    }

    return null;
  }

  detectMarketRegime(symbol) {
    const volumes = this.volumeHistory.get(symbol);
    if (!volumes || volumes.length < 10) return 'TRENDING';
    
    const recent = volumes.slice(-10).map(v => v.volume);
    const avg = recent.reduce((a, b) => a + b, 0) / 10;
    const variance = recent.reduce((sum, v) => sum + Math.pow(v - avg, 2), 0) / 10;
    const cv = Math.sqrt(variance) / avg;
    
    return cv > 0.5 ? 'SIDEWAYS' : 'TRENDING';
  }

  generateEntryExit(entryPrice, atr, atrPercent, tier) {
    const MIN_ATR_PERCENT = 0.1;
    const useAtrPercent = Math.max(atrPercent || 0, MIN_ATR_PERCENT);
    const atrValue = atr || (entryPrice * useAtrPercent / 100);

    const slPercent = tier === 'PRE_PUMP' ? 0.5 : tier === 'SNIPER' ? 1.0 : tier === 'CONFIRMED' ? 0.8 : 0.6;
    const sl = entryPrice * (1 - slPercent / 100);
    const risk = entryPrice - sl;

    const tpPercents = {
      PRE_PUMP: [1.0, 2.0, 3.0, 5.0, 8.0],
      EARLY:    [1.0, 2.0, 3.5, 5.0, 8.0],
      CONFIRMED:[1.5, 3.0, 5.0, 7.5, 10.0],
      SNIPER:   [2.0, 4.0, 6.0, 9.0, 12.0]
    };

    const tiers = config.signalTiers || {};
    const multipliers = tpPercents[tier] || tpPercents.EARLY;

    const tp1 = entryPrice * (1 + multipliers[0] / 100);
    const tp2 = entryPrice * (1 + multipliers[1] / 100);
    const tp3 = entryPrice * (1 + multipliers[2] / 100);
    const tp4 = entryPrice * (1 + multipliers[3] / 100);
    const tp5 = entryPrice * (1 + multipliers[4] / 100);

    const rr1 = multipliers[0];
    const rr2 = multipliers[1];
    const rr3 = multipliers[2];

    return {
      entry: entryPrice,
      tp1,
      tp2,
      tp3,
      tp4,
      tp5,
      sl,
      atr: atrValue,
      atrPercent: useAtrPercent,
      risk,
      rr1,
      rr2,
      rr3,
      partialExits: {
        tp1Percent: 0,
        tp2Percent: 0,
        tp3Percent: 0
      }
    };
  }

  validateRiskReward(entryPrice, sl, tp1) {
    const risk = entryPrice - sl;
    const reward = tp1 - entryPrice;
    const rr = risk > 0 ? reward / risk : 0;
    return rr >= 1.0;
  }

  validateMinimumMove(entryPrice, tp3) {
    const movePercent = ((tp3 - entryPrice) / entryPrice) * 100;
    return movePercent >= 0.5;
  }

  calculateMomentum(prices, priceChangePercent) {
    if (!prices || prices.length < 4) return priceChangePercent || 0;
    const recent = prices.slice(-4);
    if (recent.length < 4) return priceChangePercent || 0;
    
    const rate = ((recent[recent.length - 1].price - recent[0].price) / recent[0].price) * 100;
    return rate;
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
      this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, PRE_PUMP: 0, lastReset: now };
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
    this.intraDayHigh.delete(symbol);
    this.intraDayLow.delete(symbol);
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
