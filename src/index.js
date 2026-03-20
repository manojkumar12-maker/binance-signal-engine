import { wsManager } from './websocket/binanceWS.js';
import { pumpAnalyzer } from './analyzer/pumpAnalyzer.js';
import { signalGenerator } from './signals/signalGenerator.js';
import { notifier } from './notifiers/notificationManager.js';

class SignalEngine {
  constructor() {
    this.stats = {
      signalsGenerated: 0,
      symbolsMonitored: 0,
      startedAt: null
    };
  }

  async start() {
    console.log(`
╔══════════════════════════════════════════════════════╗
║       🚀 BINANCE FUTURES PUMP SIGNAL ENGINE 🚀       ║
╠══════════════════════════════════════════════════════╣
║  Monitoring all Binance USDT Perpetual Futures        ║
║  Real-time pump detection with TP1-TP5 signals        ║
╚══════════════════════════════════════════════════════╝
    `);

    this.stats.startedAt = Date.now();

    wsManager.onTicker((ticker) => {
      this.processTicker(ticker);
    });

    await wsManager.initialize();
    
    this.stats.symbolsMonitored = wsManager.symbols.length;

    setInterval(() => {
      this.showStats();
    }, 60000);

    console.log(`\n✅ Engine started! Monitoring ${this.stats.symbolsMonitored} symbols\n`);
  }

  processTicker(ticker) {
    const analysis = pumpAnalyzer.analyze(ticker);
    
    if (analysis && analysis.strength >= 60) {
      const existingSignal = signalGenerator.getActiveSignal(ticker.symbol);
      
      if (!existingSignal) {
        const signal = signalGenerator.generateSignal(analysis);
        
        if (signal) {
          this.stats.signalsGenerated++;
          console.log(signalGenerator.formatSignal(signal));
          notifier.sendSignal(signal);
        }
      } else {
        const updatedSignal = signalGenerator.updateSignal(ticker.symbol, ticker.price);
        if (updatedSignal) {
          notifier.sendUpdate(updatedSignal);
        }
      }
    }
  }

  showStats() {
    const uptime = Date.now() - this.stats.startedAt;
    const activeSignals = signalGenerator.getActiveSignals();
    
    console.clear();
    console.log(`
╔══════════════════════════════════════════════════════╗
║       🚀 BINANCE FUTURES PUMP SIGNAL ENGINE 🚀       ║
╠══════════════════════════════════════════════════════╣
║  📊 STATISTICS                                        ║
║  ───────────────────────────────────────────          ║
║  Uptime: ${this.formatUptime(uptime)}
║  Symbols Monitored: ${this.stats.symbolsMonitored}
║  Signals Generated: ${this.stats.signalsGenerated}
║  Active Signals: ${activeSignals.length}
╚══════════════════════════════════════════════════════╝
    `);

    if (activeSignals.length > 0) {
      console.log('📈 ACTIVE SIGNALS:\n');
      activeSignals.forEach(signal => {
        console.log(`  ${signal.symbol} - Entry: ${signal.entryPrice.toFixed(6)} - Status: ${signal.status}`);
      });
      console.log('');
    }
  }

  formatUptime(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`.padEnd(20, ' ');
  }

  stop() {
    console.log('\n🛑 Stopping Signal Engine...');
    wsManager.disconnect();
    console.log('✅ Engine stopped');
  }
}

const engine = new SignalEngine();

process.on('SIGINT', () => {
  engine.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  engine.stop();
  process.exit(0);
});

engine.start().catch(console.error);
