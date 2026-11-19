"""Daily loss kill switch with persistence."""
from datetime import datetime, timezone
from decimal import Decimal
from .storage import Storage
from .config import settings


def day_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def day_start_ts() -> float:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp()


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

    # ---------- daily budget (single source of truth) ----------
    def _start_equity_key(self) -> str:
        return f"daily_start_equity:{day_key()}"

    def ensure_day_start_equity(self, equity) -> None:
        """Record the first equity seen for the UTC day (used for the % budget)."""
        if equity is None:
            return
        value = Decimal(str(equity))
        if value <= 0:
            return
        if self.storage.get_setting(self._start_equity_key()) is None:
            self.storage.set_setting(self._start_equity_key(), str(value))

    def day_start_equity(self) -> Decimal:
        raw = self.storage.get_setting(self._start_equity_key())
        if raw is None:
            return settings.simulated_starting_balance
        try:
            return Decimal(str(raw))
        except Exception:
            return settings.simulated_starting_balance

    def daily_loss_limit(self) -> Decimal:
        """Effective daily loss budget: the tighter of the % and absolute caps."""
        limits = []
        pct = settings.max_daily_loss_pct
        if pct and pct > 0:
            limits.append(self.day_start_equity() * pct)
        absolute = settings.max_daily_loss_usdt
        if absolute and absolute > 0:
            limits.append(absolute)
        if not limits:
            return Decimal("0")
        return min(limits)

    def entries_today(self) -> int:
        try:
            return self.storage.count_trades_opened_since(day_start_ts())
        except Exception:
            return 0

    def record_trade_result(self, realized_pnl: Decimal):
        # realized_pnl negative = loss; should be net of fees/funding.
        if realized_pnl < 0:
            loss = -realized_pnl
            self.storage.add_daily_loss(day_key(), loss)
            total = self.storage.daily_loss(day_key())
            limit = self.daily_loss_limit()
            if limit > 0 and total >= limit:
                self.halt(f"daily loss budget reached: {total} >= {limit}")

    def daily_loss_used(self) -> Decimal:
        return self.storage.daily_loss(day_key())

    def daily_loss_remaining(self) -> Decimal:
        limit = self.daily_loss_limit()
        if limit <= 0:
            return Decimal("0")
        return max(Decimal("0"), limit - self.daily_loss_used())