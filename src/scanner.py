"""Multi-symbol, multi-timeframe market scanner with signal diagnostics."""
import time
import json
import logging
import os
from decimal import Decimal
from .binance_client import BinanceClient
from .signal_engine import SignalEngine
from .storage import Storage
from .config import settings
from .rug_check import RugChecker

log = logging.getLogger("scanner")

INTERVAL_MS = {"1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000, "30m": 1800000, "1h": 3600000}


class Scanner:
    def __init__(self, client: BinanceClient, storage: Storage, symbols: list[str] | None = None,
                 market_data=None):
        self.client = client
        self.storage = storage
        self.market_data = market_data
        self._manual_symbols = symbols is not None
        self.symbols = symbols or (market_data.get_universe() if market_data else None) or settings.symbol_list
        self.sig_engine = SignalEngine(cooldown_seconds=settings.signal_cooldown_seconds, cfg=settings)
        self.rug = RugChecker()
        self.engine_version = getattr(settings, "signal_engine_version", "v2")
        self.top_n = int(os.getenv("SCAN_TOP_N", "30"))
        self._discovered_at = 0.0
        self._discovered = None

    def discover_symbols(self) -> list[str]:
        # Auto-discover the most liquid USDT-M perpetuals by 24h quote volume.
        now = time.time()
        if self._discovered and (now - self._discovered_at) < 3600:
            return self._discovered
        try:
            info = self.client.exchange_info()
            trading = {s["symbol"] for s in info.get("symbols", [])
                       if s.get("status") == "TRADING"
                       and s.get("contractType") == "PERPETUAL"
                       and s.get("quoteAsset") == "USDT"}
            tickers = self.client.ticker_24hr()
            ranked = sorted((t for t in tickers if t.get("symbol") in trading),
                            key=lambda t: float(t.get("quoteVolume", 0) or 0), reverse=True)
            syms = [t["symbol"] for t in ranked[:self.top_n]]
            if syms:
                self._discovered = syms
                self._discovered_at = now
                self.symbols = syms
                self.storage.log_event("SCANNER", "", "discover", "ok", f"top{len(syms)} by volume")
                return syms
        except Exception as e:
            log.warning("symbol discovery failed: %s", e)
            self.storage.log_event("SCANNER", "", "discover", "error", str(e))
        return self.symbols

    def set_symbols(self, symbols: list[str]):
        self._manual_symbols = True
        self.symbols = [s.strip().upper() for s in symbols if s.strip()]

    def _resolve_symbols(self) -> list[str]:
        if self._manual_symbols:
            return self.symbols
        if not self.market_data:
            return self.discover_symbols()
        try:
            universe = self.market_data.get_universe()
        except Exception as e:
            log.warning("universe unavailable: %s", e)
            universe = None
        return universe or self.symbols

    def _get_klines(self, symbol: str, interval: str, limit: int):
        if self.market_data is not None:
            return self.market_data.get_klines(symbol, interval) or None
        return self._klines_safe(symbol, interval, limit)

    # ---- dynamic symbol selection (top liquid USDT-M perps) ----
    def refresh_symbols(self, count: int | None = None) -> list[str]:
        if not getattr(settings, "dynamic_symbols_enabled", False):
            return self.symbols
        n = count or getattr(settings, "scan_symbol_count", 20)
        try:
            tickers = self.client._request("GET", "/fapi/v1/ticker/24hr")
            info = self.client.exchange_info()
        except Exception as e:
            log.warning("dynamic symbol refresh failed: %s; keeping static list", e)
            return self.symbols
        status = {s["symbol"]: s.get("status") for s in info.get("symbols", [])}
        min_qv = Decimal(str(getattr(settings, "min_quote_volume_usdt", Decimal("50000000"))))
        rows = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("USDT") or status.get(sym) != "TRADING":
                continue
            try:
                qv = Decimal(str(t.get("quoteVolume", "0")))
            except Exception:
                continue
            if qv < min_qv:
                continue
            rows.append((sym, qv))
        rows.sort(key=lambda x: x[1], reverse=True)
        selected = [s for s, _ in rows[:n]]
        if selected:
            self.symbols = selected
            self.storage.log_event("SCANNER", "", "symbols", "refreshed", f"{len(selected)} symbols")
        return self.symbols

    def _klines_safe(self, symbol: str, interval: str, limit: int):
        try:
            return self.client.klines(symbol, interval, limit)
        except Exception:
            return None

    def scan_symbol(self, symbol: str) -> dict:
        result = {"symbol": symbol, "status": "ok", "signal": None, "risk": None, "error": None, "diagnostic": None}
        best_score = 0.0
        htf = settings.timeframe
        ltf = getattr(settings, "entry_timeframe", "5m")

        kl_htf = self._get_klines(symbol, htf, 250)
        if kl_htf is None:
            if self.market_data is not None:
                result["status"] = "waiting_for_data"
                result["error"] = "market data not loaded yet"
                return result
            result["status"] = "error"
            result["error"] = "htf fetch failed"
            self.storage.log_event("SCANNER", symbol, "scan", "error", "htf fetch failed")
            self.storage.upsert_agent_status("SCANNER", "ERROR", current_activity=f"{symbol} fetch failed", error_message="htf fetch failed")
            return result
        if len(kl_htf) < 61:
            result["status"] = "insufficient_data"
            result["error"] = "insufficient candles"
            self.storage.log_event("SCANNER", symbol, "scan", "skipped", "insufficient data")
            return result

        kl_ltf = None
        if ltf != htf:
            kl_ltf = self._get_klines(symbol, ltf, 250)
            if kl_ltf is not None and len(kl_ltf) < 61:
                kl_ltf = None  # fallback to HTF-only

        # ---- signal evaluation ----
        sig, diag = None, None
        try:
            if self.engine_version == "v2":
                sig, diag = self.sig_engine.evaluate_v2(symbol, kl_htf, kl_ltf, htf=htf, ltf=ltf)
            else:
                cct = kl_htf[-2][0] + INTERVAL_MS.get(htf, 900000)
                sig = self.sig_engine.evaluate_klines(symbol, htf, kl_htf, candle_close_time=cct)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            self.storage.log_event("SCANNER", symbol, "scan", "error", str(e))

        if diag is not None:
            result["diagnostic"] = diag.to_dict()
            le = result["diagnostic"].get("long_eval") or {}
            se = result["diagnostic"].get("short_eval") or {}
            best_score = max(le.get("score", 0) or 0, se.get("score", 0) or 0)
            should_save = (self.market_data is None
                           or getattr(settings, "persist_all_diagnostics", False)
                           or sig is not None
                           or best_score >= 60)
            if should_save:
                try:
                    self.storage.save_signal_diagnostic(diag)
                except Exception as e:
                    log.warning("diagnostic save failed: %s", e)

        if sig is not None:
            if self.storage.is_signal_seen(sig.signal_id):
                result["signal"] = {"duplicate": True, "signal_id": sig.signal_id}
            else:
                self.storage.mark_signal_seen(sig.signal_id)
                ind_dict = {"rsi": str(sig.rsi_value), "ema_fast": str(sig.ema_fast), "ema_slow": str(sig.ema_slow),
                            "ema_50": str(sig.ema_50), "macd": str(sig.macd), "atr": str(sig.atr),
                            "volume_ratio": str(sig.volume_ratio), "adx": str(sig.adx), "vwap": str(sig.vwap)}
                self.storage.save_scanner_result(symbol, sig.direction, str(sig.entry_price), str(sig.stop_loss),
                                                 str(sig.take_profit), sig.score, ind_dict, sig.explanation, sig.candle_close_time)
                self.storage.log_event("SCANNER", symbol, "signal", sig.direction, f"[{sig.strategy}/{sig.regime}] {sig.explanation}")
                result["signal"] = {
                    "signal_id": sig.signal_id,
                    "direction": sig.direction,
                    "entry_price": str(sig.entry_price),
                    "stop_loss": str(sig.stop_loss),
                    "take_profit": str(sig.take_profit),
                    "score": sig.score,
                    "strategy": sig.strategy,
                    "regime": sig.regime,
                    "explanation": sig.explanation,
                    "indicators": ind_dict,
                }

        # ---- rug check (preserved) ----
        try:
            risk = self.rug.assess(symbol, kl_htf)
            rating = risk.get("risk_rating", "UNKNOWN")
            persist_risk = (self.market_data is None
                            or getattr(settings, "persist_all_diagnostics", False)
                            or sig is not None
                            or best_score >= 60
                            or rating == "HIGH")
            if persist_risk:
                self.storage.save_risk_assessment(symbol, rating, risk["reasons"], risk["warnings"], risk["metrics"])
            result["risk"] = risk
        except Exception as e:
            result["risk"] = {"error": str(e)}

        return result

    def scan_once(self) -> list[dict]:
        symbols = self._resolve_symbols()
        self.storage.upsert_agent_status("SCANNER", "SCANNING", current_activity=f"scanning {len(symbols)} symbols")
        self.storage.log_event("SCANNER", "", "scan", "started", f"symbols={len(symbols)}")
        results = []
        for sym in symbols:
            try:
                r = self.scan_symbol(sym)
                results.append(r)
            except Exception as e:
                results.append({"symbol": sym, "status": "error", "error": str(e)})
        stats = self._scan_stats(results)
        try:
            self.storage.save_scan_stats(stats)
        except Exception as e:
            log.warning("scan stats save failed: %s", e)
        self.storage.upsert_agent_status("SCANNER", "IDLE", current_activity="scan complete", last_success=True)
        self.storage.log_event("SCANNER", "", "scan", "completed",
                               f"scanned={len(results)} signals={stats['qualified']} watchlist={stats['watchlist']}")
        return results

    def _scan_stats(self, results: list[dict]) -> dict:
        total = len(results)
        qualified = watchlist = errors = 0
        long_scores, short_scores = [], []
        for r in results:
            if r.get("status") == "error":
                errors += 1
            d = r.get("diagnostic") or {}
            if r.get("signal") and not r["signal"].get("duplicate"):
                qualified += 1
            le, se = d.get("long_eval") or {}, d.get("short_eval") or {}
            if le.get("score") is not None:
                long_scores.append(le["score"])
            if se.get("score") is not None:
                short_scores.append(se["score"])
            best = max(le.get("score", 0), se.get("score", 0))
            if 60 <= best < float(getattr(settings, "min_signal_score", 75)):
                watchlist += 1
        return {
            "ts": time.time(),
            "total_scans": total,
            "qualified": qualified,
            "watchlist": watchlist,
            "errors": errors,
            "avg_long_score": sum(long_scores) / len(long_scores) if long_scores else 0.0,
            "avg_short_score": sum(short_scores) / len(short_scores) if short_scores else 0.0,
        }
