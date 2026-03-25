import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { notifier } from './notifiers/notificationManager.js';
import { apiServer } from './api/server.js';
import { orderBookAnalyzer } from './engine/orderBookAnalyzer.js';
import { marketDataTracker } from './engine/marketDataTracker.js';
import { tradeLogger } from './engine/tradeLogger.js';
import { initDatabase, closeDatabase } from './database/db.js';
import { state, canTrigger, strongCanTrigger, addSignal, updateSignalStatus, isSymbolActive } from './state.js';
import { orderflowTracker } from './engine/orderflowTracker.js';
import { oiTracker, MAX_TRACKED } from './engine/oiTracker.js';
import { fundingService } from './engine/fundingService.js';
import { processSymbol, setOITracker, getState, updateBTCPrice, recordWin, recordLoss } from './engine/signalPipeline.js';
import { emitSignal, startDashboardServer } from './api/dashboardServer.js';

console.log('✅ All modules loaded');

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
      sniperSignals: 0,
      predictSignals: 0,
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
╔══════════════════════════════════════════════╗
║     🚀 SNIPER SIGNAL ENGINE v5.0 🚀        
╠══════════════════════════════════════════════╣
║  🔴 SNIPER | 🟠 PREDICT | ⚡ ACCUMULATION    ║
║  💎 Squeeze | Absorption | Memory System     ║
╚══════════════════════════════════════════════╝
    `);

    console.log('🔥 SERVER STARTING...');
    
    try {
      await apiServer.start();
      console.log('✅ HEALTHCHECK READY');
      startDashboardServer();
      console.log('✅ DASHBOARD READY on port 3001');
    } catch (e) {
      console.error('❌ API Server failed to start:', e.message);
    }

    this.stats.startedAt = Date.now();
    
    initDatabase().catch(err => console.log('⚠️ DB init failed, continuing:', err.message));

    this.initEngine().catch(err => console.log('⚠️ Engine init failed:', err.message));
  }

  async initEngine() {
    try {
      wsManager.onTicker((ticker) => {
        if (ticker.symbol === 'BTCUSDT') {
          updateBTCPrice(ticker.priceChange || 0);
        }
        this.processTicker(ticker);
      });

      wsManager.onTrade((trade) => {
        marketDataTracker.handleTrade(trade);
        orderflowTracker.handleTrade(trade);
        oiTracker.handleTrade(trade);
      });

      await wsManager.initialize();
      this.stats.symbolsMonitored = wsManager.symbols.length;

      pumpAnalyzer.initialize(wsManager.symbols);
      marketDataTracker.initialize(wsManager.symbols);
      orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
      await oiTracker.init(wsManager.symbols);
      setOITracker(oiTracker);

      setInterval(async () => {
        orderflowTracker.reset();
      }, 60000);

      setInterval(() => {
        const topSymbols = wsManager.symbols.slice(0, 10);
        for (const sym of topSymbols) {
          oiTracker.resetFlow(sym);
        }
      }, 60000);

      setInterval(async () => {
        const topSymbols = wsManager.symbols.slice(0, 5);
        for (const symbol of topSymbols) {
          await fundingService.fetch(symbol);
        }
      }, 10000);

      setInterval(async () => {
        try {
          await oiTracker.runCycle();
        } catch (err) {
          console.error('🔥 OI FETCH ERROR:', err.message);
        }
      }, 5000);

      setInterval(() => {
        this.processCycleSignals();
      }, 5000);

      setInterval(() => {
        this.showStats();
      }, 60000);

      console.log(`\n✅ Engine started! Monitoring ${this.stats.symbolsMonitored} symbols\n`);
    } catch (e) {
      console.error('❌ Engine initialization error:', e.message);
    }
  }

  processTicker(ticker) {
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

    if (isSymbolActive(ticker.symbol)) {
      const updatedSignal = signalGenerator.updateSignal(ticker.symbol, ticker.price);
      if (updatedSignal && updatedSignal.status !== 'ACTIVE' && updatedSignal.status !== 'WATCHLIST') {
        console.log(`\n📊 ${ticker.symbol}: ${updatedSignal.status} at ${updatedSignal.closedPrice?.toFixed(6)}\n`);
        
        if (updatedSignal.status?.startsWith('TP')) {
          recordWin(ticker.symbol);
        } else if (updatedSignal.status === 'STOPPED_OUT') {
          recordLoss(ticker.symbol);
        }
        
        updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice);
        apiServer.updateSignalStatus(ticker.symbol, updatedSignal.status, updatedSignal.closedPrice).catch(() => {});
      }
      return;
    }

    const analysis = pumpAnalyzer.analyze(ticker);
    if (!analysis || !analysis.symbol) {
      return;
    }

    const marketData = {
      symbol: ticker.symbol,
      priceChange: analysis.priceChange || 0,
      volume: analysis.volumeSpike || 1,
      orderFlow: analysis.orderflow?.ratio || 1,
      oiChange: analysis.openInterest?.change || 0,
      fakeOI: analysis.fakeOI || 0,
      priceAcceleration: analysis.acceleration || 0,
      momentum: analysis.momentum || 0,
      price: ticker.price,
      entryPrice: ticker.price,
      atr: analysis.atr || 0,
      tradeCount: analysis.tradeCount || 0,
      usdVolume: analysis.usdVolume || 0
    };

    // Debug: log key tickers occasionally
    if (Math.random() < 0.001 && marketData.volume > 2) {
      console.log(`📊 TICKER ${ticker.symbol}: PC=${marketData.priceChange.toFixed(1)}% Vol=${marketData.volume.toFixed(1)}x OF=${marketData.orderFlow.toFixed(2)} OI=${marketData.oiChange.toFixed(2)}% F=${marketData.fakeOI.toFixed(3)}`);
    }

    const result = processSymbol(ticker.symbol, marketData);

    if (!result) return;

    if (result.type === 'ACCUMULATION' || result.type === 'PREDICT') {
      emitSignal(result);
      return;
    }

    if (result.type === 'SNIPER') {
      if (!strongCanTrigger(ticker.symbol, 5 * 60 * 1000)) {
        return;
      }

      signalGenerator.generateSignal(ticker.symbol, result).then(signal => {
        if (signal) {
          addSignal(signal);
          this.stats.signalsGenerated++;
          this.stats.sniperSignals++;
          
          const squeezeEmoji = result.squeeze === 'SHORT_SQUEEZE' ? '💥' : '';
          console.log(signalGenerator.formatSignal(signal));
          console.log(`   ${squeezeEmoji} Squeeze: ${result.squeeze || 'N/A'} | Conf: ${result.confidence}%`);
          
          emitSignal(signal);
          notifier.sendSignal(signal).catch(() => {});
          apiServer.addSignal(signal).catch(() => {});
        }
      }).catch(() => {});
    }
  }

  showStats() {
    const uptime = Date.now() - this.stats.startedAt;
    const activeSignals = signalGenerator.getActiveSignals();
    
    console.clear();
    console.log(`
