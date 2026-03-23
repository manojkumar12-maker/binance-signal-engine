import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { notifier } from './notifiers/notificationManager.js';
import { apiServer } from './api/server.js';
import { autoTuner } from './engine/autoTuner.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { marketDataTracker } from './engine/marketDataTracker.js';
import { tradeLogger } from './engine/tradeLogger.js';
import { initDatabase, closeDatabase, createSignal as dbCreateSignal } from './database/db.js';
import { state, canTrigger, strongCanTrigger, addSignal, updateSignalStatus, isSymbolActive } from './state.js';
import { updateAdaptiveThresholds } from './engine/adaptiveFilter.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { oiTracker } from './engine/oiTracker.js';
import { fundingService } from './engine/fundingService.js';
import { oiCache, start, stop, getStats } from './engine/oiCache.js';

process.on('uncaughtException', (err) => {
  console.error('🔥 UNCAUGHT EXCEPTION:', err.message);
  console.error(err.stack);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('🔥 UNHANDLED REJECTION:', reason);
});

class SignalEngine {
  constructor() {
    this.stats = {
      signalsGenerated: 0,
      signalsByTier: { PRE_PUMP: 0, EARLY: 0, CONFIRMED: 0, SNIPER: 0 },
      symbolsMonitored: 0,
      startedAt: null
    };
    this.startTime = Date.now();
    this.warmupTime = 60 * 1000;
    this.warmupLogged = false;
  }

  isWarmedUp() {
    return Date.now() - this.startTime > this.warmupTime;
  }

