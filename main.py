from flask import Flask, jsonify, request
import os

import sys
sys.path.insert(0, 'app')

from app.services.strategy import generate_signal

app = Flask(__name__)

port = int(os.environ.get("PORT", 8000))

TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "ATOMUSDT", "UNIUSDT", "LTCUSDT", "ETCUSDT"
]

@app.route('/')
def root():
    return jsonify({"status": "online", "app": "Binance Signal Engine"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/api/signal/<pair>')
def get_signal(pair):
    timeframe = request.args.get('timeframe', '1h')
    return jsonify(generate_signal(pair.upper(), timeframe))

@app.route('/api/pairs')
def get_pairs():
    return jsonify({"pairs": TRADING_PAIRS})

@app.route('/api/signals')
def get_all_signals():
    timeframe = request.args.get('timeframe', '1h')
    min_confidence = int(request.args.get('min_confidence', 60))
    
    signals = []
    for pair in TRADING_PAIRS:
        result = generate_signal(pair, timeframe)
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
    for pair in TRADING_PAIRS:
        result = generate_signal(pair, timeframe)
        if result.get("signal") != "NO TRADE" and result.get("confidence", 0) >= min_confidence:
            signals.append(result)
    
    signals.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return jsonify({
        "signals": signals[:limit],
        "count": len(signals)
    })

if __name__ == '__main__':
    print(f"Starting on port {port}...")
    app.run(host='0.0.0.0', port=port)
