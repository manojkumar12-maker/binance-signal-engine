export const config = {
  binance: {
    wsUrl: 'wss://fstream.binance.com/ws',
    apiUrl: 'https://fapi.binance.com',
    streamType: 'perpetual'
  },
  signals: {
    minVolume: 1000000,
    cooldownMinutes: 2,
    minHistoryForAnalysis: 10
  },
  signalTiers: {
    EARLY: {
      scoreThreshold: 40,
      priceChangeThreshold: 1,
      volumeSpikeThreshold: 1
    },
    CONFIRMED: {
      scoreThreshold: 45,
      priceChangeThreshold: 2,
      volumeSpikeThreshold: 1.5
    },
    SNIPER: {
      scoreThreshold: 55,
      priceChangeThreshold: 3,
      volumeSpikeThreshold: 2
    }
  },
  riskManagement: {
    defaultRiskPercent: 1,
    useDynamicTP: true,
    useDynamicSL: true,
    atrPeriod: 14,
    atrMultiplier: {
      tp1: 0.5,
      tp2: 1.0,
      tp3: 1.5,
      tp4: 2.5,
      tp5: 3.5,
      sl: 1.2
    }
  },
  tradeManagement: {
    moveSLToBreakevenAtTP: 1,
    activateTrailingAtTP: 3,
    trailingATRMultiplier: 0.8,
    earlyExitOnWeakness: true,
    minTPForEarlyExit: 2
  },
  positionSizing: {
    accountSize: 10000,
    riskPercent: 0.01,
    maxPositionPercent: 0.05,
    minPositionSize: 0.001
  },
  aiFilters: {
    maxUpperWickRatio: 2.0,
    filterInsideRange: false,
    minVolumeSpikeForQuality: 1.5,
    maxRSI: 85,
    minRSI: 30
  },
  smartScoring: {
    htfTrendWeight: 15,
    bosWeight: 20,
    liquiditySweepWeight: 20,
    volumeSpikeWeight: 15,
    momentumWeight: 10,
    accelerationWeight: 10,
    candleStrengthWeight: 10,
    mtfAlignmentBonus: 10
  },
  preFilters: {
    minVolume24h: 500000,
    minTickers: 50,
    excludeStablecoins: true,
    maxSpreadPercent: 0.3
  },
  autoRelax: {
    enabled: true,
    noSignalsMinutes: 10,
    reduceScoreBy: 5,
    reduceVolumeBy: 0.3,
    minScore: 40,
    minVolume: 1.0
  },
  autoTuner: {
    enabled: true,
    baseScoreThreshold: 40,
    baseVolumeSpike: 1.3,
    basePriceChange: 1.0,
    tuneIntervalMinutes: 2
  },
  notifications: {
    discord: { enabled: false, webhookUrl: '' },
    telegram: { enabled: false, botToken: '', chatId: '' },
    console: true
  },
  feedbackLoop: {
    enabled: true,
    winRateThresholdLow: 0.40,
    winRateThresholdHigh: 0.65,
    sampleSize: 20,
    adjustmentStep: 5
  }
};
