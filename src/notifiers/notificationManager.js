import axios from 'axios';
import { config } from '../../config/config.js';

class NotificationManager {
  constructor() {
    this.enabled = true;
  }

  async sendSignal(signal) {
    const message = this.formatDiscordMessage(signal);

    if (config.notifications.console) {
      console.log(message);
    }

    if (config.notifications.discord.enabled && config.notifications.discord.webhookUrl) {
      await this.sendDiscord(message);
    }

    if (config.notifications.telegram.enabled && config.notifications.telegram.botToken) {
      await this.sendTelegram(signal);
    }
  }

  formatDiscordMessage(signal) {
    const { targets, stopLoss, metrics, riskReward } = signal;
    
    return {
      embeds: [{
        title: `🚀 PUMP SIGNAL - ${signal.symbol}`,
        color: 3066993,
        fields: [
          {
            name: '💰 Entry Price',
            value: `\`${signal.entryPrice.toFixed(6)}\``,
            inline: true
          },
          {
            name: '🛑 Stop Loss',
            value: `\`${stopLoss.toFixed(6)}\` (-${config.riskManagement.slPercent}%)`,
            inline: true
          },
          {
            name: '📊 Signal Strength',
            value: `\`${metrics.strength}/100\``,
            inline: true
          },
          {
            name: '🎯 Take Profit Levels',
            value: `**TP1:** \`${targets.tp1.toFixed(6)}\` (+${config.riskManagement.tp1Percent}%)\n` +
                   `**TP2:** \`${targets.tp2.toFixed(6)}\` (+${config.riskManagement.tp2Percent}%)\n` +
                   `**TP3:** \`${targets.tp3.toFixed(6)}\` (+${config.riskManagement.tp3Percent}%)\n` +
                   `**TP4:** \`${targets.tp4.toFixed(6)}\` (+${config.riskManagement.tp4Percent}%)\n` +
                   `**TP5:** \`${targets.tp5.toFixed(6)}\` (+${config.riskManagement.tp5Percent}%)`,
            inline: false
          },
          {
            name: '📈 Metrics',
            value: `Price Change: \`${metrics.priceChange}%\`\n` +
                   `Volume Spike: \`${metrics.volumeSpike}x\``,
            inline: true
          },
          {
            name: '⚡ Confluence',
            value: `Score: \`${signal.confluence || 0}\`\n` +
                   `Confidence: \`${signal.confidence || 0}\`\n` +
                   `Quality: \`${signal.entryQuality || 'N/A'}\``,
            inline: false
          }
        ],
        footer: {
          text: `Signal ID: #${signal.id} | Binance USDT Futures`
        },
        timestamp: new Date(signal.timestamp).toISOString()
      }]
    };
  }

  async sendDiscord(message) {
    try {
      await axios.post(config.notifications.discord.webhookUrl, message);
    } catch (error) {
      console.error('❌ Discord notification failed:', error.message);
    }
  }

  async sendTelegram(signal) {
    if (!config.notifications.telegram.botToken || !config.notifications.telegram.chatId) {
      console.log('⚠️ Telegram not configured (missing botToken or chatId)');
      return;
    }
    
    const text = this.formatTelegramMessage(signal);
    
    try {
      await axios.post(
        `https://api.telegram.org/bot${config.notifications.telegram.botToken}/sendMessage`,
        {
          chat_id: config.notifications.telegram.chatId,
          text,
          parse_mode: 'HTML'
        }
      );
      console.log(`✅ Telegram notification sent for ${signal.symbol}`);
    } catch (error) {
      console.error('❌ Telegram notification failed:', error.message);
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
TP1: ${(targets?.tp1 || 0).toFixed(6)} (+0.5%)
TP2: ${(targets?.tp2 || 0).toFixed(6)} (+1.0%)
TP3: ${(targets?.tp3 || 0).toFixed(6)} (+1.5%)

📊 <b>Confidence:</b> ${signal.confidence || 0}
📈 <b>Confluence:</b> ${signal.confluence || 0}
🎯 <b>Quality:</b> ${signal.entryQuality || 'N/A'}

⚡ Signal #${signal.id}
    `;
  }

  async sendUpdate(signal) {
    if (!config.notifications.console) return;
    
    const { update } = signal;
    if (update.tpHit.length > 0) {
      console.log(`\n🎉 ${signal.symbol} - TP${Math.max(...update.tpHit)} HIT! Price: ${update.currentPrice.toFixed(6)} (+${update.unrealizedPnL}%)\n`);
    }
    if (update.slHit) {
      console.log(`\n💔 ${signal.symbol} - STOPPED OUT! Price: ${update.currentPrice.toFixed(6)}\n`);
    }
  }
}

export const notifier = new NotificationManager();
