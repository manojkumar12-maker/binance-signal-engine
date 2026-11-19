"""Tests for risk-control and execution hardening fixes."""
import os
import tempfile
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.config import settings
from src.kill_switch import KillSwitch
from src.backtest import BacktestConfig, walk_forward
from src.paper_trading import PaperTrader
from src.sizer import Sizer
from src.storage import Storage
from src.scanner import Scanner


def _storage():
    return Storage(path=os.path.join(tempfile.mkdtemp(), "h.db"))


class _NoPriceClient:
    def ticker_price(self, symbol):
        return None


def _candles(count=100):
    rows = []
    for i in range(count):
        base = Decimal("100") + Decimal(i)
        rows.append([i * 300000, str(base), str(base + 1), str(base - 1), str(base), "1000"])
    return rows


class _FreshnessMarketData:
    def __init__(self, updated_at, candles=None):
        self._updated_at = updated_at
        self._candles = candles or _candles()

    def get_universe(self):
        return ["BTCUSDT"]

    def get_klines(self, symbol, interval):
        return self._candles

    def updated_at(self, symbol, interval):
        return self._updated_at


# ---------- daily loss budget ----------
def test_daily_loss_limit_uses_tighter_of_pct_and_absolute(monkeypatch):
    st = _storage()
    kill = KillSwitch(st)
    monkeypatch.setattr(settings, "simulated_starting_balance", Decimal("30"))
    monkeypatch.setattr(settings, "max_daily_loss_pct", Decimal("0.01"))  # 0.30
    monkeypatch.setattr(settings, "max_daily_loss_usdt", Decimal("0.10"))
    kill.ensure_day_start_equity(Decimal("30"))
    assert kill.daily_loss_limit() == Decimal("0.10")
    assert kill.day_start_equity() == Decimal("30")


def test_daily_loss_halts_at_effective_limit(monkeypatch):
    st = _storage()
    kill = KillSwitch(st)
    monkeypatch.setattr(settings, "simulated_starting_balance", Decimal("30"))
    monkeypatch.setattr(settings, "max_daily_loss_pct", Decimal("0.01"))
    monkeypatch.setattr(settings, "max_daily_loss_usdt", Decimal("0.10"))
    kill.ensure_day_start_equity(Decimal("30"))
    kill.record_trade_result(Decimal("-0.06"))
    assert kill.is_halted()[0] is False
    kill.record_trade_result(Decimal("-0.05"))
    assert kill.is_halted()[0] is True


def test_entries_per_day_blocks_sizer(monkeypatch):
    monkeypatch.setattr(settings, "max_new_entries_per_day", 1)
    d = Sizer().calculate(
        "BTCUSDT", "LONG", "50000", "49000", "53000", "5",
        rug_rating="LOW", entries_today=1,
    )
    assert d.approved is False
    assert "entries per day" in d.reason


# ---------- paper accounting ----------
def test_paper_close_does_not_double_count_slippage(monkeypatch):
    st = _storage()
    monkeypatch.setattr(settings, "estimated_slippage", Decimal("0.001"))
    monkeypatch.setattr(settings, "estimated_maker_fee", Decimal("0.0002"))
    monkeypatch.setattr(settings, "estimated_taker_fee", Decimal("0.0005"))
    pt = PaperTrader(st)
    pos = pt.open_position(
        _NoPriceClient(),
        {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "100",
         "stop_loss": "90", "take_profit": "120"},
        SimpleNamespace(quantity=Decimal("1")),
        None,
    )
    assert pos["ok"] is True
    entry = Decimal("100") * (Decimal("1") + Decimal("0.001"))
    exit_price = Decimal("110") * (Decimal("1") - Decimal("0.001"))
    expected_fees = entry * Decimal("0.0005") + exit_price * Decimal("0.0005")
    res = pt.close_position(pos["trade_id"], "110", "manual")
    assert res["ok"] is True
    assert Decimal(res["fees"]) == expected_fees


def test_paper_allows_second_symbol_under_position_cap(monkeypatch):
    st = _storage()
    monkeypatch.setattr(settings, "max_simultaneous_positions", 2)
    st.open_trade({"symbol": "ETHUSDT", "direction": "LONG", "entry_price": "2000",
                   "stop_loss": "1900", "take_profit": "2200", "quantity": "0.01"})
    pt = PaperTrader(st)
    res = pt.open_position(
        _NoPriceClient(),
        {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "100",
         "stop_loss": "90", "take_profit": "120"},
        SimpleNamespace(quantity=Decimal("1")),
        None,
    )
    assert res["ok"] is True
    again = pt.open_position(
        _NoPriceClient(),
        {"symbol": "BTCUSDT", "direction": "LONG", "entry_price": "100",
         "stop_loss": "90", "take_profit": "120"},
        SimpleNamespace(quantity=Decimal("1")),
        None,
    )
    assert again["ok"] is False
    assert "symbol" in again["reason"]


# ---------- scanner freshness and pump dedupe ----------
def test_scanner_skips_stale_cache():
    st = _storage()
    scanner = Scanner(None, st, ["BTCUSDT"], market_data=_FreshnessMarketData(updated_at=1.0))
    result = scanner.scan_symbol("BTCUSDT")
    assert result["status"] == "stale_data"


def test_scanner_pump_event_not_duplicated_for_same_candle():
    st = _storage()
    scanner = Scanner(None, st, ["BTCUSDT"])
    kl = [[i * 300000, "100", "101", "99", "100", "100"] for i in range(25)]
    kl[-2] = [23 * 300000, "100", "112", "99", "109", "5000"]
    kl[-1] = [24 * 300000, "109", "110", "108", "109", "100"]
    first = scanner._detect_pump("BTCUSDT", kl)
    second = scanner._detect_pump("BTCUSDT", kl)
    assert first is not None
    assert second is None


# ---------- walk-forward ----------
def test_walk_forward_splits_are_disjoint_out_of_sample():
    klines = [[1_600_000_000_000 + i * 900_000,
               str(100 + i), str(101 + i), str(99 + i), str(100 + i), "1000"]
              for i in range(400)]
    rep = walk_forward("BTCUSDT", klines, None, n_splits=3,
                       cfg=BacktestConfig(min_history=60))
    assert rep["mode"] == "walk_forward"
    ranges = [s["split"] for s in rep["splits"]]
    assert ranges == ["0..133", "133..266", "266..400"]
    starts = [s["eval_start_ts"] for s in rep["splits"]]
    assert starts[0] == 0
    assert starts[1] == klines[133][0]
    assert starts[2] == klines[266][0]
