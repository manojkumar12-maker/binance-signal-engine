import { readFileSync, writeFileSync, existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, '../../data');
const TRADE_LOG_FILE = join(DATA_DIR, 'trade_log.json');

class TradeLogger {
  constructor() {
    this.tradeLog = [];
    this.loadLog();
  }

  loadLog() {
    try {
      if (existsSync(TRADE_LOG_FILE)) {
        const data = readFileSync(TRADE_LOG_FILE, 'utf8');
        this.tradeLog = JSON.parse(data);
        console.log(`📊 Trade Logger loaded ${this.tradeLog.length} historical trades`);
      }
    } catch (error) {
      this.tradeLog = [];
    }
  }

  saveLog() {
    try {
      writeFileSync(TRADE_LOG_FILE, JSON.stringify(this.tradeLog.slice(-1000), null, 2));
    } catch (error) {
      console.error('Failed to save trade log:', error);
    }
  }

  logTrade(signal, result, details = {}) {
    const trade = {
      id: `trade_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
      symbol: signal.symbol,
      tier: signal.type,
      confidence: signal.confidence,
      score: signal.score,
      volumeSpike: signal.volumeSpike || signal.metrics?.volumeSpike || 0,
      momentum: signal.momentum || signal.metrics?.momentum || 0,
      priceChange: signal.priceChange || signal.metrics?.priceChange || 0,
      orderflow: signal.orderflow || 1,
      oiChange: signal.oiChange || 0,
      fundingRate: signal.fundingRate || 0,
      entryPrice: signal.entryPrice,
      exitPrice: details.exitPrice || null,
      result,
      pnlPercent: details.pnlPercent || 0,
      exitReason: details.exitReason || 'UNKNOWN',
      timestamp: Date.now(),
      duration: details.duration || 0
    };

    this.tradeLog.push(trade);
    if (this.tradeLog.length > 1000) {
      this.tradeLog = this.tradeLog.slice(-1000);
    }

    this.saveLog();
    this.analyzeAndAdapt();

    return trade;
  }

  analyzePerformance() {
    if (this.tradeLog.length === 0) {
      return {
        totalTrades: 0,
        winRate: 0,
        avgWin: 0,
        avgLoss: 0,
        bestTier: null,
        avgConfidenceWin: 0,
        avgConfidenceLoss: 0
      };
    }

    const wins = this.tradeLog.filter(t => t.result === 'WIN');
    const losses = this.tradeLog.filter(t => t.result === 'LOSS');
    const breakeven = this.tradeLog.filter(t => t.result === 'BREAKEVEN');

    const avgWin = wins.length > 0 
      ? wins.reduce((sum, t) => sum + t.pnlPercent, 0) / wins.length 
      : 0;
    
    const avgLoss = losses.length > 0 
      ? Math.abs(losses.reduce((sum, t) => sum + t.pnlPercent, 0) / losses.length)
      : 0;

    const avgConfidenceWin = wins.length > 0
      ? wins.reduce((sum, t) => sum + t.confidence, 0) / wins.length
      : 0;

    const avgConfidenceLoss = losses.length > 0
      ? losses.reduce((sum, t) => sum + t.confidence, 0) / losses.length
      : 0;

    const tierStats = {};
    ['SNIPER', 'CONFIRMED', 'EARLY'].forEach(tier => {
      const tierTrades = this.tradeLog.filter(t => t.tier === tier);
      const tierWins = tierTrades.filter(t => t.result === 'WIN').length;
      tierStats[tier] = {
        total: tierTrades.length,
        wins: tierWins,
        winRate: tierTrades.length > 0 ? tierWins / tierTrades.length : 0,
        avgConfidence: tierTrades.length > 0 
          ? tierTrades.reduce((sum, t) => sum + t.confidence, 0) / tierTrades.length 
          : 0
      };
    });

    const bestTier = Object.entries(tierStats)
      .filter(([_, stats]) => stats.total >= 3)
      .sort((a, b) => b[1].winRate - a[1].winRate)[0]?.[0] || null;

    const exitReasons = {};
    this.tradeLog.forEach(t => {
      exitReasons[t.exitReason] = (exitReasons[t.exitReason] || 0) + 1;
    });

    return {
      totalTrades: this.tradeLog.length,
      wins: wins.length,
      losses: losses.length,
      breakeven: breakeven.length,
      winRate: this.tradeLog.length > 0 ? wins.length / this.tradeLog.length : 0,
      avgWin,
      avgLoss,
      bestTier,
      avgConfidenceWin,
      avgConfidenceLoss,
      tierStats,
      exitReasons,
      profitFactor: avgLoss > 0 ? avgWin / avgLoss : 0
    };
  }

  analyzeAndAdapt() {
    const stats = this.analyzePerformance();
    
    if (stats.totalTrades < 5) return null;

    const adaptations = [];

    if (stats.winRate < 0.4 && stats.totalTrades >= 10) {
      adaptations.push({
        type: 'LOW_WINRATE',
        action: 'INCREASE_CONFIDENCE_THRESHOLD',
        reason: `Win rate ${(stats.winRate * 100).toFixed(1)}% is below 40%`
      });
    }

    if (stats.winRate > 0.7 && stats.totalTrades >= 10) {
      adaptations.push({
        type: 'HIGH_WINRATE',
        action: 'RELAX_CONFIDENCE_THRESHOLD',
        reason: `Win rate ${(stats.winRate * 100).toFixed(1)}% is excellent`
      });
    }

    if (stats.avgConfidenceWin > 0 && stats.avgConfidenceLoss > 0) {
      const diff = stats.avgConfidenceWin - stats.avgConfidenceLoss;
      if (diff > 15) {
        adaptations.push({
          type: 'CONFIDENCE_CORRELATION',
          action: 'HIGH_CONFIDENCE_ONLY',
          reason: `Win confidence avg ${stats.avgConfidenceWin.toFixed(1)} vs Loss ${stats.avgConfidenceLoss.toFixed(1)}`
        });
      }
    }

    if (stats.bestTier) {
      adaptations.push({
        type: 'TIER_PERFORMANCE',
        action: `PREFER_${stats.bestTier}`,
        reason: `${stats.bestTier} has ${(stats.tierStats[stats.bestTier].winRate * 100).toFixed(1)}% win rate`
      });
    }

    Object.entries(stats.tierStats).forEach(([tier, tierStats]) => {
      if (tierStats.total >= 5 && tierStats.winRate < 0.3) {
        adaptations.push({
          type: 'POOR_TIER',
          action: `AVOID_${tier}`,
          reason: `${tier} has only ${(tierStats.winRate * 100).toFixed(1)}% win rate`
        });
      }
    });

    return {
      stats,
      adaptations,
      recommendation: this.getRecommendation(adaptations)
    };
  }

  getRecommendation(adaptations) {
    if (adaptations.length === 0) {
      return 'System performing well. Continue current settings.';
    }

    const highPriority = adaptations.filter(a => 
      a.type === 'LOW_WINRATE' || a.type === 'POOR_TIER'
    );

    if (highPriority.length > 0) {
      return `⚠️ ${highPriority.length} critical adaptations needed. Review recommended settings.`;
    }

    return `📊 ${adaptations.length} optimizations available. System stable.`;
  }

  shouldTrade(signal) {
    const analysis = this.analyzeAndAdapt();
    if (!analysis) return { trade: true, confidence: signal.confidence };

    let confidence = signal.confidence;
    const reasons = [];

    const lowWR = analysis.adaptations.find(a => a.type === 'LOW_WINRATE');
    if (lowWR) {
      confidence -= 10;
      reasons.push('Low historical winrate');
    }

    const avoidTier = analysis.adaptations.find(a => 
      a.type === 'POOR_TIER' && a.action === `AVOID_${signal.type}`
    );
    if (avoidTier) {
      confidence -= 20;
      reasons.push(`Avoiding ${signal.type} tier`);
    }

    const preferTier = analysis.adaptations.find(a => a.action === `PREFER_${signal.type}`);
    if (preferTier) {
      confidence += 10;
      reasons.push(`${signal.type} performs well historically`);
    }

    const highConf = analysis.adaptations.find(a => a.type === 'CONFIDENCE_CORRELATION');
    if (highConf && signal.confidence >= 70) {
      confidence += 5;
      reasons.push('High confidence signal');
    }

    return {
      trade: confidence >= 60 && !avoidTier,
      confidence,
      reasons,
      analysis
    };
  }

  getOptimalThresholds() {
    const stats = this.analyzePerformance();
    
    let sniperThreshold = 80;
    let confirmedThreshold = 65;
    let earlyThreshold = 45;

    if (stats.avgConfidenceWin > 0) {
      if (stats.avgConfidenceWin > 75) {
        sniperThreshold = Math.max(70, sniperThreshold - 5);
        confirmedThreshold = Math.max(55, confirmedThreshold - 5);
      }
      if (stats.avgConfidenceWin < 55) {
        sniperThreshold = Math.min(90, sniperThreshold + 10);
        confirmedThreshold = Math.min(75, confirmedThreshold + 10);
      }
    }

    const sniperStats = stats.tierStats.SNIPER;
    if (sniperStats && sniperStats.total >= 5) {
      if (sniperStats.winRate > 0.8) {
        sniperThreshold = Math.max(65, sniperThreshold - 10);
      } else if (sniperStats.winRate < 0.5) {
        sniperThreshold = Math.min(90, sniperThreshold + 10);
      }
    }

    return {
      SNIPER: sniperThreshold,
      CONFIRMED: confirmedThreshold,
      EARLY: earlyThreshold
    };
  }

  getRecentTrades(limit = 20) {
    return this.tradeLog.slice(-limit).reverse();
  }

  getStats() {
    return this.analyzePerformance();
  }

  exportData() {
    return {
      trades: this.tradeLog,
      exportDate: new Date().toISOString(),
      analysis: this.analyzePerformance()
    };
  }
}

export const tradeLogger = new TradeLogger();