╔══════════════════════════════════════════════════════════════════╗
║        🚀 SNIPER SIGNAL ENGINE v5.0 🚀                      ║
╠══════════════════════════════════════════════════════════════════╣
║  📊 STATISTICS                                                   ║
║  ─────────────────────────────────────────────────────────────    ║
║  Uptime: ${this.formatUptime(uptime)}
║  Symbols: ${this.stats.symbolsMonitored}
║  Total SNIPER Signals: ${this.stats.sniperSignals}
║  Active: ${activeSignals.length}
╚══════════════════════════════════════════════════════════════════╝
    `);

    if (activeSignals.length > 0) {
      console.log('📈 ACTIVE SIGNALS:\n');
      activeSignals.forEach(s => {
        console.log(`  🔴 ${s.symbol} | Entry: ${s.entryPrice?.toFixed(6)} | PnL: ${s.update?.unrealizedPnL || 0}%`);
      });
      console.log('');
    }
  }

  processCycleSignals() {
    const topSymbols = wsManager.symbols.slice(0, 20);
    
    for (const symbol of topSymbols) {
      if (!canTrigger(symbol, 5 * 60 * 1000)) continue;
      if (isSymbolActive(symbol)) continue;

      const ticker = pumpAnalyzer.getTickerData?.(symbol);
      if (!ticker) continue;

      const marketData = {
        symbol,
        priceChange: ticker.priceChange || 0,
        volume: ticker.volumeSpike || 1,
        orderFlow: ticker.orderflow?.ratio || 1,
        oiChange: oiTracker.getChange(symbol) || 0,
        fakeOI: oiTracker.getFakeOI(symbol) || 0,
        priceAcceleration: ticker.acceleration || 0,
        momentum: ticker.momentum || 0,
        price: ticker.price,
        entryPrice: ticker.price,
        atr: ticker.atr,
        tradeCount: ticker.tradeCount || 0,
        usdVolume: ticker.usdVolume || 0
      };

      const result = processSymbol(symbol, marketData);

      if (result?.type === 'SNIPER') {
        signalGenerator.generateSignal(symbol, result).then(signal => {
          if (signal) {
            addSignal(signal);
            this.stats.signalsGenerated++;
            this.stats.sniperSignals++;
            
            console.log(signalGenerator.formatSignal(signal));
            notifier.sendSignal(signal).catch(() => {});
            apiServer.addSignal(signal).catch(() => {});
          }
        }).catch(() => {});
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
    oiTracker.reset();
    await closeDatabase();
    console.log('✅ Engine stopped');
  }
}

const engine = new SignalEngine();

global.engine = engine;
global.signalGenerator = signalGenerator;
global.state = state;
global.marketDataTracker = marketDataTracker;
global.tradeLogger = tradeLogger;
global.oiTracker = oiTracker;

process.on('SIGINT', async () => {
  await engine.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await engine.stop();
  process.exit(0);
});

process.on('exit', (code) => {
  console.log(`🔴 Process exiting with code: ${code}`);
});

console.log('🔰 Starting engine...');
engine.start().catch(err => {
  console.error('❌ FATAL: Engine start failed:', err);
  process.exit(1);
});

setTimeout(() => {
  console.log('🔰 Process still running after 5s...');
}, 5000);
