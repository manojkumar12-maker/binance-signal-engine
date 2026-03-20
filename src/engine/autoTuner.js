import { config } from '../../config/config.js';

class AutoTuner {
  constructor() {
    this.history = [];
    this.maxHistory = 50;
    this.baseParams = {
      scoreThreshold: config?.autoTuner?.baseScoreThreshold || 50,
      volumeSpike: config?.autoTuner?.baseVolumeSpike || 1.5,
      priceChange: config?.autoTuner?.basePriceChange || 1.5,
      relaxStep: 3,
      tightenStep: 5
    };
    this.params = { ...this.baseParams };
    this.noSignalCount = 0;
    this.lastTuneTime = Date.now();
    this.tuneInterval = (config?.autoTuner?.tuneIntervalMinutes || 5) * 60 * 1000;
  }

  recordTrade(result) {
    this.history.push(result);
    if (this.history.length > this.maxHistory) {
      this.history.shift();
    }
  }

  getWinRate() {
    if (this.history.length < 10) return null;
    const wins = this.history.filter(t => t === 'WIN').length;
    return (wins / this.history.length) * 100;
  }

  getTotalPnL() {
    if (this.history.length === 0) return 0;
    const wins = this.history.filter(t => t === 'WIN').length;
    const losses = this.history.filter(t => t === 'LOSS').length;
    return wins - losses;
  }

  tune() {
    const now = Date.now();
    if (now - this.lastTuneTime < this.tuneInterval) return;
    this.lastTuneTime = now;

    const winRate = this.getWinRate();
    const pnl = this.getTotalPnL();

    console.log(`\n🔧 Auto-Tuner: WinRate=${winRate ? winRate.toFixed(1) + '%' : 'N/A'} | History=${this.history.length}`);

    if (this.history.length < 5) {
      console.log('  📊 Collecting trade data...');
      return;
    }

    if (winRate !== null) {
      if (winRate < 40) {
        console.log('  🔻 Tightening filters (win rate low)');
        this.params.scoreThreshold += this.baseParams.tightenStep;
        this.params.volumeSpike = Math.min(this.params.volumeSpike + 0.3, 3.5);
        this.params.priceChange += 0.3;
      } else if (winRate > 65 && pnl > 3) {
        console.log('  🔥 Relaxing filters (high performance)');
        this.params.scoreThreshold -= this.baseParams.relaxStep;
        this.params.volumeSpike = Math.max(this.params.volumeSpike - 0.2, 1.2);
        this.params.priceChange = Math.max(this.params.priceChange - 0.2, 1.0);
      }
    }

    if (this.noSignalCount > 5) {
      console.log(`  ⚡ Relaxing filters (no signals for ${this.noSignalCount} checks)`);
      this.params.scoreThreshold = Math.max(this.params.scoreThreshold - 5, 25);
      this.params.volumeSpike = Math.max(this.params.volumeSpike - 0.3, 1.0);
      this.params.priceChange = Math.max(this.params.priceChange - 0.2, 0.5);
    }
    this.noSignalCount = 0;

    this.clampParams();
    console.log(`  📊 Current params: Score≥${this.params.scoreThreshold} | Vol≥${this.params.volumeSpike.toFixed(1)}x | Change≥${this.params.priceChange.toFixed(1)}%\n`);
  }

  clampParams() {
    this.params.scoreThreshold = Math.max(35, Math.min(80, this.params.scoreThreshold));
    this.params.volumeSpike = Math.max(1.0, Math.min(4.0, this.params.volumeSpike));
    this.params.priceChange = Math.max(0.8, Math.min(4.0, this.params.priceChange));
  }

  getParams() {
    return { ...this.params };
  }

  incrementNoSignal() {
    this.noSignalCount++;
  }

  resetToBase() {
    this.params = { ...this.baseParams };
    console.log('  🔄 Auto-tuner reset to base parameters');
  }

  getStats() {
    return {
      winRate: this.getWinRate(),
      totalTrades: this.history.length,
      wins: this.history.filter(t => t === 'WIN').length,
      losses: this.history.filter(t => t === 'LOSS').length,
      params: this.getParams()
    };
  }
}

export const autoTuner = new AutoTuner();
