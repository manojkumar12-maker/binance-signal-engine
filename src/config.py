import os
from decimal import Decimal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    trading_mode: str = Field(default="demo")
    broker_enabled: bool = Field(default=False)
    auto_trade: bool = Field(default=False)
    live_trading_enabled: bool = Field(default=False)
    use_testnet: bool = Field(default=True)

    binance_api_key: str = Field(default="")
    binance_api_secret: str = Field(default="")
    binance_testnet_api_key: str = Field(default="")
    binance_testnet_api_secret: str = Field(default="")

    simulated_starting_balance: Decimal = Field(default=Decimal("5.0"))
    max_simultaneous_positions: int = Field(default=1)
    max_new_entries_per_day: int = Field(default=1)
    max_daily_loss_usdt: Decimal = Field(default=Decimal("0.10"))
    max_planned_loss_per_trade: Decimal = Field(default=Decimal("0.05"))
    max_leverage: int = Field(default=2)
    cross_margin: bool = Field(default=False)

    estimated_maker_fee: Decimal = Field(default=Decimal("0.0002"))
    estimated_taker_fee: Decimal = Field(default=Decimal("0.0005"))
    estimated_slippage: Decimal = Field(default=Decimal("0.0005"))
    min_reward_to_risk: Decimal = Field(default=Decimal("2.0"))

    symbol: str = Field(default="BTCUSDT")
    timeframe: str = Field(default="15m")
    signal_cooldown_seconds: int = Field(default=3600)

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
    def live_authorized(self) -> bool:
        # Multiple independent checks required; single flag never enough.
        return (
            self.trading_mode == "live"
            and self.broker_enabled
            and self.auto_trade
            and self.live_trading_enabled
            and self.use_testnet is False
            and bool(self.binance_api_key)
            and bool(self.binance_api_secret)
        )

    @property
    def credentials(self) -> tuple[str, str]:
        if self.use_testnet or self.trading_mode != "live":
            return self.binance_testnet_api_key, self.binance_testnet_api_secret
        return self.binance_api_key, self.binance_api_secret

    def fail_closed_if_inconsistent(self) -> None:
        if self.trading_mode == "live" and not (self.broker_enabled and self.auto_trade and self.live_trading_enabled):
            raise RuntimeError("Inconsistent live-trading configuration; failing closed.")
        if self.trading_mode == "live" and self.use_testnet:
            raise RuntimeError("Live mode cannot use testnet credentials.")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    settings.fail_closed_if_inconsistent()
    return settings