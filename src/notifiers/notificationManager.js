import axios from 'axios';
import { config } from '../../config/config.js';

class NotificationManager {
  constructor() {
    this.enabled = true;
    this.lastNotification = new Map();
  }

  shouldNotify(signal) {
    const tier = signal.tier || signal.type || signal.strength;
    return ['SNIPER', 'PUMP_CONFIRMED'].includes(tier);
  }

  shouldRateLimit(symbol, minInterval = 30000) {
    const last = this.lastNotification.get(symbol) || 0;
    return Date.now() - last < minInterval;
  }

  async sendSignal(signal) {
    const tier = signal.tier || signal.type || signal.strength;
    const message = this.formatSignalMessage(signal);
    
    console.log(message);

    if (!this.shouldNotify(signal)) {
      return;
    }

    if (this.shouldRateLimit(signal.symbol)) {
      console.log(`⏳ Rate limited: ${signal.symbol}`);
      return;
    }

    this.lastNotification.set(signal.symbol, Date.now());

    if (config?.notifications?.telegram?.enabled && config?.notifications?.telegram?.botToken && config?.notifications?.telegram?.chatId) {
      await this.sendTelegram(signal);
    }
  }

  formatSignalMessage(signal) {
    const tier = signal.tier || signal.type || signal.strength || 'SIGNAL';
    const direction = signal.direction || signal.type || '';
    const { targets, stopLoss, metrics } = signal;
    
    const tierEmoji = {
      'SNIPER': '🔴',
      'PUMP_CONFIRMED': '🚀',
      'CONFIRMED': '🟢',
      'EARLY': '🟡',
      'PRE_PUMP': '🟣'
    }[tier] || '⚪';

    const oiStr = signal.oiChange !== undefined ? `OI=${signal.oiChange >= 0 ? '+' : ''}${signal.oiChange.toFixed(1)}%` : '';
    const fakeOIStr = signal.fakeOI !== undefined && signal.fakeOI !== null ? `FakeOI=${signal.fakeOI >= 0 ? '+' : ''}${signal.fakeOI.toFixed(1)}%` : '';
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${tierEmoji} ${tier} ${direction ? direction + ' ' : ''}SIGNAL: ${signal.symbol}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${oiStr || fakeOIStr ? `📊 ${[oiStr, fakeOIStr].filter(Boolean).join(' | ')}` : ''}
💰 Entry: ${(signal.entryPrice || 0).toFixed(6)}
🛑 Stop Loss: ${(stopLoss || 0).toFixed(6)}

🎯 Take Profit Levels:
   TP1: ${(targets?.tp1 || 0).toFixed(6)}
   TP2: ${(targets?.tp2 || 0).toFixed(6)}
   TP3: ${(targets?.tp3 || 0).toFixed(6)}

📈 METRICS:
   Price Change: ${metrics?.priceChange || signal.priceChange || 0}%
   Volume Spike: ${metrics?.volumeSpike || signal.volume || 0}x
   Confidence: ${signal.confidence || 0}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;
  }

  async sendTelegram(signal) {
    const text = this.formatTelegramMessage(signal);
    
    try {
      await axios.post(
        `https://api.telegram.org/bot${config?.notifications?.telegram?.botToken}/sendMessage`,
        {
          chat_id: config?.notifications?.telegram?.chatId,
          text,
          parse_mode: 'HTML'
        }
      );
      console.log(`✅ Telegram sent: ${signal.symbol}`);
    } catch (error) {
      console.error('❌ Telegram failed:', error.message);
    }
  }

  formatTelegramMessage(signal) {
    const tier = signal.tier || signal.type || signal.strength || 'SIGNAL';
    const direction = signal.direction || signal.type || '';
    const { targets, stopLoss, metrics } = signal;
    
    const tierEmoji = {
      'SNIPER': '🔴',
      'PUMP_CONFIRMED': '🚀',
      'CONFIRMED': '🟢',
      'EARLY': '🟡',
      'PRE_PUMP': '🟣'
    }[tier] || '⚪';

    const oiStr = signal.oiChange !== undefined ? `OI=${signal.oiChange >= 0 ? '+' : ''}${signal.oiChange.toFixed(1)}%` : '';
    const fakeOIStr = signal.fakeOI !== undefined && signal.fakeOI !== null ? `FakeOI=${signal.fakeOI >= 0 ? '+' : ''}${signal.fakeOI.toFixed(1)}%` : '';
    
    return `
${tierEmoji} <b>${tier} ${direction ? direction + ' ' : ''}SIGNAL - ${signal.symbol}</b>

${oiStr || fakeOIStr ? `📊 ${[oiStr, fakeOIStr].filter(Boolean).join(' | ')}` : ''}
💰 <b>Entry:</b> ${(signal.entryPrice || 0).toFixed(6)}
🛑 <b>Stop Loss:</b> ${(stopLoss || 0).toFixed(6)}

🎯 <b>Take Profit:</b>
TP1: ${(targets?.tp1 || 0).toFixed(6)}
TP2: ${(targets?.tp2 || 0).toFixed(6)}
TP3: ${(targets?.tp3 || 0).toFixed(6)}

📊 Conf: ${signal.confidence || 0}% | Vol: ${metrics?.volumeSpike || signal.volume || 0}x
`;
  }

  async sendUpdate(signal) {
    const { update } = signal;
    if (update?.tpHit?.length > 0) {
      console.log(`\n🎉 ${signal.symbol} - TP${Math.max(...update.tpHit)} HIT!\n`);
    }
    if (update?.slHit) {
      console.log(`\n💔 ${signal.symbol} - STOPPED OUT!\n`);
    }
  }
}

export const notifier = new NotificationManager();
