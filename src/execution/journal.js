import fs from 'fs';
import { state } from '../core/state.js';

const JOURNAL_FILE = 'trades.json';

export function logTrade(trade) {
  const entry = {
    ...trade,
    time: new Date().toISOString(),
    timestamp: Date.now()
  };
  
  state.tradeHistory.push(entry);
  
  if (state.tradeHistory.length > 500) {
    state.tradeHistory.shift();
  }
  
  try {
    let data = [];
    if (fs.existsSync(JOURNAL_FILE)) {
      data = JSON.parse(fs.readFileSync(JOURNAL_FILE));
    }
    
    data.push(entry);
    
    fs.writeFileSync(JOURNAL_FILE, JSON.stringify(data, null, 2));
  } catch (err) {
    console.error('❌ Journal write error:', err.message);
  }
  
  return entry;
}

export function logOpenPosition(position) {
  return logTrade({
    ...position,
    event: 'OPEN',
    result: 'OPEN'
  });
}

export function logClosePosition(position, result, pnl) {
  return logTrade({
    ...position,
    event: 'CLOSE',
    result,
    pnl,
    closedAt: new Date().toISOString()
  });
}

export function getTradeHistory(limit = 50) {
  return state.tradeHistory.slice(-limit);
}

export function getTradeStats() {
  const history = state.tradeHistory;
  
  if (history.length === 0) {
    return {
      total: 0,
      wins: 0,
      losses: 0,
      winRate: 0,
      avgPnl: 0
    };
  }
  
  const closed = history.filter(t => t.result !== 'OPEN');
  const wins = closed.filter(t => t.pnl > 0).length;
  const losses = closed.filter(t => t.pnl <= 0).length;
  const totalPnl = closed.reduce((sum, t) => sum + (t.pnl || 0), 0);
  
  return {
    total: history.length,
    wins,
    losses,
    winRate: closed.length > 0 ? wins / closed.length : 0,
    avgPnl: closed.length > 0 ? totalPnl / closed.length : 0
  };
}

export function clearJournal() {
  state.tradeHistory = [];
  if (fs.existsSync(JOURNAL_FILE)) {
    fs.unlinkSync(JOURNAL_FILE);
  }
}
