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
console.log('PORT:', process.env.PORT || 8080);

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
    this.warmupTime = 30 * 1000;
    this.warmupLogged = false;
  }

  isWarmedUp() {
    return Date.now() - this.startTime > this.warmupTime;
  }

  async start() {
    console.log(`
╔══════════════════════════════════════════════╗
║     🚀 SNIPER SIGNAL ENGINE v5.0 🚀        
╠══════════════════════════════════════════════╣
║  🔴 SNIPER | 🟠 PUMP | 🟣 PRE_PUMP        ║
╚══════════════════════════════════════════════╝
    `);

    console.log('🔥 Starting API Server...');
    
    try {
      await apiServer.start();
      console.log('✅ API SERVER READY');
    } catch (e) {
      console.error('❌ API Server error:', e.message);
    }

    this.stats.startedAt = Date.now();
    
    initDatabase().catch(err => console.log('⚠️ DB init failed:', err.message));

    this.initEngine().catch(err => console.log('⚠️ Engine init error:', err.message));
  }

  async initEngine() {
    try {
      console.log('📡 Connecting to Binance...');
      
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
      console.log(`✅ Connected! Monitoring ${this.stats.symbolsMonitored} symbols`);

      pumpAnalyzer.initialize(wsManager.symbols);
      marketDataTracker.initialize(wsManager.symbols);
      orderBookAnalyzer.start(wsManager.symbols.slice(0, 100));
      await oiTracker.init(wsManager.symbols);
      setOITracker(oiTracker);

      setInterval(async () => {
        orderflowTracker.reset();
      }, 60000);

      setInterval(async () => {
        try {
          await oiTracker.runCycle();
        } catch (err) {
          console.error('OI fetch error:', err.message);
        }
      }, 5000);

      setInterval(() => {
        this.processCycleSignals();
      }, 5000);

      console.log('✅ Engine fully initialized!');
    } catch (e) {
      console.error('❌ Engine init error:', e.message);
    }
  }

  processTicker(ticker) {
    if (!this.isWarmedUp()) {
      if (!this.warmupLogged) {
        console.log(`⏳ Warming up... ${Math.ceil((this.warmupTime - (Date.now() - this.startTime))/1000)}s remaining`);
        this.warmupLogged = true;
      }
      return;
    }

    if (isSymbolActive(ticker.symbol)) {
      const updatedSignal = signalGenerator.updateSignal(ticker.symbol, ticker.price);
      if (updatedSignal && updatedSignal.status !== 'ACTIVE' && updatedSignal.status !== 'WATCHLIST') {
        console.log(`📊 ${ticker.symbol}: ${updatedSignal.status}`);
        
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

    const result = processSymbol(ticker.symbol, marketData);

    if (!result) return;

    if (result.type === 'ACCUMULATION') {
      emitSignal(result);
      return;
    }

    if (result.type === 'SNIPER') {
      if (!strongCanTrigger(ticker.symbol, 2 * 60 * 1000)) {
        return;
      }

      signalGenerator.generateSignal(ticker.symbol, result).then(signal => {
        if (signal) {
          addSignal(signal);
          this.stats.signalsGenerated++;
          this.stats.sniperSignals++;
          
          console.log(signalGenerator.formatSignal(signal));
          emitSignal(signal);
          notifier.sendSignal(signal).catch(() => {});
          apiServer.addSignal(signal).catch(() => {});
        }
      }).catch(() => {});
    }
  }

  processCycleSignals() {
    const topSymbols = wsManager.symbols.slice(0, 20);
    
    for (const symbol of topSymbols) {
      if (!canTrigger(symbol, 2 * 60 * 1000)) continue;
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
        atr: ticker.atr || 0
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

  async stop() {
    console.log('\n🛑 Stopping Engine...');
    wsManager.disconnect();
    orderBookAnalyzer.stop();
    oiTracker.reset();
    await closeDatabase();
    console.log('✅ Stopped');
  }
}

const engine = new SignalEngine();

global.engine = engine;
global.signalGenerator = signalGenerator;

process.on('SIGINT', async () => {
  await engine.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await engine.stop();
  process.exit(0);
});

console.log('🚀 Starting engine...');
engine.start().catch(err => {
  console.error('❌ FATAL:', err.message);
});

setTimeout(() => {
  console.log('✅ Process running...');
}, 3000);
