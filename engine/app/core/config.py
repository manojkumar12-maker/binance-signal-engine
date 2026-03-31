import os
import requests

BINANCE_WS_URL = "wss://fstream.binance.com/stream"
BINANCE_REST_URL = "https://api.binance.com"
BINANCE_FUTURES_URL = "https://fapi.binance.com"

TIMEFRAMES = ["1h", "4h"]

MAX_CANDLES = 100
SCAN_INTERVAL = 15
OI_FETCH_INTERVAL = 180

SL_PERCENT = 0.005
TP1_PERCENT = 0.01
TP2_PERCENT = 0.02
TP3_PERCENT = 0.03

MIN_CONFIDENCE = 60

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def get_all_usdt_pairs():
    try:
        url = f"{BINANCE_FUTURES_URL}/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        pairs = []
        for symbol in data.get('symbols', []):
            if symbol['status'] == 'TRADING' and symbol['quoteAsset'] == 'USDT':
                pairs.append(symbol['symbol'])
        
        return pairs[:50]
    except Exception:
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
            "LINKUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "ETCUSDT"
        ]


PAIRS = get_all_usdt_pairs()
