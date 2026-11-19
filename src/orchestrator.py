"""Orchestrator coordinating the seven agents."""
import time
import json
import logging
import threading
from decimal import Decimal
from dataclasses import dataclass, asdict
from types import SimpleNamespace
from .storage import Storage
from .config import settings
from .scanner import Scanner
from .rug_check import RugChecker
from .sizer import Sizer
from .paper_trading import PaperTrader
from .execution import ExecutionEngine, exchange_execution_authorized
from .account import get_available_equity, account_snapshot
from .logger import Logger
from .equity import EquityAgent
from .kill_switch import KillSwitch
from .reconciliation import ReconciliationService
from .binance_client import BinanceClient

log = logging.getLogger("orchestrator")


@dataclass
class TaskResult:
    agent: str
    task_id: str
    symbol: str
    signal_id: str
    success: bool
    rejection_reason: str = ""
    output: dict = None
    timestamp: float = 0.0

    def to_dict(self):
        d = asdict(self)
        if d["output"] is None:
            d["output"] = {}
        return d


class Orchestrator:
    def __init__(self, client, storage, market_data=None, exchange_info=None):
        self.client = client
        self.storage = storage
        self.market_data = market_data
        self.exchange_info = exchange_info
        self.kill = KillSwitch(storage)
        self.scanner = Scanner(client, storage, market_data=market_data)
        self.rug = RugChecker()
        self.sizer = Sizer()
        self.paper = PaperTrader(storage)
        self.execution = ExecutionEngine(client, storage, exchange_info or {})
        self.logger = Logger(storage)
        self.equity = EquityAgent(storage)
        self.recon = ReconciliationService(client, storage)
        self._stage = "idle"
        self._cycle_lock = threading.Lock()

    def set_stage(self, stage):
        self._stage = stage
        try:
            self.storage.set_setting("workflow_stage", stage)
        except Exception:
            pass

    def stage(self):
        try:
            return self.storage.get_setting("workflow_stage", self._stage)
        except Exception:
            return self._stage

    def _make_task_id(self, agent, symbol, signal_id):
        return f"{agent}:{symbol}:{signal_id}:{int(time.time()*1000)}"

    def _snapshot_equity(self):
        prices = {}
        for p in self.storage.open_positions():
            try:
                prices[p["symbol"]] = self.client.ticker_price(p["symbol"])
            except Exception:
                pass
        if exchange_execution_authorized():
            try:
                acct = account_snapshot(self.client)
                realized = self.storage.equity_summary().get("realized_pnl", 0)
                self.storage.add_equity_snapshot(
                    acct["equity"], acct["balance"], realized, acct["unrealized"]
                )
                return
            except Exception:
                pass
        self.equity.snapshot({k: str(v) for k, v in prices.items()})

    def run_cycle(self) -> list[TaskResult]:
        results = []
        if not self._cycle_lock.acquire(blocking=False):
            self.logger.warning("ORCHESTRATOR", "cycle", "cycle already running; skipping")
            return results

        try:
            self.storage.update_heartbeat("running")
            self.logger.info("ORCHESTRATOR", "cycle", "cycle started")
            # pick up credentials saved via the Settings page without a restart
            try:
                key, secret = settings.credentials
                updater = getattr(self.client, "update_credentials", None)
                if updater:
                    updater(key, secret)
            except Exception:
                pass
            self.set_stage("reconciling")
            # reconciliation
            try:
                r = self.recon.reconcile()
                self.storage.log_reconciliation(__import__("json").dumps(r))
                if r.get("discrepancies"):
                    self.logger.warning("RECONCILIATION", "reconcile", str(r["discrepancies"]))
            except Exception as e:
                self.logger.error("RECONCILIATION", "reconcile", str(e))

            if self.kill.is_halted()[0]:
                self.logger.warning("KILL_SWITCH", "halted", self.kill.is_halted()[1])
                self.set_stage("halted")
                return results

            self.set_stage("scanning")
            self.storage.upsert_agent_status("SCANNER", "SCANNING", current_activity="scanning symbols")

            scan_results = self.scanner.scan_once()
            use_exchange = exchange_execution_authorized()
            use_engine = use_exchange or settings.live_mode
            if use_exchange and not (self.execution.exchange_info or {}).get("symbols"):
                try:
                    self.execution.exchange_info = self.client.exchange_info()
                except Exception as e:
                    self.logger.error("EXECUTER", "exchange_info", str(e))
            for sr in scan_results:
                symbol = sr.get("symbol")
                sig = sr.get("signal")
                # process signal if present and not duplicate
                if not (isinstance(sig, dict) and sig.get("direction") and not sig.get("duplicate")):
                    continue
                # scanner provides the real signal id (symbol:direction:strategy:candle_close_time)
                signal_id = sig.get("signal_id") or f"{symbol}:{sig.get('direction')}:{int(time.time())}"

                # Rug check (already in scan result)
                risk = sr.get("risk") or {}
                rating = risk.get("risk_rating", "UNKNOWN")
                self.set_stage("rug_check")
                self.storage.upsert_agent_status("RUG CHECK", "ANALYZING", current_activity=f"{symbol}")
                tr_rug = TaskResult("RUG CHECK", self._make_task_id("RUG CHECK", symbol, signal_id), symbol, signal_id,
                                    rating not in ("HIGH", "UNKNOWN"), rejection_reason="" if rating not in ("HIGH", "UNKNOWN") else f"risk {rating}",
                                    output=risk, timestamp=time.time())
                results.append(tr_rug)
                self.logger.info("RUG CHECK", "assess", f"{symbol} -> {rating}", metadata=risk)
                self.storage.upsert_agent_status("RUG CHECK", "IDLE", current_activity=f"{symbol} {rating}", last_success=True)

                if rating in ("HIGH", "UNKNOWN"):
                    self.storage.log_event("ORCHESTRATOR", symbol, "workflow", "rejected", f"rug check {rating}")
                    continue

                # Sizer — use Binance Demo equity when executing, else simulated equity
                self.set_stage("sizing")
                self.storage.upsert_agent_status("SIZER", "ANALYZING", current_activity=f"{symbol}")
                if use_exchange:
                    try:
                        current_equity = get_available_equity(self.client)
                    except Exception:
                        current_equity = settings.simulated_starting_balance
                else:
                    try:
                        eq = self.storage.equity_summary()
                        current_equity = settings.simulated_starting_balance + Decimal(str(eq.get("realized_pnl", 0)))
                    except Exception:
                        current_equity = settings.simulated_starting_balance
                try:
                    day_equity = current_equity
                    if use_exchange:
                        day_equity = account_snapshot(self.client).get("equity", current_equity)
                    self.kill.ensure_day_start_equity(day_equity)
                except Exception:
                    pass
                exchange_info = self.execution.exchange_info
                if not (exchange_info or {}).get("symbols"):
                    exchange_info = None
                try:
                    dd = self.sizer.calculate(
                        symbol=symbol,
                        direction=sig["direction"],
                        entry_price=sig["entry_price"],
                        stop_loss_price=sig["stop_loss"],
                        take_profit_price=sig["take_profit"],
                        available_equity=str(current_equity),
                        rug_rating=rating,
                        kill_halted=self.kill.is_halted()[0],
                        daily_loss_used=self.kill.daily_loss_used(),
                        open_positions_count=len(self.storage.open_positions()),
                        exchange_info=exchange_info,
                        daily_loss_limit=self.kill.daily_loss_limit(),
                        entries_today=self.kill.entries_today(),
                    )
                except Exception as e:
                    dd = None
                    self.logger.error("SIZER", "calculate", str(e))

                if dd is None or not dd.approved:
                    reason = dd.reason if dd else "sizer error"
                    tr = TaskResult("SIZER", self._make_task_id("SIZER", symbol, signal_id), symbol, signal_id, False, rejection_reason=reason, timestamp=time.time())
                    results.append(tr)
                    self.storage.log_event("SIZER", symbol, "size", "rejected", reason)
                    self.storage.upsert_agent_status("SIZER", "ERROR" if dd is None else "IDLE", current_activity=reason, error_message=reason)
                    continue

                tr = TaskResult("SIZER", self._make_task_id("SIZER", symbol, signal_id), symbol, signal_id, True, output={
                    "quantity": str(dd.quantity), "risk_amount": str(dd.risk_amount)}, timestamp=time.time())
                results.append(tr)
                self.storage.log_event("SIZER", symbol, "size", "approved", f"qty={dd.quantity}")
                self.storage.upsert_agent_status("SIZER", "IDLE", current_activity=f"approved {symbol}", last_success=True)

                # prevent duplicate execution beyond the (live) position cap
                max_positions = int(settings.max_simultaneous_positions)
                if len(self.storage.open_positions()) >= max_positions:
                    self.logger.info("EXECUTER", "skip", f"max positions ({max_positions}) reached")
                    continue

                # execution-level idempotency (separate namespace from scanner's seen-signal marks)
                sid = sig.get("signal_id") if isinstance(sig, dict) else None
                if sid is None:
                    sid = f"{symbol}:{sig['direction']}:{sig.get('entry_price')}"
                exec_id = f"exec:{sid}"
                if self.storage.is_signal_seen(exec_id):
                    self.logger.info("EXECUTER", "duplicate", sid)
                    continue
                self.storage.mark_signal_seen(exec_id)

                # Executer: Binance Demo/live order, or internal simulator
                self.set_stage("executing")
                self.storage.upsert_agent_status("EXECUTER", "EXECUTING", current_activity=f"opening {symbol}")
                event_type = "binance_open" if use_engine else "paper_open"
                if use_engine:
                    signal_obj = SimpleNamespace(
                        symbol=symbol,
                        direction=sig["direction"],
                        timestamp=int(time.time()),
                        entry_price=Decimal(str(sig["entry_price"])),
                        stop_loss=Decimal(str(sig["stop_loss"])),
                        take_profit=Decimal(str(sig["take_profit"])),
                        signal_id=sig.get("signal_id"),
                    )
                    try:
                        ok, reason = self.execution.execute_signal(signal_obj, symbol, size_decision=dd)
                    except Exception as e:
                        ok, reason = False, str(e)
                    res = {
                        "ok": bool(ok and reason == "executed"),
                        "reason": reason,
                        "broker": ("binance-demo" if settings.testnet_execution_ready
                                   else ("binance-live" if settings.live_authorized else "binance-gated")),
                    }
                else:
                    proposal = {"symbol": symbol, "direction": sig["direction"],
                                "entry_price": sig["entry_price"], "stop_loss": sig["stop_loss"],
                                "take_profit": sig["take_profit"]}
                    try:
                        res = self.paper.open_position(self.client, proposal, dd, None)
                    except Exception as e:
                        res = {"ok": False, "reason": str(e)}

                if res.get("ok"):
                    tr = TaskResult("EXECUTER", self._make_task_id("EXECUTER", symbol, signal_id), symbol, signal_id, True,
                                    output=res, timestamp=time.time())
                    results.append(tr)
                    self.storage.log_event("EXECUTER", symbol, event_type, "executed", str(res))
                    self.storage.upsert_agent_status("EXECUTER", "MONITORING", current_activity=f"monitoring {symbol}", last_success=True)
                    # equity snapshot
                    self.set_stage("equity")
                    self.storage.upsert_agent_status("EQUITY", "MONITORING", current_activity="snapshot")
                    try:
                        self.equity.snapshot({})
                    except Exception as e:
                        self.logger.error("EQUITY", "snapshot", str(e))
                    self.storage.upsert_agent_status("EQUITY", "IDLE", current_activity="updated", last_success=True)
                else:
                    tr = TaskResult("EXECUTER", self._make_task_id("EXECUTER", symbol, signal_id), symbol, signal_id, False,
                                    rejection_reason=res.get("reason", "execution failed"), timestamp=time.time())
                    results.append(tr)
                    self.storage.log_event("EXECUTER", symbol, event_type, "rejected", res.get("reason", ""))
                    self.storage.upsert_agent_status("EXECUTER", "ERROR", current_activity=res.get("reason", ""), error_message=res.get("reason", ""))

            # monitor existing positions
            self.set_stage("monitoring")
            self.storage.upsert_agent_status("EXECUTER", "MONITORING", current_activity="monitoring positions")
            try:
                actions = self.execution.monitor() if use_exchange else self.paper.monitor(self.client)
                for a in actions:
                    self.storage.log_event("EXECUTER", a.get("trade_id", ""), "monitor", a.get("action", ""), str(a))
                    # equity snapshot after close
                    try:
                        self._snapshot_equity()
                    except Exception:
                        pass
            except Exception as e:
                self.logger.error("EXECUTER", "monitor", str(e))

            # equity snapshot every cycle (live Demo/Live balance when available)
            self.set_stage("equity")
            self.storage.upsert_agent_status("EQUITY", "MONITORING", current_activity="snapshot")
            try:
                self._snapshot_equity()
                self.storage.upsert_agent_status("EQUITY", "IDLE", current_activity="updated", last_success=True)
            except Exception as e:
                self.logger.error("EQUITY", "snapshot", str(e))
                self.storage.upsert_agent_status("EQUITY", "ERROR", current_activity="snapshot failed", error_message=str(e))

            self.set_stage("idle")
            self.storage.upsert_agent_status("SCANNER", "IDLE", current_activity="cycle complete", last_success=True)
            self.logger.info("ORCHESTRATOR", "cycle", "cycle completed")
            self.storage.update_heartbeat("running")
        finally:
            self._cycle_lock.release()

        return results