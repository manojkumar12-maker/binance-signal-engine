import { config } from '../../config/config.js';

class SignalGenerator {
  constructor() {
    this.activeSignals = new Map();
    this.signalHistory = [];
    this.signalId = 0;
    this.tradeStats = {
      totalTrades: 0,
      wins: 0,
      losses: 0,
      recentResults: [],
      conditionStats: {
        bos: { wins: 0, losses: 0 },
        sweep: { wins: 0, losses: 0 },
        volume: { wins: 0, losses: 0 },
        mtf: { wins: 0, losses: 0 }
      },
      regimeStats: {
        TREND: { wins: 0, losses: 0 },
        RANGE: { wins: 0, losses: 0 }
      }
    };
    this.accountBalance = config.positionSizing?.accountSize || 10000;
    this.scoreThreshold = config.signals.minScoreForEntry;
    this.volumeSpikeThreshold = config.signals.volumeSpikeThreshold;
  }

  generateSignal(analysis) {
    if (analysis.strength < this.scoreThreshold) return null;

    const { ticker, priceChange, volumeSpike, momentum, factors, signals, atr, metadata, 
            mtfAligned, mtfStrength, pullbackEntry, validation, regime } = analysis;
    
    const position = this.calculatePositionSize(signals.entry, signals.sl);
    const riskAmount = this.accountBalance * config.positionSizing.riskPercent;
    
    const signal = {
      id: ++this.signalId,
      symbol: ticker.symbol,
      type: 'LONG',
      timestamp: Date.now(),
      entryPrice: signals.entry,
      atr: atr,
      targets: {
        tp1: signals.tp1,
        tp2: signals.tp2,
        tp3: signals.tp3,
        tp4: signals.tp4,
        tp5: signals.tp5
      },
      stopLoss: signals.sl,
      initialStopLoss: signals.sl,
      positionSize: position,
      riskAmount: riskAmount,
      potentialReward: (signals.tp5 - signals.entry) * position,
      riskReward: {
        tp1: ((signals.tp1 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp2: ((signals.tp2 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp3: ((signals.tp3 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp4: ((signals.tp4 - signals.entry) / (signals.entry - signals.sl)).toFixed(2),
        tp5: ((signals.tp5 - signals.entry) / (signals.entry - signals.sl)).toFixed(2)
      },
      metrics: {
        priceChange: priceChange.toFixed(2),
        volumeSpike: volumeSpike.toFixed(1),
        momentum: momentum.toFixed(4),
        strength: analysis.strength,
        atr: atr.toFixed(6)
      },
      factors: factors,
      validation: validation,
      metadata: metadata,
      regime: regime,
      mtfAligned: mtfAligned,
      mtfStrength: mtfStrength,
      status: 'ACTIVE',
      management: {
        slMovedToBreakeven: false,
        trailingActive: false,
        tpHits: [],
        partialExits: [],
        earlyExitTriggered: false
      }
    };

    this.activeSignals.set(signal.symbol, signal);
    this.signalHistory.push(signal);

    return signal;
  }

  calculatePositionSize(entryPrice, stopLoss) {
    const { riskPercent, accountSize } = config.positionSizing;
    const riskAmount = accountSize * riskPercent;
    const riskPerUnit = Math.abs(entryPrice - stopLoss);
    return riskAmount / riskPerUnit;
  }

  formatSignal(signal) {
    const { targets, stopLoss, metrics, riskReward, factors, metadata, 
            positionSize, riskAmount, potentialReward, regime, mtfAligned } = signal;
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 ELITE SIGNAL #${signal.id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
🕐 Time: ${new Date(signal.timestamp).toLocaleString()}
🏷️ Regime: ${regime}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 ENTRY: ${signal.entryPrice.toFixed(6)}
📏 ATR: ${signal.atr.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 DYNAMIC TAKE PROFIT LEVELS:
   TP1: ${targets.tp1.toFixed(6)} | R/R: ${riskReward.tp1}
   TP2: ${targets.tp2.toFixed(6)} | R/R: ${riskReward.tp2}
   TP3: ${targets.tp3.toFixed(6)} | R/R: ${riskReward.tp3}
   TP4: ${targets.tp4.toFixed(6)} | R/R: ${riskReward.tp4}
   TP5: ${targets.tp5.toFixed(6)} | R/R: ${riskReward.tp5}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛑 STOP LOSS: ${stopLoss.toFixed(6)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💎 POSITION SIZING:
   Size: ${positionSize.toFixed(4)} units
   Risk: $${riskAmount.toFixed(2)} (${config.positionSizing.riskPercent * 100}%)
   Potential Reward: $${potentialReward.toFixed(2)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 METRICS:
   Price Change: ${metrics.priceChange}%
   Volume Spike: ${metrics.volumeSpike}x
   Momentum: ${metrics.momentum}
   Signal Strength: ${metrics.strength}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 VALIDATION:
   MTF Aligned: ${mtfAligned ? '✅' : '❌'}
   Break of Structure: ${metadata?.breakOfStructure ? '✅' : '❌'}
   Liquidity Sweep: ${metadata?.liquiditySweep ? '✅' : '❌'}
   RSI: ${metadata?.rsi?.toFixed(1)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 FACTORS:
${factors.map(f => `   • ${f}`).join('\n')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;
  }

  updateSignal(symbol, currentPrice, weaknessDetected = false) {
    const signal = this.activeSignals.get(symbol);
    if (!signal) return null;

    const update = {
      currentPrice,
      unrealizedPnL: ((currentPrice - signal.entryPrice) / signal.entryPrice * 100).toFixed(2),
      tpHit: [],
      slHit: false,
      slMoved: false,
      trailingActive: false,
      earlyExit: false
    };

    if (signal.regime === 'RANGE') {
      update.adjustedTPs = this.getAdjustedTPsForRange(signal);
    }

    this.applyTradeManagement(signal, currentPrice, update);

    if (currentPrice >= signal.targets.tp1) update.tpHit.push(1);
    if (currentPrice >= signal.targets.tp2) update.tpHit.push(2);
    if (currentPrice >= signal.targets.tp3) update.tpHit.push(3);
    if (currentPrice >= signal.targets.tp4) update.tpHit.push(4);
    if (currentPrice >= signal.targets.tp5) update.tpHit.push(5);
    if (currentPrice <= signal.stopLoss) update.slHit = true;

    if (weaknessDetected && !signal.management.earlyExitTriggered && update.tpHit.length >= 2) {
      signal.management.earlyExitTriggered = true;
      update.earlyExit = true;
      signal.status = 'EARLY_EXIT';
      signal.closedAt = Date.now();
      signal.closedPrice = currentPrice;
      this.activeSignals.delete(symbol);
      this.updateTradeStats(signal, false, 'Weakness Detected');
      return signal;
    }

    if (update.tpHit.length > 0) {
      update.tpHit.forEach(tp => {
        if (!signal.management.tpHits.includes(tp)) {
          signal.management.tpHits.push(tp);
        }
      });
    }

    if (update.tpHit.length > 0 || update.slHit) {
      if (update.slHit) {
        signal.status = 'STOPPED_OUT';
      } else {
        const maxTP = Math.max(...update.tpHit);
        if (update.tpHit.length === 5 || (maxTP >= 3 && update.tpHit.length >= 3)) {
          signal.status = `TP${maxTP}_HIT`;
        } else if (maxTP >= 1) {
          signal.status = `TP${maxTP}_HIT`;
        }
      }
      signal.closedAt = Date.now();
      signal.closedPrice = currentPrice;
      this.activeSignals.delete(symbol);
      this.updateTradeStats(signal, !update.slHit);
    }

    signal.update = update;
    return signal;
  }

  getAdjustedTPsForRange(signal) {
    return {
      tp1: signal.entryPrice + (signal.atr * 0.3),
      tp2: signal.entryPrice + (signal.atr * 0.5),
      tp3: signal.entryPrice + (signal.atr * 0.8)
    };
  }

  applyTradeManagement(signal, currentPrice, update) {
    const tp1Hit = currentPrice >= signal.targets.tp1;
    const tp3Hit = currentPrice >= signal.targets.tp3;

    if (tp1Hit && !signal.management.slMovedToBreakeven) {
      signal.stopLoss = signal.entryPrice;
      signal.management.slMovedToBreakeven = true;
      update.slMoved = true;
    }

    if (tp3Hit && !signal.management.trailingActive) {
      signal.management.trailingActive = true;
      update.trailingActive = true;
    }

    if (signal.management.trailingActive) {
      const trailingSL = currentPrice - (config.tradeManagement.trailingATRMultiplier * signal.atr);
      if (trailingSL > signal.stopLoss) {
        signal.stopLoss = trailingSL;
        update.slMoved = true;
      }
    }
  }

  updateTradeStats(signal, won, reason = '') {
    this.tradeStats.totalTrades++;
    
    if (won) {
      this.tradeStats.wins++;
      this.tradeStats.recentResults.push('win');
    } else {
      this.tradeStats.losses++;
      this.tradeStats.recentResults.push('loss');
    }

    if (this.tradeStats.recentResults.length > config.feedbackLoop.sampleSize) {
      this.tradeStats.recentResults.shift();
    }

    if (signal.validation) {
      if (signal.validation.bos) {
        won ? this.tradeStats.conditionStats.bos.wins++ : this.tradeStats.conditionStats.bos.losses++;
      }
      if (signal.validation.sweep) {
        won ? this.tradeStats.conditionStats.sweep.wins++ : this.tradeStats.conditionStats.sweep.losses++;
      }
      if (signal.validation.volume) {
        won ? this.tradeStats.conditionStats.volume.wins++ : this.tradeStats.conditionStats.volume.losses++;
      }
      if (signal.mtfAligned) {
        won ? this.tradeStats.conditionStats.mtf.wins++ : this.tradeStats.conditionStats.mtf.losses++;
      }
    }

    if (signal.regime) {
      won ? this.tradeStats.regimeStats[signal.regime].wins++ : this.tradeStats.regimeStats[signal.regime].losses++;
    }

    if (config.feedbackLoop.enabled) {
      this.adjustThresholds();
    }
  }

  adjustThresholds() {
    const recentResults = this.tradeStats.recentResults.slice(-config.feedbackLoop.sampleSize);
    if (recentResults.length < 10) return;

    const winRate = recentResults.filter(r => r === 'win').length / recentResults.length;
    
    if (winRate < config.feedbackLoop.winRateThresholdLow) {
      this.scoreThreshold = Math.min(90, this.scoreThreshold + config.feedbackLoop.adjustmentStep);
      this.volumeSpikeThreshold = Math.min(5, this.volumeSpikeThreshold + 0.5);
    } else if (winRate > config.feedbackLoop.winRateThresholdHigh) {
      this.scoreThreshold = Math.max(70, this.scoreThreshold - 2);
      this.volumeSpikeThreshold = Math.max(2.5, this.volumeSpikeThreshold - 0.25);
    }

    this.adjustConditionWeights();
  }

  adjustConditionWeights() {
    const { bos, sweep, volume, mtf } = this.tradeStats.conditionStats;
    
    const conditions = [
      { name: 'bos', stats: bos, weightKey: 'bosWeight' },
      { name: 'sweep', stats: sweep, weightKey: 'liquiditySweepWeight' },
      { name: 'volume', stats: volume, weightKey: 'volumeSpikeWeight' }
    ];
    
    for (const cond of conditions) {
      const total = cond.stats.wins + cond.stats.losses;
      if (total >= 10) {
        const winRate = cond.stats.wins / total;
        if (winRate < 0.5) {
          config.smartScoring[cond.weightKey] = Math.max(5, config.smartScoring[cond.weightKey] - 2);
        }
      }
    }
  }

  getAdaptiveThresholds() {
    return {
      scoreThreshold: this.scoreThreshold,
      volumeSpikeThreshold: this.volumeSpikeThreshold,
      currentWinRate: this.tradeStats.recentResults.length > 0 
        ? (this.tradeStats.recentResults.filter(r => r === 'win').length / this.tradeStats.recentResults.length * 100).toFixed(1) + '%'
        : 'N/A'
    };
  }

  getPerformanceDashboard() {
    const total = this.tradeStats.wins + this.tradeStats.losses;
    const winRate = total > 0 ? (this.tradeStats.wins / total * 100).toFixed(1) + '%' : 'N/A';
    
    const avgWin = this.signalHistory
      .filter(s => s.status !== 'ACTIVE' && s.status !== 'STOPPED_OUT')
      .slice(-20)
      .reduce((sum, s) => {
        const pnl = ((s.closedPrice - s.entryPrice) / s.entryPrice * 100);
        return sum + pnl;
      }, 0) / Math.max(1, this.signalHistory.filter(s => s.status !== 'ACTIVE' && s.status !== 'STOPPED_OUT').slice(-20).length);
    
    const avgLoss = this.signalHistory
      .filter(s => s.status === 'STOPPED_OUT')
      .slice(-20)
      .reduce((sum, s) => {
        const pnl = ((s.closedPrice - s.entryPrice) / s.entryPrice * 100);
        return sum + pnl;
      }, 0) / Math.max(1, this.signalHistory.filter(s => s.status === 'STOPPED_OUT').slice(-20).length);

    const conditionWinRates = {};
    for (const [condition, stats] of Object.entries(this.tradeStats.conditionStats)) {
      const condTotal = stats.wins + stats.losses;
      conditionWinRates[condition] = condTotal > 0 
        ? `${(stats.wins / condTotal * 100).toFixed(1)}% (${condTotal})`
        : 'N/A';
    }

    const regimeStats = {};
    for (const [regime, stats] of Object.entries(this.tradeStats.regimeStats)) {
      const regimeTotal = stats.wins + stats.losses;
      regimeStats[regime] = regimeTotal > 0 
        ? `${(stats.wins / regimeTotal * 100).toFixed(1)}% (${regimeTotal})`
        : 'N/A';
    }

    const recentSignals = this.signalHistory.slice(-10).map(s => ({
      id: s.id,
      symbol: s.symbol,
      status: s.status,
      pnl: s.closedPrice ? ((s.closedPrice - s.entryPrice) / s.entryPrice * 100).toFixed(2) + '%' : 'Open'
    }));

    return {
      overview: {
        totalTrades: this.tradeStats.totalTrades,
        wins: this.tradeStats.wins,
        losses: this.tradeStats.losses,
        winRate,
        avgWin: avgWin > 0 ? avgWin.toFixed(2) + '%' : 'N/A',
        avgLoss: avgLoss < 0 ? avgLoss.toFixed(2) + '%' : 'N/A',
        expectancy: avgWin > 0 && avgLoss < 0 
          ? ((winRate / 100 * avgWin) - ((1 - parseFloat(winRate) / 100) * Math.abs(avgLoss))).toFixed(2) + '%'
          : 'N/A'
      },
      adaptiveThresholds: this.getAdaptiveThresholds(),
      conditionPerformance: conditionWinRates,
      regimePerformance: regimeStats,
      recentSignals,
      activeSignals: this.activeSignals.size
    };
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

  getTradeStats() {
    return {
      ...this.tradeStats,
      winRate: this.tradeStats.totalTrades > 0 
        ? ((this.tradeStats.wins / this.tradeStats.totalTrades) * 100).toFixed(1) + '%'
        : 'N/A',
      adaptiveThresholds: this.getAdaptiveThresholds()
    };
  }

  updateAccountBalance(newBalance) {
    this.accountBalance = newBalance;
  }

  getAccountBalance() {
    return this.accountBalance;
  }
}

export const signalGenerator = new SignalGenerator();
