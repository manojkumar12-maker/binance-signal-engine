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
import { liquidityTrapDetector } from '../engine/liquidityTrapDetector.js';
import { signalPipeline, STAGES, signalStateMachine } from '../engine/signalPipeline.js';

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
    this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, PRE_PUMP: 0, PUMP_CONFIRMED: 0, lastReset: Date.now() };
    this.volumeRateHistory = new Map();
    this.quoteVolumeHistory = new Map();
    this.orderbookImbalance = new Map();
    this.lastSignalEmit = 0;
    this.signalQueue = [];
    this.vwapHistory = new Map();
    this.symbols = [];
    this.cycleSignals = [];
    this.lastCycleProcess = Date.now();
    this.prePumpState = new Map();
  }

  classifyOI(priceChange, oiChange, fakeOI = null) {
    const pc = priceChange || 0;
    const oi = oiChange || 0;
    const fake = fakeOI || 0;
    
    if (fakeOI !== null && fakeOI !== 0) {
      if (pc > 0 && fake > 0.5) return 'EARLY_LONG';
      if (pc > 0 && fake < -0.5) return 'SHORT_SQUEEZE';
      if (pc < 0 && fake > 0.5) return 'EARLY_SHORT';
      if (pc < 0 && fake < -0.5) return 'LONG_EXIT';
    }
    
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
    
    if (oiChange === null || oiChange === undefined) {
      if (fakeOI !== null && Math.abs(fakeOI) > 0.5) {
        const emoji = fakeOI > 0 ? '⚡' : '⚡';
        return { label: `${emoji} EARLY (${fakeOI > 0 ? '+' : ''}${fakeOI.toFixed(1)}%)`, tag: 'EARLY' };
      }
      return { label: '⚪ NO_OI', tag: 'NO_OI' };
    }
    if (Math.abs(oi) < 0.3) return { label: '🟡 FLAT', tag: 'FLAT' };
    
    if (pc > 0 && oi > 0.5) return { label: '🟢 LONG_BUILDUP', tag: 'LONG_BUILDUP' };
    if (pc > 0 && oi < -0.3) return { label: '💥 SHORT_SQUEEZE', tag: 'SHORT_SQUEEZE' };
    if (pc < 0 && oi > 0.5) return { label: '🔴 SHORT_BUILDUP', tag: 'SHORT_BUILDUP' };
    if (pc < 0 && oi < -0.3) return { label: '🪤 LONG_EXIT', tag: 'LONG_EXIT' };
    
    return { label: '🟡 FLAT', tag: 'FLAT' };
  }

  interpretOI(priceChange, oiChange) {
    if (oiChange === null || oiChange === undefined) return { type: 'NO_DATA', confidenceDelta: 0 };
    
    const pc = priceChange || 0;
    const oi = oiChange;
    
    if (Math.abs(oi) < 0.3) return { type: 'FLAT', confidenceDelta: 0 };
    
    if (pc > 0 && oi > 0.5) {
      return { type: 'LONG_BUILDUP', confidenceDelta: 20, description: 'Smart money entering long' };
    }
    if (pc > 0 && oi < -0.3) {
      return { type: 'SHORT_SQUEEZE', confidenceDelta: 15, description: 'Shorts getting liquidated' };
    }
    if (pc < 0 && oi > 0.5) {
      return { type: 'SHORT_BUILDUP', confidenceDelta: 10, description: 'Bearish accumulation' };
    }
    if (pc < 0 && oi < -0.3) {
      return { type: 'LONG_EXIT', confidenceDelta: -10, description: 'Longs being liquidated' };
    }
    
    return { type: 'NEUTRAL', confidenceDelta: 0 };
  }

  calculateOIScore(oiChange) {
    if (oiChange === null || oiChange === undefined) return 0;
    const oi = Math.abs(oiChange);
    
    if (oi > 2) return 25;
    if (oi > 1) return 15;
    if (oi > 0.5) return 10;
    if (oi > 0.3) return 5;
    if (oi < -1) return -15;
    if (oi < -0.5) return -10;
    return 0;
  }

  calculatePendingRankScore(d) {
    const conf = d.confidence || 0;
    const volumeScore = Math.min((d.volumeSpike || 0) * 20, 100);
    const priceScore = Math.min(Math.abs(d.priceChange || 0) * 10, 100);
    const ofScore = Math.min((d.orderflow || 1) * 30, 100);
    const momentumScore = Math.min(Math.abs(d.momentum || 0) * 1000, 100);
    const confluenceScore = ((d.confluence || 0) / 5) * 100;
    const oiScore = this.calculateOIScore(d.oiChange);

    return Math.min(100, Math.max(0,
      conf * 0.25 + volumeScore * 0.20 + priceScore * 0.15 +
      ofScore * 0.15 + momentumScore * 0.05 + confluenceScore * 0.05 + oiScore
    ));
  }

  initialize(symbols) {
    this.symbols = symbols;
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
    
    signalStateMachine.checkTimeout(symbol);
    
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
      candle: candles && candles.length > 0 ? candles[candles.length - 1] : null,
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
    const fakeOI = oiTracker.getFakeOI(symbol);
    const fakeOIClass = oiTracker.classifyFakeOI(priceChange, symbol);
    const fundingData = fundingService.getFundingData(symbol);
    const liqData = liquidationEngine.analyze(symbol, analysis.entryPrice || 0);
    const ofRatio = orderflowData?.ratio || 1;
    const oiChange = oiData?.change ?? 0;
    
    const combinedOI = fakeOI !== null ? (oiChange + fakeOI) / 2 : oiChange;
    
    if (oiData.current === 0 && Math.random() < 0.001) {
      console.log(`⚠️ NO OI DATA: ${symbol}`);
    } else {
      oiTracker.markPriority(symbol);
    }
    const fundingRate = fundingData?.rate || 0;

    const trapData = {
      priceChange,
      volume: volumeSpike,
      oi: oiChange,
      fakeOI,
      candle: analysis.candle,
      symbol
    };
    const trapResult = liquidityTrapDetector.detect(trapData);
    const trapSkip = liquidityTrapDetector.shouldSkipSignal(symbol, priceChange);
    const isReversalSetup = liquidityTrapDetector.isReversalSetup(symbol, priceChange);

    const prePumpData = {
      priceChange,
      volumeSpike,
      orderflow: ofRatio,
      oiChange,
      fundingRate,
      imbalance: orderbookImbalance,
      momentum,
      fakeOI
    };
    const prePumpResult = prePumpDetector.analyze(symbol, prePumpData);

    const HARD_PUMP_FILTERS = priceChange >= 3 && volumeSpike >= 5 && ofRatio >= 1.5 && (Math.abs(oiChange) >= 0.3 || Math.abs(fakeOI || 0) >= 0.4);
    if (!HARD_PUMP_FILTERS && Math.random() < 0.01) {
      console.log(`❌ ${symbol} → HardFilter: PC=${priceChange.toFixed(1)}% Vol=${volumeSpike.toFixed(1)}x OF=${ofRatio.toFixed(2)} OI=${oiChange.toFixed(1)}% F=${(fakeOI || 0).toFixed(2)}`);
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

    const oiState = this.getOIStateLabel(priceChange, oiChange);
    const oiInterpretation = this.interpretOI(priceChange, oiChange);
    const hasOI = oiChange !== null && Math.abs(oiChange) >= 0.3;
    const isBadOIState = ['⚠️ SHORT_CVR', '⚠️ LONG_EXT'].includes(oiState.label);
    const isGoodOIState = ['🚀 LONG', '🔻 SHORT'].includes(oiState.label);

    if (oiInterpretation.type === 'REAL_PUMP' || oiInterpretation.type === 'REAL_DUMP') {
      enhancedResult.confidence += oiInterpretation.confidenceDelta;
      enhancedResult.confidence = Math.min(enhancedResult.confidence, 100);
    } else if (oiInterpretation.type === 'FAKE_PUMP' || oiInterpretation.type === 'FAKE_DUMP') {
      enhancedResult.confidence += oiInterpretation.confidenceDelta;
    }

    const buildSignal = (type, ex) => {
      return { symbol, type, score, ...enhancedResult, oiChange, oiTag: oiState.tag, priority: type === 'SNIPER' ? 1 : type === 'CONFIRMED' ? 2 : 0, signalTime: Date.now(), signals: ex };
    };

    const tryEmit = (type, ex, minScore = 55) => {
      if (trapSkip.skip) {
        if (Math.random() < 0.01) {
          console.log(`⚠️ TRAP DETECTED: ${symbol} Type: ${trapSkip.type} → ${trapSkip.reason}`);
        }
        return null;
      }
      
      const oiClass = this.classifyOI(priceChange, oiChange, fakeOI);
      const fakeClass = fakeOIClass;
      const isGoodOI = ['LONG_BUILDUP', 'SHORT_BUILDUP', 'SHORT_SQUEEZE', 'EARLY_LONG', 'EARLY_SHORT'].includes(oiClass);
      const isBadOI = ['LONG_EXIT'].includes(oiClass) && priceChange < 0;
      
      let trapBoost = 0;
      if (isReversalSetup && trapResult.confidence > 70) {
        trapBoost = 10;
        console.log(`🔥 REVERSAL SETUP: ${symbol} | ${trapResult.type} | Confidence: ${trapResult.confidence}`);
        console.log(`   → Reasons: ${trapResult.reasons.join(', ')}`);
      }
      
      const scoreOI = fakeOI !== null ? combinedOI : oiChange;
      const rawScore = this.calculatePendingRankScore({ ...enhancedResult, priceChange, volumeSpike, orderflow: ofRatio, momentum: enhancedResult.momentum, oiChange: scoreOI || 0, confidence: enhancedResult.confidence + trapBoost, confluence });

      if (isGoodOI) {
        const oiStr = oiChange > 0.1 ? `${oiChange > 0 ? '+' : ''}${oiChange.toFixed(1)}%` : fakeOI !== null ? `⚡${fakeOI > 0 ? '+' : ''}${fakeOI.toFixed(1)}%` : '0.0%';
        const realStr = oiChange > 0.1 ? `|Real OI=${oiChange > 0 ? '+' : ''}${oiChange.toFixed(1)}%` : '';
        const emoji = oiClass.includes('LONG') ? '🟢' : oiClass.includes('SHORT') ? '🔴' : '💥';
        console.log(`${type === 'SNIPER' ? '🔴' : '🟢'} ${type} ⭐🔥: ${symbol}\n  PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OF=${ofRatio.toFixed(2)}\n  OI=${oiStr} ${emoji} ${oiClass}${realStr}\n  Conf=${enhancedResult.confidence + trapBoost} | R:R=${ex.rr1.toFixed(1)}`);
        const signal = buildSignal(type, ex);
        signal.trapBoost = trapBoost;
        signal.isReversal = isReversalSetup;
        this.signalCounts[type]++;
        incrementSignalCount();
        return signal;
      }

      if (rawScore >= minScore) {
        const oiStr = oiChange !== null && Math.abs(oiChange) > 0.1 ? `${oiChange > 0 ? '+' : ''}${oiChange.toFixed(1)}%` : fakeOI !== null ? `⚡${fakeOI > 0 ? '+' : ''}${fakeOI.toFixed(1)}%` : 'N/A';
        const emoji = fakeOI !== null && Math.abs(fakeOI) > 0.5 ? '⚡' : oiClass === 'LONG_EXIT' ? '🪤' : oiClass === 'FLAT' ? '🟡' : '⚪';
        console.log(`${type === 'SNIPER' ? '🔴' : '🟢'} ${type}: ${symbol} | PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OI=${oiStr} ${emoji} ${oiClass}`);
        const signal = buildSignal(type, ex);
        signal.flags = signal.flags || [];
        signal.flags.push(oiClass);
        this.signalCounts[type]++;
        incrementSignalCount();
        return signal;
      }

      if (Math.random() < 0.01) console.log(`❌ ${symbol} ${type}: low score ${rawScore.toFixed(0)}, skipping`);
      return null;
    };

    const sniperData = {
      priceChange,
      volumeSpike,
      orderFlow: ofRatio,
      oiChange,
      fakeOI,
      momentum
    };

    if (priceChange >= 5 && volumeSpike >= 3 && ofRatio >= 1.5 && priceChange <= 15) {
      const oiValid = Math.abs(oiChange) >= 0.05 || Math.abs(fakeOI || 0) >= 0.6;
      if (!oiValid) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} SNIPER: OI not valid (OI=${oiChange.toFixed(4)}% fake=${(fakeOI || 0).toFixed(2)})`);
        return null;
      }
      
      if (this.isTrap(sniperData)) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} SNIPER: TRAP DETECTED, skipping`);
        return null;
      }
      
      const state = signalStateMachine.getState(symbol);
      if (state.stage !== STAGES.CONFIRMED && state.stage !== STAGES.SNIPER) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} SNIPER: must progress from CONFIRMED (current: ${state.stage})`);
        return null;
      }
      
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'SNIPER')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'SNIPER');
      
      const confidence = this.calculateSniperConfidence(sniperData);
      
      signalStateMachine.setState(symbol, STAGES.SNIPER, { 
        priceChange, volume: volumeSpike, oiChange, fakeOI, confidence 
      });
      
      const direction = this.getDirection(priceChange, ofRatio);
      console.log(`🔴 SNIPER ${direction}: ${symbol}\n  PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OF=${ofRatio.toFixed(2)}\n  OI=${oiChange.toFixed(2)}% F=⚡${(fakeOI || 0).toFixed(2)} | Conf=${confidence}`);
      
      const signal = buildSignal('SNIPER', ex);
      signal.confidence = confidence;
      signal.direction = direction;
      this.signalCounts.SNIPER++;
      incrementSignalCount();
      return signal;
    }

    if (priceChange >= 8 && volumeSpike >= 5 && ofRatio >= 2.0 && priceChange <= 15) {
      const oiValid = Math.abs(oiChange) >= 0.03 || Math.abs(fakeOI || 0) >= 0.4;
      if (!oiValid) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} CONFIRMED: OI not valid (OI=${oiChange.toFixed(4)}% fake=${(fakeOI || 0).toFixed(2)})`);
        return null;
      }
      
      const state = signalStateMachine.getState(symbol);
      if (state.stage !== STAGES.EARLY && state.stage !== STAGES.CONFIRMED) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} CONFIRMED: must progress from EARLY (current: ${state.stage})`);
        return null;
      }
      
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'CONFIRMED')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'CONFIRMED');
      
      signalStateMachine.setState(symbol, STAGES.CONFIRMED, { 
        priceChange, volume: volumeSpike, oiChange, fakeOI, confidence: 65 
      });
      
      return tryEmit('CONFIRMED', ex, 55);
    }

    if (this.updatePrePumpState(symbol, sniperData)) {
      const state = this.prePumpState.get(symbol);
      if (state?.count >= 3 && this.detectPumpConfirmed(sniperData, state)) {
        signalStateMachine.setState(symbol, STAGES.PUMP_CONFIRMED, {
          priceChange, volume: volumeSpike, oiChange, fakeOI, confidence: 75
        });
        
        if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PUMP_CONFIRMED')) return null;
        const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PUMP_CONFIRMED');
        
        const direction = this.getDirection(priceChange, ofRatio);
        console.log(`🔥 PUMP_CONFIRMED ${direction}: ${symbol}\n  PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OF=${ofRatio.toFixed(2)}\n  OI=${oiChange.toFixed(2)}% F=⚡${(fakeOI || 0).toFixed(2)} | PrePump cycles: ${state.count}`);
        
        const signal = buildSignal('PUMP_CONFIRMED', ex);
        signal.direction = direction;
        signal.prePumpCycles = state.count;
        this.signalCounts.PUMP_CONFIRMED++;
        incrementSignalCount();
        return signal;
      }
    }

    if (prePumpResult.isPrePump && prePumpResult.prePumpScore >= 4 && volumeSpike >= 2.5 && ofRatio >= 1.3 && !isFilteredSymbol) {
      const fakeValid = fakeOI !== null && Math.abs(fakeOI) >= 0.3;
      if (!fakeValid) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} PRE_PUMP: fakeOI not valid (fake=${(fakeOI || 0).toFixed(2)})`);
        return null;
      }
      
      const state = signalStateMachine.getState(symbol);
      if (state.stage !== STAGES.IDLE && state.stage !== STAGES.PRE_PUMP) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} PRE_PUMP: must start from IDLE (current: ${state.stage})`);
        return null;
      }
      
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PRE_PUMP')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'PRE_PUMP');
      
      signalStateMachine.setState(symbol, STAGES.PRE_PUMP, { 
        priceChange, volume: volumeSpike, oiChange, fakeOI, confidence: 50 
      });
      
      const oiStr = oiChange !== null ? `${oiChange > 0 ? '+' : ''}${oiChange.toFixed(2)}%` : 'N/A';
      const oiClass = this.classifyOI(priceChange, oiChange);
      const emoji = oiClass === 'LONG_BUILDUP' ? '🟢' : oiClass === 'SHORT_SQUEEZE' ? '💥' : '🟡';
      console.log(`🟣 PRE-PUMP 🚀: ${symbol}\n  PrePump:${prePumpResult.prePumpScore} | Vol:${volumeSpike.toFixed(1)}x | OF:${ofRatio.toFixed(2)}\n  OI=${oiStr} F=⚡${(fakeOI || 0).toFixed(2)} ${emoji} ${oiClass}\n   → ${prePumpResult.reasons.join(' | ')}`);
      const signal = buildSignal('PRE_PUMP', ex);
      this.signalCounts.PRE_PUMP++;
      incrementSignalCount();
      return signal;
    }

    if (priceChange >= 1.5 && volumeSpike >= 2.0 && ofRatio >= 1.2 && momentum > 0 && enhancedResult.confidence >= 45 && priceChange <= 15) {
      const state = signalStateMachine.getState(symbol);
      if (state.stage !== STAGES.IDLE && state.stage !== STAGES.EARLY) {
        if (Math.random() < 0.01) console.log(`⚠️ ${symbol} EARLY: must start from IDLE (current: ${state.stage})`);
        return null;
      }
      
      if (!checkRR(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'EARLY')) return null;
      const ex = this.generateEntryExit(analysis.entryPrice, analysis.atr, analysis.atrPercent, 'EARLY');
      
      signalStateMachine.setState(symbol, STAGES.EARLY, { 
        priceChange, volume: volumeSpike, oiChange, fakeOI, confidence: 50 
      });
      
      const oiStr = oiChange !== null ? `${oiChange > 0 ? '+' : ''}${oiChange.toFixed(2)}%` : 'N/A';
      const fakeStr = fakeOI !== null ? `F=⚡${fakeOI > 0 ? '+' : ''}${fakeOI.toFixed(2)}` : '';
      const oiClass = this.classifyOI(priceChange, oiChange);
      const emoji = oiClass === 'LONG_BUILDUP' ? '🟢' : oiClass === 'SHORT_SQUEEZE' ? '💥' : '🟡';
      console.log(`🟡 EARLY 🔎: ${symbol}\n  PC=${priceChange.toFixed(1)}% | Vol=${volumeSpike.toFixed(1)}x | OF=${ofRatio.toFixed(2)}\n  OI=${oiStr} ${fakeStr} ${emoji} ${oiClass} | Conf=${enhancedResult.confidence}`);
      const signal = buildSignal('EARLY', ex);
      this.signalCounts.EARLY++;
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
    this.prePumpState.delete(symbol);
  }

  detectPrePump(data) {
    const { priceChange, volumeSpike, orderFlow, oiChange, fakeOI } = data;
    return (
      Math.abs(priceChange) < 2 &&
      volumeSpike > 2 &&
      orderFlow > 1.2 &&
      (oiChange > 0.03 || (fakeOI !== null && fakeOI > 0.3))
    );
  }

  updatePrePumpState(symbol, data) {
    const state = this.prePumpState.get(symbol) || { count: 0, lastUpdate: 0 };
    
    if (this.detectPrePump(data)) {
      state.count += 1;
    } else {
      state.count = Math.max(0, state.count - 1);
    }
    state.lastUpdate = Date.now();
    this.prePumpState.set(symbol, state);
    
    return state.count >= 3;
  }

  detectPumpConfirmed(data, state) {
    const { priceChange, volumeSpike, orderFlow, oiChange, fakeOI } = data;
    
    const breakout = Math.abs(priceChange) > 2.5;
    const strongFlow = orderFlow > 2;
    const strongVolume = volumeSpike > 4;
    const oiValid = oiChange > 0.08 || (fakeOI !== null && fakeOI > 0.5);
    
    return (
      state?.count >= 3 &&
      breakout &&
      strongFlow &&
      strongVolume &&
      oiValid
    );
  }

  isTrap(data) {
    const { priceChange, orderFlow, oiChange, fakeOI, momentum } = data;
    
    if (priceChange > 5 && orderFlow < 1.2) return true;
    if (priceChange > 4 && oiChange < 0.02 && (fakeOI === null || fakeOI < 0.3)) return true;
    if (Math.abs(priceChange) > 12) return true;
    if (momentum !== undefined && momentum < 0.01) return true;
    
    return false;
  }

  isSniper(data) {
    const { priceChange, volumeSpike, orderFlow, oiChange, fakeOI, momentum } = data;
    
    const cleanMove = Math.abs(priceChange) > 3 && Math.abs(priceChange) < 12;
    const strongVolume = volumeSpike > 4.5;
    const strongFlow = orderFlow > 2.0;
    const momentumValid = momentum === undefined || momentum > 0.05;
    
    const oiValid = oiChange > 0.08;
    const fakeValid = fakeOI !== null && fakeOI > 0.6;
    
    return cleanMove && strongVolume && strongFlow && momentumValid && (oiValid || fakeValid);
  }

  getDirection(priceChange, orderFlow) {
    if (priceChange > 0 && orderFlow > 1) return 'LONG';
    if (priceChange < 0 && orderFlow < 1) return 'SHORT';
    return 'NEUTRAL';
  }

  calculateSniperConfidence(data) {
    let confidence = 70;
    const { oiChange, volumeSpike, fakeOI, momentum } = data;
    
    if (oiChange > 0.15) confidence += 10;
    if (volumeSpike > 6) confidence += 5;
    if (fakeOI !== null && fakeOI > 0.7) confidence += 5;
    if (!this.isTrap(data)) confidence += 5;
    if (momentum !== undefined && momentum > 0.1) confidence += 5;
    
    return Math.min(confidence, 95);
  }
}

export const pumpAnalyzer = new PumpAnalyzer();
