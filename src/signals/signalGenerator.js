import { config } from '../../config/config.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.signalId = 0;
    this.accountBalance = config?.positionSizing?.accountSize || 10000;
  }

  generateSignal(analysis) {
    if (!analysis || !analysis.type) return null;

    const { type, score, priceChange, volumeSpike, momentum, factors, signals, atr, ticker, metadata } = analysis;
    
    const signal = {
      id: ++this.signalId,
      symbol: ticker.symbol,
      type,
      tier: type,
      timestamp: Date.now(),
      entryPrice: signals.entry,
      atr,
      targets: {
        tp1: signals.tp1,
        tp2: signals.tp2,
        tp3: signals.tp3,
        tp4: signals.tp4,
        tp5: signals.tp5
      },
      stopLoss: signals.sl,
      riskReward: {
        tp1: ((signals.tp1 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp2: ((signals.tp2 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp3: ((signals.tp3 - signals.entry) / (signals.entry - signals.sl)).toFixed(2)
      },
      metrics: {
        priceChange: priceChange.toFixed(2),
        volumeSpike: volumeSpike.toFixed(1),
        momentum: momentum?.toFixed(4) || '0',
        score
      },
      factors,
      metadata,
      status: type === 'SNIPER' ? 'HOT' : type === 'CONFIRMED' ? 'ACTIVE' : 'WATCHLIST',
      management: {
        slMovedToBreakeven: false,
        trailingActive: false,
        tpHits: []
      }
    };

    this.activeSignals.set(signal.symbol, signal);
    this.signalHistory.push(signal);

    return signal;
  }

  formatSignal(signal) {
    const { targets, stopLoss, metrics, riskReward, factors } = signal;
    
    const tierEmoji = signal.tier === 'SNIPER' ? '🔴' : signal.tier === 'CONFIRMED' ? '🟢' : '🟡';
    const tierLabel = signal.tier === 'SNIPER' ? 'HIGH ACCURACY' : signal.tier === 'CONFIRMED' ? 'CONFIRMED ENTRY' : 'EARLY WATCH';
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${tierEmoji} ${signal.tier} SIGNAL #${signal.id} - ${tierLabel}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${signal.entryPrice.toFixed(6)}
📏 ATR: ${signal.atr.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TAKE PROFIT LEVELS:
   TP1: ${targets.tp1.toFixed(6)} | R/R: ${riskReward.tp1}
   TP2: ${targets.tp2.toFixed(6)} | R/R: ${riskReward.tp2}
   TP3: ${targets.tp3.toFixed(6)} | R/R: ${riskReward.tp3}
   TP4: ${targets.tp4.toFixed(6)}
   TP5: ${targets.tp5.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 STOP LOSS: ${stopLoss.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 METRICS:
   Price Change: ${metrics.priceChange}%
   Volume Spike: ${metrics.volumeSpike}x
   Momentum: ${metrics.momentum}
   Score: ${metrics.score}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 FACTORS:
${factors.map(f => `   • ${f}`).join('\n')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;
  }

  updateSignal(symbol, currentPrice) {
    const signal = this.activeSignals.get(symbol);
    if (!signal) return null;

    const update = {
      currentPrice,
      unrealizedPnL: ((currentPrice - signal.entryPrice) / signal.entryPrice * 100).toFixed(2),
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
