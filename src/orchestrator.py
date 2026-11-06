"""Orchestrator coordinating the seven agents."""
import time
import json
import logging
from decimal import Decimal
from dataclasses import dataclass, asdict
from .storage import Storage
from .config import settings
from .scanner import Scanner
from .rug_check import RugChecker
from .sizer import Sizer
from .paper_trading import PaperTrader
from .logger import Logger
from .equity import EquityAgent
from .worker_lock import WorkerLock
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
    def __init__(self, client, storage):
        self.client = client
        self.storage = storage
        self.kill = KillSwitch(storage)
        self.lock = WorkerLock()
        self.scanner = Scanner(client, storage, settings.symbol_list)
        self.rug = RugChecker()
        self.sizer = Sizer()
        self.paper = PaperTrader(storage)
        self.logger = Logger(storage)
        self.equity = EquityAgent(storage)
        self.recon = ReconciliationService(client, storage)
        self._stage = "idle"

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

    def run_cycle(self) -> list[TaskResult]:
        results = []
        if not self.lock.acquire():
            self.logger.warning("ORCHESTRATOR", "cycle", "another worker running; skipping")
            return results

        try:
            self.storage.update_heartbeat("running")
            self.logger.info("ORCHESTRATOR", "cycle", "cycle started")
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
            for sr in scan_results:
                symbol = sr.get("symbol")
                sig = sr.get("signal")
                # process signal if present and not duplicate
                if not (isinstance(sig, dict) and sig.get("direction") and not sig.get("duplicate")):
                    continue
                signal_id = None  # scanner didn't return id; build from symbol+direction+time
                # try to find latest signal id in storage? Use scanner result candle time
                # We'll use a synthetic id
                signal_id = f"{symbol}:{sig.get('direction')}:{int(time.time())}"

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

                # Sizer
                self.set_stage("sizing")
                self.storage.upsert_agent_status("SIZER", "ANALYZING", current_activity=f"{symbol}")
                try:
                    from decimal import Decimal
                    dd = self.sizer.calculate(
                        symbol=symbol,
                        direction=sig["direction"],
                        entry_price=sig["entry_price"],
                        stop_loss_price=sig["stop_loss"],
                        take_profit_price=sig["take_profit"],
                        available_equity=str(settings.simulated_starting_balance),
                        rug_rating=rating,
                        kill_halted=self.kill.is_halted()[0],
                        daily_loss_used=self.kill.daily_loss_used(),
                        open_positions_count=len(self.storage.open_positions()),
                        exchange_info=None,
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

                # prevent duplicate execution
                if self.storage.open_positions():
                    self.logger.info("EXECUTER", "skip", "position already open")
                    continue

                # idempotency: check signal seen
                # Build a simple signal id for dedup using scanner result
                sid = sig.get("signal_id") if isinstance(sig, dict) else None
                if sid is None:
                    sid = f"{symbol}:{sig['direction']}:{sig.get('entry_price')}"
                if self.storage.is_signal_seen(sid):
                    self.logger.info("SCANNER", "duplicate", sid)
                    continue
                self.storage.mark_signal_seen(sid)

                # Executer: open paper position
                self.set_stage("executing")
                self.storage.upsert_agent_status("EXECUTER", "EXECUTING", current_activity=f"opening {symbol}")
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
                    self.storage.log_event("EXECUTER", symbol, "paper_open", "executed", str(res))
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
                    self.storage.log_event("EXECUTER", symbol, "paper_open", "rejected", res.get("reason", ""))
                    self.storage.upsert_agent_status("EXECUTER", "ERROR", current_activity=res.get("reason", ""), error_message=res.get("reason", ""))

            # monitor existing positions
            self.set_stage("monitoring")
            self.storage.upsert_agent_status("EXECUTER", "MONITORING", current_activity="monitoring positions")
            try:
                actions = self.paper.monitor(self.client)
                for a in actions:
                    self.storage.log_event("EXECUTER", a.get("trade_id", ""), "monitor", a.get("action", ""), str(a))
                    # equity snapshot after close
                    try:
                        self.equity.snapshot({})
                    except Exception:
                        pass
            except Exception as e:
                self.logger.error("EXECUTER", "monitor", str(e))

            self.set_stage("idle")
            self.storage.upsert_agent_status("SCANNER", "IDLE", current_activity="cycle complete", last_success=True)
            self.logger.info("ORCHESTRATOR", "cycle", "cycle completed")
            self.storage.update_heartbeat("running")
        finally:
            self.lock.release()

        return results