"""Signal Engine V2.

Two independent setups evaluated on closed candles only:
  Strategy A: trend momentum breakout/breakdown
  Strategy B: trend pullback + rejection

Weighted scoring per direction (max 100). Hard filters always reject first,
regardless of score. Every scan produces a SignalDiagnostic explaining the
decision. Legacy evaluate()/evaluate_klines() interfaces are preserved.
"""
import time
from decimal import Decimal
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import indicators as ind
from .regime import RegimeClassifier


# ---------- data structures ----------

@dataclass
class Signal:
    symbol: str
    direction: str
    timestamp: int
    timeframe: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    confidence: float = 0.0
    gross_rr: Decimal = Decimal(0)
    net_rr: Decimal = Decimal(0)
    invalidation: str = ""
    rsi_value: Optional[Decimal] = None
    ema_fast: Optional[Decimal] = None
    ema_slow: Optional[Decimal] = None
    ema_50: Optional[Decimal] = None
    macd: Optional[Decimal] = None
    atr: Optional[Decimal] = None
    volume_ratio: Optional[Decimal] = None
    score: float = 0.0
    explanation: str = ""
    candle_close_time: int = 0
    strategy: str = ""
    regime: str = ""
    adx: Optional[Decimal] = None
    vwap: Optional[Decimal] = None

    @property
    def signal_id(self) -> str:
        return f"{self.symbol}:{self.direction}:{self.strategy}:{self.candle_close_time}"


@dataclass
class DirectionEval:
    direction: str
    score: float = 0.0
    checks: dict = field(default_factory=dict)  # name -> (passed, points, detail)
    decision: str = "REJECTED"
    reason: str = ""
    strategy: str = ""

    def add(self, name: str, passed: bool, points: float, detail: str = ""):
        self.checks[name] = {"passed": bool(passed), "points": points if passed else 0.0, "max": points, "detail": detail}
        if passed:
            self.score += points

    def first_failure(self) -> str:
        for name, c in self.checks.items():
            if not c["passed"]:
                return f"{name}: {c['detail'] or 'FAIL'}"
        return "score below threshold"


@dataclass
class SignalDiagnostic:
    symbol: str
    timestamp: float
    regime: str
    regime_detail: dict
    long_eval: dict
    short_eval: dict
    final_decision: str
    rejection_reason: str = ""
    signal_id: str = ""

    def to_dict(self):
        return asdict(self)


# ---------- indicator helpers (legacy, kept for compatibility) ----------

def ema(values, period):
    return ind.ema(values, period)


def rsi(values, period=14):
    return ind.rsi(values, period)


# ---------- engine ----------

DEFAULT_WEIGHTS = {
    "htf_trend": 20.0,
    "ema_align": 15.0,
    "rsi": 10.0,
    "macd": 10.0,
    "volume": 10.0,
    "vwap": 10.0,
    "setup": 15.0,   # breakout or pullback confirmation
    "adx": 5.0,
    "candle": 5.0,
}


