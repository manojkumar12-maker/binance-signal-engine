"""Historical backtesting for Signal Engine V2.

Chronological, no look-ahead: at each step the engine sees only candles up to
that point. Fees and slippage included. Same-candle SL/TP ambiguity resolved
conservatively (stop-loss assumed first). Open trade at end is closed at the
last close price.
"""
import time
from decimal import Decimal
from dataclasses import dataclass, field

from .signal_engine import SignalEngine
from .risk_engine import fee_estimate


@dataclass
class BacktestConfig:
    starting_balance: Decimal = Decimal("1000")
    risk_per_trade_pct: Decimal = Decimal("0.005")
    max_positions: int = 1
    max_daily_loss_pct: Decimal = Decimal("0.01")
    min_score: float = 75.0
    cooldown_seconds: int = 3600
    taker_fee: Decimal = Decimal("0.0005")
    maker_fee: Decimal = Decimal("0.0002")
    slippage: Decimal = Decimal("0.0005")
    htf: str = "15m"
    ltf: str = "5m"
    min_history: int = 60  # candles needed before evaluating


@dataclass
class BTTrade:
    symbol: str
    direction: str
    strategy: str
    regime: str
    score: float
    entry_time: int
    entry_price: Decimal
    exit_time: int = 0
    exit_price: Decimal = Decimal(0)
    stop_loss: Decimal = Decimal(0)
    take_profit: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)
    pnl: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    r_multiple: Decimal = Decimal(0)
    exit_reason: str = ""


