/**
 * Telegram Notifier — Unified SMC + Pump signal delivery
 */

import axios from 'axios';

const TOKEN   = process.env.TELEGRAM_TOKEN   || process.env.TELEGRAM_BOT_TOKEN;
const CHAT_ID = process.env.TELEGRAM_CHAT_ID;

const sentMessages = new Map();
const DEDUP_TTL    = 4 * 60_000;

function isDuplicate(symbol, type) {
  const key  = `${symbol}:${type}`;
  const last = sentMessages.get(key) || 0;
  if (Date.now() - last < DEDUP_TTL) return true;
  sentMessages.set(key, Date.now());
  return false;
}

async function sendRaw(text) {
  if (!TOKEN || !CHAT_ID) {
    console.log('📵 Telegram not configured — skipping');
    return false;
  }
  try {
    await axios.post(
      `https://api.telegram.org/bot${TOKEN}/sendMessage`,
      { chat_id: CHAT_ID, text },
      { timeout: 8000 }
    );
    console.log('✅ Telegram sent');
    return true;
  } catch (err) {
    console.error('❌ Telegram error:', err.response?.data?.description || err.message);
    return false;
  }
}

export async function sendTelegram(message) {
  return sendRaw(message);
}

export async function sendSignal(signalEvent) {
  const { type, symbol, message } = signalEvent;
  if (isDuplicate(symbol, type)) return false;
  console.log(`📤 Sending ${type} signal for ${symbol}`);
  return sendRaw(message);
}

export async function sendStartup(symbolCount) {
  return sendRaw(
    `✅ Signal Engine Started\n` +
    `📊 Watching ${symbolCount} USDT Perpetuals\n` +
    `🔧 Mode: SMC (D1+H4+M15) + Pump Detector\n` +
    `🕐 ${new Date().toUTCString()}`
  );
}

export async function sendError(err) {
  return sendRaw(`❌ Engine Error: ${err?.message || err}`);
}

export async function sendDailySummary(stats) {
  const lines = [
    `📊 Daily Summary — ${new Date().toUTCString()}`,
    ``,
    `Signals sent:`,
    `  🏆 Confluence : ${stats.confluence || 0}`,
    `  📐 SMC        : ${stats.smc        || 0}`,
    `  ⚡ Pump        : ${stats.pump       || 0}`,
    ``,
    `Top symbols: ${(stats.topSymbols || []).join(', ')}`
  ];
  return sendRaw(lines.join('\n'));
}