class SignalEngine:
    def __init__(self, cooldown_seconds: int = 3600, cfg=None):
        self.cooldown_seconds = cooldown_seconds
        self._last_signal_ts: dict = {}
        self._seen_ids: set = set()
        self.weights = dict(DEFAULT_WEIGHTS)
        self.cfg = cfg  # optional settings-like object; falls back to defaults
        self.regime_clf = RegimeClassifier()

    # -- config accessors with safe defaults (avoid importing settings at module load for tests)
    def _c(self, name, default):
        if self.cfg is not None and hasattr(self.cfg, name):
            return getattr(self.cfg, name)
        try:
            from .config import settings
            return getattr(settings, name, default)
        except Exception:
            return default

    # ---------- legacy interface (preserved) ----------

    def evaluate(self, symbol: str, timeframe: str, closes: list, candle_close_time: int = 0) -> Optional[Signal]:
        if len(closes) < 60:
            return None
        fast = ind.ema(closes, 9)
        slow = ind.ema(closes, 21)
        r = ind.rsi(closes, 14)
        if r is None:
            return None
        rsi_long_min, rsi_long_max = Decimal("40"), Decimal("70")
        rsi_short_min, rsi_short_max = Decimal("30"), Decimal("60")
        last_fast, prev_fast = fast[-1], fast[-2]
        last_slow, prev_slow = slow[-1], slow[-2]
        direction = None
        if prev_fast <= prev_slow and last_fast > last_slow and rsi_long_min <= r <= rsi_long_max:
            direction = "LONG"
        elif prev_fast >= prev_slow and last_fast < last_slow and rsi_short_min <= r <= rsi_short_max:
            direction = "SHORT"
        if direction is None:
            return None
        now = int(time.time())
        last = self._last_signal_ts.get(symbol, 0)
        if now - last < self.cooldown_seconds:
            return None
        entry = closes[-1]
        recent = closes[-14:]
        hi, lo = max(recent), min(recent)
        atr_approx = (hi - lo) / Decimal(2)
        if atr_approx <= 0:
            atr_approx = entry * Decimal("0.005")
        if direction == "LONG":
            stop = entry - atr_approx * Decimal("1.5")
            tp = entry + atr_approx * Decimal("3.0")
        else:
            stop = entry + atr_approx * Decimal("1.5")
            tp = entry - atr_approx * Decimal("3.0")
        gross_rr = abs(tp - entry) / abs(entry - stop) if abs(entry - stop) > 0 else Decimal(0)
        sig = Signal(symbol=symbol, direction=direction, timestamp=now, timeframe=timeframe,
                     entry_price=entry, stop_loss=stop, take_profit=tp,
                     confidence=float(r) / 100.0, gross_rr=gross_rr, net_rr=gross_rr,
                     invalidation="EMA cross reversal or RSI extreme", rsi_value=r,
                     ema_fast=last_fast, ema_slow=last_slow,
                     candle_close_time=candle_close_time or int(time.time()))
        if sig.signal_id in self._seen_ids:
            return None
        self._seen_ids.add(sig.signal_id)
        self._last_signal_ts[symbol] = now
        return sig

    def evaluate_klines(self, symbol: str, timeframe: str, klines: list, candle_close_time: int = 0) -> Optional[Signal]:
        """Legacy V1 strict-crossover evaluation. Kept for backward compatibility."""
        if not klines or len(klines) < 60:
            return None
        completed = klines[:-1]
        if len(completed) < 50:
            return None
        closes = [Decimal(str(k[4])) for k in completed]
        highs = [Decimal(str(k[2])) for k in completed]
        lows = [Decimal(str(k[3])) for k in completed]
        volumes = [Decimal(str(k[5])) for k in completed]
        fast_ema = ind.ema(closes, 9)
        slow_ema = ind.ema(closes, 21)
        ema50 = ind.ema(closes, 50)
        r = ind.rsi(closes, 14)
        macd_line, macd_sig, macd_hist = ind.macd(closes)
        atr_val = ind.atr(highs, lows, closes, 14)
        vr = ind.volume_ratio(volumes, 20)
        if r is None or atr_val is None or macd_hist is None:
            return None
        last_fast, prev_fast = fast_ema[-1], fast_ema[-2]
        last_slow, prev_slow = slow_ema[-1], slow_ema[-2]
        last_ema50 = ema50[-1]
        now = int(time.time())
        last = self._last_signal_ts.get(symbol, 0)
        if now - last < self.cooldown_seconds:
            return None
        direction, score, reasons = None, 0.0, []
        long_cond = (last_fast > last_slow and last_slow > last_ema50 and prev_fast <= prev_slow
                     and Decimal("40") <= r <= Decimal("70") and macd_hist > 0
                     and vr is not None and vr >= Decimal("1.2"))
        short_cond = (last_fast < last_slow and last_slow < last_ema50 and prev_fast >= prev_slow
                      and Decimal("30") <= r <= Decimal("60") and macd_hist < 0
                      and vr is not None and vr >= Decimal("1.2"))
        if long_cond:
            direction, score = "LONG", 70.0
            reasons = ["EMA9>EMA21>EMA50", "RSI in range", "MACD hist positive", "volume spike"]
        elif short_cond:
            direction, score = "SHORT", 70.0
            reasons = ["EMA9<EMA21<EMA50", "RSI in range", "MACD hist negative", "volume spike"]
        else:
            return None
        entry = closes[-1]
        if direction == "LONG":
            stop = entry - atr_val * Decimal("1.5")
            tp = entry + atr_val * Decimal("3.0")
        else:
            stop = entry + atr_val * Decimal("1.5")
            tp = entry - atr_val * Decimal("3.0")
        gross_rr = abs(tp - entry) / abs(entry - stop) if abs(entry - stop) > 0 else Decimal(0)
        cct = candle_close_time or int(completed[-1][0])
        sig = Signal(symbol=symbol, direction=direction, timestamp=now, timeframe=timeframe,
                     entry_price=entry, stop_loss=stop, take_profit=tp,
                     confidence=float(r) / 100.0, gross_rr=gross_rr, net_rr=gross_rr,
                     invalidation="EMA cross reversal or RSI extreme", rsi_value=r,
                     ema_fast=last_fast, ema_slow=last_slow, ema_50=last_ema50,
                     macd=macd_hist, atr=atr_val, volume_ratio=vr or Decimal(0),
                     score=score, explanation="; ".join(reasons), candle_close_time=cct)
        if sig.signal_id in self._seen_ids:
            return None
        self._seen_ids.add(sig.signal_id)
        self._last_signal_ts[symbol] = now
        return sig

    # ---------- V2 ----------

    def _candle_features(self, o, h, l, c):
        body = c - o
        rng = h - l
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        return {
            "body": body, "range": rng, "upper_wick": upper_wick, "lower_wick": lower_wick,
            "bullish": body > 0, "bearish": body < 0,
        }

    def _bullish_rejection(self, f, atr_val) -> bool:
        if atr_val is None or atr_val <= 0 or f["range"] <= 0:
            return False
        return f["bullish"] or (f["lower_wick"] > abs(f["body"]) and f["lower_wick"] > atr_val * Decimal("0.3"))

    def _bearish_rejection(self, f, atr_val) -> bool:
        if atr_val is None or atr_val <= 0 or f["range"] <= 0:
            return False
        return f["bearish"] or (f["upper_wick"] > abs(f["body"]) and f["upper_wick"] > atr_val * Decimal("0.3"))

    def evaluate_v2(self, symbol: str, htf_klines: list, ltf_klines: Optional[list] = None,
                    htf: str = "15m", ltf: str = "5m") -> tuple[Optional[Signal], SignalDiagnostic]:
        """Multi-timeframe V2 evaluation.

        htf_klines: trend/regime timeframe (15m). ltf_klines: entry timeframe (5m).
        If ltf_klines is None or insufficient, htf is used for entry as fallback.
        Returns (signal_or_None, diagnostic).
        """
        now = time.time()
        entry_tf = ltf if ltf_klines else htf

        def reject_all(regime_r, long_ev, short_ev, reason):
            long_ev.decision, long_ev.reason = "REJECTED", reason
            short_ev.decision, short_ev.reason = "REJECTED", reason
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev),
                                          "NO_TRADE", reason)

        # --- hard filter: data sufficiency ---
        if not htf_klines or len(htf_klines) < 61:
            reg = self.regime_clf.classify([], [], [], [])
            le, se = DirectionEval("LONG"), DirectionEval("SHORT")
            return reject_all(reg, le, se, "insufficient HTF candle history")

        htf_c = htf_klines[:-1]  # completed candles only
        h_closes = [Decimal(str(k[4])) for k in htf_c]
        h_highs = [Decimal(str(k[2])) for k in htf_c]
        h_lows = [Decimal(str(k[3])) for k in htf_c]
        h_vols = [Decimal(str(k[5])) for k in htf_c]

        ltf_src = ltf_klines[:-1] if (ltf_klines and len(ltf_klines) >= 61) else htf_c
        e_closes = [Decimal(str(k[4])) for k in ltf_src]
        e_highs = [Decimal(str(k[2])) for k in ltf_src]
        e_lows = [Decimal(str(k[3])) for k in ltf_src]
        e_vols = [Decimal(str(k[5])) for k in ltf_src]
        e_opens = [Decimal(str(k[1])) for k in ltf_src]

        # --- hard filter: malformed last candle ---
        try:
            if e_highs[-1] < e_lows[-1] or e_closes[-1] <= 0:
                raise ValueError
        except Exception:
            reg = self.regime_clf.classify([], [], [], [])
            le, se = DirectionEval("LONG"), DirectionEval("SHORT")
            return reject_all(reg, le, se, "invalid candle data")

        # --- regime on HTF ---
        regime_r = self.regime_clf.classify(h_highs, h_lows, h_closes, h_vols)
        long_ev, short_ev = DirectionEval("LONG"), DirectionEval("SHORT")

        if regime_r.regime in ("HIGH_VOLATILITY", "LOW_LIQUIDITY"):
            return reject_all(regime_r, long_ev, short_ev, f"regime {regime_r.regime}: {'; '.join(regime_r.reasons)}")

        # --- HTF indicators ---
        h_ema9 = ind.ema(h_closes, 9)
        h_ema21 = ind.ema(h_closes, 21)
        h_ema50 = ind.ema(h_closes, 50)
        h_bull = h_ema9[-1] > h_ema21[-1] > h_ema50[-1] and h_closes[-1] > h_ema50[-1]
        h_bear = h_ema9[-1] < h_ema21[-1] < h_ema50[-1] and h_closes[-1] < h_ema50[-1]

        # --- entry-TF indicators ---
        price = e_closes[-1]
        e_ema9 = ind.ema(e_closes, 9)
        e_ema21 = ind.ema(e_closes, 21)
        e_ema50 = ind.ema(e_closes, 50)
        r = ind.rsi(e_closes, 14)
        _, _, macd_hist = ind.macd(e_closes)
        # previous histogram for improving/weakening detection
        prev_hist = None
        if len(e_closes) >= 36:
            _, _, prev_hist = ind.macd(e_closes[:-1])
        atr_val = ind.atr_wilder(e_highs, e_lows, e_closes, 14)
        vr = ind.volume_ratio(e_vols, 20)
        vwap_val = ind.rolling_vwap(e_highs, e_lows, e_closes, e_vols, 48)
        adx_val = ind.adx(e_highs, e_lows, e_closes, 14)
        feat = self._candle_features(e_opens[-1], e_highs[-1], e_lows[-1], e_closes[-1])

        if r is None or atr_val is None or macd_hist is None:
            return reject_all(regime_r, long_ev, short_ev, "indicator calculation failed (insufficient data)")

        atr_pct = ind.atr_percent(atr_val, price)
        atr_pct_max = Decimal(str(self._c("atr_pct_max", Decimal("5.0"))))
        if atr_pct is not None and atr_pct > atr_pct_max:
            return reject_all(regime_r, long_ev, short_ev, f"abnormal volatility: ATR% {atr_pct:.2f} > {atr_pct_max}")

        vol_min = Decimal(str(self._c("volume_ratio_min", Decimal("1.2"))))
        adx_min = Decimal(str(self._c("adx_trend_min", Decimal("25"))))
        max_ext = Decimal(str(self._c("max_extended_candle_atr", Decimal("2.0"))))
        sl_mult = Decimal(str(self._c("sl_atr_mult", Decimal("1.5"))))
        tp_mult = Decimal(str(self._c("tp_atr_mult", Decimal("3.0"))))
        pb_tol = Decimal(str(self._c("pullback_tolerance_atr", Decimal("0.5"))))
        lookback = int(self._c("breakout_lookback", 20))
        min_score = float(self._c("min_signal_score", 75))
        w = self.weights

        # --- hard filter: excessively extended candle (chasing) ---
        extended_up = feat["range"] > atr_val * max_ext and feat["bullish"]
        extended_down = feat["range"] > atr_val * max_ext and feat["bearish"]

        # --- setup detection ---
        res_levels, sup_levels = ind.swing_levels(e_highs[:-1], e_lows[:-1], 3, 3)
        recent_high = max(e_highs[-lookback - 1:-1]) if len(e_highs) > lookback else max(e_highs[:-1])
        recent_low = min(e_lows[-lookback - 1:-1]) if len(e_lows) > lookback else min(e_lows[:-1])
        breakout_ref = max([recent_high] + res_levels) if res_levels else recent_high
        breakdown_ref = min([recent_low] + sup_levels) if sup_levels else recent_low

        breakout_long = e_closes[-1] > breakout_ref and e_closes[-2] <= breakout_ref
        breakdown_short = e_closes[-1] < breakdown_ref and e_closes[-2] >= breakdown_ref

        tol = atr_val * pb_tol
        near_support_long = min(abs(price - e_ema9[-1]), abs(price - e_ema21[-1]),
                                abs(price - vwap_val)) <= tol if vwap_val else min(abs(price - e_ema9[-1]), abs(price - e_ema21[-1])) <= tol
        near_resist_short = near_support_long  # same distance check; direction handled below
        pullback_long = h_bull and near_support_long and self._bullish_rejection(feat, atr_val) and price > e_ema50[-1]
        pullback_short = h_bear and near_resist_short and self._bearish_rejection(feat, atr_val) and price < e_ema50[-1]

        macd_improving = prev_hist is not None and macd_hist > prev_hist
        macd_weakening = prev_hist is not None and macd_hist < prev_hist

        # ---------- LONG evaluation ----------
        long_ev.add("htf_trend", h_bull, w["htf_trend"],
                    "HTF bull EMA alignment + price>EMA50" if h_bull else "HTF not bullish")
        long_ev.add("ema_align", e_ema9[-1] > e_ema21[-1] > e_ema50[-1], w["ema_align"],
                    "entry EMA9>21>50" if e_ema9[-1] > e_ema21[-1] > e_ema50[-1] else "entry EMAs not aligned")
        long_ev.add("rsi", Decimal("50") <= r <= Decimal("75"), w["rsi"], f"RSI {r:.1f}")
        long_ev.add("macd", macd_hist > 0 or macd_improving, w["macd"], f"hist {macd_hist:.5f}")
        long_ev.add("volume", vr is not None and vr >= vol_min, w["volume"], f"vol ratio {vr if vr else 0:.2f} < {vol_min}" if not (vr and vr >= vol_min) else f"vol ratio {vr:.2f}")
        long_ev.add("vwap", vwap_val is not None and price > vwap_val, w["vwap"], "price above VWAP" if vwap_val and price > vwap_val else "price below VWAP")
        setup_long = "breakout" if breakout_long else ("pullback" if pullback_long else "")
        long_ev.add("setup", breakout_long or pullback_long, w["setup"],
                    f"{setup_long} confirmed" if setup_long else "no breakout or pullback")
        long_ev.add("adx", adx_val is not None and adx_val >= adx_min, w["adx"], f"ADX {adx_val if adx_val else 0:.1f}")
        long_ev.add("candle", self._bullish_rejection(feat, atr_val) and not extended_up, w["candle"],
                    "bull candle, not extended" if self._bullish_rejection(feat, atr_val) and not extended_up else "weak/extended candle")
        long_ev.strategy = setup_long

        # ---------- SHORT evaluation ----------
        short_ev.add("htf_trend", h_bear, w["htf_trend"],
                     "HTF bear EMA alignment + price<EMA50" if h_bear else "HTF not bearish")
        short_ev.add("ema_align", e_ema9[-1] < e_ema21[-1] < e_ema50[-1], w["ema_align"],
                     "entry EMA9<21<50" if e_ema9[-1] < e_ema21[-1] < e_ema50[-1] else "entry EMAs not aligned")
        short_ev.add("rsi", Decimal("25") <= r <= Decimal("50"), w["rsi"], f"RSI {r:.1f}")
        short_ev.add("macd", macd_hist < 0 or macd_weakening, w["macd"], f"hist {macd_hist:.5f}")
        short_ev.add("volume", vr is not None and vr >= vol_min, w["volume"], f"vol ratio {vr if vr else 0:.2f} < {vol_min}" if not (vr and vr >= vol_min) else f"vol ratio {vr:.2f}")
        short_ev.add("vwap", vwap_val is not None and price < vwap_val, w["vwap"], "price below VWAP" if vwap_val and price < vwap_val else "price above VWAP")
        setup_short = "breakdown" if breakdown_short else ("pullback" if pullback_short else "")
        short_ev.add("setup", breakdown_short or pullback_short, w["setup"],
                     f"{setup_short} confirmed" if setup_short else "no breakdown or pullback")
        short_ev.add("adx", adx_val is not None and adx_val >= adx_min, w["adx"], f"ADX {adx_val if adx_val else 0:.1f}")
        short_ev.add("candle", self._bearish_rejection(feat, atr_val) and not extended_down, w["candle"],
                     "bear candle, not extended" if self._bearish_rejection(feat, atr_val) and not extended_down else "weak/extended candle")
        short_ev.strategy = setup_short

        # ---------- promote scored directions to candidates ----------
        for ev in (long_ev, short_ev):
            if ev.score >= min_score:
                ev.decision = "CANDIDATE"

        # ---------- regime gating (hard) ----------
        if regime_r.regime in ("STRONG_DOWNTREND", "WEAK_DOWNTREND") and long_ev.decision != "REJECTED":
            long_ev.decision, long_ev.reason = "REJECTED", f"LONG against {regime_r.regime}"
        if regime_r.regime in ("STRONG_UPTREND", "WEAK_UPTREND") and short_ev.decision != "REJECTED":
            short_ev.decision, short_ev.reason = "REJECTED", f"SHORT against {regime_r.regime}"
        if regime_r.regime == "SIDEWAYS":
            if long_ev.decision != "REJECTED" and long_ev.score >= min_score:
                long_ev.decision, long_ev.reason = "REJECTED", "sideways regime: no trend entries"
            if short_ev.decision != "REJECTED" and short_ev.score >= min_score:
                short_ev.decision, short_ev.reason = "REJECTED", "sideways regime: no trend entries"

        # ---------- pick best qualified ----------
        cands = []
        for ev in (long_ev, short_ev):
            if ev.decision == "REJECTED":
                continue
            if ev.score >= min_score:
                cands.append(ev)
            else:
                ev.decision = "REJECTED"
                ev.reason = f"score {ev.score:.0f} < {min_score:.0f} ({ev.first_failure()})"
        cands.sort(key=lambda e: e.score, reverse=True)

        if not cands:
            reason = f"LONG {long_ev.score:.0f} ({long_ev.reason or long_ev.first_failure()}); SHORT {short_ev.score:.0f} ({short_ev.reason or short_ev.first_failure()})"
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev), "NO_TRADE", reason)

        best = cands[0]
        # --- cooldown / dedup (hard) ---
        now_i = int(now)
        last = self._last_signal_ts.get(symbol, 0)
        if now_i - last < self.cooldown_seconds:
            best.decision, best.reason = "REJECTED", "cooldown active"
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev), "NO_TRADE", "cooldown active")

        # --- build signal with ATR stops ---
        direction = best.direction
        entry = price
        if direction == "LONG":
            stop = entry - atr_val * sl_mult
            tp = entry + atr_val * tp_mult
        else:
            stop = entry + atr_val * sl_mult
            tp = entry - atr_val * tp_mult
        if stop <= 0 or abs(entry - stop) == 0:
            best.decision, best.reason = "REJECTED", "invalid stop-loss"
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev), "NO_TRADE", "invalid stop-loss")
        gross_rr = abs(tp - entry) / abs(entry - stop)
        min_rr = Decimal(str(self._c("min_reward_to_risk", Decimal("2.0"))))
        if gross_rr < min_rr:
            best.decision, best.reason = "REJECTED", f"R:R {gross_rr:.2f} < {min_rr}"
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev), "NO_TRADE", f"R:R {gross_rr:.2f} below minimum")

        cct = int(ltf_src[-1][0]) + self._interval_ms(entry_tf)
        sig = Signal(symbol=symbol, direction=direction, timestamp=now_i, timeframe=entry_tf,
                     entry_price=entry, stop_loss=stop, take_profit=tp,
                     confidence=best.score / 100.0, gross_rr=gross_rr, net_rr=gross_rr,
                     invalidation="HTF trend reversal or structure break", rsi_value=r,
                     ema_fast=e_ema9[-1], ema_slow=e_ema21[-1], ema_50=e_ema50[-1],
                     macd=macd_hist, atr=atr_val, volume_ratio=vr or Decimal(0),
                     score=best.score, explanation=self._explain(best), candle_close_time=cct,
                     strategy=best.strategy or "trend", regime=regime_r.regime,
                     adx=adx_val, vwap=vwap_val)
        if sig.signal_id in self._seen_ids:
            best.decision, best.reason = "REJECTED", "duplicate signal"
            return None, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                          self._ev_dict(long_ev), self._ev_dict(short_ev), "NO_TRADE", "duplicate signal", sig.signal_id)
        self._seen_ids.add(sig.signal_id)
        self._last_signal_ts[symbol] = now_i
        best.decision, best.reason = "ACCEPTED", ""
        loser = short_ev if direction == "LONG" else long_ev
        if loser.decision != "REJECTED":
            loser.decision, loser.reason = "REJECTED", f"score {loser.score:.0f} below threshold or opposite side taken"
        return sig, SignalDiagnostic(symbol, now, regime_r.regime, regime_r.to_dict(),
                                     self._ev_dict(long_ev), self._ev_dict(short_ev), "SIGNAL", "", sig.signal_id)

    def _interval_ms(self, tf: str) -> int:
        return {"1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000,
                "30m": 1800000, "1h": 3600000, "4h": 14400000}.get(tf, 900000)

    def _ev_dict(self, ev: DirectionEval) -> dict:
        return {"direction": ev.direction, "score": round(ev.score, 1),
                "checks": ev.checks, "decision": ev.decision, "reason": ev.reason,
                "strategy": ev.strategy}

    def _explain(self, ev: DirectionEval) -> str:
        passed = [f"{n}({c['detail']})" for n, c in ev.checks.items() if c["passed"]]
        return "; ".join(passed)
