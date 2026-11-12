"""Central validated settings management."""
from decimal import Decimal
from .storage import Storage
from .config import settings
from .secrets import SecretBox


# secret name -> (api_key name, api_secret name)
CREDENTIAL_KEYS = {
    "live": ("binance_api_key", "binance_api_secret"),
    "testnet": ("binance_testnet_api_key", "binance_testnet_api_secret"),
}

class SettingsManager:
    def __init__(self, storage: Storage, secret_box: SecretBox | None = None):
        self.storage = storage
        self.box = secret_box or SecretBox()

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
        # decrypt persisted binance credentials into the running config
        for network, (key_name, secret_name) in CREDENTIAL_KEYS.items():
            api_key = self._read_secret(key_name)
            api_secret = self._read_secret(secret_name)
            if not (api_key and api_secret):
                continue
            if network == "live":
                settings.binance_api_key = api_key
                settings.binance_api_secret = api_secret
            else:
                settings.binance_testnet_api_key = api_key
                settings.binance_testnet_api_secret = api_secret

    # ---------- encrypted Binance credentials ----------
    def _read_secret(self, name: str) -> str:
        row = self.storage.get_secret(name)
        if not row:
            return ""
        try:
            return self.box.decrypt(row["ciphertext"])
        except Exception:
            return ""

    def _mask(self, value: str) -> str:
        if not value:
            return ""
        return "****" + value[-4:] if len(value) > 4 else "****"

    def _network_status(self, network: str) -> dict:
        key_name, secret_name = CREDENTIAL_KEYS[network]
        key_row = self.storage.get_secret(key_name)
        secret_row = self.storage.get_secret(secret_name)
        api_key = self._read_secret(key_name)
        return {
            "configured": bool(key_row and secret_row),
            "api_key_last4": self._mask(api_key),
            "updated_at": (key_row or {}).get("updated_at"),
        }

    def get_binance_status(self) -> dict:
        if settings.testnet_execution_ready:
            execution_mode = "binance-demo"
        elif settings.live_authorized:
            execution_mode = "binance-live"
        else:
            execution_mode = "simulated"
        return {
            "encryption_available": self.box.available,
            "active_network": settings.binance_environment,
            "trading_mode": settings.normalized_mode,
            "live_trading_enabled": settings.live_trading_enabled,
            "execution_mode": execution_mode,
            "testnet": self._network_status("testnet"),
            "live": self._network_status("live"),
        }

    def save_binance_credentials(self, api_key: str, api_secret: str, network: str = "testnet") -> dict:
        network = (network or "testnet").strip().lower()
        if network not in CREDENTIAL_KEYS:
            return {"ok": False, "error": "network must be 'testnet' or 'live'"}
        api_key = str(api_key or "").strip()
        api_secret = str(api_secret or "").strip()
        if len(api_key) < 8 or len(api_secret) < 8:
            return {"ok": False, "error": "API key and secret must be at least 8 characters"}
        if len(api_key) > 512 or len(api_secret) > 512:
            return {"ok": False, "error": "API key or secret is too long"}
        if not self.box.available:
            return {"ok": False, "error": "encryption unavailable; set SETTINGS_ENCRYPTION_KEY"}
        try:
            key_blob = self.box.encrypt(api_key)
            secret_blob = self.box.encrypt(api_secret)
        except Exception as exc:
            return {"ok": False, "error": f"encryption failed: {exc}"}
        key_name, secret_name = CREDENTIAL_KEYS[network]
        self.storage.set_secret(key_name, key_blob)
        self.storage.set_secret(secret_name, secret_blob)
        if network == "live":
            settings.binance_api_key = api_key
            settings.binance_api_secret = api_secret
        else:
            settings.binance_testnet_api_key = api_key
            settings.binance_testnet_api_secret = api_secret
        return {"ok": True, "network": network, "status": self.get_binance_status()}

    def clear_binance_credentials(self, network: str = "testnet") -> dict:
        network = (network or "testnet").strip().lower()
        if network not in CREDENTIAL_KEYS:
            return {"ok": False, "error": "network must be 'testnet' or 'live'"}
        key_name, secret_name = CREDENTIAL_KEYS[network]
        self.storage.delete_secret(key_name)
        self.storage.delete_secret(secret_name)
        if network == "live":
            settings.binance_api_key = ""
            settings.binance_api_secret = ""
        else:
            settings.binance_testnet_api_key = ""
            settings.binance_testnet_api_secret = ""
        return {"ok": True, "network": network, "status": self.get_binance_status()}

    def get_credentials(self, network: str = "testnet") -> tuple[str, str]:
        network = (network or "testnet").strip().lower()
        if network not in CREDENTIAL_KEYS:
            return "", ""
        key_name, secret_name = CREDENTIAL_KEYS[network]
        return self._read_secret(key_name), self._read_secret(secret_name)

    def test_binance_connection(self, network: str = "testnet",
                                api_key: str | None = None,
                                api_secret: str | None = None) -> dict:
        """Read-only signed check. Never places an order."""
        network = (network or "testnet").strip().lower()
        if network not in CREDENTIAL_KEYS:
            return {"ok": False, "network": network, "error": "network must be 'testnet' or 'live'"}
        if api_key is None or api_secret is None:
            api_key, api_secret = self.get_credentials(network)
        api_key = (api_key or "").strip()
        api_secret = (api_secret or "").strip()
        if not api_key or not api_secret:
            return {"ok": False, "network": network, "error": "no credentials configured"}
        try:
            from .binance_client import BinanceClient
        except Exception as exc:
            return {"ok": False, "network": network, "error": f"client unavailable: {exc}"}
        client = BinanceClient(api_key=api_key, api_secret=api_secret, testnet=(network == "testnet"))
        try:
            client.sync_time()
            account = client.account()
        except Exception as exc:
            message = str(exc).replace(api_secret, "***").replace(api_key, "***")
            return {"ok": False, "network": network, "error": message[:300]}
        finally:
            try:
                client.close()
            except Exception:
                pass
        can_trade = bool(account.get("canTrade"))
        can_withdraw = bool(account.get("canWithdraw"))
        return {
            "ok": True,
            "network": network,
            "can_trade": can_trade,
            "can_withdraw": can_withdraw,
            "can_deposit": bool(account.get("canDeposit")),
            "account_type": account.get("accountType"),
            "total_wallet_balance": account.get("totalWalletBalance"),
            "available_balance": account.get("availableBalance"),
            "warning": "API key has withdrawal permission; disable it." if can_withdraw else "",
        }

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
