import asyncio
import logging
from datetime import datetime
from typing import Dict
from core.config import SCAN_INTERVAL, PAIRS, WARMUP_SECONDS, INITIAL_FETCH_LIMIT
from core.logging_utils import setup_logger
from strategy.signal_engine import scan_all_pairs, process_pair
from alerts.telegram import send_alert
from core.redis_client import get_data, set_data
from data.rest_fetcher import sync_all_data
from data.oi_fetcher import get_active_pairs_for_oi

logger = setup_logger("scheduler", logging.INFO)

SENT_SIGNALS = {}
SIGNAL_COUNT = 0
SCAN_COUNT = 0
LAST_REST_ERROR = None


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
    global SIGNAL_COUNT
    SIGNAL_COUNT += 1


async def run_scanner():
    global SCAN_COUNT, LAST_REST_ERROR
    
    logger.info(f"=" * 50)
    logger.info(f"🚀 SCANNER STARTED - Monitoring {len(PAIRS)} pairs")
    logger.info(f"⏱️ Scan interval: {SCAN_INTERVAL} seconds")
    logger.info(f"📡 Data mode: REST polling (hybrid model)")
    logger.info(f"📊 Telegram alerts: {'Enabled' if hasattr(send_alert, '__call__') else 'Not configured'}")
    logger.info(f"=" * 50)
    
    logger.info(f"")
    logger.info(f"📥 INITIAL DATA FETCH - Fetching candles for {INITIAL_FETCH_LIMIT} pairs...")
    
    initial_pairs = PAIRS[:INITIAL_FETCH_LIMIT]
    sync_result = await sync_all_data(initial_pairs, "1h")
    logger.info(f"✅ Initial fetch complete - {sync_result['candles_updated']} pairs loaded")
    
    logger.info(f"")
    logger.info(f"⏳ WARMUP COMPLETE - Starting market scans!")
    
    while True:
        try:
            SCAN_COUNT += 1
            
            logger.info(f"")
            logger.info(f"━" * 50)
            logger.info(f"🔍 SCAN #{SCAN_COUNT} - Syncing + Scanning {len(PAIRS)} pairs...")
            
            try:
                sync_result = await sync_all_data(PAIRS, "1h")
                LAST_REST_ERROR = None
            except Exception as rest_err:
                LAST_REST_ERROR = rest_err
                logger.error(f"❌ REST fetch failed: {rest_err}")
                logger.info(f"⏭️ Using cached data from previous cycle")
            
            cache = {}
            for pair in PAIRS:
                candles = get_data(f"{pair}:1h")
                if candles:
                    cache[pair] = candles
            
            active_pairs = get_active_pairs_for_oi(PAIRS, cache, min_move_pct=0.003)
            logger.info(f"📊 Active pairs (>0.3% move): {len(active_pairs)}")
            
            signals = scan_all_pairs(max_signals=5)
            
            logger.info(f"📈 Analysis complete - Found {len(signals)} signals")
            
            if not signals:
                logger.info(f"❌ No valid signals - Market conditions not met")
            else:
                for signal in signals:
                    if not is_duplicate(signal):
                        send_alert(signal)
                        mark_sent(signal)
                        
                        logger.info(f"")
                        logger.info(f"🎯 SIGNAL #{SIGNAL_COUNT} DETECTED!")
                        logger.info(f"   📌 Pair: {signal['pair']}")
                        logger.info(f"   📊 Type: {signal['signal']}")
                        logger.info(f"   💰 Entry: {signal['entry']}")
                        logger.info(f"   🛡️ SL: {signal['sl']}")
                        logger.info(f"   🎯 TP1: {signal['tp1']} | TP2: {signal['tp2']} | TP3: {signal['tp3']}")
                        logger.info(f"   📊 Confidence: {signal['confidence']}%")
                        logger.info(f"   📈 Trend: {signal['trend']}")
                        logger.info(f"   💧 Liquidity: {signal['liquidity']}")
                        logger.info(f"   ⚡ Risk: {signal['risk_pct']}%")
                    else:
                        logger.info(f"⏭️ Skipped duplicate: {signal['pair']} {signal['signal']}")
            
            last_scan = datetime.utcnow().strftime("%H:%M:%S")
            set_data("last_scan", last_scan)
            
            logger.info(f"")
            logger.info(f"✅ Scan #{SCAN_COUNT} complete at {last_scan}")
            logger.info(f"━" * 50)
            
        except Exception as e:
            logger.error(f"❌ Scanner error: {e}")
        
        await asyncio.sleep(SCAN_INTERVAL)


async def run_monitoring():
    logger.info(f"")
    logger.info(f"=" * 50)
    logger.info(f"📊 TRADE MONITOR STARTED")
    logger.info(f"=" * 50)
    
    while True:
        try:
            active_signals = get_data("active_signals") or []
            
            if active_signals:
                logger.info(f"📋 Monitoring {len(active_signals)} active trades")
                
                for signal in active_signals:
                    current = process_pair(signal['pair'])
                    if current:
                        logger.info(f"   📌 {signal['pair']}: {current['entry']} (Target: {signal['tp3']})")
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(30)


def print_system_status():
    logger.info(f"")
    logger.info(f"╔" + "═" * 58 + "╗")
    logger.info(f"║" + " " * 10 + "BINANCE SIGNAL ENGINE STATUS" + " " * 12 + "║")
    logger.info(f"╠" + "═" * 58 + "╣")
    logger.info(f"║  Pairs:     {len(PAIRS):>10} pairs                    ║")
    logger.info(f"║  Scanner:  {'Active':>10}                           ║")
    logger.info(f"║  Monitor:   {'Active':>10}                           ║")
    logger.info(f"║  Telegram:  {'Ready':>10}                           ║")
    logger.info(f"╚" + "═" * 58 + "╝")
    logger.info(f"")
