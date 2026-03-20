import 'dotenv/config';
import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { notifier } from './notifiers/notificationManager.js';
import { apiServer } from './api/server.js';
import { autoTuner } from './engine/autoTuner.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { initDatabase, closeDatabase, createSignal as dbCreateSignal } from './database/db.js';
import { state, canTrigger, addSignal, updateSignalStatus } from './state.js';

class SignalEngine {
  constructor() {
    this.stats = {
      signalsGenerated: 0,
      signalsByTier: { EARLY: 0, CONFIRMED: 0, SNIPER: 0 },
      symbolsMonitored: 0,
      startedAt: null
    };
  }

  async start() {
    console.log(`
╔══════════════════════════════════════════════════════╗
║     🚀 BINANCE FUTURES SIGNAL ENGINE v3.0 🚀        ║
╠══════════════════════════════════════════════════════╣
║  🧠 Auto-Tuner | 📊 Orderbook Edge | 🔴 SNIPER     ║
║  🟢 CONFIRMED | 🟡 EARLY                            ║
╚══════════════════════════════════════════════════════╝
    `);

    await initDatabase();
    this.stats.startedAt = Date.now();
    await apiServer.start();

    wsManager.onTicker((ticker) => {
      this.processTicker(ticker);
    });

    await wsManager.initialize();
    this.stats.symbolsMonitored = wsManager.symbols.length;

    orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));

    setInterval(() => {
      this.showStats();
    }, 60000);

    console.log(`\n✅ Engine started! Monitoring ${this.stats.symbolsMonitored} symbols\n`);
  }

  shouldGenerateSignal(analysis) {
    const { type, priceChange, score } = analysis;
    
    const ENTRY_WINDOW = {
      EARLY: { min: 1, max: 15 },
      CONFIRMED: { min: 2, max: 12 },
      SNIPER: { min: 2.5, max: 10 }
    };
    
    const window = ENTRY_WINDOW[type];
    if (!window) return false;
    
    if (priceChange < window.min || priceChange > window.max) {
      return false;
    }
    
    return true;
  }

  async processTicker(ticker) {
    const analysis = pumpAnalyzer.analyze(ticker);
    
    if (analysis && analysis.type) {
      const existingSignal = signalGenerator.getActiveSignal(ticker.symbol);
      
      if (!existingSignal) {
        if (!this.shouldGenerateSignal(analysis)) {
          return;
        }
        
        if (!canTrigger(ticker.symbol, 5 * 60 * 1000)) {
          return;
        }
        
        const signal = await signalGenerator.generateSignal(analysis);
        
        if (signal) {
          addSignal(signal);
          this.stats.signalsGenerated++;
          this.stats.signalsByTier[signal.tier]++;
          
          if (signal.tier !== 'EARLY') {
            console.log(signalGenerator.formatSignal(signal));
            await notifier.sendSignal(signal);
            await apiServer.addSignal(signal);
          } else {
            console.log(`🟡 EARLY: ${signal.symbol} (Score: ${signal.metrics.score})`);
          }
        }
      } else {
        const updatedSignal = signalGenerator.updateSignal(ticker.symbol, ticker.price);
        if (updatedSignal && updatedSignal.status !== 'ACTIVE' && updatedSignal.status !== 'WATCHLIST') {
          console.log(`\n📊 ${ticker.symbol}: ${updatedSignal.status} at ${updatedSignal.closedPrice?.toFixed(6)}\n`);
          updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice);
          await apiServer.updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice);
        }
      }
    }
  }

  showStats() {
    const uptime = Date.now() - this.stats.startedAt;
    const activeSignals = signalGenerator.getActiveSignals();
    const tunerStats = autoTuner.getStats();
    
    console.clear();
    console.log(`
╔══════════════════════════════════════════════════════════════════╗
║        🚀 BINANCE FUTURES SIGNAL ENGINE v3.0 🚀              ║
╠══════════════════════════════════════════════════════════════════╣
║  📊 STATISTICS                                                   ║
║  ─────────────────────────────────────────────────────────────    ║
║  Uptime: ${this.formatUptime(uptime)}
║  Symbols: ${this.stats.symbolsMonitored}
║  Total Signals: ${this.stats.signalsGenerated}
║  🔴 SNIPER: ${this.stats.signalsByTier.SNIPER}  🟢 CONFIRMED: ${this.stats.signalsByTier.CONFIRMED}  🟡 EARLY: ${this.stats.signalsByTier.EARLY}
║  Active: ${activeSignals.length}
╠══════════════════════════════════════════════════════════════════╣
║  🧠 AUTO-TUNER                                                    ║
║  ─────────────────────────────────────────────────────────────    ║
║  Win Rate: ${tunerStats.winRate ? tunerStats.winRate.toFixed(1) + '%' : 'N/A'}  |  Trades: ${tunerStats.totalTrades}  |  PnL: ${tunerStats.wins - tunerStats.losses > 0 ? '+' : ''}${tunerStats.wins - tunerStats.losses}
║  Params: Score≥${tunerStats.params.scoreThreshold}  Vol≥${tunerStats.params.volumeSpike.toFixed(1)}x  Change≥${tunerStats.params.priceChange.toFixed(1)}%
╚══════════════════════════════════════════════════════════════════╝
    `);

    if (activeSignals.length > 0) {
      console.log('📈 ACTIVE SIGNALS:\n');
      activeSignals.forEach(s => {
        const tierEmoji = s.tier === 'SNIPER' ? '🔴' : s.tier === 'CONFIRMED' ? '🟢' : '🟡';
        console.log(`  ${tierEmoji} ${s.symbol} | Entry: ${s.entryPrice.toFixed(6)} | PnL: ${s.update?.unrealizedPnL || 0}%`);
      });
      console.log('');
    }
  }

  formatUptime(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`.padEnd(20, ' ');
  }

  async stop() {
    console.log('\n🛑 Stopping Signal Engine...');
    wsManager.disconnect();
    orderBookAnalyzer.stop();
    await closeDatabase();
    console.log('✅ Engine stopped');
  }
}

const engine = new SignalEngine();

global.engine = engine;
global.signalGenerator = signalGenerator;
global.autoTuner = autoTuner;
global.state = state;

process.on('SIGINT', async () => {
  await engine.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await engine.stop();
  process.exit(0);
});

engine.start().catch(console.error);
