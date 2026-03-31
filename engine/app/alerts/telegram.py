import requests
import logging
from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from core.logging_utils import setup_logger

logger = setup_logger("telegram", logging.WARNING)


def send_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured")
        return
    
    if isinstance(message, dict):
        message = format_signal_message(message)
    
    if message == "Trade Closed:":
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def format_signal_message(signal: dict) -> str:
    signal_type = signal.get('signal', 'N/A')
    pair = signal.get('pair', 'N/A')
    entry = signal.get('entry', 0)
    sl = signal.get('sl', 0)
    tp1 = signal.get('tp1', 0)
    tp2 = signal.get('tp2', 0)
    tp3 = signal.get('tp3', 0)
    confidence = signal.get('confidence', 0)
    risk = signal.get('risk_pct', 0)
    
    emoji = "🟢" if signal_type == "BUY" else "🔴"
    
    message = f"""
{emoji} *{pair} {signal_type}*

📍 Entry: `{entry}`
🛑 SL: `{sl}`
🎯 TP1: `{tp1}`
🎯 TP2: `{tp2}`
🎯 TP3: `{tp3}`

📊 Confidence: {confidence}%
⚠️ Risk: {risk}%

Trend: {signal.get('trend', 'N/A')}
Liquidity: {signal.get('liquidity', 'N/A')}
"""
    return message


def send_closed_trade_alert(signal: dict, closed_price: float, remarks: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    entry = signal.get('entry', 0)
    signal_type = signal.get('signal', 'N/A')
    pair = signal.get('pair', 'N/A')
    
    if signal_type == "BUY":
        pl_pct = round((closed_price - entry) / entry * 100, 2)
    else:
        pl_pct = round((entry - closed_price) / entry * 100, 2)
    
    pl_emoji = "🟢" if pl_pct >= 0 else "🔴"
    
    message = f"""
🔔 *Trade Closed: {pair}*

❗️ Remarks: {remarks}
📍 Entry: `{entry}`
📍 Closed: `{closed_price}`

{pl_emoji} P/L: {pl_pct}%
"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram error: {e}")
