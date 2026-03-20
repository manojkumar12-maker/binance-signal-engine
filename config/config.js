export const config = {
  binance: {
    wsUrl: 'wss://fstream.binance.com/ws',
    apiUrl: 'https://fapi.binance.com',
    streamType: 'perpetual'
  },
  signals: {
    minVolume: 1000000,
    minPriceChange: 2,
    pumpThreshold: 5,
    timeframes: ['1m', '5m', '15m'],
    volumeSpikeMultiplier: 3,
    priceAccelerationThreshold: 0.5
  },
  riskManagement: {
    defaultRiskPercent: 1,
    tp1Percent: 0.5,
    tp2Percent: 1.0,
    tp3Percent: 2.0,
    tp4Percent: 3.5,
    tp5Percent: 5.0,
    slPercent: 1.5
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
  filters: {
    minVolume24h: 1000000,
    minTickers: 50,
    excludeStablecoins: true
  }
};
