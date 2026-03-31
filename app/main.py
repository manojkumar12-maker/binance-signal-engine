from flask import Flask, jsonify, request
from app.services.strategy import generate_signal

app = Flask(__name__)

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
    return jsonify({
        "pairs": [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT"
        ]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
