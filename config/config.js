export const config = {
  binance: {
    wsUrl: 'wss://fstream.binance.com/ws',
    apiUrl: 'https://fapi.binance.com',
    streamType: 'perpetual'
  },
  signals: {
    minVolume: 1000000,
    minPriceChange: 2,
    pumpThreshold: 2.5,
    earlyPumpThreshold: 2.5,
    timeframes: ['1m', '5m', '15m'],
    volumeSpikeMultiplier: 3,
    priceAccelerationThreshold: 0.5,
    scoreThreshold: 70,
    volumeSpikeThreshold: 2.5,
    minScoreForEntry: 70,
    cooldownMinutes: 5,
    minHistoryForAnalysis: 20
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
    maxUpperWickRatio: 1.5,
    filterInsideRange: true,
    minVolumeSpikeForQuality: 2,
    maxRSI: 80,
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
    minVolume24h: 1000000,
    minTickers: 50,
    excludeStablecoins: true,
    maxSpreadPercent: 0.2,
    minLiquidityPercent: 0.1
  },
  entryFilters: {
    microPullbackRequired: true,
    pullbackMaxPercent: 0.5,
    atrPullbackMultiplier: 0.3
  },
  volatilityFilters: {
    minATRPercent: 0.5,
    atrMALength: 20,
    requireVolatilityExpansion: true
  },
  regimeDetection: {
    trendThreshold: 0.3,
    rangeThreshold: 0.15,
    lookbackPeriod: 50
  },
  notifications: {
    discord: {
      enabled: false,
      webhookUrl: ''
    },
    telegram: {
      enabled: false,
      botToken: '',
      chatId: ''
    },
    console: true
  },
  feedbackLoop: {
    enabled: true,
    winRateThresholdLow: 0.45,
    winRateThresholdHigh: 0.65,
    sampleSize: 20,
    adjustmentStep: 5,
    minSampleForAdjustment: 10
  },
  performanceTracking: {
    trackConditionStats: true,
    trackRegimeStats: true,
    trackRecentTrades: true,
    maxRecentTrades: 20
  }
};
