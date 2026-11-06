"""Central validated settings management."""
from decimal import Decimal
from .storage import Storage
from .config import settings


class SettingsManager:
    def __init__(self, storage: Storage):
        self.storage = storage

    def _get(self, key, default=None):
        v = self.storage.get_setting(key)
        return v if v is not None else default

    def load_into_settings(self):
        # apply persisted settings to settings object if present
        try:
            if self.storage.get_setting("risk_per_trade_pct") is not None:
                settings.risk_per_trade_pct = Decimal(self.storage.get_setting("risk_per_trade_pct"))
        except Exception:
            pass
        try:
            if self.storage.get_setting("max_daily_loss_pct") is not None:
                settings.max_daily_loss_pct = Decimal(self.storage.get_setting("max_daily_loss_pct"))
        except Exception:
            pass
        try:
            syms = self.storage.get_setting("scanner_symbols")
            if syms:
                settings.symbols = syms
        except Exception:
            pass

    def get_all(self):
        return {
            "trading_mode": settings.normalized_mode,
            "scanner_symbols": settings.symbol_list,
            "scan_interval_seconds": settings.scan_interval_seconds,
            "risk_per_trade_pct": str(settings.risk_per_trade_pct),
            "max_daily_loss_pct": str(settings.max_daily_loss_pct),
            "max_concurrent_positions": settings.max_simultaneous_positions,
            "default_leverage": settings.max_leverage,
            "estimated_maker_fee": str(settings.estimated_maker_fee),
            "estimated_taker_fee": str(settings.estimated_taker_fee),
            "estimated_slippage": str(settings.estimated_slippage),
            "log_retention_days": 30,
            "equity_snapshot_interval": 300,
        }

    def validate_and_set(self, data: dict):
        errors = []
        # trading mode: never allow live via dashboard
        if "trading_mode" in data:
            mode = str(data["trading_mode"]).lower()
            if mode in ("live",):
                errors.append("LIVE cannot be activated via dashboard")
            elif mode in ("paper", "demo", "testnet"):
                # don't change settings.trading_mode? allow paper/testnet
                if mode == "demo":
                    mode = "paper"
                settings.trading_mode = mode
                self.storage.set_setting("trading_mode", mode)
            else:
                errors.append("invalid trading mode")

        if "scanner_symbols" in data:
            syms = data["scanner_symbols"]
            if isinstance(syms, str):
                syms = [s.strip() for s in syms.split(",") if s.strip()]
            if not isinstance(syms, list) or not syms:
                errors.append("scanner_symbols must be non-empty list")
            else:
                syms = [str(s).strip().upper() for s in syms]
                settings.symbols = ",".join(syms)
                self.storage.set_setting("scanner_symbols", ",".join(syms))

        if "scan_interval_seconds" in data:
            v = int(data["scan_interval_seconds"])
            if v < 10 or v > 3600:
                errors.append("scan_interval_seconds out of range")
            else:
                settings.scan_interval_seconds = v

        if "risk_per_trade_pct" in data:
            v = Decimal(str(data["risk_per_trade_pct"]))
            if v < Decimal("0.0001") or v > Decimal("0.05"):
                errors.append("risk_per_trade_pct out of range")
            else:
                settings.risk_per_trade_pct = v
                self.storage.set_setting("risk_per_trade_pct", str(v))

        if "max_daily_loss_pct" in data:
            v = Decimal(str(data["max_daily_loss_pct"]))
            if v < Decimal("0.001") or v > Decimal("0.1"):
                errors.append("max_daily_loss_pct out of range")
            else:
                settings.max_daily_loss_pct = v
                self.storage.set_setting("max_daily_loss_pct", str(v))

        if "max_concurrent_positions" in data:
            v = int(data["max_concurrent_positions"])
            if v < 1 or v > 5:
                errors.append("max_concurrent_positions out of range")
            else:
                settings.max_simultaneous_positions = v

        if "default_leverage" in data:
            v = int(data["default_leverage"])
            if v < 1 or v > 5:
                errors.append("default_leverage out of range")
            else:
                settings.max_leverage = v

        if errors:
            return {"ok": False, "errors": errors}
        self.storage.log_admin_action("settings_update", details=str(data))
        return {"ok": True, "errors": []}