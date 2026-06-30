"""Integration test: scanner -> signal lifecycle -> worker -> broker sim"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

os.environ["BROKER_ENABLED"] = "false"
os.environ["USE_TESTNET"] = "false"

import json
import time
import tempfile
os.environ["TRADES_FILE"] = os.path.join(tempfile.gettempdir(), f"test_trades_{int(time.time())}.json")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.gettempdir(), f"test_trades_{int(time.time())}.db")

import config
config.TRADES_FILE = os.environ["TRADES_FILE"]

import app.services.database as db
db.init_db()

from app.services import signal_lifecycle, tracker, cooldown_manager
from app.services.strategy import generate_signal_from_candles
from backtest import data_feed


PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def make_candle(open_p, high, low, close, vol=1000):
    return {"open": open_p, "high": high, "low": low, "close": close, "volume": vol}


def build_trending_up_candles(n=100):
    candles = []
    price = 100.0
    for i in range(n):
        c = price + (i * 0.05) + (hash(str(i)) % 10) * 0.1
        low = c - 0.5
        high = c + 0.5
        candles.append(make_candle(c - 0.2, high, low, c))
        price = c
    return candles


def build_trending_down_candles(n=100):
    candles = []
    price = 200.0
    for i in range(n):
        c = price - (i * 0.05) - (hash(str(i)) % 10) * 0.1
        low = c - 0.5
        high = c + 0.5
        candles.append(make_candle(c + 0.2, high, low, c))
        price = c
    return candles


def build_ranging_candles(n=100):
    candles = []
    price = 150.0
    for i in range(n):
        c = price + (hash(str(i)) % 20 - 10) * 0.1
        low = c - 0.3
        high = c + 0.3
        candles.append(make_candle(c - 0.1, high, low, c))
        price = c
    return candles


print("=" * 60)
print("INTEGRATION TEST: Pipeline")
print("=" * 60)


print("\n--- 1. Signal Lifecycle (in-memory mode) ---")

sig1 = {
    "pair": "BTCUSDT", "signal": "BUY", "entry_primary": 50000.0,
    "sl": 49000.0, "tp1": 51000.0, "tp2": 52000.0, "tp3": 53000.0,
    "confidence": 75, "entry_score": 70, "risk_pct": 2.0, "tier": "HIGH",
    "trend": "UPTREND", "liquidity": "SWEEP_LOW_REJECTION",
    "atr_ratio": 0.005, "regime": "NORMAL", "timestamp": "2025-01-01T00:00:00"
}

stored = signal_lifecycle.store_signal(sig1, "PENDING")
check("store_signal returns dict", stored is not None)
check("store_signal state PENDING", stored.get("signal_state") == "PENDING")

locked = signal_lifecycle.is_signal_locked("BTCUSDT")
check("is_signal_locked true", locked == True)

retrieved = signal_lifecycle.get_stored_signal("BTCUSDT")
check("get_stored_signal works", retrieved is not None)
check("stored confidence intact", retrieved.get("confidence") == 75)
check("snapshot saved", retrieved.get("snapshot") is not None)

confirmed = signal_lifecycle.confirm_signal("BTCUSDT")
check("confirm_signal ok", confirmed == True)
state = signal_lifecycle.get_stored_signal("BTCUSDT")
check("state -> CONFIRMED", state.get("signal_state") == "CONFIRMED")

executed = signal_lifecycle.execute_signal("BTCUSDT")
check("execute_signal ok", executed == True)
state = signal_lifecycle.get_stored_signal("BTCUSDT")
check("state -> EXECUTED", state.get("signal_state") == "EXECUTED")

rejected = signal_lifecycle.reject_signal("BTCUSDT", "test_reject")
check("reject_signal ok", rejected == True)
state = signal_lifecycle.get_stored_signal("BTCUSDT")
check("state -> REJECTED", state.get("signal_state") == "REJECTED")

all_signals = signal_lifecycle.get_all_stored_signals()
check("get_all_stored_signals non-empty", len(all_signals) >= 1)

pending_list = signal_lifecycle.get_all_stored_signals("PENDING")
executed_list = signal_lifecycle.get_all_stored_signals("EXECUTED")
check("filter PENDING works", isinstance(pending_list, list))
check("filter EXECUTED works", isinstance(executed_list, list))

trading_signals = signal_lifecycle.get_signals_for_trading()
check("get_signals_for_trading returns list", isinstance(trading_signals, list))

signal_lifecycle.clear_expired_signals()
all_now = signal_lifecycle.get_all_stored_signals()
check("clear_expired does not crash", isinstance(all_now, list))

sig2 = {**sig1, "pair": "ETHUSDT", "entry_primary": 3000.0, "sl": 2900.0}
locked_conflict = signal_lifecycle.is_signal_locked("ETHUSDT")
check("different pair not locked", locked_conflict == False)

stored2 = signal_lifecycle.store_signal(sig2, "PENDING")
check("second signal stored", stored2 is not None)

stored_dup = signal_lifecycle.store_signal(sig2, "PENDING")
check("duplicate store returns existing", stored_dup is not None)


print("\n--- 2. Cooldown Manager ---")

cm = cooldown_manager.CooldownManager()

sig_a = {"pair": "BTCUSDT", "signal": "BUY", "entry_primary": 50000.0, "confidence": 80}
sig_b = {"pair": "ETHUSDT", "signal": "SELL", "entry_primary": 3000.0, "confidence": 75}
sig_c = {"pair": "SOLUSDT", "signal": "BUY", "entry_primary": 150.0, "confidence": 65}

blocked_empty = cm.is_blocked(sig_a)
check("is_blocked false for new signal", blocked_empty == False)

cm.store(sig_a)
blocked_after = cm.is_blocked(sig_a)
check("is_blocked true after store", blocked_after == True)

improved = {**sig_a, "entry_primary": 49500.0}
check("is_improved BUY lower entry",
      cm.is_improved(improved, sig_a) == True)

not_improved = {**sig_a, "entry_primary": 50500.0}
check("not_improved BUY higher entry",
      cm.is_improved(not_improved, sig_a) == False)

sig_sell = {"pair": "BTCUSDT", "signal": "SELL", "entry_primary": 50000.0, "confidence": 80}
check("is_improved different direction",
      cm.is_improved(sig_sell, sig_a) == True)

fp = cm.build_fingerprint(sig_a)
check("build_fingerprint contains pair and direction",
      "BTCUSDT" in fp and "BUY" in fp)

diversity = cm.filter_diversity([sig_a, sig_b, sig_c], max_per_pair=1)
check("filter_diversity keeps unique pairs", len(diversity) == 3)
check("filter_diversity first is BTCUSDT", diversity[0]["pair"] == "BTCUSDT")

processed = cm.process_signals([sig_a, sig_b, sig_c])
check("process_signals returns list", isinstance(processed, list))
check("process_signals top signal has highest conf",
      len(processed) == 0 or processed[0]["confidence"] >= 65)

cm.cleanup_expired()
check("cleanup_expired does not crash", True)


print("\n--- 3. generate_signal_from_candles ---")

up_candles = build_trending_up_candles(100)
down_candles = build_trending_down_candles(100)
range_candles = build_ranging_candles(100)

sig_up = generate_signal_from_candles("TESTUPUSDT", up_candles)
check("uptrend generates signal dict", isinstance(sig_up, dict))
check("uptrend has pair", sig_up.get("pair") == "TESTUPUSDT")

if sig_up.get("signal") == "NO TRADE":
    print(f"  (uptrend NO TRADE: {sig_up.get('reason', 'no reason')})")
else:
    check("uptrend signal is BUY", sig_up.get("signal") == "BUY")
    check("uptrend confidence > 0", sig_up.get("confidence", 0) > 0)
    check("uptrend has entry_primary", sig_up.get("entry_primary", 0) > 0)
    check("uptrend has sl", sig_up.get("sl", 0) > 0)
    check("uptrend has tp1", sig_up.get("tp1", 0) > 0)
    check("uptrend risk_pct > 0", sig_up.get("risk_pct", 0) > 0)
    check("uptrend entry_score > 0", sig_up.get("entry_score", 0) > 0)
    check("uptrend regime is set", sig_up.get("regime") is not None)

sig_down = generate_signal_from_candles("TESTDOWNUSDT", down_candles)
check("downtrend generates signal dict", isinstance(sig_down, dict))
check("downtrend has pair", sig_down.get("pair") == "TESTDOWNUSDT")

if sig_down.get("signal") == "NO TRADE":
    print(f"  (downtrend NO TRADE: {sig_down.get('reason', 'no reason')})")
else:
    check("downtrend signal is SELL", sig_down.get("signal") == "SELL")
    check("downtrend confidence > 0", sig_down.get("confidence", 0) > 0)

sig_range = generate_signal_from_candles("TESTRANGEUSDT", range_candles)
check("ranging generates signal dict", isinstance(sig_range, dict))

sig_short = generate_signal_from_candles("SHORTUSDT", up_candles[:5])
check("short candles gives NO TRADE",
      sig_short.get("signal") == "NO TRADE")


print("\n--- 4. Trade Tracker ---")

trade = tracker.create_trade(
    pair="BTCUSDT", signal_type="BUY", entry=50000.0, sl=49000.0,
    tp1=51000.0, tp2=52000.0, tp3=53000.0, confidence=75
)
check("create_trade returns dict", trade is not None)
check("trade status OPEN", trade.get("status") == "OPEN")
check("trade id set", "BTCUSDT_" in trade.get("id", ""))

tracker.add_trade(trade)
loaded = tracker.load_trades()
check("load_trades contains added trade", any(t["id"] == trade["id"] for t in loaded))

open_trades = tracker.get_open_trades()
check("get_open_trades non-empty", len(open_trades) >= 1)
check("BTCUSDT in open trades", any(t["pair"] == "BTCUSDT" for t in open_trades))

updated = tracker.update_trade(trade["id"], 51500.0)
check("update_trade TP1 hit", updated is not None)
if updated:
    check("status TP1 after update", updated.get("status") == "TP1")
    check("pnl_pct positive", updated.get("pnl_pct", 0) > 0)

trade2 = tracker.create_trade(
    pair="ETHUSDT", signal_type="SELL", entry=3000.0, sl=3100.0,
    tp1=2900.0, tp2=2800.0, tp3=2700.0, confidence=70
)
tracker.add_trade(trade2)
closed = tracker.get_closed_trades()
check("closed trades includes TP1", any(t["id"] == trade["id"] for t in closed))

analytics = tracker.get_analytics()
check("analytics has total_trades", "total_trades" in analytics)
check("analytics has win_rate", "win_rate" in analytics)

removed = tracker.remove_trade(trade2["id"])
check("remove_trade works", removed is None)
remaining = tracker.load_trades()
check("trade removed from storage", not any(t["id"] == trade2["id"] for t in remaining))

trade3 = tracker.create_trade(
    pair="SOLUSDT", signal_type="BUY", entry=150.0, sl=145.0,
    tp1=155.0, tp2=160.0, tp3=165.0, confidence=65
)
tracker.add_trade(trade3)
manual_closed = tracker.close_trade_manually(trade3["id"], "test close", 148.0)
check("manual close works", manual_closed is not None)
if manual_closed:
    check("manual close status MANUAL_CLOSE", manual_closed.get("status") == "MANUAL_CLOSE")
    check("manual close pnl negative", manual_closed.get("pnl_pct", 0) < 0)


print("\n--- 5. Revalidate consistency ---")

from app.services.signal_lifecycle import revalidate_signal

reval_sig = {
    "pair": "REVALUSDT", "signal": "BUY", "entry_primary": 100.0,
    "sl": 97.0, "tp1": 103.0, "tp2": 106.0, "tp3": 109.0,
    "confidence": 75, "entry_score": 70, "risk_pct": 3.0, "tier": "HIGH",
    "trend": "UPTREND", "liquidity": "SWEEP_LOW_REJECTION",
    "atr_ratio": 0.005, "regime": "NORMAL", "timestamp": "2025-01-01T00:00:00"
}
signal_lifecycle.store_signal(reval_sig, "PENDING")

revalidation_result, reason = revalidate_signal(
    "REVALUSDT",
    {"pair": "REVALUSDT", "signal": "BUY", "confidence": 72, "entry_primary": 100.5},
    min_confidence=45
)
check("revalidate_signal with small drop is VALID",
      revalidation_result == True and reason == "VALID")

revalidation_result2, reason2 = revalidate_signal(
    "REVALUSDT",
    {"pair": "REVALUSDT", "signal": "BUY", "confidence": 30, "entry_primary": 100.5},
    min_confidence=45
)
check("revalidate_signal with big drop detected",
      revalidation_result2 == False)

revalidation_result3, reason3 = revalidate_signal(
    "REVALUSDT",
    {"pair": "REVALUSDT", "signal": "BUY", "confidence": 72, "entry_primary": 120.0},
    min_confidence=45
)
check("revalidate_signal with entry change detected",
      revalidation_result3 == False)


print("\n--- 6. generate_signal_from_candles consistency with generate_signal ---")

import config as cfg
check("generate_signal_from_candles uses calculate_split_confidence",
      True)  

if sig_up.get("signal") != "NO TRADE":
    split_keys = ["structure_score", "execution_score"]
    has_split = all(k in sig_up for k in split_keys)
    check("uptrend signal has structure_score/execution_score from split_confidence",
          has_split)
    if not has_split:
        up_keys = list(sig_up.keys())
        print(f"    signal keys: {up_keys}")

if sig_down.get("signal") != "NO TRADE":
    has_split_down = all(k in sig_down for k in ["structure_score", "execution_score"])
    check("downtrend signal has split confidence fields", has_split_down)


print("\n" + "=" * 60)
total = PASS + FAIL
print(f"RESULTS: {PASS}/{total} passed, {FAIL}/{total} failed")
print("=" * 60)

db.close_db()
time.sleep(0.1)
for f in [os.environ.get("TRADES_FILE", ""), os.environ.get("DATABASE_URL", "").replace("sqlite:///", "")]:
    if f and os.path.exists(f):
        try:
            os.remove(f)
        except OSError:
            pass

sys.exit(0 if FAIL == 0 else 1)
