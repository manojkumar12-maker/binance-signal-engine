export class SignalRankingEngine {
  constructor() {
    this.recentSignals = new Map();
    this.maxActive = 10;
    this.CLEANUP_INTERVAL = 300000;
    this.lastCleanup = Date.now();
  }

  calculateRankScore(d) {
    const conf = d.confidence || 0;
    const volumeScore = Math.min((d.volumeSpike || 0) * 20, 100);
    const priceScore = Math.min((d.priceChange || 0) * 10, 100);
    const ofScore = Math.min((d.orderflow || 1) * 30, 100);
    const momentumScore = Math.min(Math.abs(d.momentum || 0) * 1000, 100);
    const confluenceScore = ((d.confluence || 0) / 5) * 100;

    const finalScore =
      conf * 0.30 +
      volumeScore * 0.20 +
      priceScore * 0.15 +
      ofScore * 0.15 +
      momentumScore * 0.10 +
      confluenceScore * 0.10;

    return Math.min(100, Math.max(0, finalScore));
  }

  applyBoost(score, d) {
    let boosted = score;

    if ((d.orderflow || 1) >= 2.5 && (d.volumeSpike || 0) >= 4) {
      boosted += 10;
    }

    if ((d.momentum || 0) > 0.05) {
      boosted += 5;
    }

    if ((d.priceChange || 0) > 6) {
      boosted += 5;
    }

    if ((d.prePump?.prePumpScore || 0) >= 5) {
      boosted += 5;
    }

    return Math.min(100, boosted);
  }

  isValidEarlySignal(d) {
    if ((d.priceChange || 0) < 3) return false;
    if ((d.volumeSpike || 0) < 3) return false;
    if ((d.orderflow || 1) < 1.5) return false;
    if ((d.momentum || 0) <= 0) return false;
    if ((d.confidence || 0) < 55) return false;
    return true;
  }

  isDuplicate(symbol) {
    const now = Date.now();
    const last = this.recentSignals.get(symbol);

    if (last && now - last < 300000) {
      return true;
    }

    this.recentSignals.set(symbol, now);

    if (now - this.lastCleanup > this.CLEANUP_INTERVAL) {
      for (const [sym, time] of this.recentSignals) {
        if (now - time > 300000) {
          this.recentSignals.delete(sym);
        }
      }
      this.lastCleanup = now;
    }

    return false;
  }

  processSignals(rawSignals) {
    if (!rawSignals || rawSignals.length === 0) return [];

    const ranked = [];

    for (const s of rawSignals) {
      if (!this.isValidEarlySignal(s)) continue;

      let score = this.calculateRankScore(s);
      score = this.applyBoost(score, s);

      if (score < 60) continue;

      s.rankScore = score;
      ranked.push(s);
    }

    ranked.sort((a, b) => (b.rankScore || 0) - (a.rankScore || 0));

    const limited = {
      sniper: ranked.filter(s => s.type === 'SNIPER').slice(0, 2),
      confirmed: ranked.filter(s => s.type === 'CONFIRMED').slice(0, 3),
      prepump: ranked.filter(s => s.type === 'PRE_PUMP').slice(0, 2),
      early: ranked.filter(s => s.type === 'EARLY').slice(0, 2),
    };

    const result = [
      ...limited.sniper,
      ...limited.confirmed,
      ...limited.prepump,
      ...limited.early
    ];

    const bestPerSymbol = new Map();
    for (const s of result) {
      const existing = bestPerSymbol.get(s.symbol);
      if (!existing || (s.rankScore || 0) > (existing.rankScore || 0)) {
        bestPerSymbol.set(s.symbol, s);
      }
    }

    return Array.from(bestPerSymbol.values());
  }

  getQuality(conf) {
    if (conf >= 70) return 'EXCELLENT';
    if (conf >= 60) return 'GOOD';
    if (conf >= 50) return 'OK';
    return 'WEAK';
  }

  getStats() {
    return {
      trackedSymbols: this.recentSignals.size,
      maxActive: this.maxActive
    };
  }
}

export const signalRankingEngine = new SignalRankingEngine();
