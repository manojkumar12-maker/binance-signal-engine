export class SignalRankingEngine {
  constructor() {
    this.recentSignals = new Map();
    this.maxActive = 10;
    this.CLEANUP_INTERVAL = 300000;
    this.lastCleanup = Date.now();
  }

  getOIState(priceChange, oiChange) {
    const pc = priceChange || 0;
    const oi = oiChange || 0;

    if (pc > 0 && oi > 0.3) return 'STRONG_LONG';
    if (pc > 0 && oi < -0.3) return 'SHORT_COVERING';
    if (pc < 0 && oi > 0.3) return 'STRONG_SHORT';
    if (pc < 0 && oi < -0.3) return 'LONG_EXIT';
    return 'NEUTRAL';
  }

  getOIScore(d) {
    const state = this.getOIState(d.priceChange, d.oiChange);

    switch (state) {
      case 'STRONG_LONG': return 100;
      case 'STRONG_SHORT': return 100;
      case 'SHORT_COVERING': return 0;
      case 'LONG_EXIT': return 0;
      default: return 0;
    }
  }

  isOIValid(d) {
    const state = this.getOIState(d.priceChange, d.oiChange);
    if (state === 'SHORT_COVERING') return false;
    if (state === 'LONG_EXIT') return false;
    return true;
  }

  isOISniper(d) {
    return (
      (d.orderflow || 1) >= 2.5 &&
      (d.volumeSpike || 0) >= 4 &&
      (d.priceChange || 0) >= 4 &&
      (d.oiChange || 0) > 1.5 &&
      (d.momentum || 0) > 0.04
    );
  }

  isValidEarlySignal(d) {
    return true;
  }

  calculateRankScore(d) {
    const conf = d.confidence || 0;
    const volumeScore = Math.min((d.volumeSpike || 0) * 20, 100);
    const priceScore = Math.min(Math.abs(d.priceChange || 0) * 10, 100);
    const ofScore = Math.min((d.orderflow || 1) * 30, 100);
    const momentumScore = Math.min(Math.abs(d.momentum || 0) * 1000, 100);
    const confluenceScore = ((d.confluence || 0) / 5) * 100;
    const oiScore = this.getOIScore(d);

    const finalScore =
      conf * 0.25 +
      volumeScore * 0.20 +
      priceScore * 0.15 +
      ofScore * 0.15 +
      momentumScore * 0.05 +
      confluenceScore * 0.05 +
      oiScore * 0.15;

    return Math.min(100, Math.max(0, finalScore));
  }

  applyBoost(score, d) {
    let boosted = score;

    if (this.isOISniper(d)) {
      boosted += 15;
    }

    const oiState = this.getOIState(d.priceChange, d.oiChange);
    if (oiState === 'STRONG_LONG' || oiState === 'STRONG_SHORT') {
      boosted += 10;
    }

    if ((d.orderflow || 1) >= 2.5 && (d.volumeSpike || 0) >= 4) {
      boosted += 8;
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

      let oiBlocked = false;
      if (!this.isOIValid(s)) {
        if (Math.random() < 0.01) {
          const oi = (s.oiChange || 0).toFixed(1);
          const pc = (s.priceChange || 0).toFixed(1);
          console.log(`⚠️ ${s.symbol} → Bad OI state: PC=${pc}% OI=${oi}% (passing with penalty)`);
        }
        oiBlocked = true;
      }

      let score = this.calculateRankScore(s);
      score = this.applyBoost(score, s);

      if (oiBlocked) {
        score -= 10;
      }

      if (score < 60) continue;

      s.rankScore = score;
      s.oiState = this.getOIState(s.priceChange, s.oiChange);

      if (this.isOISniper(s)) {
        s.type = 'SNIPER';
        s.oiSniper = true;
      }

      ranked.push(s);
    }

    ranked.sort((a, b) => (b.rankScore || 0) - (a.rankScore || 0));

    const limited = {
      sniper: ranked.filter(s => s.type === 'SNIPER').slice(0, 3),
      confirmed: ranked.filter(s => s.type === 'CONFIRMED').slice(0, 3),
      prepump: ranked.filter(s => s.type === 'PRE_PUMP').slice(0, 2),
      early: ranked.filter(s => s.type === 'EARLY').slice(0, 3),
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
