"""Percent-based position sizer."""
from decimal import Decimal
from dataclasses import dataclass
from .config import settings
from .risk_engine import fee_estimate
from .exchange_filters import validate_order, get_lot_size_filter, round_quantity


@dataclass
class SizeDecision:
    approved: bool
    reason: str
    quantity: Decimal = Decimal("0")
    risk_amount: Decimal = Decimal("0")
    estimated_loss: Decimal = Decimal("0")
    estimated_fees: Decimal = Decimal("0")
    margin_required: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    reward_to_risk: Decimal = Decimal("0")


class Sizer:
    def calculate(self, symbol, direction, entry_price, stop_loss_price, take_profit_price,
                 available_equity, rug_rating="LOW", kill_halted=False, daily_loss_used=Decimal("0"),
                 open_positions_count=0, exchange_info=None):
        entry = Decimal(str(entry_price))
        stop = Decimal(str(stop_loss_price))
        tp = Decimal(str(take_profit_price))
        equity = Decimal(str(available_equity))

        if kill_halted:
            return SizeDecision(False, "kill switch halted")
        if entry <= 0 or stop <= 0:
            return SizeDecision(False, "invalid prices")
        if entry == stop:
            return SizeDecision(False, "zero risk distance")
        if direction not in ("LONG", "SHORT"):
            return SizeDecision(False, "invalid direction")
        if rug_rating in ("HIGH", "UNKNOWN"):
            return SizeDecision(False, f"rug check {rug_rating}")

        risk_pct = settings.risk_per_trade_pct
        max_daily_pct = settings.max_daily_loss_pct

        max_daily_loss = (equity * max_daily_pct)  # simplified; better use starting equity but equity approx
        if daily_loss_used >= max_daily_loss:
            return SizeDecision(False, "daily loss limit reached")

        if open_positions_count >= settings.max_simultaneous_positions:
            return SizeDecision(False, "max positions reached")

        risk_budget = equity * risk_pct
        stop_distance = abs(entry - stop)
        max_qty_by_risk = risk_budget / stop_distance

        leverage = min(settings.max_leverage, settings.max_leverage)
        if leverage < 1:
            leverage = 1
        max_qty_by_margin = (equity * Decimal(leverage)) / entry

        qty = min(max_qty_by_risk, max_qty_by_margin)
        if qty <= 0:
            return SizeDecision(False, "no valid quantity")

        fees = fee_estimate(qty, entry, stop, settings.estimated_maker_fee,
                            settings.estimated_taker_fee, settings.estimated_slippage)
        gross_risk = qty * stop_distance
        total_loss = gross_risk + fees
        if total_loss > risk_budget and total_loss > 0:
            scale = risk_budget / total_loss
            qty = qty * scale
            fees = fee_estimate(qty, entry, stop, settings.estimated_maker_fee,
                                settings.estimated_taker_fee, settings.estimated_slippage)
            gross_risk = qty * stop_distance
            total_loss = gross_risk + fees

        if total_loss > risk_budget + Decimal("0.000001"):
            return SizeDecision(False, "cannot satisfy risk budget", quantity=qty, estimated_loss=total_loss, estimated_fees=fees, risk_amount=risk_budget)

        reward = abs(tp - entry) * qty
        net_reward = reward - fees
        rr = (net_reward / total_loss) if total_loss > 0 else Decimal(0)
        if total_loss > 0 and rr < settings.min_reward_to_risk:
            return SizeDecision(False, "reward-to-risk below minimum", quantity=qty, estimated_loss=total_loss,
                                estimated_fees=fees, reward_to_risk=rr)

        notional = qty * entry
        margin_required = notional / Decimal(leverage)
        if margin_required > equity:
            return SizeDecision(False, "insufficient margin", quantity=qty)

        # exchange filters
        if exchange_info is not None:
            from .exchange_filters import get_lot_size_filter, round_quantity, validate_order
            lot = get_lot_size_filter(exchange_info, symbol)
            if lot:
                step = Decimal(lot["stepSize"])
                min_qty = Decimal(lot["minQty"])
                rounded = round_quantity(qty, step)
                if rounded < min_qty:
                    return SizeDecision(False, f"quantity below min {min_qty}", quantity=rounded)
                if rounded > qty:
                    # rounding up not allowed
                    rounded = round_quantity(qty, step)
                qty = rounded
                okf, freason = validate_order(exchange_info, symbol, qty, entry)
                if not okf:
                    # if notional below min, reject (no risk increase)
                    return SizeDecision(False, f"filter rejected: {freason}", quantity=qty)

        # recompute after rounding
        gross_risk = qty * stop_distance
        fees = fee_estimate(qty, entry, stop, settings.estimated_maker_fee,
                            settings.estimated_taker_fee, settings.estimated_slippage)
        total_loss = gross_risk + fees
        notional = qty * entry
        margin_required = notional / Decimal(leverage)

        return SizeDecision(True, "approved", quantity=qty, risk_amount=risk_budget,
                            estimated_loss=total_loss, estimated_fees=fees, margin_required=margin_required,
                            notional=notional, reward_to_risk=rr)