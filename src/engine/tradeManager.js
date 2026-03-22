import { riskManager } from './riskManager.js';

export class TradeManager {
  constructor() {
    this.activeTrades = new Map();
    this.tradeHistory = [];
    this.defaultLeverage = 5;
  }

  createTrade({ symbol, entry, stopLoss, takeProfits, quantity, confidence, tier }) {
    const trade = {
      id: `trade_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      symbol,
      entry,
      stopLoss,
      currentPrice: entry,
      quantity,
      leverage: this.defaultLeverage,
      confidence,
      tier,
      status: 'OPEN',
      entryTime: Date.now(),
      tpHits: [],
      partialExits: [],
      stopLossMoved: false,
      trailingActive: false,
      trailingDistance: 0,
      highestPrice: entry,
      lowestPrice: entry
    };

    if (takeProfits && Array.isArray(takeProfits)) {
      trade.tpLevels = takeProfits.map((tp, index) => ({
        level: index + 1,
        price: tp.price,
        target: tp.target,
        hit: false,
        closedPercent: index === 0 ? 0.3 : index === 1 ? 0.3 : 0.4
      }));
    }

    this.activeTrades.set(symbol, trade);
    
    return trade;
  }

  updateTrade(symbol, currentPrice) {
    const trade = this.activeTrades.get(symbol);
    if (!trade) return null;

    trade.currentPrice = currentPrice;
    
    if (trade.direction === 'LONG') {
      trade.highestPrice = Math.max(trade.highestPrice, currentPrice);
    } else {
      trade.lowestPrice = Math.min(trade.lowestPrice, currentPrice);
    }

    const update = this.checkTradeProgress(trade);
    
    if (update.status === 'CLOSED') {
      this.closeTrade(symbol, update.reason, currentPrice);
    }

    return { trade, update };
  }

  checkTradeProgress(trade) {
    const update = {
      status: 'ACTIVE',
      reason: null,
      pnl: 0,
      pnlPercent: 0,
      tpHit: [],
      slHit: false,
      partialClose: null
    };

    update.pnl = (trade.currentPrice - trade.entry) * trade.quantity * trade.leverage;
    update.pnlPercent = ((trade.currentPrice - trade.entry) / trade.entry * 100 * trade.leverage).toFixed(2);

    if (trade.tpLevels) {
      for (const tp of trade.tpLevels) {
        if (!tp.hit && trade.currentPrice >= tp.price) {
          tp.hit = true;
          update.tpHit.push(tp.level);
          update.partialClose = {
            level: tp.level,
            percent: tp.closedPercent,
            price: tp.price
          };

          if (tp.level === 1 && !trade.stopLossMoved) {
            trade.stopLoss = trade.entry;
            trade.stopLossMoved = true;
          } else if (tp.level === 2) {
            trade.stopLoss = trade.tpLevels[0].price;
          }
        }
      }
    }

    if (trade.currentPrice <= trade.stopLoss) {
      update.status = 'CLOSED';
      update.slHit = true;
      update.reason = 'STOP_LOSS';
      update.pnl = (trade.stopLoss - trade.entry) * trade.quantity * trade.leverage;
    }

    return update;
  }

  closeTrade(symbol, reason, price) {
    const trade = this.activeTrades.get(symbol);
    if (!trade) return null;

    trade.status = 'CLOSED';
    trade.closeTime = Date.now();
    trade.closePrice = price;
    trade.closeReason = reason;

    const pnl = (price - trade.entry) * trade.quantity * trade.leverage;
    const pnlPercent = ((price - trade.entry) / trade.entry * 100 * trade.leverage).toFixed(2);

    const result = {
      ...trade,
      pnl,
      pnlPercent
    };

    this.tradeHistory.push(result);
    this.activeTrades.delete(symbol);
    
    riskManager.updateDailyStats({ pnl, won: pnl > 0 });

    if (this.tradeHistory.length > 1000) {
      this.tradeHistory = this.tradeHistory.slice(-500);
    }

    return result;
  }

  getActiveTrades() {
    return Array.from(this.activeTrades.values());
  }

  getTrade(symbol) {
    return this.activeTrades.get(symbol);
  }

  getTradeHistory(limit = 100) {
    return this.tradeHistory.slice(-limit);
  }

  getStats() {
    const history = this.tradeHistory;
    const totalTrades = history.length;
    const wins = history.filter(t => t.pnl > 0).length;
    const losses = history.filter(t => t.pnl <= 0).length;
    const winRate = totalTrades > 0 ? (wins / totalTrades * 100).toFixed(1) : 0;
    const totalPnl = history.reduce((sum, t) => sum + t.pnl, 0);
    const avgWin = wins > 0 ? history.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / wins : 0;
    const avgLoss = losses > 0 ? history.filter(t => t.pnl <= 0).reduce((sum, t) => sum + t.pnl, 0) / losses : 0;

    return {
      totalTrades,
      wins,
      losses,
      winRate,
      totalPnl: totalPnl.toFixed(2),
      avgWin: avgWin.toFixed(2),
      avgLoss: avgLoss.toFixed(2),
      profitFactor: losses > 0 && avgLoss !== 0 ? Math.abs(avgWin / avgLoss).toFixed(2) : 'N/A'
    };
  }

  cancelTrade(symbol) {
    const trade = this.activeTrades.get(symbol);
    if (trade) {
      trade.status = 'CANCELLED';
      this.activeTrades.delete(symbol);
      return true;
    }
    return false;
  }
}

export const tradeManager = new TradeManager();
