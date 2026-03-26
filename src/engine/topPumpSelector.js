const OI_SPIKE_THRESHOLD = 1.5;
const CANDIDATE_OI_MIN = 0.5;      // minimum meaningful OI change (%)
const CANDIDATE_VOL_MIN = 2;       // volume ratio threshold
const CANDIDATE_MOM_MIN = 0.002;   // minimal momentum

class TopPumpSelector {
  constructor() {
    this.snapshots = new Map();
    this.topSymbols = new Set();
    this.lastEmit = new Map();
  }

  ingest(analysis, ticker = {}) {
    if (!analysis?.symbol) return null;

    const snapshot = {
      symbol: analysis.symbol,
      price: ticker.price || analysis.entryPrice || 0,
      volume: analysis.volumeSpike || 1,
      volumeRatio: analysis.volumeRatio || analysis.volumeSpike || 1,
      orderFlow: analysis.orderflow?.ratio || 1,
      oiChange: analysis.openInterest?.change ?? 0,
      fakeOI: analysis.fakeOI ?? 0,
      momentum: analysis.momentum || 0,
      acceleration: analysis.acceleration || 0,
      imbalance: analysis.orderbookImbalance || analysis.imbalance || 1,
      atr: analysis.atr || 0,
      atrPercent: analysis.atrPercent || 0,
      priceChange: analysis.priceChange || analysis.localChange || 0,
      liquidationSignal: analysis.liquidationSignal || false,
      liquidationDirection: analysis.liquidationDirection || null,
      timestamp: Date.now()
    };

    snapshot.rankScore = this.computeScore(snapshot);
    this.snapshots.set(snapshot.symbol, snapshot);
    return snapshot;
  }

  computeScore(s) {
    const volumeScore = Math.max(s.volumeRatio || s.volume || 0, 0);
    const oiScore = Math.abs(s.oiChange || 0);
    const momentumScore = Math.abs(s.momentum || 0);
    const imbalanceScore = s.imbalance || 0;
    // Strong pump weighting: favor OI spikes and momentum
    const raw =
      volumeScore * 3 +
      oiScore * 5 +
      momentumScore * 4 +
      imbalanceScore * 2;
    return Number.isFinite(raw) ? raw : 0;
  }

  evaluateTop(limit = 5) {
    const now = Date.now();
    for (const [sym, snap] of this.snapshots.entries()) {
      if (now - (snap.timestamp || 0) > 120000) {
        this.snapshots.delete(sym);
      }
    }

    const ranked = Array.from(this.snapshots.values())
      .map(s => {
        const rankScore = this.computeScore(s);
        const isCandidate =
          Math.abs(s.oiChange || 0) > CANDIDATE_OI_MIN &&
          (s.volumeRatio || s.volume || 0) > CANDIDATE_VOL_MIN &&
          Math.abs(s.momentum || 0) > CANDIDATE_MOM_MIN;
        const oiSpike = Math.abs(s.oiChange || 0) > OI_SPIKE_THRESHOLD;
        return { ...s, rankScore, isCandidate, oiSpike };
      })
      .filter(s => s.isCandidate)
      .sort((a, b) => (b.rankScore || 0) - (a.rankScore || 0))
      .slice(0, limit);

    this.topSymbols = new Set(ranked.map(r => r.symbol));
    return ranked;
  }

  getTopByOI(limit = 5) {
    return Array.from(this.snapshots.values())
      .map(s => ({
        symbol: s.symbol,
        oi: s.oiChange || 0,
        volume: s.volumeRatio || s.volume || 0,
        momentum: s.momentum || 0,
        imbalance: s.imbalance || 0,
        rankScore: this.computeScore(s)
      }))
      .sort((a, b) => Math.abs(b.oi) - Math.abs(a.oi))
      .slice(0, limit);
  }

  isTop(symbol) {
    return this.topSymbols.has(symbol);
  }

  applyLiquidationBoost(snapshot, strength) {
    if (
      snapshot.liquidationSignal &&
      (snapshot.imbalance || 1) > 1.3
    ) {
      const priceUp = (snapshot.priceChange || 0) > 0;
      const priceDown = (snapshot.priceChange || 0) < 0;
      const reversalLong = snapshot.liquidationDirection === 'DOWN' && priceUp;
      const reversalShort = snapshot.liquidationDirection === 'UP' && priceDown;

      if (reversalLong || reversalShort) {
        return strength + 2;
      }
    }
    return strength;
  }

  pumpTrigger(snapshot) {
    const vol = snapshot.volumeRatio || snapshot.volume || 0;
    const oi = Math.abs(snapshot.oiChange || 0);
    const accumulation = vol > 1.8 && (snapshot.orderFlow || 1) > 1.2;
    const compression = snapshot.atrPercent
      ? snapshot.atrPercent < 1
      : Math.abs(snapshot.priceChange || 0) < 1.2;
    const breakout = Math.abs(snapshot.priceChange || 0) > 2 || (snapshot.acceleration || 0) > 0.05;
    const momentum = (snapshot.momentum || 0) > 0.03 || (snapshot.acceleration || 0) > 0.05;
    const volumeOk = vol > 2;
    const oiOk = oi > 2;

    const triggered = accumulation && compression && breakout && momentum && volumeOk && oiOk;
    let signalStrength = this.computeScore(snapshot);
    if (triggered) signalStrength += 5;
    signalStrength = this.applyLiquidationBoost(snapshot, signalStrength);

    return {
      triggered,
      signalStrength,
      context: { accumulation, compression, breakout, momentum, volumeOk, oiOk }
    };
  }

  canEmit(symbol, cooldownMs = 60000) {
    const last = this.lastEmit.get(symbol) || 0;
    if (Date.now() - last < cooldownMs) return false;
    this.lastEmit.set(symbol, Date.now());
    return true;
  }

  toPipelineInput(snapshot) {
    return {
      symbol: snapshot.symbol,
      priceChange: snapshot.priceChange || 0,
      volume: snapshot.volumeRatio || snapshot.volume || 1,
      orderFlow: snapshot.orderFlow || 1,
      oiChange: snapshot.oiChange || 0,
      fakeOI: snapshot.fakeOI || 0,
      priceAcceleration: snapshot.acceleration || 0,
      momentum: snapshot.momentum || 0,
      price: snapshot.price || 0,
      atr: snapshot.atr || 0
    };
  }
}

export const topPumpSelector = new TopPumpSelector();
