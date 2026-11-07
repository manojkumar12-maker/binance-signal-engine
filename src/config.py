from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    trading_mode: str = Field(default="paper")
    broker_enabled: bool = Field(default=False)
    auto_trade: bool = Field(default=False)
    live_trading_enabled: bool = Field(default=False)
    use_testnet: bool = Field(default=True)

    binance_api_key: str = Field(default="")
    binance_api_secret: str = Field(default="")
    binance_testnet_api_key: str = Field(default="")
    binance_testnet_api_secret: str = Field(default="")

    simulated_starting_balance: Decimal = Field(default=Decimal("30.0"))
    max_simultaneous_positions: int = Field(default=1)
    max_new_entries_per_day: int = Field(default=1)
    max_daily_loss_usdt: Decimal = Field(default=Decimal("0.10"))
    max_planned_loss_per_trade: Decimal = Field(default=Decimal("0.05"))
    risk_per_trade_pct: Decimal = Field(default=Decimal("0.005"))
    max_daily_loss_pct: Decimal = Field(default=Decimal("0.01"))
    max_leverage: int = Field(default=1)
    cross_margin: bool = Field(default=False)

    estimated_maker_fee: Decimal = Field(default=Decimal("0.0002"))
    estimated_taker_fee: Decimal = Field(default=Decimal("0.0005"))
    estimated_slippage: Decimal = Field(default=Decimal("0.0005"))
    min_reward_to_risk: Decimal = Field(default=Decimal("2.0"))

    symbol: str = Field(default="BTCUSDT")
    symbols: str = Field(default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT")
    timeframe: str = Field(default="15m")
    signal_cooldown_seconds: int = Field(default=3600)
    scan_interval_seconds: int = Field(default=60)

    # Signal Engine V2
    entry_timeframe: str = Field(default="5m")
    dynamic_symbols_enabled: bool = Field(default=False)
    scan_symbol_count: int = Field(default=20)
    min_quote_volume_usdt: Decimal = Field(default=Decimal("50000000"))

    # Market data ingestion (all USDT-M perpetuals)
    scan_all_usdt_perpetuals: bool = Field(default=True)
    market_data_refresh_seconds: int = Field(default=300)
    market_data_limit: int = Field(default=100)
    market_data_workers: int = Field(default=8)
    market_data_weight_per_min: int = Field(default=1200)
    market_data_universe_refresh_seconds: int = Field(default=3600)
    persist_all_diagnostics: bool = Field(default=False)
    max_spread_pct: Decimal = Field(default=Decimal("0.05"))
    min_signal_score: Decimal = Field(default=Decimal("75"))
    strong_signal_score: Decimal = Field(default=Decimal("85"))
    volume_ratio_min: Decimal = Field(default=Decimal("1.2"))
    adx_trend_min: Decimal = Field(default=Decimal("25"))
    adx_strong_min: Decimal = Field(default=Decimal("30"))
    atr_pct_max: Decimal = Field(default=Decimal("5.0"))
    atr_pct_low_liquidity: Decimal = Field(default=Decimal("0.05"))
    max_extended_candle_atr: Decimal = Field(default=Decimal("2.0"))
    sl_atr_mult: Decimal = Field(default=Decimal("1.5"))
    tp_atr_mult: Decimal = Field(default=Decimal("3.0"))
    pullback_tolerance_atr: Decimal = Field(default=Decimal("0.5"))
    breakout_lookback: int = Field(default=20)

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")

    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    database_url: str = Field(default="sqlite:///data/bot.db")

    @field_validator("simulated_starting_balance")
    @classmethod
    def _positive_balance(cls, v):
        if v <= 0:
            raise ValueError("simulated_starting_balance must be positive")
        return v

    @field_validator("max_daily_loss_usdt", "max_planned_loss_per_trade")
    @classmethod
    def _non_negative(cls, v):
        if v < 0:
            raise ValueError("loss budgets must be non-negative")
        return v

    @property
    def normalized_mode(self) -> str:
        # Backward-compatible alias: demo -> paper
        if self.trading_mode == "demo":
            return "paper"
        return self.trading_mode

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    @property
    def paper_mode(self) -> bool:
        return self.normalized_mode == "paper"

    @property
    def testnet_mode(self) -> bool:
        return self.normalized_mode == "testnet"

    @property
    def live_mode(self) -> bool:
        return self.normalized_mode == "live"

    @property
    def live_authorized(self) -> bool:
        # Multiple independent checks required; single flag never enough.
        return (
            self.normalized_mode == "live"
            and self.broker_enabled
            and self.auto_trade
            and self.live_trading_enabled
            and self.use_testnet is False
            and bool(self.binance_api_key)
            and bool(self.binance_api_secret)
        )

    @property
    def credentials(self) -> tuple[str, str]:
        if self.use_testnet or self.normalized_mode != "live":
            return self.binance_testnet_api_key, self.binance_testnet_api_secret
        return self.binance_api_key, self.binance_api_secret

    def fail_closed_if_inconsistent(self) -> None:
        if self.normalized_mode == "live" and not (self.broker_enabled and self.auto_trade and self.live_trading_enabled):
            raise RuntimeError("Inconsistent live-trading configuration; failing closed.")
        if self.normalized_mode == "live" and self.use_testnet:
            raise RuntimeError("Live mode cannot use testnet credentials.")
        if self.normalized_mode not in ("paper", "testnet", "live"):
            raise RuntimeError(f"Unknown trading mode: {self.trading_mode}")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    settings.fail_closed_if_inconsistent()
    return settings