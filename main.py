from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import logging
import sys
import requests
sys.path.insert(0, 'app')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import config
from app.services.strategy import generate_signal
from app.services import tracker, market, bias_engine
from app.services.redis_client import set_cache, get_cache
from app.services.cooldown_manager import cooldown_manager
from app.services.signal_lifecycle import (
    store_signal, get_stored_signal, is_signal_locked, validate_stored_signal,
    confirm_signal, execute_signal, clear_expired_signals, get_all_stored_signals
)
from app.services.telegram_alerts import alert_trade_entry, alert_bot_started
from app.services.execution_worker import start_execution_worker
import threading
import time
import asyncio
import aiohttp
from datetime import datetime

SIGNALS_CACHE = []
SCANNER_RUNNING = False
SCANNER_ERROR_COUNT = 0
CONSECUTIVE_LOSSES = 0
LOSS_STREAK_START = 0
PRICE_CACHE = {}

async def fetch_klines_async(session, symbol, interval="1h", limit=100):
    url = f"{config.FUTURES_API_URL}/fapi/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return await resp.json()
    except:
        return None


async def scanner_async_loop():
    global SIGNALS_CACHE, SCANNER_RUNNING, SCANNER_ERROR_COUNT, CONSECUTIVE_LOSSES, LOSS_STREAK_START
    
    logger.info(">>> ASYNC SCANNER: Started")
    SCANNER_RUNNING = True
    
    while True:
        try:
            if CONSECUTIVE_LOSSES >= 3:
                if time.time() - LOSS_STREAK_START < 3600:
                    logger.info(f">>> LOSS STREAK ACTIVE: Waiting (3 losses in row)")
                    await asyncio.sleep(60)
                    continue
                else:
                    CONSECUTIVE_LOSSES = 0
                    LOSS_STREAK_START = 0
            
            results = []
            scan_count = 0
            analysis_count = 0
            
            async with aiohttp.ClientSession() as session:
                tasks = []
                for pair in TRADING_PAIRS:
                    task = fetch_klines_async(session, pair, "1h", config.CANDLE_LIMIT)
                    tasks.append((pair, task))
                
                for pair, task in tasks:
                    try:
                        scan_count += 1
                        klines = await task
                        if klines and len(klines) >= 20:
                            from app.services import market as market_service
                            candles = market_service.parse_klines(klines)
                            from app.services.strategy import generate_signal_from_candles
                            from app.services import bias_engine
                            
                            signal = generate_signal_from_candles(pair, candles)
                            analysis_count += 1
                            
                            if signal and signal.get("signal") != "NO TRADE" and signal.get("confidence", 0) >= config.MIN_CONFIDENCE:
                                btc_1h = await fetch_klines_async(session, "BTCUSDT", "1h", 20)
                                if btc_1h:
                                    btc_candles = market_service.parse_klines(btc_1h)
                                    bias = bias_engine.get_market_bias(btc_candles, [])
                                    
                                    signal_direction = signal.get("signal")
                                    market_bias = bias.get("bias", "NEUTRAL")
                                    
                                    regime = signal.get("regime", "TRANSITION")
                                    if regime == "LOW_VOL":
                                        logger.info(f">>> SKIPPED (low_vol): {pair}")
                                        continue
                                    
                                    if market_bias == "BEARISH" and signal_direction == "BUY":
                                        logger.info(f">>> SKIPPED (bias_mismatch): {pair}")
                                        continue
                                    if market_bias == "BULLISH" and signal_direction == "SELL":
                                        logger.info(f">>> SKIPPED (bias_mismatch): {pair}")
                                        continue
                                    
                                    signal["market_bias"] = market_bias
                                    
                                    if market_bias == signal_direction:
                                        signal["confidence"] = min(100, signal.get("confidence", 0) + 10)
                                    
                                    if signal.get("confidence", 0) < 65:
                                        continue
                                    
                                    whale_signal = signal.get("whale_signal", "NEUTRAL")
                                    if whale_signal == "DISTRIBUTION" and signal_direction == "BUY":
                                        logger.info(f">>> SKIPPED (whale_mismatch): {pair}")
                                        continue
                                    if whale_signal == "ACCUMULATION" and signal_direction == "SELL":
                                        logger.info(f">>> SKIPPED (whale_mismatch): {pair}")
                                        continue
                                    
                                    liquidity = signal.get("liquidity")
                                    order_flow = signal.get("order_flow", 0.5)
                                    fake_breakout = signal.get("fake_breakout", False)
                                    
                                    if liquidity != "SWEEP_LOW_REJECTION" and liquidity != "SWEEP_HIGH_REJECTION":
                                        if not fake_breakout and order_flow < 0.6:
                                            logger.info(f">>> SKIPPED (weak_setup): {pair}")
                                            continue
                                    
                                    current_hour = datetime.utcnow().hour
                                    if current_hour < 6 or current_hour > 23:
                                        logger.info(f">>> SKIPPED (dead_hours): {pair}")
                                        continue
                                    
                                    results.append(signal)
                        else:
                            SCANNER_ERROR_COUNT += 1
                    except Exception as e:
                        SCANNER_ERROR_COUNT += 1
            
            results = cooldown_manager.filter_diversity(results, max_per_pair=1)
            SIGNALS_CACHE = cooldown_manager.process_signals(results)
            set_cache("top_signals", SIGNALS_CACHE, ttl=60)
            
            from app.services import signal_lifecycle
            signal_lifecycle.clear_expired_signals()
            
            cooldown_manager.cleanup_expired()
            
            logger.info(f">>> SCAN COMPLETE: {len(SIGNALS_CACHE)} signals, processing via signal lifecycle...")
            
            for signal in SIGNALS_CACHE[:5]:
                if signal.get("signal") == "NO TRADE":
                    continue
                
                pair = signal.get("pair")
                signal_type = signal.get("signal")
                entry = signal.get("entry_primary")
                
                if not entry or entry <= 0:
                    continue
                
                if signal_lifecycle.is_signal_locked(pair):
                    locked = signal_lifecycle.get_stored_signal(pair)
                    if locked and locked.get("signal_state") in ["CONFIRMED", "EXECUTED"]:
                        logger.info(f">>> SKIP {pair}: already in progress (state={locked.get('signal_state')})")
                        continue
                    
                    if locked and locked.get("signal_state") == "PENDING":
                        is_valid, reason = signal_lifecycle.validate_stored_signal(pair, config.MIN_CONFIDENCE)
                        if is_valid:
                            signal_lifecycle.confirm_signal(pair)
                            logger.info(f">>> CONFIRMED {pair}: passed validation")
                            
                            trade = tracker.create_trade(
                                pair=pair,
                                signal_type=signal_type,
                                entry=entry,
                                sl=signal.get("sl"),
                                tp1=signal.get("tp1"),
                                tp2=signal.get("tp2"),
                                tp3=signal.get("tp3"),
                                confidence=signal.get("confidence", 0),
                                entry_limit=signal.get("entry_limit")
                            )
                            tracker.add_trade(trade)
                            signal_lifecycle.execute_signal(pair)
                            logger.info(f">>> AUTO TRADE: {pair} {signal_type} @ {entry}")
                            
                            alert_trade_entry(signal, {"leverage": 1, "risk_pct": 0.01, "rr": 2})
                        else:
                            logger.info(f">>> REJECTED {pair}: {reason}")
                        continue
                
                stored = signal_lifecycle.store_signal(signal, "PENDING")
                if not stored:
                    logger.warning(f">>> FAILED TO STORE {pair}")
                    continue
                
                logger.info(f">>> LOCKED {pair}: state=PENDING, confidence={signal.get('confidence')}")
                
                is_valid, reason = signal_lifecycle.validate_stored_signal(pair, config.MIN_CONFIDENCE)
                if is_valid:
                    signal_lifecycle.confirm_signal(pair)
                    logger.info(f">>> CONFIRMED {pair}: passed validation")
                    
                    trade = tracker.create_trade(
                        pair=pair,
                        signal_type=signal_type,
                        entry=entry,
                        sl=signal.get("sl"),
                        tp1=signal.get("tp1"),
                        tp2=signal.get("tp2"),
                        tp3=signal.get("tp3"),
                        confidence=signal.get("confidence", 0),
                        entry_limit=signal.get("entry_limit")
                    )
                    tracker.add_trade(trade)
                    signal_lifecycle.execute_signal(pair)
                    logger.info(f">>> AUTO TRADE: {pair} {signal_type} @ {entry}")
                    
                    alert_trade_entry(signal, {"leverage": 1, "risk_pct": 0.01, "rr": 2})
                else:
                    logger.info(f">>> REJECTED {pair}: {reason}")
            
            logger.info(f">>> ASYNC SCANNER: Cached {len(SIGNALS_CACHE)} signals | Errors: {SCANNER_ERROR_COUNT}")
            
            if SIGNALS_CACHE:
                for i, s in enumerate(SIGNALS_CACHE[:3]):
                    logger.info(f">>> TOP {i+1}: {s.get('pair')} {s.get('signal')} Conf:{s.get('confidence')} Entry:{s.get('entry_primary')}")
            
        except Exception as e:
            logger.error(f">>> ASYNC SCANNER ERROR: {e}")
        
        await asyncio.sleep(60)


