"""Multi-symbol market scanner."""
import time
import logging
from decimal import Decimal
from .binance_client import BinanceClient
from .signal_engine import SignalEngine
from .storage import Storage
from .config import settings
from .rug_check import RugChecker

log = logging.getLogger("scanner")


class Scanner:
    def __init__(self, client: BinanceClient, storage: Storage, symbols: list[str] | None = None):
        self.client = client
        self.storage = storage
        self.symbols = symbols or settings.symbol_list
        self.sig_engine = SignalEngine(cooldown_seconds=settings.signal_cooldown_seconds)
        self.rug = RugChecker()

    def set_symbols(self, symbols: list[str]):
        self.symbols = [s.strip().upper() for s in symbols if s.strip()]

    def scan_symbol(self, symbol: str) -> dict:
        result = {"symbol": symbol, "status": "ok", "signal": None, "risk": None, "error": None}
        try:
            kl = self.client.klines(symbol, settings.timeframe, 200)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            self.storage.log_event("SCANNER", symbol, "scan", "error", str(e))
            self.storage.upsert_agent_status("SCANNER", "ERROR", current_activity=f"{symbol} fetch failed", error_message=str(e))
            return result

        if not kl or len(kl) < 60:
            result["status"] = "insufficient_data"
            result["error"] = "insufficient candles"
            self.storage.log_event("SCANNER", symbol, "scan", "skipped", "insufficient data")
            return result

        # signal
        try:
            cct = kl[-2][0] + ({"1m":60000,"3m":180000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000}.get(settings.timeframe, 900000))
            sig = self.sig_engine.evaluate_klines(symbol, settings.timeframe, kl, candle_close_time=cct)
            if sig is not None:
                if self.storage.is_signal_seen(sig.signal_id):
                    result["signal"] = {"duplicate": True, "signal_id": sig.signal_id}
                else:
                    self.storage.mark_signal_seen(sig.signal_id)
                    # Save scanner result
                    import json
                    ind = {"rsi": str(sig.rsi_value), "ema_fast": str(sig.ema_fast), "ema_slow": str(sig.ema_slow),
                           "ema_50": str(sig.ema_50), "macd": str(sig.macd), "atr": str(sig.atr),
                           "volume_ratio": str(sig.volume_ratio)}
                    self.storage.save_scanner_result(symbol, sig.direction, str(sig.entry_price), str(sig.stop_loss),
                                                    str(sig.take_profit), sig.score, ind, sig.explanation, sig.candle_close_time)
                    self.storage.log_event("SCANNER", symbol, "signal", sig.direction, sig.explanation)
                    result["signal"] = {
                        "direction": sig.direction,
                        "entry_price": str(sig.entry_price),
                        "stop_loss": str(sig.stop_loss),
                        "take_profit": str(sig.take_profit),
                        "score": sig.score,
                        "explanation": sig.explanation,
                        "indicators": ind,
                    }
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            self.storage.log_event("SCANNER", symbol, "scan", "error", str(e))

        # rug check
        try:
            risk = self.rug.assess(symbol, kl)
            self.storage.save_risk_assessment(symbol, risk["risk_rating"], risk["reasons"], risk["warnings"], risk["metrics"])
            result["risk"] = risk
        except Exception as e:
            result["risk"] = {"error": str(e)}

        return result

    def scan_once(self) -> list[dict]:
        self.storage.upsert_agent_status("SCANNER", "SCANNING", current_activity="scanning symbols")
        self.storage.log_event("SCANNER", "", "scan", "started", f"symbols={len(self.symbols)}")
        results = []
        for sym in self.symbols:
            try:
                r = self.scan_symbol(sym)
                results.append(r)
            except Exception as e:
                results.append({"symbol": sym, "status": "error", "error": str(e)})
        self.storage.upsert_agent_status("SCANNER", "IDLE", current_activity="scan complete", last_success=True)
        self.storage.log_event("SCANNER", "", "scan", "completed", f"scanned={len(results)}")
        return results