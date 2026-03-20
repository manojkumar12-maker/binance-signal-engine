export const config = {
  binance: {
    wsUrl: process.env.BINANCE_WS_URL || 'wss://fstream.binance.com/ws',
    apiUrl: process.env.BINANCE_API_URL || 'https://fapi.binance.com'
  },
  signals: {
    minVolume: 1000000,
    cooldownMinutes: 2
  },
  signalTiers: {
    EARLY: { scoreThreshold: 40, priceChangeThreshold: 1, volumeSpikeThreshold: 1 },
    CONFIRMED: { scoreThreshold: 45, priceChangeThreshold: 2, volumeSpikeThreshold: 1.5 },
    SNIPER: { scoreThreshold: 55, priceChangeThreshold: 3, volumeSpikeThreshold: 2 }
  },
  riskManagement: {
    atrPeriod: 14,
    atrMultiplier: {
      tp1: 0.5, tp2: 1.0, tp3: 1.5, tp4: 2.5, tp5: 3.5, sl: 1.2
    }
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