def start_async_scanner():
    asyncio.run(scanner_async_loop())


def get_pairs_with_oi_limit(pairs, limit):
    return pairs[:limit]


app = Flask(__name__)
CORS(app)

logger.info("=== SYSTEM STARTING ===")
logger.info(f"Config: MIN_CONFIDENCE={config.MIN_CONFIDENCE}, MIN_ATR_RATIO={config.MIN_ATR_RATIO}")
logger.info(f"Precision loaded: {len(config.PRICE_PRECISION)} symbols")
logger.info(f"OI_PAIRS_LIMIT={config.OI_PAIRS_LIMIT}")
logger.info("=== COMPONENTS LOADED ===")
logger.info("- strategy.generate_signal")
logger.info("- market.get_klines, market.get_open_interest")
logger.info("- bias_engine.get_market_bias")
logger.info("- tracker (trade management)")
logger.info("- scoring (fake breakout, liquidity validation)")
logger.info("- async scanner with Redis cache")
logger.info("=== READY ===")

port = int(os.environ.get("PORT", 8000))

BLACKLIST = [
    "LUNA2USDT", "USTCUSDT", "BTTUSDT", "HOTUSDT", "WAVESUSDT",
    "1INCHUSDT", "CHZUSDT", "ENJUSDT", "MANAUSDT", "SANDUSDT",
    "GALAUSDT", "AXSUSDT", "APEUSDT", "FTMUSDT", "OPUSDT"
]

