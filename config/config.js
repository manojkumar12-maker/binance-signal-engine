export const config = {
  binance: {
    wsUrl: process.env.BINANCE_WS_URL || 'wss://fstream.binance.com/ws',
    apiUrl: process.env.BINANCE_API_URL || 'https://fapi.binance.com'
  },
  signals: {
    minVolume: 1000000,
    cooldownMinutes: 2,
    maxSignalsPerCycle: 3,
    signalDecayMinutes: 3,
    rollingWindowSize: 50
  },
  preFilters: {
    minVolume24h: 500000,
    maxSpreadPercent: 0.5,
    excludeStablecoins: true
  },
  signalTiers: {
    PRE_PUMP: { scoreThreshold: 4, confidenceThreshold: 0, priceChangeMin: 1, priceChangeMax: 5, volumeSpikeThreshold: 2.5 },
    EARLY: { scoreThreshold: 30, confidenceThreshold: 45, priceChangeMin: 1.5, priceChangeMax: 15, volumeSpikeThreshold: 2.0 },
    CONFIRMED: { scoreThreshold: 40, confidenceThreshold: 55, priceChangeMin: 2, priceChangeMax: 12, volumeSpikeThreshold: 3.0 },
    SNIPER: { scoreThreshold: 45, confidenceThreshold: 70, priceChangeMin: 3, priceChangeMax: 10, volumeSpikeThreshold: 5.0 }
  },
  scoring: {
    priceActionWeight: 30,
    volumeWeight: 25,
    momentumWeight: 15,
    orderbookWeight: 10,
    liquiditySweepWeight: 10,
    trendWeight: 10,
    orderflowWeight: 20,
    oiWeight: 15,
    fundingWeight: 10
  },
  riskManagement: {
    atrPeriod: 14,
    atrMultiplier: {
      tp1: 0.5, tp2: 1.0, tp3: 1.5, tp4: 2.5, tp5: 3.0, sl: 1.2
    },
    dynamicTP: {
      enabled: true,
      basePercent: 0.3,
      volatilityMultiplier: true
    },
    leverage: 5,
    riskPerTradePercent: 0.1,
    maxRiskPerTrade: 2,
    dailyLossLimit: 5,
    minTPPercent: 0.5
  },
  positionSizing: {
    accountSize: 10000,
    leverage: 5,
    riskPercent: 10
  },
  filters: {
    volatilityExpansionBonus: 10,
    volatilityExpansionPenalty: 10,
    entryPrecisionMaxPullback: 0.005,
    entryPrecisionPenalty: 10,
    latePumpPenalty: 15,
    smartMoneyBonus: 15,
    signalDecayPenalty: 10,
    chopMarketPenalty: 15,
    minOrderflowRatio: 0.8,
    maxOrderflowRatio: 1.6,
    minOIChange: -2,
    maxOIChange: 5,
    fundingThreshold: 0.01
  },
  advancedFeatures: {
    fastMode: true,
    orderflow: {
      enabled: true,
      windowMs: 60000,
      tradeWeight: true
    },
    openInterest: {
      enabled: true,
      updateIntervalMs: 60000
    },
    fundingRate: {
      enabled: true,
      updateIntervalMs: 3600000
    },
    liquidationZones: {
      enabled: true
    },
    parallelEvaluation: true,
    penaltiesNotFilters: true
  },
  notifications: {
    telegram: {
      enabled: process.env.TELEGRAM_ENABLED === 'true',
      botToken: process.env.TELEGRAM_BOT_TOKEN || '',
      chatId: process.env.TELEGRAM_CHAT_ID || ''
    },
    console: true
  }
};
