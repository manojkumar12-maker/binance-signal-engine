import os
import requests
import math

BINANCE_API_URL = "https://api.binance.com"
FUTURES_API_URL = "https://fapi.binance.com"
BINANCE_FUTURES_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"

DEFAULT_TIMEFRAME = "1h"
CANDLE_LIMIT = 100

SL_PERCENT = 0.005
TP1_PERCENT = 0.01
TP2_PERCENT = 0.02
TP3_PERCENT = 0.03

ATR_BASED_TP_SL = True
ATR_SL_MULTIPLIER = 1.5
ATR_TP1_MULTIPLIER = 1.5
ATR_TP2_MULTIPLIER = 3.0
ATR_TP3_MULTIPLIER = 5.0

MIN_CONFIDENCE = 82
MIN_ATR_RATIO = 0.005

SNIPER_MODE = True
ELITE_THRESHOLD = 88
MAX_SIGNALS = 5
AUTO_TRADE = True

EXTENSION_FILTER_1H = 0.05
EXTENSION_FILTER_4H = 0.08

ENTRY_QUALITY_THRESHOLD = 70

SNIPER_MODE_CONFIDENCE = 85
SNIPER_MODE_ENTRY_SCORE = 80
SNIPER_MODE_WHALE_ALIGNMENT = True
SNIPER_MODE_LIQUIDITY_CONFIRMED = True

VOLATILITY_COMPRESSION_THRESHOLD = 0.6

RISK_PER_TRADE = 0.01
HIGH_CONFIDENCE_RISK = 0.015
MEDIUM_CONFIDENCE_RISK = 0.01
NORMAL_RISK = 0.007
LOW_CONFIDENCE_RISK = 0.005
MIN_RR_RATIO = 2.0

MAX_DRAWDOWN_PCT = 0.05
DAILY_LOSS_LIMIT = 0.03
MAX_OPEN_TRADES = 3
MAX_LEVERAGE = 10
MAX_ENTRY_SLIPPAGE = 0.005

MIN_ENTRY_SCORE = 80
MIN_RR_FILTER = 2.0

SIGNAL_DECAY_MINUTES = 30
MAX_TOTAL_RISK_PCT = 0.05

NO_TRADE_PUMP_DUMP_THRESHOLD = 0.10

OI_PAIRS_LIMIT = 60


def get_precision_from_tick(tick_size: float) -> int:
    tick_str = f"{tick_size:.10f}".rstrip('0')
    if '.' in tick_str:
        return len(tick_str.split('.')[1])
    return 0


def load_precision_map():
    try:
        data = requests.get(BINANCE_FUTURES_INFO_URL, timeout=10).json()
        precision_map = {}
        for symbol in data.get("symbols", []):
            pair = symbol["symbol"]
            for f in symbol.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    tick_size = float(f.get("tickSize", 0))
                    precision_map[pair] = get_precision_from_tick(tick_size)
                    break
        return precision_map
    except Exception:
        return {}


PRICE_PRECISION = load_precision_map()


def format_price(pair: str, price: float) -> float:
    precision = PRICE_PRECISION.get(pair, 4)
    return round(price, precision)


def round_to_tick(pair: str, price: float) -> float:
    precision = PRICE_PRECISION.get(pair, 4)
    tick = 10 ** (-precision)
    return round(round(price / tick) * tick, precision)


def min_price_filter(entry: float) -> bool:
    return entry >= 0.0001


def validate_trade(entry: float, sl: float) -> bool:
    if entry <= 0 or sl <= 0:
        return False
    risk_pct = abs(entry - sl) / entry
    if risk_pct < 0.002:
        return False
    if risk_pct > 0.02:
        return False
    return True


def calculate_position_size(balance: float, risk_percent: float, entry: float, sl: float) -> float:
    if entry <= 0 or sl <= 0:
        return 0
    risk_amount = balance * risk_percent
    stop_distance = abs(entry - sl)
    if stop_distance == 0:
        return 0
    position_size = risk_amount / stop_distance
    return round(position_size, 3)
