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
            name: '⚡ Factors',
            value: signal.factors.map(f => `• ${f}`).join('\n'),
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
    } catch (error) {
      console.error('❌ Telegram notification failed:', error.message);
    }
  }

  formatTelegramMessage(signal) {
    const { targets, stopLoss, metrics } = signal;
    
    return `
🚀 <b>PUMP SIGNAL - ${signal.symbol}</b>

💰 <b>Entry:</b> ${signal.entryPrice.toFixed(6)}
🛑 <b>Stop Loss:</b> ${stopLoss.toFixed(6)}

🎯 <b>Take Profit:</b>
TP1: ${targets.tp1.toFixed(6)} (+${config.riskManagement.tp1Percent}%)
TP2: ${targets.tp2.toFixed(6)} (+${config.riskManagement.tp2Percent}%)
TP3: ${targets.tp3.toFixed(6)} (+${config.riskManagement.tp3Percent}%)
TP4: ${targets.tp4.toFixed(6)} (+${config.riskManagement.tp4Percent}%)
TP5: ${targets.tp5.toFixed(6)} (+${config.riskManagement.tp5Percent}%)

📊 <b>Metrics:</b>
Price Change: ${metrics.priceChange}%
Volume Spike: ${metrics.volumeSpike}x
Strength: ${metrics.strength}

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
