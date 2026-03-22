import axios from 'axios';
import { config } from '../../config/config.js';

class NotificationManager {
  constructor() {
    this.enabled = true;
  }

  async sendSignal(signal) {
    const message = this.formatSignalMessage(signal);
    
    console.log(message);

    if (config?.notifications?.telegram?.enabled && config?.notifications?.telegram?.botToken && config?.notifications?.telegram?.chatId) {
      await this.sendTelegram(signal);
    }
  }

  formatSignalMessage(signal) {
    const { targets, stopLoss, metrics } = signal;
    
    const tierEmoji = signal.tier === 'SNIPER' ? '🔴' : signal.tier === 'CONFIRMED' ? '🟢' : '🟡';
    
    return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${tierEmoji} ${signal.tier} SIGNAL #${signal.id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: ${signal.symbol}
💰 Entry: ${(signal.entryPrice || 0).toFixed(6)}
🛑 Stop Loss: ${(stopLoss || 0).toFixed(6)}

🎯 Take Profit Levels:
   TP1: ${(targets?.tp1 || 0).toFixed(6)}
   TP2: ${(targets?.tp2 || 0).toFixed(6)}
   TP3: ${(targets?.tp3 || 0).toFixed(6)}

📈 METRICS:
   Price Change: ${metrics?.priceChange || 0}%
   Volume Spike: ${metrics?.volumeSpike || 0}x
   Confidence: ${signal.confidence || 0}
   Confluence: ${signal.confluence || 0}
   Quality: ${signal.entryQuality || 'N/A'}
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
    const { targets, stopLoss, metrics } = signal;
    
    const tierEmoji = signal.tier === 'SNIPER' ? '🔴' : signal.tier === 'CONFIRMED' ? '🟢' : '🟡';
    
    return `
${tierEmoji} <b>${signal.tier} SIGNAL - ${signal.symbol}</b>

💰 <b>Entry:</b> ${(signal.entryPrice || 0).toFixed(6)}
🛑 <b>Stop Loss:</b> ${(stopLoss || 0).toFixed(6)}

🎯 <b>Take Profit:</b>
TP1: ${(targets?.tp1 || 0).toFixed(6)}
TP2: ${(targets?.tp2 || 0).toFixed(6)}
TP3: ${(targets?.tp3 || 0).toFixed(6)}

📊 Conf: ${signal.confidence || 0} | Confluence: ${signal.confluence || 0} | Quality: ${signal.entryQuality || 'N/A'}
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
