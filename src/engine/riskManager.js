import { config } from '../../config/config.js';

export class RiskManager {
  constructor() {
    this.settings = {
      defaultLeverage: 5,
      maxLeverage: 10,
      riskPerTradePercent: 0.1,
      maxRiskPerTrade: 2,
      dailyLossLimit: 5,
      maxOpenTrades: 2,
      minTPPercent: 0.5
    };
    
    this.dailyStats = {
      trades: 0,
      wins: 0,
      losses: 0,
      pnl: 0,
      startTime: Date.now()
    };
  }

  calculatePositionSize({ riskAmount, entry, stopLoss, leverage = this.settings.defaultLeverage }) {
    if (!entry || !stopLoss || entry <= 0 || stopLoss <= 0) {
      return null;
    }

    const riskPerUnit = Math.abs(entry - stopLoss);
    if (riskPerUnit === 0) return null;

    const quantity = (riskAmount * leverage) / riskPerUnit;
    
    if (isNaN(quantity) || !isFinite(quantity) || quantity <= 0) {
      return null;
    }

    const positionValue = quantity * entry;
    const actualRisk = riskPerUnit * quantity / leverage;

    return {
      quantity,
      positionValue,
      actualRisk,
      leverage,
      riskPerUnit
    };
  }

  calculateRiskAmount(accountBalance) {
    const riskAmount = accountBalance * this.settings.riskPerTradePercent;
    return Math.min(riskAmount, this.settings.maxRiskPerTrade);
  }

  shouldTakeTrade({ confidence, volumeSpike, priceChange, entry, stopLoss }) {
    const minTP = (this.settings.minTPPercent / 100) * entry;
    const tpDistance = Math.abs(entry - stopLoss);
    
    if (tpDistance < minTP) {
      return { allowed: false, reason: 'TP too small (fees would eat profit)' };
    }

    if (confidence < 60) {
      return { allowed: false, reason: 'Confidence too low' };
    }

    if (volumeSpike < 2) {
      return { allowed: false, reason: 'Volume too low' };
    }

    if (priceChange > 10) {
      return { allowed: false, reason: 'Move already too large' };
    }

    if (this.dailyStats.pnl <= -this.settings.dailyLossLimit) {
      return { allowed: false, reason: 'Daily loss limit reached' };
    }

    if (this.dailyStats.trades >= this.settings.maxOpenTrades) {
      return { allowed: false, reason: 'Max open trades reached' };
    }

    return { allowed: true };
  }

  calculateStopLoss(entry, atr, direction = 'LONG', multiplier = 1.5) {
    if (direction === 'LONG') {
      return entry - (atr * multiplier);
    } else {
      return entry + (atr * multiplier);
    }
  }

  calculateTakeProfits(entry, quantity, leverage = 5) {
    const profitTargets = [2, 4, 6];
    
    return profitTargets.map(target => {
      const priceMove = target / (quantity * leverage);
      return {
        target: target,
        price: entry + priceMove,
        pricePercent: (priceMove / entry * 100).toFixed(2)
      };
    });
  }

  updateDailyStats(result) {
    this.dailyStats.trades++;
    
    if (result.pnl > 0) {
      this.dailyStats.wins++;
      this.dailyStats.pnl += result.pnl;
    } else {
      this.dailyStats.losses++;
      this.dailyStats.pnl += result.pnl;
    }

    const hoursSinceStart = (Date.now() - this.dailyStats.startTime) / (1000 * 60 * 60);
    if (hoursSinceStart >= 24) {
      this.resetDailyStats();
    }
  }

  resetDailyStats() {
    this.dailyStats = {
      trades: 0,
      wins: 0,
      losses: 0,
      pnl: 0,
      startTime: Date.now()
    };
  }

  getStats() {
    const winRate = this.dailyStats.trades > 0 
      ? (this.dailyStats.wins / this.dailyStats.trades * 100).toFixed(1)
      : 0;
      
    return {
      ...this.dailyStats,
      winRate,
      dailyLossLimit: this.settings.dailyLossLimit,
      maxOpenTrades: this.settings.maxOpenTrades
    };
  }
}

export const riskManager = new RiskManager();
