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
  signalTiers: {
    PRE_PUMP: { scoreThreshold: 0, confidenceThreshold: 0, priceChangeMin: 0, priceChangeMax: 2, volumeSpikeThreshold: 1.5 },
    EARLY: { scoreThreshold: 50, confidenceThreshold: 50, priceChangeMin: 1, priceChangeMax: 6, volumeSpikeThreshold: 1.5 },
    CONFIRMED: { scoreThreshold: 60, confidenceThreshold: 65, priceChangeMin: 2, priceChangeMax: 10, volumeSpikeThreshold: 2 },
    SNIPER: { scoreThreshold: 55, confidenceThreshold: 80, priceChangeMin: 2.5, priceChangeMax: 10, volumeSpikeThreshold: 2.5 }
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
    }
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
