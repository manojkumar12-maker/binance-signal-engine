"""Daily loss kill switch with persistence."""
from datetime import datetime, timezone
from decimal import Decimal
from .storage import Storage
from .config import settings


def day_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class KillSwitch:
    def __init__(self, storage: Storage):
        self.storage = storage

    def is_halted(self) -> tuple[bool, str]:
        return self.storage.is_halted()

    def halt(self, reason: str):
        self.storage.set_halted(True, reason)

    def reset(self, operator_confirmed: bool = False):
        if not operator_confirmed:
            raise RuntimeError("reset requires operator confirmation")
        self.storage.set_halted(False, "")

    def record_trade_result(self, realized_pnl: Decimal):
        # realized_pnl negative = loss
        if realized_pnl < 0:
            loss = -realized_pnl
            self.storage.add_daily_loss(day_key(), loss)
            total = self.storage.daily_loss(day_key())
            if total >= settings.max_daily_loss_usdt:
                self.halt(f"daily loss budget reached: {total} >= {settings.max_daily_loss_usdt}")

    def daily_loss_used(self) -> Decimal:
        return self.storage.daily_loss(day_key())

    def daily_loss_remaining(self) -> Decimal:
        return settings.max_daily_loss_usdt - self.daily_loss_used()