def get_all_usdt_pairs():
    try:
        url = f"{config.FUTURES_API_URL}/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        pairs = []
        for symbol in data.get('symbols', []):
            if (
                symbol.get('status') == 'TRADING' and
                symbol.get('quoteAsset') == 'USDT' and
                symbol.get('contractType') == 'PERPETUAL' and
                symbol.get('marginAsset') == 'USDT' and
                symbol.get('symbol') not in BLACKLIST
            ):
                pairs.append(symbol.get('symbol'))
        
        logger.info(f"[CONFIG] Found {len(pairs)} USDT pairs from Binance")
        return pairs[:200]
    except Exception as e:
        logger.error(f"[CONFIG] Error fetching pairs: {e}")
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"
        ]

TRADING_PAIRS = get_all_usdt_pairs()
logger.info(f"[CONFIG] Scanning {len(TRADING_PAIRS)} pairs: {TRADING_PAIRS[:10]}...")

scanner_thread = threading.Thread(target=start_async_scanner, daemon=True)
scanner_thread.start()
time.sleep(2)

alert_bot_started()

@app.route('/api/telegram-test')
def test_telegram():
    from app.services.telegram_alerts import is_configured, send_telegram
    if not is_configured():
        return jsonify({"configured": False, "error": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"})
    result = send_telegram("🧪 Test message from Binance Signal Engine")
    return jsonify({"configured": True, "sent": result})


@app.route('/')
def root():
    return jsonify({"status": "online", "app": "Binance Signal Engine"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/api/signal/<pair>')
def get_signal(pair):
    logger.info(f"[API] /api/signal/{pair}")
    
    pair_upper = pair.upper()
    
    if is_signal_locked(pair_upper):
        locked = get_stored_signal(pair_upper)
        if locked:
            state = locked.get("signal_state")
            
            if state in ["PENDING", "CONFIRMED", "EXECUTED"]:
                logger.info(f"[API] {pair}: returning LOCKED signal (state={state})")
                return jsonify(locked)
    
    timeframe = request.args.get('timeframe', '1h')
    fetch_oi = request.args.get('fetch_oi', 'true').lower() == 'true'
    use_bias = request.args.get('use_bias', 'true').lower() == 'true'
    result = generate_signal(pair_upper, timeframe, fetch_oi, use_bias)
    logger.info(f"[API] {pair}: {result.get('signal')} | Conf: {result.get('confidence')} | Risk: {result.get('risk_pct')}%")
    return jsonify(result)

@app.route('/api/pairs')
def get_pairs():
    logger.info("[API] /api/pairs")
    return jsonify({"pairs": TRADING_PAIRS})


@app.route('/api/price/<pair>')
def get_price(pair):
    global PRICE_CACHE
    try:
        symbol = pair.upper()
        
        if symbol in PRICE_CACHE:
            return jsonify({"pair": symbol, "price": PRICE_CACHE[symbol], "cached": True})
        
        url = f"{config.FUTURES_API_URL}/fapi/v1/ticker/price?symbol={symbol}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        if "price" in data:
            price = float(data["price"])
            PRICE_CACHE[symbol] = price
            return jsonify({"pair": symbol, "price": price})
        
        logger.warning(f"[API] price fallback for {symbol}")
        klines = market.get_klines(symbol, "1h", 1)
        if klines and len(klines) > 0:
            current_price = float(klines[-1][4])
            PRICE_CACHE[symbol] = current_price
            return jsonify({"pair": symbol, "price": current_price})
        
        return jsonify({"error": "No data"}), 404
    except Exception as e:
        logger.error(f"[API] price error: {e}")
        cached = PRICE_CACHE.get(pair.upper())
        if cached:
            return jsonify({"pair": pair.upper(), "price": cached, "cached": True})
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-bias')
def get_market_bias():
    logger.info("[API] /api/market-bias")
    try:
        btc_1h = market.get_klines("BTCUSDT", "1h", config.CANDLE_LIMIT)
        btc_4h = market.get_klines("BTCUSDT", "4h", config.CANDLE_LIMIT)
        bias = bias_engine.get_market_bias(btc_1h, btc_4h)
        logger.info(f"[API] BTC Bias: {bias.get('bias')} | Score: {bias.get('score')}")
        return jsonify(bias)
    except Exception as e:
        logger.error(f"[API] market-bias error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/signals')
def get_all_signals():
    logger.info("[API] /api/signals - using cache")
    min_confidence = int(request.args.get('min_confidence', config.MIN_CONFIDENCE))
    
    filtered = [s for s in SIGNALS_CACHE if s.get("confidence", 0) >= min_confidence]
    filtered = filtered[:10]
    
    executed_from_redis = get_all_stored_signals("EXECUTED")
    executed_pairs = [s.get("pair") for s in executed_from_redis]
    
    executed_signals = []
    for pair in executed_pairs:
        stored = get_stored_signal(pair)
        if stored:
            executed_signals.append({
                "pair": pair,
                "signal": stored.get("signal", "BUY"),
                "entry_primary": stored.get("entry_primary"),
                "sl": stored.get("sl"),
                "tp1": stored.get("tp1"),
                "tp2": stored.get("tp2"),
                "tp3": stored.get("tp3"),
                "confidence": stored.get("confidence", 0),
                "risk_pct": stored.get("risk_pct", 0),
                "signal_state": "EXECUTED"
            })
    
    return jsonify({
        "signals": filtered,
        "executed_signals": executed_signals,
        "count": len(filtered)
    })

@app.route('/api/top-signals')
def get_top_signals():
    logger.info(">>> API: Returning cached signals")
    
    cached = get_cache("top_signals")
    cache_to_use = cached if cached else SIGNALS_CACHE
    
    limit = int(request.args.get('limit', 5))
    min_confidence = int(request.args.get('min_confidence', config.MIN_CONFIDENCE))
    
    filtered = [s for s in cache_to_use if s.get("confidence", 0) >= min_confidence]
    filtered = filtered[:limit]
    
    logger.info(f">>> API: Returning {len(filtered)} signals from cache")
    
    return jsonify({
        "signals": filtered,
        "count": len(filtered)
    })

@app.route('/api/trades', methods=['GET'])
def get_trades():
    logger.info("[API] /api/trades")
    status = request.args.get('status', 'all')
    
    trades = tracker.load_trades()
    
    open_trades = [t for t in trades if t.get("status") == "OPEN"]
    for trade in open_trades:
        try:
            pair = trade.get("pair")
            url = f"{config.FUTURES_API_URL}/fapi/v1/ticker/price?symbol={pair}"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if "price" in data:
                    current_price = float(data["price"])
                    entry = trade.get("entry", 0)
                    signal_type = trade.get("type", "BUY")
                    if entry > 0:
                        if signal_type == "BUY":
                            pnl = (current_price - entry) / entry * 100
                        else:
                            pnl = (entry - current_price) / entry * 100
                        trade["current_price"] = current_price
                        trade["pnl"] = round(pnl, 2)
        except:
            pass
    
    if status == 'open':
        filtered = [t for t in trades if t.get("status") == "OPEN"]
        return jsonify({"trades": filtered, "count": len(filtered)})
    elif status == 'closed':
        filtered = [t for t in trades if t.get("status") != "OPEN"]
        return jsonify({"trades": filtered, "count": len(filtered)})
    else:
        return jsonify({"trades": trades, "count": len(trades)})

@app.route('/api/trade/open', methods=['POST'])
def open_trade():
    logger.info("[API] /api/trade/open")
    data = request.json
    trade = tracker.create_trade(
        pair=data.get('pair'),
        signal_type=data.get('type'),
        entry=data.get('entry'),
        sl=data.get('sl'),
        tp1=data.get('tp1'),
        tp2=data.get('tp2'),
        tp3=data.get('tp3'),
        confidence=data.get('confidence', 0),
        entry_limit=data.get('entry_limit')
    )
    tracker.add_trade(trade)
    logger.info(f"[TRADE] Opened: {trade['pair']} {trade['type']} @ {trade['entry']}")
    return jsonify({"success": True, "trade": trade})

@app.route('/api/trade/<trade_id>', methods=['PUT'])
def update_trade(trade_id):
    logger.info(f"[API] /api/trade/{trade_id}")
    price_str = request.args.get('price', '0')
    try:
        current_price = float(price_str) if price_str and price_str != 'undefined' else 0
    except:
        current_price = 0
    if current_price > 0:
        result = tracker.update_trade(trade_id, current_price)
        return jsonify({"success": True, "trade": result})
    return jsonify({"success": False, "error": "Price required"}), 400

@app.route('/api/trade/<trade_id>', methods=['DELETE'])
def delete_trade(trade_id):
    logger.info(f"[API] DELETE /api/trade/{trade_id}")
    tracker.remove_trade(trade_id)
    return jsonify({"success": True})

@app.route('/api/trade/<trade_id>/close', methods=['POST'])
def close_trade(trade_id):
    global CONSECUTIVE_LOSSES, LOSS_STREAK_START
    logger.info(f"[API] /api/trade/{trade_id}/close")
    data = request.json
    result = tracker.close_trade_manually(
        trade_id=trade_id,
        remarks=data.get('remarks', 'Manual Close'),
        close_price=float(data.get('close_price', 0))
    )
    if result:
        if result.get('pnl_pct', 0) < 0:
            CONSECUTIVE_LOSSES += 1
            if CONSECUTIVE_LOSSES == 1:
                LOSS_STREAK_START = time.time()
        else:
            CONSECUTIVE_LOSSES = 0
            LOSS_STREAK_START = 0
        logger.info(f"[TRADE] Closed: {result['pair']} {result['type']} | PnL: {result['pnl_pct']}% | {result['remarks']}")
        return jsonify({"success": True, "trade": result})
    return jsonify({"success": False, "error": "Trade not found"}), 404

@app.route('/api/config', methods=['GET', 'POST'])
def get_set_config():
    global cooldown_manager
    
    if request.method == 'POST':
        data = request.json
        if 'sniper_mode' in data:
            cooldown_manager.SNIPER_MODE = data['sniper_mode']
            logger.info(f">>> SNIPER MODE: {'ENABLED' if data['sniper_mode'] else 'DISABLED'}")
        
        if 'auto_trade' in data:
            config.AUTO_TRADE = data['auto_trade']
            logger.info(f">>> AUTO TRADE: {'ENABLED' if data['auto_trade'] else 'DISABLED'}")
        
        return jsonify({
            "sniper_mode": cooldown_manager.SNIPER_MODE,
            "auto_trade": config.AUTO_TRADE,
            "elite_threshold": config.ELITE_THRESHOLD,
            "max_signals": config.MAX_SIGNALS
        })
    
    return jsonify({
        "sniper_mode": cooldown_manager.SNIPER_MODE,
        "auto_trade": config.AUTO_TRADE,
        "elite_threshold": config.ELITE_THRESHOLD,
        "max_signals": config.MAX_SIGNALS
    })

@app.route('/api/analytics')
def get_analytics():
    logger.info("[API] /api/analytics")
    return jsonify(tracker.get_analytics())


@app.route('/api/signal-states')
def get_signal_states():
    from app.services.signal_lifecycle import get_all_stored_signals
    try:
        all_signals = get_all_stored_signals()
        return jsonify({
            "signals": all_signals,
            "count": len(all_signals)
        })
    except Exception as e:
        logger.error(f"[API] signal-states error: {e}")
        return jsonify({"signals": [], "count": 0, "error": str(e)}), 500


@app.route('/api/system-status')
def get_system_status():
    from app.services.signal_lifecycle import get_all_stored_signals
    
    all_signals = get_all_stored_signals()
    pending = sum(1 for s in all_signals if s.get("signal_state") == "PENDING")
    confirmed = sum(1 for s in all_signals if s.get("signal_state") == "CONFIRMED")
    executed = sum(1 for s in all_signals if s.get("signal_state") == "EXECUTED")
    rejected = sum(1 for s in all_signals if s.get("signal_state") == "REJECTED")
    
    return jsonify({
        "scanner_running": SCANNER_RUNNING,
        "scanner_errors": SCANNER_ERROR_COUNT,
        "signals_in_pipeline": {
            "pending": pending,
            "confirmed": confirmed,
            "executed": executed,
            "rejected": rejected,
            "total": len(all_signals)
        },
        "consecutive_losses": CONSECUTIVE_LOSSES,
        "cache_size": len(SIGNALS_CACHE)
    })


if __name__ == '__main__':
    print(f"Starting on port {port}...")
    app.run(host='0.0.0.0', port=port)
