from flask import Flask, jsonify, request
import os

import sys
sys.path.insert(0, 'app')

import config
from app.services.strategy import generate_signal
from app.services import tracker, market, bias_engine

app = Flask(__name__)

port = int(os.environ.get("PORT", 8000))

TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "ATOMUSDT", "UNIUSDT", "LTCUSDT", "ETCUSDT"
]

def get_pairs_with_oi_limit(pairs, limit):
    return pairs[:limit]

@app.route('/')
def root():
    return jsonify({"status": "online", "app": "Binance Signal Engine"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/api/signal/<pair>')
def get_signal(pair):
    timeframe = request.args.get('timeframe', '1h')
    fetch_oi = request.args.get('fetch_oi', 'true').lower() == 'true'
    use_bias = request.args.get('use_bias', 'true').lower() == 'true'
    return jsonify(generate_signal(pair.upper(), timeframe, fetch_oi, use_bias))

@app.route('/api/pairs')
def get_pairs():
    return jsonify({"pairs": TRADING_PAIRS})

@app.route('/api/market-bias')
def get_market_bias():
    try:
        btc_1h = market.get_klines("BTCUSDT", "1h", config.CANDLE_LIMIT)
        btc_4h = market.get_klines("BTCUSDT", "4h", config.CANDLE_LIMIT)
        bias = bias_engine.get_market_bias(btc_1h, btc_4h)
        return jsonify(bias)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/signals')
def get_all_signals():
    timeframe = request.args.get('timeframe', '1h')
    min_confidence = int(request.args.get('min_confidence', 60))
    
    signals = []
    oi_limit = int(request.args.get('oi_limit', config.OI_PAIRS_LIMIT))
    pairs_with_oi = get_pairs_with_oi_limit(TRADING_PAIRS, oi_limit)
    
    for i, pair in enumerate(TRADING_PAIRS):
        fetch_oi = pair in pairs_with_oi
        result = generate_signal(pair, timeframe, fetch_oi, True)
        if result.get("signal") != "NO TRADE" and result.get("confidence", 0) >= min_confidence:
            signals.append(result)
    
    signals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return jsonify({
        "signals": signals[:10],
        "count": len(signals)
    })

@app.route('/api/top-signals')
def get_top_signals():
    timeframe = request.args.get('timeframe', '1h')
    limit = int(request.args.get('limit', 5))
    min_confidence = int(request.args.get('min_confidence', 60))
    
    signals = []
    oi_limit = int(request.args.get('oi_limit', config.OI_PAIRS_LIMIT))
    pairs_with_oi = get_pairs_with_oi_limit(TRADING_PAIRS, oi_limit)
    
    for pair in TRADING_PAIRS:
        fetch_oi = pair in pairs_with_oi
        result = generate_signal(pair, timeframe, fetch_oi, True)
        if result.get("signal") != "NO TRADE" and result.get("confidence", 0) >= min_confidence:
            signals.append(result)
    
    signals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return jsonify({
        "signals": signals[:limit],
        "count": len(signals)
    })

@app.route('/api/trades', methods=['GET'])
def get_trades():
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
    return jsonify({"success": True, "trade": trade})

@app.route('/api/trade/<trade_id>', methods=['PUT'])
def update_trade(trade_id):
    current_price = float(request.args.get('price', 0))
    if current_price > 0:
        result = tracker.update_trade(trade_id, current_price)
        return jsonify({"success": True, "trade": result})
    return jsonify({"success": False, "error": "Price required"}), 400

@app.route('/api/trade/<trade_id>', methods=['DELETE'])
def delete_trade(trade_id):
    tracker.remove_trade(trade_id)
    return jsonify({"success": True})

@app.route('/api/trade/<trade_id>/close', methods=['POST'])
def close_trade(trade_id):
    data = request.json
    result = tracker.close_trade_manually(
        trade_id=trade_id,
        remarks=data.get('remarks', 'Manual Close'),
        close_price=float(data.get('close_price', 0))
    )
    if result:
        return jsonify({"success": True, "trade": result})
    return jsonify({"success": False, "error": "Trade not found"}), 404

@app.route('/api/analytics')
def get_analytics():
    return jsonify(tracker.get_analytics())

if __name__ == '__main__':
    print(f"Starting on port {port}...")
    app.run(host='0.0.0.0', port=port)
