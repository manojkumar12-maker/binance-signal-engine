import time
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

from app.services import signal_lifecycle, tracker, strategy
from app.services.broker import (
    place_market_order, place_limit_order, place_stop_loss, place_take_profit,
    cancel_order, get_account_balance, get_position, compute_position_size,
    reconcile_positions, KillSwitchError, OrderRejectedError, BrokerError
)
from app.services.execution_engine import get_execution_mode
import config


EXECUTION_CHECK_INTERVAL = 5
CONFIRMATION_WAIT_TIME = 60
RECONCILE_INTERVAL = config.RECONCILE_INTERVAL_SECONDS


class ExecutionWorker:
    def __init__(self):
        self.running = False
        self.last_check = {}
        self._reconcile_ts = 0.0

    async def start(self):
        self.running = True
        logger.info(">>> EXECUTION WORKER: Started")

        while self.running:
            try:
                await self.process_signals()
            except Exception as e:
                logger.error(f">>> EXECUTION WORKER ERROR: {e}")

            now = time.time()
            if now - self._reconcile_ts >= RECONCILE_INTERVAL:
                try:
                    await reconcile_positions()
                except Exception as e:
                    logger.error(f">>> RECONCILE ERROR: {e}")
                self._reconcile_ts = now

            await asyncio.sleep(EXECUTION_CHECK_INTERVAL)

    def stop(self):
        self.running = False
        logger.info(">>> EXECUTION WORKER: Stopped")

    async def process_signals(self):
        pending_signals = signal_lifecycle.get_signals_for_trading()

        for signal in pending_signals:
            pair = signal.get("pair")
            state = signal.get("signal_state")

            if not pair:
                continue

            if not signal_lifecycle.acquire_lock(pair, ttl=30):
                logger.debug(f">>> LOCKED {pair}: cannot acquire lock")
                continue

            try:
                if state == "PENDING":
                    await self.handle_pending_signal(pair, signal)
                elif state == "CONFIRMED":
                    await self.handle_confirmed_signal(pair, signal)
            finally:
                signal_lifecycle.release_lock(pair)

    async def handle_pending_signal(self, pair: str, signal: Dict):
        now = time.time()
        locked_at = signal.get("locked_at", 0)

        if now - locked_at < CONFIRMATION_WAIT_TIME:
            time_since_lock = round(now - locked_at, 1)
            if time_since_lock % 30 < 1:
                logger.info(f">>> PENDING {pair}: waiting {time_since_lock}s (need {CONFIRMATION_WAIT_TIME}s)")
            return

        new_signal = self.revalidate_signal(pair)

        if not new_signal:
            signal_lifecycle.reject_signal(pair, "revalidation_failed")
            logger.info(f">>> REJECTED {pair}: revalidation failed")
            return

        is_valid, reason = signal_lifecycle.validate_stored_signal(pair, config.MIN_CONFIDENCE)

        if is_valid:
            signal_lifecycle.confirm_signal(pair)
            logger.info(f">>> CONFIRMED {pair}: passed revalidation")
        else:
            signal_lifecycle.reject_signal(pair, reason)
            logger.info(f">>> REJECTED {pair}: {reason}")

    async def handle_confirmed_signal(self, pair: str, signal: Dict):
        if self.has_recent_execution(pair):
            logger.debug(f">>> SKIP {pair}: recently executed")
            return

        entry = signal.get("entry_primary")
        signal_type = signal.get("signal", "BUY")
        sl = signal.get("sl")
        confidence = signal.get("confidence", 0)

        if not entry or entry <= 0 or not sl:
            signal_lifecycle.reject_signal(pair, "invalid_params")
            return

        quantity = compute_position_size(entry, sl, confidence)
        if quantity <= 0:
            signal_lifecycle.reject_signal(pair, "invalid_position_size")
            return

        execution_mode = get_execution_mode(confidence, signal.get("atr_ratio", 0.005))
        mode_config = {
            "SAFE": {"max_slippage": 0.003, "use_limit": True, "split_orders": False},
            "BALANCED": {"max_slippage": 0.005, "use_limit": True, "split_orders": True},
            "AGGRESSIVE": {"max_slippage": 0.008, "use_limit": False, "split_orders": False}
        }.get(execution_mode, {})

        use_limit = mode_config.get("use_limit", False)

        try:
            if use_limit:
                limit_price = entry * 0.999 if signal_type == "BUY" else entry * 1.001
                order_result = await place_limit_order(pair, signal_type, quantity, limit_price)
            else:
                order_result = await place_market_order(pair, signal_type, quantity)
        except KillSwitchError as e:
            signal_lifecycle.reject_signal(pair, f"kill_switch_{e}")
            logger.error(f">>> KILL SWITCH {pair}: {e}")
            return
        except (OrderRejectedError, BrokerError) as e:
            signal_lifecycle.reject_signal(pair, f"order_failed_{e}")
            logger.error(f">>> ORDER FAILED {pair}: {e}")
            return

        trade = self.create_trade_from_signal(signal)
        if not trade:
            signal_lifecycle.reject_signal(pair, "trade_creation_failed")
            return

        trade["quantity"] = quantity
        trade["execution_mode"] = execution_mode
        trade["order_id"] = str(order_result.get("orderId", ""))
        trade["simulated"] = order_result.get("simulated", not config.BROKER_ENABLED)

        tracker.add_trade(trade)
        signal_lifecycle.execute_signal(pair)

        try:
            await self.place_protection_orders(pair, signal, quantity)
        except Exception as e:
            logger.warning(f">>> PROTECTION ORDER FAILED {pair}: {e}")

        self.last_check[pair] = time.time()
        logger.info(f">>> EXECUTED {pair}: {signal_type} {quantity} {pair} @ {entry} mode={execution_mode}")

    async def place_protection_orders(self, pair: str, signal: Dict, quantity: float):
        signal_type = signal.get("signal", "BUY")
        sl = signal.get("sl")
        tp1 = signal.get("tp1")
        if not sl:
            return

        partial_qty = round(quantity * 0.5, 3)
        if partial_qty > 0 and tp1:
            try:
                await place_take_profit(pair, signal_type, partial_qty, tp1)
            except Exception as e:
                logger.warning(f">>> TP PLACEMENT FAILED {pair}: {e}")

        await place_stop_loss(pair, signal_type, quantity, sl)

    def revalidate_signal(self, pair: str) -> Optional[Dict]:
        try:
            new_signal = strategy.generate_signal(pair, "1h", fetch_oi=True, use_bias=True)

            if new_signal.get("signal") == "NO TRADE":
                return None

            is_valid, reason = signal_lifecycle.revalidate_signal(pair, new_signal, config.MIN_CONFIDENCE)

            if not is_valid:
                logger.info(f">>> REVALIDATION {pair}: {reason}")
                return None

            return new_signal
        except Exception as e:
            logger.error(f">>> REVALIDATION ERROR {pair}: {e}")
            return None

    def create_trade_from_signal(self, signal: Dict) -> Optional[Dict]:
        pair = signal.get("pair")
        signal_type = signal.get("signal")
        entry = signal.get("entry_primary")

        if not pair or not entry or entry <= 0:
            return None

        trade = tracker.create_trade(
            pair=pair,
            signal_type=signal_type,
            entry=entry,
            sl=signal.get("sl"),
            tp1=signal.get("tp1"),
            tp2=signal.get("tp2"),
            tp3=signal.get("tp3"),
            confidence=signal.get("confidence", 0),
            entry_limit=signal.get("entry_limit")
        )

        return trade

    def has_recent_execution(self, pair: str) -> bool:
        if pair not in self.last_check:
            return False

        return time.time() - self.last_check[pair] < 300


execution_worker = ExecutionWorker()


async def start_execution_worker():
    await execution_worker.start()


def stop_execution_worker():
    execution_worker.stop()
