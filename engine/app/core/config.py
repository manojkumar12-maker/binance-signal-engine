import os
import requests

BINANCE_WS_URL = "wss://fstream.binance.com/stream"
BINANCE_REST_URL = "https://api.binance.com"
BINANCE_FUTURES_URL = "https://fapi.binance.com"

TIMEFRAMES = ["1h"]  # Only 1H - build 4H internally

MAX_CANDLES = 100
SCAN_INTERVAL = 20  # Increased to reduce CPU load
OI_FETCH_INTERVAL = 180

SL_PERCENT = 0.005
TP1_PERCENT = 0.01
TP2_PERCENT = 0.02
TP3_PERCENT = 0.03

MIN_CONFIDENCE = 65
MAX_PAIRS_PER_STREAM = 100  # Optimized for fewer connections

WARMUP_SECONDS = 60  # Wait for data before scanning

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

BLACKLIST = [
    "LUNA2USDT", "USTCUSDT", "BTTUSDT", "HOTUSDT", "WAVESUSDT",
    "1INCHUSDT", "CHZUSDT", "ENJUSDT", "MANAUSDT", "SANDUSDT",
    "GALAUSDT", "AXSUSDT", "APEUSDT", "FTMUSDT", "OPUSDT"
]

PAIRS_BLACKLIST = os.environ.get("PAIRS_BLACKLIST", "")
if PAIRS_BLACKLIST:
    BLACKLIST.extend(PAIRS_BLACKLIST.split(","))


def get_all_usdt_pairs():
    try:
        url = f"{BINANCE_FUTURES_URL}/fapi/v1/exchangeInfo"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        pairs = []
        for symbol in data.get('symbols', []):
            if (
                symbol['status'] == 'TRADING' and
                symbol['quoteAsset'] == 'USDT' and
                symbol['contractType'] == 'PERPETUAL' and
                symbol['symbol'] not in BLACKLIST
            ):
                pairs.append(symbol['symbol'])
        
        return pairs
    except Exception as e:
        print(f"Error fetching pairs: {e}")
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
            "LINKUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "ETCUSDT"
        ]


def chunk_pairs(pairs, size=MAX_PAIRS_PER_STREAM):
    for i in range(0, len(pairs), size):
        yield pairs[i:i + size]


PAIRS = get_all_usdt_pairs()
