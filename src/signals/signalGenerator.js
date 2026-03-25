import { config } from '../../config/config.js';
import { createSignal as dbCreateSignal } from '../database/db.js';
import { addToActive } from '../state.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.MAX_ACTIVE = 10;
  }

  async generateSignal(symbol, pipelineResult) {
    if (!pipelineResult || pipelineResult.type !== 'SNIPER') return null;

    if (this.activeSignals.size >= this.MAX_ACTIVE) {
      return null;
    }

    const { entry, stopLoss, tp1, tp2, tp3, confidence, data } = pipelineResult;

    const signal = {
      id: `sig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      symbol,
      type: 'SNIPER',
      tier: 'SNIPER',
      timestamp: Date.now(),
      entryPrice: entry,
      stopLoss,
      targets: { tp1, tp2, tp3 },
      riskReward: { rr1: 1, rr2: 2, rr3: 3 },
      confidence,
      status: 'HOT',
      metrics: {
        priceChange: data.priceChange,
        volumeSpike: data.volume,
        orderFlow: data.orderFlow,
        oiChange: data.oiChange,
        fakeOI: data.fakeOI
      },
      management: {
        slMovedToBreakeven: false,
        tpHits: []
      }
    };

    this.activeSignals.set(signal.symbol, signal);
    this.signalHistory.push(signal);
    addToActive(signal.symbol);

    dbCreateSignal(signal).catch(() => {});

    return signal;
  }

  formatSignal(signal) {
    const { targets, stopLoss, metrics } = signal;
    
    return `
🔥 SNIPER ENTRY #${signal.id}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${signal.entryPrice?.toFixed(6)}
🛑 STOP LOSS: ${stopLoss?.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TAKE PROFIT:
   TP1: ${targets?.tp1?.toFixed(6)} | 1R ✅
   TP2: ${targets?.tp2?.toFixed(6)} | 2R ✅
   TP3: ${targets?.tp3?.toFixed(6)} | 3R
━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 METRICS:
   Confidence: ${signal.confidence}%
   Volume: ${metrics?.volumeSpike?.toFixed(1)}x
   Order Flow: ${metrics?.orderFlow?.toFixed(2)}
   OI Change: ${metrics?.oiChange?.toFixed(2)}%
   Fake OI: ${metrics?.fakeOI?.toFixed(2)}
━━━━━━━━━━━━━━━━━━━━━━━━━━
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
    if (currentPrice <= signal.stopLoss) update.slHit = true;

    if (update.tpHit.length > 0) {
      update.tpHit.forEach(tp => {
        if (!signal.management.tpHits.includes(tp)) {
          signal.management.tpHits.push(tp);
        }
      });
    }

    if (signal.management.tpHits.includes(1) && !signal.management.slMovedToBreakeven) {
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
