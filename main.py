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
                                    
                                    if cooldown_manager.is_blocked(signal):
                                        logger.info(f">>> SKIPPED (cooldown): {pair}")
                                    else:
                                        cooldown_manager.store(signal)
                                        results.append(signal)
                                else:
                                    if signal.get("confidence", 0) < 65:
                                        continue
                                    if cooldown_manager.is_blocked(signal):
                                        logger.info(f">>> SKIPPED (cooldown): {pair}")
                                    else:
                                        cooldown_manager.store(signal)
                                        results.append(signal)
                        else:
                            SCANNER_ERROR_COUNT += 1
                    except Exception as e:
                        SCANNER_ERROR_COUNT += 1
            
            results = cooldown_manager.filter_diversity(results, max_per_pair=1)
            results = sorted(results, key=lambda x: x.get("confidence", 0), reverse=True)
            elite_signals = [s for s in results if s.get("confidence", 0) >= 65][:5]
            SIGNALS_CACHE = elite_signals
            set_cache("top_signals", SIGNALS_CACHE, ttl=60)
            
            cooldown_manager.cleanup_expired()
            
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


@app.route('/')
def root():
    return jsonify({"status": "online", "app": "Binance Signal Engine"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/api/signal/<pair>')
def get_signal(pair):
    logger.info(f"[API] /api/signal/{pair}")
    timeframe = request.args.get('timeframe', '1h')
    fetch_oi = request.args.get('fetch_oi', 'true').lower() == 'true'
    use_bias = request.args.get('use_bias', 'true').lower() == 'true'
    result = generate_signal(pair.upper(), timeframe, fetch_oi, use_bias)
    logger.info(f"[API] {pair}: {result.get('signal')} | Conf: {result.get('confidence')} | Risk: {result.get('risk_pct')}%")
    return jsonify(result)

@app.route('/api/pairs')
def get_pairs():
    logger.info("[API] /api/pairs")
    return jsonify({"pairs": TRADING_PAIRS})

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
    
    return jsonify({
        "signals": filtered,
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
    if status == 'open':
        return jsonify({"trades": tracker.get_open_trades(), "count": len(tracker.get_open_trades())})
    elif status == 'closed':
        return jsonify({"trades": tracker.get_closed_trades(), "count": len(tracker.get_closed_trades())})
    else:
        all_trades = tracker.load_trades()
        return jsonify({"trades": all_trades, "count": len(all_trades)})

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
    current_price = float(request.args.get('price', 0))
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

@app.route('/api/analytics')
def get_analytics():
    logger.info("[API] /api/analytics")
    return jsonify(tracker.get_analytics())

if __name__ == '__main__':
    print(f"Starting on port {port}...")
    app.run(host='0.0.0.0', port=port)
