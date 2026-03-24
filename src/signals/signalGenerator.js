import { config } from '../../config/config.js';
import { createSignal as dbCreateSignal } from '../database/db.js';
import { addToActive } from '../state.js';
import { riskManager } from '../engine/riskManager.js';
import { getSmartOI } from '../engine/signalPipeline.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.signalId = 0;
    this.accountBalance = config?.positionSizing?.accountSize || 10000;
    this.leverage = config?.positionSizing?.leverage || 5;
    this.MAX_ACTIVE = 10;
  }

  getQuality(conf) {
    if (conf >= 70) return 'EXCELLENT';
    if (conf >= 60) return 'GOOD';
    if (conf >= 50) return 'OK';
    return 'WEAK';
  }

  async generateSignal(symbol, analysis) {
    if (!analysis || !analysis.type) return null;

    if (this.activeSignals.size >= this.MAX_ACTIVE) {
      if (Math.random() < 0.01) {
        console.log(`⚠️ MAX_ACTIVE (${this.MAX_ACTIVE}) reached, skipping ${symbol}`);
      }
      return null;
    }

    const { type, score, priceChange, volumeSpike, momentum, factors, signals, atr, entryPrice, metadata } = analysis;
    
    const signalEntry = entryPrice || (signals?.entry);
    const signalSL = signals?.sl;
    
    const riskAmount = riskManager.calculateRiskAmount(this.accountBalance);
    
    const positionCalc = riskManager.calculatePositionSize({
      riskAmount,
      entry: signalEntry,
      stopLoss: signalSL,
      leverage: this.leverage
    });
    
    const pumpTPs = signals?.tp1 ? {
      tp1: signals.tp1,
      tp2: signals.tp2,
      tp3: signals.tp3,
      tp4: signals.tp4,
      tp5: signals.tp5,
      rr1: signals.rr1,
      rr2: signals.rr2,
      rr3: signals.rr3,
      risk: signals.risk
    } : null;
    
    const signal = {
      id: `sig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      symbol: symbol || 'UNKNOWN',
      type,
      tier: type,
      timestamp: Date.now(),
      entryPrice: signalEntry,
      atr,
      leverage: this.leverage,
      riskAmount,
      positionSize: positionCalc,
      rankScore: analysis.rankScore || 0,
      quality: this.getQuality(analysis.confidence || 0),
      targets: {
        tp1: signals?.tp1 || signalSL ? signalEntry + (signalEntry - signalSL) * 1 : null,
        tp2: signals?.tp2 || signalSL ? signalEntry + (signalEntry - signalSL) * 2 : null,
        tp3: signals?.tp3 || signalSL ? signalEntry + (signalEntry - signalSL) * 3 : null,
        tp4: signals?.tp4 || signalSL ? signalEntry + (signalEntry - signalSL) * 4 : null,
        tp5: signals?.tp5 || signalSL ? signalEntry + (signalEntry - signalSL) * 5 : null
      },
      stopLoss: signalSL,
      risk: signals?.risk || (signalSL ? signalEntry - signalSL : 0),
      riskReward: {
        rr1: signals?.rr1 || (signalSL && signalEntry ? 1 : 0),
        rr2: signals?.rr2 || (signalSL && signalEntry ? 2 : 0),
        rr3: signals?.rr3 || (signalSL && signalEntry ? 3 : 0)
      },
      trailingStop: {
        tp1Trailing: signalEntry,
        tp2Trailing: signalEntry + (signalEntry - signalSL) * 0.5,
        tp3Trailing: signalEntry + (signalEntry - signalSL) * 1.5
      },
      tradeDetails: {
        quantity: positionCalc?.quantity?.toFixed(4) || 'N/A',
        positionValue: positionCalc?.positionValue?.toFixed(2) || 'N/A',
        actualRisk: positionCalc?.actualRisk?.toFixed(2) || 'N/A'
      },
      metrics: {
        priceChange: typeof priceChange === 'number' ? priceChange.toFixed(2) : '0',
        volumeSpike: typeof volumeSpike === 'number' ? volumeSpike.toFixed(1) : '0',
        momentum: typeof momentum === 'number' ? momentum.toFixed(4) : '0',
        score
      },
      factors: Array.isArray(factors) ? factors : [],
      metadata,
      confidence: analysis.confidence || 0,
      confluence: analysis.confluence || 0,
      confluenceReasons: analysis.confluenceReasons || [],
      entryQuality: analysis.entryQuality || 'N/A',
      action: analysis.action || 'UNKNOWN',
      shouldTrade: analysis.shouldTrade || false,
      status: type === 'SNIPER' ? 'HOT' : type === 'PRE_PUMP' ? 'BUILDING' : type === 'CONFIRMED' ? 'ACTIVE' : 'WATCHLIST',
      prePump: analysis.prePump || null,
      management: {
        slMovedToBreakeven: false,
        trailingActive: false,
        tpHits: []
      }
    };

    this.activeSignals.set(signal.symbol, signal);
    this.signalHistory.push(signal);
    addToActive(signal.symbol);

    try {
      await dbCreateSignal(signal);
    } catch (error) {
      console.error('Failed to persist signal to database:', error);
    }

    return signal;
  }

  formatSignal(signal) {
    const { targets, stopLoss, metrics, riskReward } = signal;
    
    const tierEmoji = signal.tier === 'SNIPER' ? '🔴' : signal.tier === 'CONFIRMED' ? '🟢' : signal.tier === 'PRE_PUMP' ? '🟣' : '🟡';
    const tierLabel = signal.tier === 'SNIPER' ? 'HIGH ACCURACY' : signal.tier === 'CONFIRMED' ? 'CONFIRMED ENTRY' : signal.tier === 'PRE_PUMP' ? 'PRE-PUMP BUILDING' : 'EARLY WATCH';
    
    const atrDisplay = signal.atr && !isNaN(signal.atr) ? signal.atr.toFixed(6) : 'N/A';
    const entryDisplay = signal.entryPrice && !isNaN(signal.entryPrice) ? signal.entryPrice.toFixed(6) : 'N/A';
    const slDisplay = stopLoss && !isNaN(stopLoss) ? stopLoss.toFixed(6) : 'N/A';
    const tp1Display = targets?.tp1 && !isNaN(targets.tp1) ? targets.tp1.toFixed(6) : 'N/A';
    const tp2Display = targets?.tp2 && !isNaN(targets.tp2) ? targets.tp2.toFixed(6) : 'N/A';
    const tp3Display = targets?.tp3 && !isNaN(targets.tp3) ? targets.tp3.toFixed(6) : 'N/A';
    const tp4Display = targets?.tp4 && !isNaN(targets.tp4) ? targets.tp4.toFixed(6) : 'N/A';
    const tp5Display = targets?.tp5 && !isNaN(targets.tp5) ? targets.tp5.toFixed(6) : 'N/A';
    
    const factors = signal.confluenceReasons || signal.factors || [];
    const factorsList = Array.isArray(factors) ? factors.map(f => `   • ${f}`).join('\n') : `   • ${factors}`;
    
    let prePumpSection = '';
    if (signal.prePump && signal.tier === 'PRE_PUMP') {
      prePumpSection = `
⚠️ PRE-PUMP INDICATORS:
   Score: ${signal.prePump.prePumpScore || 0}
   Direction: ${signal.prePump.direction || 'NEUTRAL'}
   Reasons: ${(signal.prePump.reasons || []).join(', ')}
⏱️ Expect move in 5-10 minutes
`;
    }
    
    const tradeDetails = signal.tradeDetails || {};
    const trailing = signal.trailingStop || {};
    const rr1 = signal.riskReward?.rr1 || 0;
    const rr2 = signal.riskReward?.rr2 || 0;
    const rr3 = signal.riskReward?.rr3 || 0;
    const riskSection = `
💎 RISK MANAGEMENT:
   Leverage: ${signal.leverage || 5}x
   Quantity: ${tradeDetails.quantity || 'N/A'}
   Position Value: $${tradeDetails.positionValue || 'N/A'}
   Risk Amount: $${signal.riskAmount?.toFixed(2) || 'N/A'}
   Actual Risk: $${tradeDetails.actualRisk || 'N/A'}
   Risk: ${signal.risk ? signal.risk.toFixed(6) : 'N/A'}
`;
    const trailingSection = `
🔒 TRAILING STOP:
   After TP1: Move SL to breakeven
   After TP2: Lock ${rr2.toFixed(1)}R profit
   After TP3: Let run to ${rr3.toFixed(1)}R
`;
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${tierEmoji} ${signal.tier} SIGNAL #${signal.id} - ${tierLabel}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
${prePumpSection}${riskSection}${trailingSection}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 RANK: ${(signal.rankScore || 0).toFixed(0)} | Quality: ${signal.quality || 'N/A'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${entryDisplay}
🛑 STOP LOSS: ${slDisplay}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TAKE PROFIT LEVELS:
   TP1: ${tp1Display} | R/R: ${rr1.toFixed(1)}R ✅ (50% close)
   TP2: ${tp2Display} | R/R: ${rr2.toFixed(1)}R ✅ (30% close)
   TP3: ${tp3Display} | R/R: ${rr3.toFixed(1)}R ✅ (let run)
   TP4: ${tp4Display}
   TP5: ${tp5Display}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 METRICS:
   Confidence: ${signal.confidence || 0}
   Price Change: ${metrics?.priceChange || 0}%
   Volume Spike: ${metrics?.volumeSpike || 0}x
   Momentum: ${metrics?.momentum || 0}
   Score: ${metrics?.score || 0}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 CONFLUENCE (${signal.confluence || 0}):
${factorsList}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;
  }

  updateSignal(symbol, currentPrice) {
    const signal = this.activeSignals.get(symbol);
    if (!signal) return null;

    const update = {
      currentPrice,
      unrealizedPnL: parseFloat(((currentPrice - signal.entryPrice) / signal.entryPrice * 100).toFixed(2)),
      tpHit: [],
      slHit: false
    };

    if (currentPrice >= signal.targets.tp1) update.tpHit.push(1);
    if (currentPrice >= signal.targets.tp2) update.tpHit.push(2);
    if (currentPrice >= signal.targets.tp3) update.tpHit.push(3);
    if (currentPrice >= signal.targets.tp4) update.tpHit.push(4);
    if (currentPrice >= signal.targets.tp5) update.tpHit.push(5);
    if (currentPrice <= signal.stopLoss) update.slHit = true;

    if (update.tpHit.length > 0) {
      update.tpHit.forEach(tp => {
        if (!signal.management.tpHits.includes(tp)) {
          signal.management.tpHits.push(tp);
        }
      });
    }

    if (signal.tier !== 'EARLY' && signal.management.tpHits.includes(1) && !signal.management.slMovedToBreakeven) {
      signal.stopLoss = signal.entryPrice;
      signal.management.slMovedToBreakeven = true;
    }

    if (update.tpHit.length > 0 || update.slHit) {
      if (update.slHit) {
        signal.status = 'STOPPED_OUT';
      } else {
        const maxTP = Math.max(...update.tpHit);
        signal.status = `TP${maxTP}_HIT`;
      }
      signal.closedAt = Date.now();
      signal.closedPrice = currentPrice;
      this.activeSignals.delete(symbol);
    }

    signal.update = update;
    return signal;
  }

  getActiveSignals() {
    return Array.from(this.activeSignals.values());
  }

  getSignalHistory() {
    return this.signalHistory;
  }

  getActiveSignal(symbol) {
    return this.activeSignals.get(symbol);
  }
}

export const signalGenerator = new SignalGenerator();
