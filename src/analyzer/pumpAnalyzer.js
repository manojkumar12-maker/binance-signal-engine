import { config } from '../../config/config.js';
import { autoTuner } from '../engine/autoTuner.js';
import { orderBookAnalyzer } from '../engine/orderBookAnalyzer.js';
import { marketDataTracker } from '../engine/marketDataTracker.js';
import { tradeLogger } from '../engine/tradeLogger.js';
import { analyzeSignal, getSmartEntry } from '../engine/confidenceEngine.js';
import { adaptiveState, passesAdaptiveFilter, getRejectionReason, incrementSignalCount } from '../engine/adaptiveFilter.js';
import { PrePumpDetector } from '../engine/prePumpDetector.js';
import { LiquidationService } from '../engine/liquidationService.js';
import { orderflowTracker } from '../engine/orderflowTracker.js';
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
    this.lastSignalTime = new Map();
    this.signalCounts = { EARLY: 0, CONFIRMED: 0, SNIPER: 0, lastReset: Date.now() };
    this.volumeRateHistory = new Map();
    this.quoteVolumeHistory = new Map();
    this.orderbookImbalance = new Map();
    this.lastSignalEmit = 0;
    this.signalQueue = [];
    this.vwapHistory = new Map();
    this.symbols = [];
    this.cycleSignals = [];
    this.lastCycleProcess = Date.now();
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

  calculateATRMA(symbol, period = 14) {
    const atrHistory = [];
    const candles = this.candleHistory.get(symbol);
    if (!candles || candles.length < period * 2) return null;
    
    for (let i = period; i < candles.length; i++) {
      const trs = [];
      for (let j = i - period + 1; j <= i; j++) {
        const tr = Math.max(
          candles[j].high - candles[j].low,
          Math.abs(candles[j].high - candles[j - 1].close),
          Math.abs(candles[j].low - candles[j - 1].close)
        );
        trs.push(tr);
      }
      atrHistory.push(trs.reduce((a, b) => a + b, 0) / period);
    }
    
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
      
      if (tier.confidence < (config.signalTiers[tier.type]?.confidenceThreshold || 30)) {
        return null;
      }
      
      this.signalQueue.push(tier);
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
    
    if (now - this.lastCycleProcess < 5000 && this.cycleSignals.length < 10) {
      return [];
    }
    
    const ranked = this.cycleSignals
      .sort((a, b) => {
        const scoreA = (a.confidence || 0) + (a.score || 0);
        const scoreB = (b.confidence || 0) + (b.score || 0);
        return scoreB - scoreA;
      })
      .slice(0, 5);
    
    this.cycleSignals = [];
    this.lastCycleProcess = now;
    
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
    let { score, priceChange, volumeSpike, momentum, orderbookImbalance } = analysis;

    const orderflowData = orderflowTracker.getOrderflowData(symbol);
    const oiData = oiTracker.getOIData(symbol);
    const fundingData = fundingService.getFundingData(symbol);
    const liqData = liquidationEngine.analyze(symbol, analysis.entryPrice);
    const ofRatio = orderflowData?.ratio || 1;
    const oiChange = oiData?.change || 0;
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

    let confluence = 0;
    if (volumeSpike > 2) confluence++;
    if (ofRatio > 1.2) confluence++;
    if (oiChange > 2) confluence++;
    if (momentum > 0.05) confluence++;
    if (priceChange > 2) confluence++;
    confluence = Math.min(confluence, 5);

    if (
      ofRatio < 1.1 ||
      oiChange < 1.5 ||
      volumeSpike < 1.5 ||
      confluence < 2
    ) {
      return null;
    }

    if (score < 45) return null;

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

    if (!enhancedResult.shouldGenerateSignal) {
      const reasons = getRejectionReason({ score, confidence: enhancedResult.confidence, confluence, orderflow: ofRatio, oiChange, volumeSpike });
      if (reasons.length > 0) {
        console.log(`❌ ${symbol} → ${reasons.join(' | ')}`);
      }
      return null;
    }
    if (enhancedResult.isFakePump) return null;

    const filterData = { score, confidence: enhancedResult.confidence, confluence, orderflow: ofRatio, oiChange, volumeSpike };
    
    if (!passesAdaptiveFilter(filterData)) {
      const reasons = getRejectionReason(filterData);
      if (adaptiveState.mode === 'RELAXED' || Math.random() < 0.05) {
        console.log(`❌ ${symbol} → ${reasons.join(' | ')}`);
      }
      return null;
    }

    const tiers = config.signalTiers || {};
    
    const tradeDecision = tradeLogger.shouldTrade({ ...enhancedResult, symbol, type: enhancedResult.tier });
    if (!tradeDecision.trade) {
      return null;
    }
    
    if (prePumpResult.isPrePump && prePumpResult.prePumpScore >= 3) {
      console.log(`🟣 PRE-PUMP 🚀: ${symbol} | PrePump:${prePumpResult.prePumpScore} | OI:${oiChange?.toFixed(1) || '0.0'}% | OF:${ofRatio?.toFixed(2) || '1.00'} | Vol:${volumeSpike?.toFixed(1) || '0'}x | Fund:${(fundingRate * 100).toFixed(3)}%`);
      console.log(`   → ${prePumpResult.reasons.join(' | ')}`);
      const signal = { symbol, type: 'PRE_PUMP', score, ...enhancedResult, priority: 0, signalTime: Date.now(), signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'PRE_PUMP') };
      incrementSignalCount();
      return signal;
    }
    
    if (enhancedResult.tier === 'SNIPER' && enhancedResult.hasConfluence && enhancedResult.confidence >= (tiers.SNIPER?.confidenceThreshold || 80)) {
      if (priceChange >= (tiers.SNIPER?.priceChangeMin || 2) && priceChange <= (tiers.SNIPER?.priceChangeMax || 8)) {
        console.log(`🔴 SNIPER ⭐🔥: ${symbol} | Conf=${enhancedResult.confidence} | Score=${score?.toFixed(0) || 'N/A'} | PriceChg=${priceChange?.toFixed(1) || 0}% | Vol=${volumeSpike?.toFixed(1) || 0}x | OF:${ofRatio?.toFixed(2) || '1.00'} | OI:${oiChange?.toFixed(1) || '0.0'}% | Fund:${(fundingRate * 100).toFixed(3)}%`);
        const signal = { symbol, type: 'SNIPER', score, ...enhancedResult, priority: 1, signalTime: Date.now(), signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'SNIPER') };
        incrementSignalCount();
        return signal;
      }
    }

    if (enhancedResult.tier === 'CONFIRMED' && enhancedResult.hasConfluence && enhancedResult.confluenceCount >= 3 && enhancedResult.confidence >= (tiers.CONFIRMED?.confidenceThreshold || 65)) {
      if (priceChange >= (tiers.CONFIRMED?.priceChangeMin || 2) && priceChange <= (tiers.CONFIRMED?.priceChangeMax || 10)) {
        console.log(`🟢 CONFIRMED ⭐🔥: ${symbol} | Conf=${enhancedResult.confidence} | Score=${score?.toFixed(0) || 'N/A'} | PriceChg=${priceChange?.toFixed(1) || 0}% | Vol=${volumeSpike?.toFixed(1) || 0}x | OF:${ofRatio?.toFixed(2) || '1.00'} | OI:${oiChange?.toFixed(1) || '0.0'}% | Confluence:${confluence}`);
        const signal = { symbol, type: 'CONFIRMED', score, ...enhancedResult, priority: 2, signalTime: Date.now(), signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'CONFIRMED') };
        incrementSignalCount();
        return signal;
      }
    }

    if ((enhancedResult.tier === 'EARLY' || enhancedResult.confidence >= 50) && !enhancedResult.isFakePump) {
      if (priceChange >= (tiers.EARLY?.priceChangeMin || 1) && priceChange <= (tiers.EARLY?.priceChangeMax || 8)) {
        console.log(`🟡 EARLY 👀: ${symbol} | Conf=${enhancedResult.confidence} | Score=${score?.toFixed(0) || 'N/A'} | PriceChg=${priceChange?.toFixed(1) || 0}% | Vol=${volumeSpike?.toFixed(1) || 0}x | OF:${ofRatio?.toFixed(2) || '1.00'} | OI:${oiChange?.toFixed(1) || '0.0'}%`);
        const signal = { symbol, type: 'EARLY', score, ...enhancedResult, priority: 3, signalTime: Date.now(), signals: this.generateEntryExit(analysis.entryPrice, analysis.atr, 'EARLY') };
        incrementSignalCount();
        return signal;
      }
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

  generateEntryExit(entryPrice, atr, tier) {
    const fallbackAtr = atr || (entryPrice * 0.005);
    const multipliers = config?.riskManagement?.atrMultiplier || { tp1: 0.5, tp2: 1.0, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.2 };
    const tierMultipliers = tier === 'SNIPER' ? { tp1: 1, tp2: 2, tp3: 3, tp4: 4, tp5: 5, sl: 1.5 } :
                            tier === 'CONFIRMED' ? { tp1: 0.75, tp2: 1.5, tp3: 2.5, tp4: 3.5, tp5: 5, sl: 1.2 } :
                            { tp1: 0.5, tp2: 1, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.0 };

    return {
      entry: entryPrice,
      tp1: entryPrice + (tierMultipliers.tp1 * fallbackAtr),
      tp2: entryPrice + (tierMultipliers.tp2 * fallbackAtr),
      tp3: entryPrice + (tierMultipliers.tp3 * fallbackAtr),
      tp4: entryPrice + (tierMultipliers.tp4 * fallbackAtr),
      tp5: entryPrice + (tierMultipliers.tp5 * fallbackAtr),
      sl: entryPrice - (tierMultipliers.sl * fallbackAtr),
      atr: fallbackAtr
    };
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
