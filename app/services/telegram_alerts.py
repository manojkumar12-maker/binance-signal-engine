import requests
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    if not is_configured():
        logger.warning("Telegram not configured - message not sent")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": parse_mode
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def alert_trade_entry(signal: Dict, position: Dict) -> bool:
    msg = f"""
🚀 *NEW TRADE EXECUTED*

*Symbol:* {signal.get('pair')}
*Side:* {signal.get('signal')}
*Entry:* {signal.get('entry_primary')}
*Stop Loss:* {signal.get('sl')}
*Take Profit:* {signal.get('tp1')}

*Leverage:* {position.get('leverage', 1)}x
*Risk:* {round(position.get('risk_pct', 0) * 100, 2)}%
*Confidence:* {signal.get('confidence')}%
*RR:* {position.get('rr', 0)}:1

🧠 Regime: {signal.get('regime', 'N/A')}
🐋 Whale: {signal.get('whale_signal', 'N/A')}
💧 Liquidity: {signal.get('liquidity', 'N/A')}
"""
    return send_telegram(msg)


def alert_trade_exit(trade: Dict, result: Dict) -> bool:
    pnl = result.get('pnl', 0)
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    
    msg = f"""
📊 *TRADE CLOSED* {pnl_emoji}

*Symbol:* {trade.get('pair')}
*Side:* {trade.get('type')}
*Entry:* {trade.get('entry')}
*Exit:* {trade.get('current_price', 'N/A')}
*Result:* {pnl_emoji} {pnl}% ({result.get('pnl', 0)} USD)
*RR:* {result.get('rr', 0)}:1
*Remarks:* {trade.get('remarks', 'N/A')}

📈 Balance: {result.get('balance', 0)}
"""
    return send_telegram(msg)


def alert_sl_hit(signal: Dict) -> bool:
    msg = f"""
🔴 *STOP LOSS HIT*

*Symbol:* {signal.get('pair')}
*Side:* {signal.get('signal')}
*Entry:* {signal.get('entry_primary')}
*SL:* {signal.get('sl')}
*Confidence:* {signal.get('confidence')}%
"""
    return send_telegram(msg)


def alert_tp_hit(signal: Dict, tp_level: str) -> bool:
    msg = f"""
🎯 *TAKE PROFIT HIT - {tp_level}*

*Symbol:* {signal.get('pair')}
*Side:* {signal.get('signal')}
*Entry:* {signal.get('entry_primary')}
*TP:* {signal.get('tp1' if tp_level == 'TP1' else 'tp2' if tp_level == 'TP2' else 'tp3')}
"""
    return send_telegram(msg)


def alert_drawdown_warning(current_drawdown: float) -> bool:
    msg = f"""
⚠️ *DRAWDOWN WARNING*

Current Drawdown: *{round(current_drawdown * 100, 2)}%*

Trading has been paused to protect capital.
Review your positions and wait for recovery.
"""
    return send_telegram(msg)


def alert_daily_loss_limit() -> bool:
    msg = f"""
🛑 *DAILY LOSS LIMIT REACHED*

Trading paused for today.
No more trades will be executed.
See you tomorrow.
"""
    return send_telegram(msg)


def alert_max_trades_reached() -> bool:
    msg = f"""
⏸️ *MAX TRADES REACHED*

Currently at maximum open trades ({3}).
Waiting for positions to close before new entries.
"""
    return send_telegram(msg)


def alert_liquidation_warning(signal: Dict, liq_price: float) -> bool:
    msg = f"""
🚨 *LIQUIDATION WARNING*

*Symbol:* {signal.get('pair')}
*Entry:* {signal.get('entry_primary')}
*Liquidation Price:* {liq_price}

⚠️ Trade rejected - liquidation risk too high
"""
    return send_telegram(msg)


def alert_system_status(status: str, details: str = "") -> bool:
    msg = f"""
📡 *SYSTEM STATUS*

Status: *{status}*
{details}
"""
    return send_telegram(msg)


def alert_error(error_msg: str) -> bool:
    msg = f"""
❌ *SYSTEM ERROR*

{error_msg}
"""
    return send_telegram(msg)


def alert_sniper_trade(signal: Dict) -> bool:
    msg = f"""
💎 *SNIPER TRADE ALERT*

*Symbol:* {signal.get('pair')}
*Side:* {signal.get('signal')}
*Entry:* {signal.get('entry_primary')}
*Confidence:* {signal.get('confidence')}%
*Entry Score:* {signal.get('entry_score', 0)}
*Whale:* {signal.get('whale_signal', 'N/A')}

🔥 HIGH QUALITY SIGNAL DETECTED
"""
    return send_telegram(msg)


def alert_bot_started() -> bool:
    msg = f"""
✅ *TRADING BOT STARTED*

All systems operational.
Scanning for signals...
"""
    return send_telegram(msg)


def alert_daily_summary(stats: Dict) -> bool:
    msg = f"""
📒 *DAILY SUMMARY*

Trades: {stats.get('total_trades', 0)}
Wins: {stats.get('wins', 0)}
Losses: {stats.get('losses', 0)}
Win Rate: {stats.get('win_rate', 0)}%
Total PnL: {stats.get('total_pnl', 0)}%
Balance: {stats.get('balance', 0)}
"""
    return send_telegram(msg)