class Backtester:
    def __init__(self, cfg: BacktestConfig | None = None):
        self.cfg = cfg or BacktestConfig()

    def _interval_ms(self, tf: str) -> int:
        return {"1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000,
                "30m": 1800000, "1h": 3600000, "4h": 14400000}.get(tf, 900000)

    def run(self, symbol: str, htf_klines: list, ltf_klines: list | None = None,
            engine: SignalEngine | None = None) -> dict:
        cfg = self.cfg
        eng = engine or SignalEngine(cooldown_seconds=cfg.cooldown_seconds)
        eng.weights = eng.weights  # defaults
        entry_kl = ltf_klines if ltf_klines else htf_klines
        htf_interval = self._interval_ms(cfg.htf)
        ltf_interval = self._interval_ms(cfg.ltf)

        # Map each LTF candle index to the HTF slice containing only HTF candles
        # that closed before this LTF candle opens (no look-ahead).
        htf_times = [k[0] for k in htf_klines]

        def htf_slice_upto(ts_ms: int) -> list:
            # include htf candles with close time <= ts_ms (close = open + interval)
            n = 0
            for t in htf_times:
                if t + htf_interval <= ts_ms:
                    n += 1
                else:
                    break
            return htf_klines[:n]

        equity = cfg.starting_balance
        day_start_equity = cfg.starting_balance
        current_day = None
        position: BTTrade | None = None
        trades: list[BTTrade] = []
        equity_curve = []
        last_signal_ts: dict = {}

        total = len(entry_kl)
        for i in range(cfg.min_history + 1, total):
            candle = entry_kl[i]
            ts = int(candle[0])
            o, h = Decimal(str(candle[1])), Decimal(str(candle[2]))
            l, c = Decimal(str(candle[3])), Decimal(str(candle[4]))

            day = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000))
            if day != current_day:
                current_day = day
                day_start_equity = equity

            # ---- manage open position on this candle ----
            if position is not None:
                hit_sl = (position.direction == "LONG" and l <= position.stop_loss) or \
                         (position.direction == "SHORT" and h >= position.stop_loss)
                hit_tp = (position.direction == "LONG" and h >= position.take_profit) or \
                         (position.direction == "SHORT" and l <= position.take_profit)
                exit_price, reason = None, ""
                if hit_sl and hit_tp:
                    # ambiguous candle: conservative assumption — stop first
                    exit_price, reason = position.stop_loss, "stop_loss_ambiguous"
                elif hit_sl:
                    exit_price, reason = position.stop_loss, "stop_loss"
                elif hit_tp:
                    exit_price, reason = position.take_profit, "take_profit"
                if exit_price is not None:
                    slip = exit_price * cfg.slippage
                    exit_price = exit_price - slip if position.direction == "LONG" else exit_price + slip
                    if position.direction == "LONG":
                        gross = (exit_price - position.entry_price) * position.quantity
                    else:
                        gross = (position.entry_price - exit_price) * position.quantity
                    fees = fee_estimate(position.quantity, position.entry_price, exit_price,
                                        cfg.maker_fee, cfg.taker_fee, Decimal("0"))
                    net = gross - fees
                    equity += net
                    risk_unit = abs(position.entry_price - position.stop_loss) * position.quantity
                    position.exit_time = ts
                    position.exit_price = exit_price
                    position.pnl = net
                    position.fees = fees
                    position.r_multiple = (net / risk_unit) if risk_unit > 0 else Decimal(0)
                    position.exit_reason = reason
                    trades.append(position)
                    position = None

            # ---- daily loss guard ----
            daily_loss = day_start_equity - equity
            daily_limit = day_start_equity * cfg.max_daily_loss_pct
            if daily_loss >= daily_limit:
                equity_curve.append((ts, equity))
                continue

            # ---- signal evaluation (closed candles only) ----
            htf_slice = htf_slice_upto(ts)
            if len(htf_slice) < cfg.min_history + 1:
                continue
            ltf_slice = entry_kl[:i + 1]
            # cooldown
            last = last_signal_ts.get(symbol, 0)
            if ts / 1000 - last < cfg.cooldown_seconds:
                continue
            # max positions
            if position is not None:
                equity_curve.append((ts, equity))
                continue

            sig, diag = eng.evaluate_v2(symbol, htf_slice, ltf_slice if ltf_klines else None,
                                        htf=cfg.htf, ltf=cfg.ltf)
            if sig is None or sig.score < cfg.min_score:
                continue
            # position sizing: risk pct of equity / stop distance
            stop_dist = abs(sig.entry_price - sig.stop_loss)
            if stop_dist <= 0:
                continue
            risk_amt = equity * cfg.risk_per_trade_pct
            qty = risk_amt / stop_dist
            notional = qty * sig.entry_price
            if notional > equity:  # 1x leverage cap
                qty = equity / sig.entry_price
                if qty <= 0:
                    continue
            # entry fills at next candle open + slippage (no intra-candle fill assumption)
            if i + 1 >= total:
                break
            nxt = entry_kl[i + 1]
            fill = Decimal(str(nxt[1]))
            slip = fill * cfg.slippage
            fill = fill + slip if sig.direction == "LONG" else fill - slip
            position = BTTrade(symbol=symbol, direction=sig.direction, strategy=sig.strategy,
                               regime=sig.regime, score=sig.score, entry_time=int(nxt[0]),
                               entry_price=fill, stop_loss=sig.stop_loss,
                               take_profit=sig.take_profit, quantity=qty)
            last_signal_ts[symbol] = ts / 1000
            equity_curve.append((ts, equity))

        # close leftover position at final close
        if position is not None:
            last = entry_kl[-1]
            exit_price = Decimal(str(last[4]))
            gross = ((exit_price - position.entry_price) if position.direction == "LONG"
                     else (position.entry_price - exit_price)) * position.quantity
            fees = fee_estimate(position.quantity, position.entry_price, exit_price,
                                cfg.maker_fee, cfg.taker_fee, Decimal("0"))
            net = gross - fees
            equity += net
            risk_unit = abs(position.entry_price - position.stop_loss) * position.quantity
            position.exit_time = int(last[0])
            position.exit_price = exit_price
            position.pnl = net
            position.fees = fees
            position.r_multiple = (net / risk_unit) if risk_unit > 0 else Decimal(0)
            position.exit_reason = "end_of_data"
            trades.append(position)

        return self._report(symbol, trades, equity, equity_curve)

    def _report(self, symbol: str, trades: list[BTTrade], final_equity: Decimal, curve) -> dict:
        cfg = self.cfg
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gross_profit = sum((t.pnl for t in wins), Decimal(0))
        gross_loss = abs(sum((t.pnl for t in losses), Decimal(0)))
        total = len(trades)
        win_rate = (len(wins) / total * 100) if total else 0.0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (Decimal("999") if gross_profit > 0 else Decimal(0))
        avg_win = (gross_profit / len(wins)) if wins else Decimal(0)
        avg_loss = (gross_loss / len(losses)) if losses else Decimal(0)
        expectancy = (sum((t.pnl for t in trades), Decimal(0)) / total) if total else Decimal(0)
        avg_r = (sum((t.r_multiple for t in trades), Decimal(0)) / total) if total else Decimal(0)

        # max drawdown from equity curve
        peak = cfg.starting_balance
        max_dd = Decimal(0)
        for _, eq in curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        # Sharpe (per-trade, annualized assumption: ~trades/day unknown, report raw)
        import statistics
        rets = [float(t.pnl) / float(cfg.starting_balance) for t in trades]
        sharpe = 0.0
        if len(rets) > 1 and statistics.pstdev(rets) > 0:
            sharpe = statistics.mean(rets) / statistics.pstdev(rets)

        def agg(ts):
            n = len(ts)
            w = [t for t in ts if t.pnl > 0]
            pnl = sum((t.pnl for t in ts), Decimal(0))
            return {"trades": n, "wins": len(w), "pnl": str(pnl), "win_rate": round(len(w) / n * 100, 1) if n else 0.0}

        by_dir_l = [t for t in trades if t.direction == "LONG"]
        by_dir_s = [t for t in trades if t.direction == "SHORT"]
        strat_names = sorted({t.strategy for t in trades})
        regime_names = sorted({t.regime for t in trades})

        return {
            "symbol": symbol,
            "config": {"starting_balance": str(cfg.starting_balance), "min_score": cfg.min_score,
                       "risk_per_trade_pct": str(cfg.risk_per_trade_pct)},
            "total_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "net_pnl": str(sum((t.pnl for t in trades), Decimal(0))),
            "gross_profit": str(gross_profit),
            "gross_loss": str(gross_loss),
            "total_fees": str(sum((t.fees for t in trades), Decimal(0))),
            "profit_factor": str(pf.quantize(Decimal("0.01"))) if pf else "0",
            "avg_win": str(avg_win.quantize(Decimal("0.0001"))),
            "avg_loss": str(avg_loss.quantize(Decimal("0.0001"))),
            "expectancy_per_trade": str(expectancy.quantize(Decimal("0.0001"))),
            "avg_r_multiple": str(avg_r.quantize(Decimal("0.01"))),
            "max_drawdown": str(max_dd.quantize(Decimal("0.01"))),
            "max_drawdown_pct": str(((max_dd / cfg.starting_balance) * 100).quantize(Decimal("0.01"))) if cfg.starting_balance else "0",
            "sharpe_per_trade": round(sharpe, 3),
            "final_equity": str(final_equity.quantize(Decimal("0.01"))),
            "long": agg(by_dir_l),
            "short": agg(by_dir_s),
            "by_strategy": {s: agg([t for t in trades if t.strategy == s]) for s in strat_names},
            "by_regime": {r: agg([t for t in trades if t.regime == r]) for r in regime_names},
            "trades_detail": [
                {"dir": t.direction, "strategy": t.strategy, "regime": t.regime, "score": t.score,
                 "entry": str(t.entry_price), "exit": str(t.exit_price), "pnl": str(t.pnl),
                 "r": str(t.r_multiple), "reason": t.exit_reason} for t in trades
            ],
        }


def walk_forward(symbol: str, htf_klines: list, ltf_klines: list | None, n_splits: int = 3,
                 cfg: BacktestConfig | None = None) -> dict:
    """Chronological walk-forward: split data into n equal slices, test each out-of-sample slice."""
    total = len(htf_klines)
    if total < 200 or n_splits < 2:
        bt = Backtester(cfg)
        return {"splits": [bt.run(symbol, htf_klines, ltf_klines)], "mode": "single"}
    step = total // n_splits
    splits = []
    ltf_total = len(ltf_klines) if ltf_klines else 0
    for s in range(1, n_splits):
        h_end = (s + 1) * step
        h_slice = htf_klines[:h_end]
        l_slice = None
        if ltf_klines and ltf_total:
            cutoff = htf_klines[h_end - 1][0]
            l_slice = [k for k in ltf_klines if k[0] <= cutoff]
        bt = Backtester(cfg)
        rep = bt.run(symbol, h_slice, l_slice)
        rep["split"] = f"0..{h_end}"
        splits.append(rep)
    return {"splits": splits, "mode": "walk_forward"}
