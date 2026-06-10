import os
import logging
import threading
import time
import json
from datetime import datetime
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
    TELEGRAM_LIB_AVAILABLE = True
except ImportError:
    TELEGRAM_LIB_AVAILABLE = False
    logger.warning("python-telegram-bot not installed - bot commands disabled")

from app.services import telegram_alerts, system_control, performance_tracker, tracker

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
UPDATE_INTERVAL = 300

bot_instance = None
update_thread = None
running = False

trade_log_file = "trades.json"


def log_trade(trade: Dict):
    try:
        with open(trade_log_file, "a") as f:
            f.write(json.dumps({
                **trade,
                "logged_at": datetime.utcnow().isoformat()
            }) + "\n")
    except Exception as e:
        logger.error(f"Failed to log trade: {e}")


def load_trades(limit: int = 100) -> list:
    trades = []
    try:
        with open(trade_log_file, "r") as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))
    except FileNotFoundError:
        pass
    return trades[-limit:]


def get_status_message() -> str:
    state = system_control.get_system_state()
    perf = performance_tracker.get_stats()
    
    open_trades = tracker.get_open_trades()
    
    return f"""
⚙️ *SYSTEM STATUS*

*Bot:* {"🟢 RUNNING" if state['running'] else "🔴 PAUSED/HALTED"}
*Reason:* {state.get('paused_reason', state.get('halt_reason', 'N/A'))}

📊 *PERFORMANCE*
Win Rate: {perf.get('win_rate', 0)}%
Recent WR: {perf.get('recent_win_rate', 0)}%
Wins: {perf.get('wins', 0)} | Losses: {perf.get('losses', 0)}
Total PnL: {perf.get('total_pnl', 0)}%

📈 *OPEN TRADES:* {len(open_trades)}
"""


def build_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("▶ Start", callback_data='cmd_start'),
            InlineKeyboardButton("⏸ Pause", callback_data='cmd_pause')
        ],
        [
            InlineKeyboardButton("🛑 Halt", callback_data='cmd_halt'),
            InlineKeyboardButton("🔄 Resume", callback_data='cmd_resume')
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data='cmd_status'),
            InlineKeyboardButton("❌ Close All", callback_data='cmd_close_all')
        ],
        [
            InlineKeyboardButton("📒 Daily Report", callback_data='cmd_daily_report')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def handle_command(command: str) -> str:
    if command == "cmd_start":
        system_control.resume_trading()
        return "✅ Bot resumed"
    
    elif command == "cmd_pause":
        system_control.pause_trading("MANUAL")
        return "⏸️ Bot paused"
    
    elif command == "cmd_halt":
        system_control.halt_system("MANUAL", auto_resume=False)
        return "🛑 System halted"
    
    elif command == "cmd_resume":
        system_control.resume_from_halt()
        return "🔄 System resumed"
    
    elif command == "cmd_status":
        return get_status_message()
    
    elif command == "cmd_close_all":
        open_trades = tracker.get_open_trades()
        for trade in open_trades:
            try:
                tracker.close_trade_manually(
                    trade_id=trade.get("id"),
                    remarks="Manual close from Telegram",
                    close_price=trade.get("current_price", trade.get("entry"))
                )
            except:
                pass
        return f"❌ Closed {len(open_trades)} trades"
    
    elif command == "cmd_daily_report":
        trades = load_trades(limit=50)
        if not trades:
            return "No trades recorded"
        
        wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
        losses = len(trades) - wins
        total_pnl = sum(t.get("pnl_pct", 0) for t in trades)
        
        return f"""
📒 *DAILY REPORT*

Trades: {len(trades)}
Wins: {wins} | Losses: {losses}
Win Rate: {wins/len(trades)*100:.1f}%
Total PnL: {total_pnl:.2f}%
"""
    
    return "Unknown command"


def button_handler_callback(update, context):
    query = update.callback_query
    query.answer()
    
    response = handle_command(query.data)
    
    keyboard = build_keyboard()
    query.edit_message_text(response, reply_markup=keyboard)


def start_handler(update, context):
    keyboard = build_keyboard()
    update.message.reply_text("⚙️ *BINANCE SIGNAL ENGINE*\n\nControl Panel:", reply_markup=keyboard)


def error_handler(update, context):
    logger.error(f"Telegram error: {context.error}")
    if update and update.message:
        update.message.reply_text("❌ Error processing command")


def pnl_update_loop():
    while running:
        try:
            state = system_control.get_system_state()
            if not state.get("running"):
                time.sleep(UPDATE_INTERVAL)
                continue
            
            perf = performance_tracker.get_stats()
            open_trades = tracker.get_open_trades()
            
            msg = f"""
📊 *LIVE UPDATE*

Open Trades: {len(open_trades)}
Win Rate: {perf.get('win_rate', 0)}%
Total PnL: {perf.get('total_pnl', 0)}%
"""
            telegram_alerts.send_telegram(msg)
        except Exception as e:
            logger.error(f"PnL update error: {e}")
        
        time.sleep(UPDATE_INTERVAL)


def start_telegram_bot():
    global bot_instance, running
    
    if not TELEGRAM_LIB_AVAILABLE:
        logger.warning("Telegram library not available")
        return False
    
    if not BOT_TOKEN:
        logger.warning("Telegram bot token not configured")
        return False
    
    try:
        bot_instance = Updater(BOT_TOKEN, use_context=True)
        dp = bot_instance.dispatcher
        
        dp.add_handler(CommandHandler("start", start_handler))
        dp.add_handler(CommandHandler("status", lambda u, c: u.message.reply_text(get_status_message())))
        dp.add_handler(CommandHandler("pause", lambda u, c: u.message.reply_text(handle_command("cmd_pause"))))
        dp.add_handler(CommandHandler("resume", lambda u, c: u.message.reply_text(handle_command("cmd_resume"))))
        dp.add_handler(CallbackQueryHandler(button_handler_callback))
        
        dp.add_error_handler(error_handler)
        
        bot_instance.start_polling()
        running = True
        
        if UPDATE_INTERVAL > 0:
            global update_thread
            update_thread = threading.Thread(target=pnl_update_loop, daemon=True)
            update_thread.start()
        
        logger.info("Telegram bot started")
        
        if CHAT_ID:
            telegram_alerts.send_telegram("✅ *Trading Bot Started*\n\nUse /start for control panel")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to start telegram bot: {e}")
        return False


def stop_telegram_bot():
    global running, bot_instance
    running = False
    
    if bot_instance:
        try:
            bot_instance.stop()
        except:
            pass
    
    logger.info("Telegram bot stopped")


def send_live_update():
    if not telegram_alerts.is_configured():
        return
    
    perf = performance_tracker.get_stats()
    open_trades = tracker.get_open_trades()
    
    msg = f"""
📊 *LIVE UPDATE*

Open Trades: {len(open_trades)}
Win Rate: {perf.get('win_rate', 0)}%
Recent WR: {perf.get('recent_win_rate', 0)}%
Total PnL: {perf.get('total_pnl', 0)}%
"""
    telegram_alerts.send_telegram(msg)
