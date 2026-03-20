import { config } from '../../config/config.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.signalId = 0;
  }

  generateSignal(analysis) {
    if (analysis.strength < 60) return null;

    const { ticker, priceChange, volumeSpike, momentum, factors, signals } = analysis;
    
    const signal = {
      id: ++this.signalId,
      symbol: ticker.symbol,
      type: 'LONG',
      timestamp: Date.now(),
      entryPrice: signals.entry,
      targets: {
        tp1: signals.tp1,
        tp2: signals.tp2,
        tp3: signals.tp3,
        tp4: signals.tp4,
        tp5: signals.tp5
      },
      stopLoss: signals.sl,
      riskReward: {
        tp1: (signals.tp1Risk / signals.slRisk).toFixed(2),
        tp2: (signals.tp2Risk / signals.slRisk).toFixed(2),
        tp3: (signals.tp3Risk / signals.slRisk).toFixed(2),
        tp4: (signals.tp4Risk / signals.slRisk).toFixed(2),
        tp5: (signals.tp5Risk / signals.slRisk).toFixed(2)
      },
      metrics: {
        priceChange: priceChange.toFixed(2),
        volumeSpike: volumeSpike.toFixed(1),
        momentum: momentum.toFixed(4),
        strength: analysis.strength
      },
      factors: factors,
      status: 'ACTIVE'
    };

    this.activeSignals.set(signal.symbol, signal);
    this.signalHistory.push(signal);

    return signal;
  }

  formatSignal(signal) {
    const { targets, stopLoss, metrics, riskReward, factors } = signal;
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 PUMP SIGNAL #${signal.id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${signal.entryPrice.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TAKE PROFIT LEVELS:
   TP1: ${targets.tp1.toFixed(6)} (+${config.riskManagement.tp1Percent}%) R/R: ${riskReward.tp1}
   TP2: ${targets.tp2.toFixed(6)} (+${config.riskManagement.tp2Percent}%) R/R: ${riskReward.tp2}
   TP3: ${targets.tp3.toFixed(6)} (+${config.riskManagement.tp3Percent}%) R/R: ${riskReward.tp3}
   TP4: ${targets.tp4.toFixed(6)} (+${config.riskManagement.tp4Percent}%) R/R: ${riskReward.tp4}
   TP5: ${targets.tp5.toFixed(6)} (+${config.riskManagement.tp5Percent}%) R/R: ${riskReward.tp5}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 STOP LOSS: ${stopLoss.toFixed(6)} (-${config.riskManagement.slPercent}%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 METRICS:
   Price Change: ${metrics.priceChange}%
   Volume Spike: ${metrics.volumeSpike}x
   Momentum: ${metrics.momentum}
   Signal Strength: ${metrics.strength}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 FACTORS:
${factors.map(f => `   • ${f}`).join('\n')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

    if (update.tpHit.length > 0 || update.slHit) {
      signal.status = update.slHit ? 'STOPPED_OUT' : `TP${Math.max(...update.tpHit)}_HIT`;
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
