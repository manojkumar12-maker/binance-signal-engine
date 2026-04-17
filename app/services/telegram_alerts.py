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
    pair = signal.get('pair', '')
    side = signal.get('signal', '')
    entry = signal.get('entry_primary', 0)
    sl = signal.get('sl', 0)
    tp1 = signal.get('tp1', 0)
    tp2 = signal.get('tp2', 0)
    tp3 = signal.get('tp3', 0)
    confidence = signal.get('confidence', 0)
    tier = signal.get('tier', 'N/A')
    setup = signal.get('setup_type', 'N/A')
    regime = signal.get('regime', 'N/A')
    bos = signal.get('bos', '')
    choch = signal.get('choch', '')
    ltf = signal.get('ltf_entry_trigger', False)
    
    risk_pct = round(position.get('risk_pct', 0) * 100, 2)
    rr = position.get('rr', 0)
    leverage = position.get('leverage', 1)
    
    risk_reward = f"{rr}:1" if rr else "N/A"
    risk_percent = f"{risk_pct}%"
    
    direction_emoji = "🟢" if side == "BUY" else "🔴"
    
    structure_info = []
    if bos: structure_info.append(f"BOS:{bos}")
    if choch: structure_info.append(f"CHoCh:{choch}")
    if ltf: structure_info.append("LTF:✓")
    structure_str = " | ".join(structure_info) if structure_info else "N/A"
    
    msg = f"""{direction_emoji} *{side} {pair}* (Tier:{tier})

📊 *Entry:* `{entry}`
🛡️ *SL:* `{sl}`
🎯 *TP1:* `{tp1}` | *TP2:* `{tp2}` | *TP3:* `{tp3}`

⚡ *Confidence:* {confidence}% | 🎯 *RR:* {risk_reward}
💰 *Risk:* {risk_percent} | 📈 *Lev:* {leverage}x

🧠 Setup: {setup} | 📐 Regime: {regime}
🔍 Structure: {structure_str}

💎 Tier: {tier} | ⏱️ LTF Trigger: {ltf}"""
    return send_telegram(msg)


def alert_trade_exit(trade: Dict, result: Dict) -> bool:
    pair = trade.get('pair', '')
    side = trade.get('type', '')
    entry = trade.get('entry', 0)
    exit_price = trade.get('current_price', 0)
    pnl = result.get('pnl', 0)
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    rr = result.get('rr', 0)
    status = trade.get('status', '')
    closed_pct = trade.get("closed_pct", 0)
    
    direction_emoji = "🟢" if side == "BUY" else "🔴"
    rr_str = f"{rr}:1" if rr else "N/A"
    partial_info = f" ({closed_pct}% closed)" if closed_pct > 0 else ""
    
    msg = f"""{direction_emoji} *EXIT {pair}* {pnl_emoji}{partial_info}

📊 Entry: `{entry}` → Exit: `{exit_price}`
💰 PnL: {pnl_emoji} {pnl}% | 🎯 RR: {rr_str}
📋 Status: {status}

💎 Trade Complete"""
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
