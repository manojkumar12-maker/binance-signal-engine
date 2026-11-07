"""Tests for full-universe market data ingestion and cached scanning."""
import os
import tempfile
from decimal import Decimal

from src.market_data import MarketDataService, WeightLimiter
from src.scanner import Scanner
from src.storage import Storage


def _klines(count=100):
    rows = []
    for i in range(count):
        o = Decimal("100") + Decimal(i)
        c = o + Decimal("0.5")
        rows.append([i * 300000, str(o), str(c + Decimal("0.2")), str(o - Decimal("0.2")), str(c), "1000"])
    return rows


class FakeClient:
    def __init__(self):
        self.kline_calls = 0

    def exchange_info(self):
        return {"symbols": [
            {"symbol": "AAAUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING"},
            {"symbol": "BBBUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING"},
            {"symbol": "CCCUSDT", "quoteAsset": "USDT", "contractType": "CURRENT_QUARTER", "status": "TRADING"},
            {"symbol": "DDDBTC", "quoteAsset": "BTC", "contractType": "PERPETUAL", "status": "TRADING"},
        ]}

    def _request(self, method, path, params=None, signed=False):
        if path == "/fapi/v1/ticker/24hr":
            return [{"symbol": "AAAUSDT", "quoteVolume": "123"}, {"symbol": "BBBUSDT", "quoteVolume": "456"}]
        raise AssertionError(path)

    def klines(self, symbol, interval, limit=100):
        self.kline_calls += 1
        return _klines()


def test_universe_only_usdt_perpetuals():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "md.db"))
    md = MarketDataService(FakeClient(), storage=st, intervals=["15m", "5m"], limit=100, workers=2,
                           weight_per_min=60000)
    assert md.refresh_universe() == ["AAAUSDT", "BBBUSDT"]
    st.close()


def test_refresh_all_persists_every_symbol_and_series():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "md.db"))
    md = MarketDataService(FakeClient(), storage=st, intervals=["15m", "5m"], limit=100, workers=2,
                           weight_per_min=60000)
    md.refresh_universe()
    stats = md.refresh_all()
    assert stats["symbols"] == 2
    assert stats["series"] == 4
    assert stats["errors"] == 0
    assert len(md.get_klines("AAAUSDT", "5m")) == 100
    assert st.market_data_summary()["universe_symbols"] == 2
    st.close()


def test_scanner_reads_cache_for_full_universe():
    d = tempfile.mkdtemp()
    st = Storage(path=os.path.join(d, "md.db"))
    client = FakeClient()
    md = MarketDataService(client, storage=st, intervals=["15m", "5m"], limit=100, workers=2,
                           weight_per_min=60000)
    md.refresh_universe()
    md.refresh_all()
    calls_before = client.kline_calls
    scanner = Scanner(client, st, market_data=md)
    results = scanner.scan_once()
    assert {r["symbol"] for r in results} == {"AAAUSDT", "BBBUSDT"}
    assert client.kline_calls == calls_before
    st.close()


def test_weight_limiter_paces_requests():
    import time
    limiter = WeightLimiter(budget_per_min=600, window_seconds=60)  # 10 per second
    started = time.monotonic()
    for _ in range(5):
        limiter.acquire(1)
    # 5 slots at 100ms each -> at least ~0.4s
    assert time.monotonic() - started >= 0.35
