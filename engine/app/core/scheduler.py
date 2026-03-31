import asyncio
import logging
from datetime import datetime
from app.core.config import SCAN_INTERVAL, PAIRS
from app.strategy.signal_engine import scan_all_pairs, process_pair
from app.alerts.telegram import send_alert
from app.core.redis_client import get_data, set_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENT_SIGNALS = {}


def is_duplicate(signal: Dict) -> bool:
    key = f"{signal['pair']}_{signal['signal']}_{signal.get('entry', 0)}"
    if key in SENT_SIGNALS:
        sent_time = SENT_SIGNALS[key]
        if (datetime.utcnow() - sent_time).seconds < 3600:
            return True
    return False


def mark_sent(signal: Dict):
    key = f"{signal['pair']}_{signal['signal']}_{signal.get('entry', 0)}"
    SENT_SIGNALS[key] = datetime.utcnow()


async def run_scanner():
    logger.info(f"Starting signal scanner for {len(PAIRS)} pairs...")
    
    while True:
        try:
            signals = scan_all_pairs()
            
            for signal in signals:
                if not is_duplicate(signal):
                    send_alert(signal)
                    mark_sent(signal)
                    logger.info(f"Signal: {signal['pair']} {signal['signal']} @ {signal['entry']}")
            
            set_data("last_scan", datetime.utcnow().isoformat())
            
        except Exception as e:
            logger.error(f"Scanner error: {e}")
        
        await asyncio.sleep(SCAN_INTERVAL)


async def run_monitoring():
    logger.info("Starting trade monitor...")
    
    while True:
        try:
            active_signals = get_data("active_signals") or []
            
            for signal in active_signals:
                current = process_pair(signal['pair'])
                if not current:
                    continue
                
                entry = signal['entry']
                sl = signal['sl']
                tp1 = signal['tp1']
                tp2 = signal['tp2']
                tp3 = signal['tp3']
                
                current_price = current['entry']
                closed = False
                remarks = ""
                
                if signal['signal'] == 'BUY':
                    if current_price <= sl:
                        closed = True
                        remarks = "SL Hit"
                    elif current_price >= tp3:
                        closed = True
                        remarks = "TP3 Hit"
                    elif current_price >= tp2:
                        closed = True
                        remarks = "TP2 Hit"
                    elif current_price >= tp1:
                        closed = True
                        remarks = "TP1 Hit"
                else:
                    if current_price >= sl:
                        closed = True
                        remarks = "SL Hit"
                    elif current_price <= tp3:
                        closed = True
                        remarks = "TP3 Hit"
                    elif current_price <= tp2:
                        closed = True
                        remarks = "TP2 Hit"
                    elif current_price <= tp1:
                        closed = True
                        remarks = "TP1 Hit"
                
                if closed:
                    closed_signals = get_data("closed_signals") or []
                    signal['closedAt'] = datetime.utcnow().isoformat()
                    signal['closedPrice'] = current_price
                    signal['remarks'] = remarks
                    closed_signals.insert(0, signal)
                    set_data("closed_signals", closed_signals)
                    
                    active_signals.remove(signal)
                    set_data("active_signals", active_signals)
                    
                    send_alert(f"Trade Closed: {signal['pair']} {remarks}")
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(run_scanner())
