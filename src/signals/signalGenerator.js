import { config } from '../../config/config.js';
import { createSignal as dbCreateSignal } from '../database/db.js';
import { addToActive } from '../state.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.signalId = 0;
    this.accountBalance = config?.positionSizing?.accountSize || 10000;
  }

  async generateSignal(analysis) {
    if (!analysis || !analysis.type) return null;

    const { type, score, priceChange, volumeSpike, momentum, factors, signals, atr, entryPrice, symbol, metadata } = analysis;
    
    const signalEntry = entryPrice || (signals?.entry);
    const signalSL = signals?.sl;
    
    const signal = {
      id: `sig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      symbol: symbol || 'UNKNOWN',
      type,
      tier: type,
      timestamp: Date.now(),
      entryPrice: signalEntry,
      atr,
      targets: {
        tp1: signals?.tp1,
        tp2: signals?.tp2,
        tp3: signals?.tp3,
        tp4: signals?.tp4,
        tp5: signals?.tp5
      },
      stopLoss: signalSL,
      riskReward: {
        tp1: signalSL && signalEntry ? ((signals.tp1 - signalEntry) / (signalEntry - signalSL)).toFixed(2) : '0',
        tp2: signalSL && signalEntry ? ((signals.tp2 - signalEntry) / (signalEntry - signalSL)).toFixed(2) : '0',
        tp3: signalSL && signalEntry ? ((signals.tp3 - signalEntry) / (signalEntry - signalSL)).toFixed(2) : '0'
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
      status: type === 'SNIPER' ? 'HOT' : type === 'CONFIRMED' ? 'ACTIVE' : 'WATCHLIST',
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
    
    const tierEmoji = signal.tier === 'SNIPER' ? '🔴' : signal.tier === 'CONFIRMED' ? '🟢' : '🟡';
    const tierLabel = signal.tier === 'SNIPER' ? 'HIGH ACCURACY' : signal.tier === 'CONFIRMED' ? 'CONFIRMED ENTRY' : 'EARLY WATCH';
    
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
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${tierEmoji} ${signal.tier} SIGNAL #${signal.id} - ${tierLabel}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${entryDisplay}
📏 ATR: ${atrDisplay}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TAKE PROFIT LEVELS:
   TP1: ${tp1Display} | R/R: ${riskReward?.tp1 || 'N/A'}
   TP2: ${tp2Display} | R/R: ${riskReward?.tp2 || 'N/A'}
   TP3: ${tp3Display} | R/R: ${riskReward?.tp3 || 'N/A'}
   TP4: ${tp4Display}
   TP5: ${tp5Display}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 STOP LOSS: ${slDisplay}
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