  getWarmupStatus() {
    const elapsed = Date.now() - this.startTime;
    const remaining = Math.max(0, this.warmupTime - elapsed);
    return {
      isWarmedUp: this.isWarmedUp(),
      elapsed: Math.floor(elapsed / 1000),
      remaining: Math.floor(remaining / 1000)
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

    wsManager.onTrade((trade) => {
      marketDataTracker.handleTrade(trade);
      orderflowTracker.handleTrade(trade);
    });

    await wsManager.initialize();
    this.stats.symbolsMonitored = wsManager.symbols.length;

    pumpAnalyzer.initialize(wsManager.symbols);
    marketDataTracker.initialize(wsManager.symbols);
    orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
    start(wsManager.symbols);

    setInterval(() => {
      orderflowTracker.reset();
    }, 60000);

    setInterval(async () => {
      const topSymbols = wsManager.symbols.slice(0, 30);
      for (const symbol of topSymbols) {
        await oiTracker.fetch(symbol);
        await fundingService.fetch(symbol);
      }
      const oiStats = oiTracker.getStats();
      const updatedCount = Array.from(oiTracker.changeCache.values()).filter(v => v !== 0).length;
      if (updatedCount > 0) {
        console.log(`📊 OI Tracker: ${updatedCount} symbols with OI data`);
      }
    }, 15000);

    setInterval(() => {
      this.processCycleSignals();
      updateAdaptiveThresholds();
    }, 5000);

    setInterval(() => {
      this.showStats();
    }, 60000);

    setInterval(() => {
      const topSymbols = wsManager.symbols.slice(0, 5);
      const samples = topSymbols.map(sym => {
        const of = orderflowTracker.getOrderflow(sym);
        const oi = oiTracker.getChange(sym);
        const oiData = oiTracker.getOIData(sym);
        const ofData = orderflowTracker.getOrderflowData(sym);
        return `${sym}:OF=${of.toFixed(2)}(b=${ofData.buyVolume.toFixed(0)}s=${ofData.sellVolume.toFixed(0)})|OI=${oi.toFixed(1)}%(${oiData.trend})`;
      }).join(' | ');
      const oiStats = oiTracker.getStats();
      const cacheStats = getStats();
      console.log(`📊 DATA CHECK: ${samples}`);
      console.log(`📊 OI Cache: total=${cacheStats.total} withData=${cacheStats.withData} priority=${cacheStats.priorityCount} | OI Tracker: tracked=${oiStats.tracked} pos=${oiStats.positive} neg=${oiStats.negative} | OF: active=${orderflowTracker.getStats().activeSymbols}`);
    }, 20000);

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
    if (!this.isWarmedUp()) {
      if (!this.warmupLogged) {
        console.log(`⏳ Warming up... ${this.getWarmupStatus().remaining}s remaining`);
        this.warmupLogged = true;
      }
      return;
    } else if (this.warmupLogged) {
      console.log('✅ Warmup complete - engine active');
      this.warmupLogged = false;
    }

    const analysis = pumpAnalyzer.analyze(ticker);
    
    if (analysis && analysis.type) {
      if (!analysis.atr || isNaN(analysis.atr)) {
        return;
      }
      
      const of = analysis.orderflow?.ratio || 1;
      const oi = analysis.openInterest?.change || 0;
      if (of === 1 && oi === 0 && !analysis.orderflow) {
        return;
      }
      
      if (isSymbolActive(ticker.symbol)) {
        const updatedSignal = signalGenerator.updateSignal(ticker.symbol, ticker.price);
        if (updatedSignal && updatedSignal.status !== 'ACTIVE' && updatedSignal.status !== 'WATCHLIST') {
          console.log(`\n📊 ${ticker.symbol}: ${updatedSignal.status} at ${updatedSignal.closedPrice?.toFixed(6)}\n`);
          updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice);
          await apiServer.updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice);
        }
        return;
      }
      
      if (!this.shouldGenerateSignal(analysis)) {
        return;
      }
      
      if (!strongCanTrigger(ticker.symbol, 5 * 60 * 1000)) {
        return;
      }
      
      const signal = await signalGenerator.generateSignal(ticker.symbol, analysis);
      
      if (signal) {
        addSignal(signal);
        this.stats.signalsGenerated++;
        this.stats.signalsByTier[signal.tier]++;
        
        console.log(signalGenerator.formatSignal(signal));
        await notifier.sendSignal(signal);
        await apiServer.addSignal(signal);
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
║  🟣 PRE_PUMP: ${this.stats.signalsByTier.PRE_PUMP}  🔴 SNIPER: ${this.stats.signalsByTier.SNIPER}  🟢 CONFIRMED: ${this.stats.signalsByTier.CONFIRMED}  🟡 EARLY: ${this.stats.signalsByTier.EARLY}
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
        const tierEmoji = s.tier === 'SNIPER' ? '🔴' : s.tier === 'CONFIRMED' ? '🟢' : s.tier === 'PRE_PUMP' ? '🟣' : '🟡';
        console.log(`  ${tierEmoji} ${s.symbol} | Entry: ${s.entryPrice.toFixed(6)} | PnL: ${s.update?.unrealizedPnL || 0}%`);
      });
      console.log('');
    }
  }

  async processCycleSignals() {
    const signals = pumpAnalyzer.getCycleSignals();
    
    if (signals.length === 0) return;
    
    console.log(`\n🚀 Processing Top ${signals.length} signals:\n`);
    
    for (const analysis of signals) {
      if (!canTrigger(analysis.symbol, 5 * 60 * 1000)) {
        continue;
      }
      
      const signal = await signalGenerator.generateSignal(analysis.symbol, analysis);
      
      if (signal) {
        addSignal(signal);
        this.stats.signalsGenerated++;
        this.stats.signalsByTier[signal.tier]++;
        
        console.log(signalGenerator.formatSignal(signal));
        await notifier.sendSignal(signal);
        await apiServer.addSignal(signal);
      }
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
    stop();
    await closeDatabase();
    console.log('✅ Engine stopped');
  }
}

const engine = new SignalEngine();

global.engine = engine;
global.signalGenerator = signalGenerator;
global.autoTuner = autoTuner;
global.state = state;
global.marketDataTracker = marketDataTracker;
global.tradeLogger = tradeLogger;
global.oiCache = oiCache;

process.on('SIGINT', async () => {
  await engine.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await engine.stop();
  process.exit(0);
});

engine.start().catch(console.error);
