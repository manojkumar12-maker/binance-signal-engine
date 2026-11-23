# ADR 0001 — Signal engine architecture: layered single-process design with agent pipeline

Date: 2026-11-23 · Status: Accepted

## Context

binance-signal-engine is a paper-only Binance USDT-M Futures signal engine
(~7,000 lines in `src/`, FastAPI + SQLite, real market data, no live orders by
default). Constraints: single operator, no message broker or external
database, cost must stay near zero, and live trading must be impossible by
misconfiguration (fail-closed).

## Options considered

1. **Layered single process, agent pipeline (chosen)** — one Python process
   runs a worker thread (scan → score → size → execute loop) beside a FastAPI
   dashboard, sharing a SQLite store. Agents are plain classes orchestrated
   sequentially.
2. **Event-driven microservices** — scanner, engine, sizer, executor as
   separate services on a queue (Redis/NATS). Better horizontal scale and
   isolation, but adds infra, deployment and observability cost for a
   single-user tool whose bottleneck is rate-limited Binance REST calls, not
   compute. Rejected for now; the agent interfaces (`TaskResult`,
   `upsert_agent_status`) leave room to split later.

## Decision

Keep the layered single-process design. Layers and modules:

| Layer | Modules | Responsibility |
|---|---|---|
| Entry | `main.py`, `src/worker.py`, `src/dashboard.py` | boot (fail-closed via `settings.fail_closed_if_inconsistent()`), worker thread + FastAPI |
| 1 Data | `market_data.py`, `binance_client.py`, `exchange_filters.py` | klines, tickers, symbol filters |
| 2 Signal | `scanner.py`, `rug_check.py`, `signal_engine.py`, `indicators.py`, `regime.py`, `fibonacci.py` | universe → rug filter → V2 score → SL/TP (ATR or Fib extension) |
| 3 Risk | `sizer.py`, `risk_engine.py`, `kill_switch.py` | position size, drawdown caps, emergency stop |
| 4 Execution | `execution.py`, `paper_trading.py`, `reconciliation.py` | paper (default) or authorized live fills, SL/TP monitor |
| 5 Persistence/Ops | `storage.py`, `logger.py`, `equity.py`, `admin.py`, `auth.py`, `agent_status.py`, `settings_manager.py`, `worker_lock.py` | SQLite, trade logs, equity snapshots, per-agent status |
| 6 UI | `ui/index.html` | dashboard over `/api/*` |

Seven agents (Scanner, Rug Check, Sizer, Executer, Logger, Equity, Admin
Logs) run sequentially per cycle in `src/orchestrator.py`, each reporting
state through `storage.upsert_agent_status`.

Failure modes: Binance API slow/down → cycle errors are caught per-agent,
agent status shows ERROR, next cycle retries; no partial fills persist in
paper mode. Process crash → SQLite is the source of truth; reconciliation
rebuilds open-position state on restart. Live mode is gated by
`exchange_execution_authorized` (`src/execution.py`), so the riskiest
path is disabled unless explicitly authorized.

## Consequences

- Simple to run (`python main.py`) and back up (single SQLite file);
  bounded by one machine and REST rate limits.
- Sequential orchestration means one slow symbol delays the cycle;
  acceptable at current universe size.
- Splitting agents into services later is mechanical because each agent
  already communicates only through storage and return values.

## Known open item

The default threshold (score ≥ 75) emitted zero trades on real May–Jul 2026
data in the audit probe; historical profitability is unproven until the full
scenario matrix (6 symbols × 3 splits × 6 stress configs) finishes.
