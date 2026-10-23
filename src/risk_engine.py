"""Centralized risk engine for 5 USDT account."""
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
from .config import settings


@dataclass
class TradeProposal:
    symbol: str
    direction: str  # LONG or SHORT
    entry_price: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    quantity: Decimal = Decimal("0")
    leverage: int = 1


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    quantity: Decimal = Decimal("0")
    estimated_loss: Decimal = Decimal("0")
    estimated_fees: Decimal = Decimal("0")
    reward_to_risk: Decimal = Decimal("0")


def compute_stop_loss_risk(qty: Decimal, entry: Decimal, stop: Decimal) -> Decimal:
    return qty * abs(entry - stop)


def fee_estimate(qty: Decimal, entry: Decimal, exit_price: Decimal, maker: Decimal, taker: Decimal, slippage: Decimal) -> Decimal:
    notional_entry = qty * entry
    notional_exit = qty * exit_price
    entry_fee = notional_entry * taker
    exit_fee = notional_exit * taker
    slip = (notional_entry + notional_exit) * slippage
    return entry_fee + exit_fee + slip


def size_position(proposal: TradeProposal, available_equity: Decimal) -> RiskDecision:
    if proposal.entry_price <= 0 or proposal.stop_loss_price <= 0:
        return RiskDecision(False, "invalid prices")
    if proposal.entry_price == proposal.stop_loss_price:
        return RiskDecision(False, "zero risk distance")
    if proposal.direction not in ("LONG", "SHORT"):
        return RiskDecision(False, "invalid direction")

    leverage = min(proposal.leverage, settings.max_leverage)
    if leverage < 1:
        leverage = 1

    risk_budget = settings.max_planned_loss_per_trade
    # iterative: try to find qty such that total estimated loss <= budget
    # Start from a conservative notional cap.
    stop_distance = abs(proposal.entry_price - proposal.stop_loss_price)
    # max quantity by risk budget ignoring fees
    if stop_distance == 0:
        return RiskDecision(False, "zero stop distance")
    max_qty_by_risk = risk_budget / stop_distance

    # Apply leverage margin constraint: margin = notional / leverage <= available_equity
    # notional = qty * entry <= available_equity * leverage
    max_qty_by_margin = (available_equity * Decimal(leverage)) / proposal.entry_price

    qty = min(max_qty_by_risk, max_qty_by_margin)
    if qty <= 0:
        return RiskDecision(False, "no valid quantity")

    # fee-aware refinement: reduce qty until estimated total loss <= budget
    fees = fee_estimate(qty, proposal.entry_price, proposal.stop_loss_price, settings.estimated_maker_fee,
                        settings.estimated_taker_fee, settings.estimated_slippage)
    gross_risk = compute_stop_loss_risk(qty, proposal.entry_price, proposal.stop_loss_price)
    total_loss = gross_risk + fees
    # if over budget, scale down
    if total_loss > risk_budget and total_loss > 0:
        scale = risk_budget / total_loss
        qty = qty * scale
        fees = fee_estimate(qty, proposal.entry_price, proposal.stop_loss_price, settings.estimated_maker_fee,
                            settings.estimated_taker_fee, settings.estimated_slippage)
        gross_risk = compute_stop_loss_risk(qty, proposal.entry_price, proposal.stop_loss_price)
        total_loss = gross_risk + fees

    if total_loss > risk_budget:
        return RiskDecision(False, "cannot satisfy risk budget", quantity=qty, estimated_loss=total_loss, estimated_fees=fees)

    # reward-to-risk check
    reward = abs(proposal.take_profit_price - proposal.entry_price) * qty
    net_reward = reward - fees
    if total_loss > 0 and (net_reward / total_loss) < settings.min_reward_to_risk:
        return RiskDecision(False, "reward-to-risk below minimum", quantity=qty, estimated_loss=total_loss,
                            estimated_fees=fees, reward_to_risk=(net_reward / total_loss))

    # margin check
    notional = qty * proposal.entry_price
    required_margin = notional / Decimal(leverage)
    if required_margin > available_equity:
        return RiskDecision(False, "insufficient margin", quantity=qty)

    return RiskDecision(True, "approved", quantity=qty, estimated_loss=total_loss, estimated_fees=fees,
                        reward_to_risk=(net_reward / total_loss if total_loss > 0 else Decimal("0")))