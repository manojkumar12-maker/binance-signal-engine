import axios from 'axios';

const TOKEN = process.env.TELEGRAM_TOKEN;
const CHAT_ID = process.env.TELEGRAM_CHAT_ID;

export async function sendTelegram(message) {
  if (!TOKEN || !CHAT_ID) {
    console.log('❌ Telegram missing TOKEN or CHAT_ID; skipping send');
    return;
  }

  try {
    const url = `https://api.telegram.org/bot${TOKEN}/sendMessage`;
    await axios.post(url, {
      chat_id: CHAT_ID,
      text: message
    });
    console.log('✅ Telegram sent');
  } catch (err) {
    console.log('❌ Telegram error:', err.response?.data || err.message);
  }
}
